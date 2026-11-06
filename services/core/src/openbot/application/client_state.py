"""Versioned client settings and factual run traces on the existing durable writer."""

import hashlib
import re
import secrets
import sqlite3
import time
from collections.abc import Callable
from typing import Any

from openbot.application.operations import task_record
from openbot.contracts import ContractError, canonicalize, strict_json
from openbot.observability.redaction import RedactionPipeline
from openbot.storage.inbox import InboundContext, authorize
from openbot.storage.writer import LookupResult, RequestConflict, Writer, WriterCommand

_KINDS = frozenset(
    {
        "RUN_STARTED",
        "SKILL_LOADED",
        "MODEL_REQUESTED",
        "MODEL_RETURNED",
        "TOOL_PROPOSED",
        "WAITING_APPROVAL",
        "TOOL_DISPATCHED",
        "TOOL_RETURNED",
        "OUTCOME_VERIFIED",
        "RUN_FINISHED",
        "RUN_INTERRUPTED",
    }
)
_DATA_KEYS = frozenset(
    {
        "skill_id",
        "sha256",
        "version",
        "source",
        "model",
        "server_id",
        "tool",
        "call_id",
        "operation_id",
        "attempt_id",
        "approval_id",
        "status",
        "error_code",
        "artifact_id",
        "input_tokens",
        "output_tokens",
        "text",
        "arguments_summary",
        "elapsed_ms",
        "summary_key",
        "effect",
        "usage_estimated",
    }
)
_TERMINAL = frozenset({"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"})
_RUN_OUTCOMES = _TERMINAL | frozenset({"INTERRUPTED"})


class ClientState:
    def __init__(self, writer: Writer, context: InboundContext, redactor: RedactionPipeline):
        self.writer, self.context, self.redactor = writer, context, redactor

    def _settings(self, db: sqlite3.Connection) -> dict[str, Any]:
        mode = authorize(db, self.context)
        row = db.execute(
            "SELECT payload_json FROM events WHERE aggregate_kind='ClientSettings' "
            "AND aggregate_id=? ORDER BY seq DESC LIMIT 1",
            (self.context.profile_id,),
        ).fetchone()
        if row:
            return dict(strict_json(row[0])["receipt"])
        return {
            "revision": 0,
            "config": {
                "locale": "zh-CN",
                "model": "gpt-5.5",
                "mode": mode,
                "max_steps": 4,
                "skill_enabled": True,
                "mcp_enabled": False,
                "feishu_enabled": False,
            },
        }

    def settings(self) -> dict[str, Any]:
        return self.writer.read(self._settings)

    def _validate_config(self, config: Any) -> dict[str, Any]:
        expected = {
            "locale",
            "model",
            "mode",
            "max_steps",
            "skill_enabled",
            "mcp_enabled",
            "feishu_enabled",
        }
        if not isinstance(config, dict) or set(config) != expected:
            raise ContractError("CLIENT_CONFIG_FIELDS_INVALID")
        if (
            type(config["locale"]) is not str
            or type(config["mode"]) is not str
            or config["locale"] not in {"zh-CN", "en"}
            or config["mode"] not in {"CONNECTED", "LOCAL_MODEL", "OFFLINE"}
            or type(config["model"]) is not str
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,95}", config["model"])
            or config["model"].startswith("sk-")
            or "://" in config["model"]
            or type(config["max_steps"]) is not int
            or not 1 <= config["max_steps"] <= 8
            or any(
                type(config[k]) is not bool
                for k in ("skill_enabled", "mcp_enabled", "feishu_enabled")
            )
            or (config["mode"] == "OFFLINE" and config["feishu_enabled"])
        ):
            raise ContractError("CLIENT_CONFIG_INVALID")
        raw = canonicalize(config).decode()
        if (
            self.redactor.sanitize_sink(
                sink="ui_event", text=raw, data_class="WORKSPACE"
            ).sanitized_text
            != raw
        ):
            raise ContractError("CLIENT_CONFIG_SECRET_FORBIDDEN")
        return dict(config)

    def preview(self, raw: str | bytes) -> dict[str, Any]:
        doc = strict_json(raw)
        if not isinstance(doc, dict) or set(doc) != {"expected_revision", "config"}:
            raise ContractError("CLIENT_PREVIEW_FIELDS_INVALID")
        if type(doc["expected_revision"]) is not int or doc["expected_revision"] < 0:
            raise ContractError("CLIENT_REVISION_INVALID")
        candidate = self._validate_config(doc["config"])
        current = self.settings()
        if current["revision"] != doc["expected_revision"]:
            raise RequestConflict("CLIENT_REVISION_CONFLICT")
        binding = {"profile_id": self.context.profile_id, **doc}
        changed = [k for k in sorted(candidate) if candidate[k] != current["config"][k]]
        return {
            **doc,
            "preview_hash": hashlib.sha256(canonicalize(binding)).hexdigest(),
            "changes": changed,
            "activation": "APPLIED" if set(changed) <= {"locale"} else "NEXT_RUN",
        }

    def _write(
        self, request_id: str, payload: Any, apply: Callable[[sqlite3.Connection, str], bytes]
    ) -> dict[str, Any]:
        fingerprint = hashlib.sha256(
            canonicalize([self.context.profile_id, self.context.principal_id, payload])
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            authorize(db, self.context)
            row = db.execute(
                "SELECT payload_json FROM events WHERE actor_principal_id=? "
                "AND json_extract(payload_json,'$.request_id')=?",
                (self.context.principal_id, request_id),
            ).fetchone()
            if row is None:
                return None
            doc = strict_json(row[0])
            return LookupResult(doc["command_hash"], canonicalize(doc["receipt"]))

        def execute(db: sqlite3.Connection) -> bytes:
            authorize(db, self.context)
            return apply(db, fingerprint)

        command = WriterCommand(
            request_id, fingerprint, "normal", int(time.monotonic() * 1000) + 5000, execute, lookup
        )
        return dict(strict_json(self.writer.submit(command).result(timeout=5)))

    def _event(
        self,
        db: sqlite3.Connection,
        *,
        aggregate: str,
        aggregate_id: str,
        revision: int,
        kind: str,
        task_id: str | None,
        receipt: dict[str, Any],
        request_id: str,
        fingerprint: str,
        event_id: str,
    ) -> int:
        now = time.time_ns() // 1_000_000
        cur = db.execute(
            "INSERT INTO events(event_id,aggregate_kind,aggregate_id,aggregate_version,task_id,"
            "actor_principal_id,event_type,schema_version,trace_id,payload_json,created_at) "
            "VALUES(?,?,?,?,?,?,?,1,?,?,?)",
            (
                event_id,
                aggregate,
                aggregate_id,
                revision,
                task_id,
                self.context.principal_id,
                kind,
                "trc_" + hashlib.sha256(request_id.encode()).hexdigest()[:32],
                canonicalize(
                    {"request_id": request_id, "command_hash": fingerprint, "receipt": receipt}
                ).decode(),
                now,
            ),
        )
        seq = int(cur.lastrowid or 0)
        db.execute(
            "INSERT INTO outbox(outbox_id,task_id,target_key,target_json,semantic_key,revision,"
            "payload_json,delivery_class,not_before,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,'UPSERT_REVISION',?,?,?)",
            (
                "out_" + secrets.token_hex(16),
                task_id,
                "local:" + self.context.principal_id,
                canonicalize({"principal_id": self.context.principal_id}).decode(),
                "client:" + aggregate_id,
                seq,
                canonicalize({"event_id": event_id, "seq": seq}).decode(),
                now,
                now,
                now,
            ),
        )
        return seq

    def apply(self, raw: str | bytes, request_id: str) -> dict[str, Any]:
        doc = strict_json(raw)
        fields = {"expected_revision", "config", "preview_hash", "changes", "activation", "confirm"}
        if not isinstance(doc, dict) or set(doc) != fields or doc["confirm"] is not True:
            raise ContractError("CLIENT_APPLY_CONFIRM_REQUIRED")
        candidate = self._validate_config(doc["config"])
        req = "client-config:" + request_id

        def apply(db: sqlite3.Connection, fingerprint: str) -> bytes:
            current = self._settings(db)
            binding = {
                "profile_id": self.context.profile_id,
                "expected_revision": doc["expected_revision"],
                "config": candidate,
            }
            if (
                current["revision"] != doc["expected_revision"]
                or doc["preview_hash"] != hashlib.sha256(canonicalize(binding)).hexdigest()
            ):
                raise RequestConflict("CLIENT_PREVIEW_STALE_OR_CHANGED")
            revision = current["revision"] + 1
            if any(
                candidate[k] != current["config"][k]
                for k in ("mode", "mcp_enabled", "skill_enabled", "feishu_enabled")
            ):
                rules = strict_json(
                    db.execute(
                        "SELECT rules_json FROM policy_revisions "
                        "WHERE version=(SELECT policy_version FROM profile_config)"
                    ).fetchone()[0]
                )
                rules["client_control_revision"] = revision
                policy_version = int(
                    db.execute("SELECT max(version)+1 FROM policy_revisions").fetchone()[0]
                )
                now = time.time_ns() // 1_000_000
                db.execute(
                    "INSERT INTO policy_revisions VALUES(?,?,?,?,?)",
                    (
                        policy_version,
                        hashlib.sha256(canonicalize(rules)).hexdigest(),
                        canonicalize(rules).decode(),
                        now,
                        now,
                    ),
                )
                db.execute(
                    "UPDATE profile_config SET privacy_mode=?,policy_version=?,"
                    "version=version+1,updated_at=? WHERE singleton=1",
                    (candidate["mode"], policy_version, now),
                )
            receipt = {"revision": revision, "config": candidate}
            self._event(
                db,
                aggregate="ClientSettings",
                aggregate_id=self.context.profile_id,
                revision=revision,
                kind="CLIENT_CONFIG_APPLIED",
                task_id=None,
                receipt=receipt,
                request_id=req,
                fingerprint=fingerprint,
                event_id="evt_" + secrets.token_hex(16),
            )
            return canonicalize(receipt)

        return self._write(req, doc, apply)

    def _run(self, db: sqlite3.Connection, task_id: str) -> dict[str, Any]:
        task_record(db, self.context, task_id)
        checkpoint = strict_json(
            db.execute("SELECT checkpoint_json FROM tasks WHERE task_id=?", (task_id,)).fetchone()[
                0
            ]
        )
        return dict(checkpoint.get("agent_run", {}))

    def run(self, task_id: str) -> dict[str, Any]:
        return self.writer.read(lambda db: self._run(db, task_id))

    def start_run(self, task_id: str, request_id: str | None = None) -> dict[str, Any]:
        # Each accepted start is a distinct run; a fixed key would replay the previous receipt
        # and leave the resumed task without a live marker.
        req = request_id or "client-start:" + task_id

        def apply(db: sqlite3.Connection, fingerprint: str) -> bytes:
            state, version, _ = task_record(db, self.context, task_id)
            if state in _TERMINAL:
                raise PermissionError("TERMINAL_TASK_CANNOT_RESTART")
            active = db.execute(
                "SELECT task_id FROM tasks WHERE state NOT IN "
                "('SUCCEEDED','FAILED','CANCELLED','PARTIAL') AND "
                "json_extract(checkpoint_json,'$.agent_run.run_id') IS NOT NULL "
                "AND task_id<>? LIMIT 1",
                (task_id,),
            ).fetchone()
            if active:
                raise RequestConflict("ONE_ACTIVE_RUN_REQUIRED")
            old = self._run(db, task_id)
            if old:
                return canonicalize(old)
            settings = self._settings(db)
            inbound = db.execute(
                "SELECT source_scope FROM inbox WHERE task_id=?", (task_id,)
            ).fetchone()
            source = (
                "FEISHU"
                if inbound and strict_json(inbound[0]).get("channel") == "feishu"
                else "LOCAL"
            )
            run = {
                "run_id": "run_" + secrets.token_hex(16),
                "config_revision": settings["revision"],
                "config": settings["config"],
                "source": source,
                "started_at_ms": time.time_ns() // 1_000_000,
            }
            checkpoint = strict_json(
                db.execute(
                    "SELECT checkpoint_json FROM tasks WHERE task_id=?", (task_id,)
                ).fetchone()[0]
            )
            checkpoint["agent_run"] = run
            db.execute(
                "UPDATE tasks SET checkpoint_json=?,version=version+1 "
                "WHERE task_id=? AND version=?",
                (canonicalize(checkpoint).decode(), task_id, version),
            )
            self._event(
                db,
                aggregate="AgentRun",
                aggregate_id=run["run_id"],
                revision=0,
                kind="RUN_STARTED",
                task_id=task_id,
                receipt=run,
                request_id=req,
                fingerprint=fingerprint,
                event_id="evt_" + secrets.token_hex(16),
            )
            return canonicalize(run)

        return self._write(req, {"task_id": task_id}, apply)

    def finish_run(self, task_id: str, status: str) -> dict[str, Any]:
        """Retire the live marker so a finished run cannot hold the single active-run slot."""
        if status not in _RUN_OUTCOMES:
            raise ValueError("RUN_FINISH_STATUS_INVALID")
        req = "client-finish:" + task_id + ":" + status

        def apply(db: sqlite3.Connection, fingerprint: str) -> bytes:
            state, version, _ = task_record(db, self.context, task_id)
            run = self._run(db, task_id)
            if not run:
                return canonicalize({"task_id": task_id, "retired": False, "state": state})
            retired = {**run, "status": status, "finished_at_ms": time.time_ns() // 1_000_000}
            checkpoint = strict_json(
                db.execute(
                    "SELECT checkpoint_json FROM tasks WHERE task_id=?", (task_id,)
                ).fetchone()[0]
            )
            checkpoint.pop("agent_run")
            checkpoint["last_agent_run"] = retired
            db.execute(
                "UPDATE tasks SET checkpoint_json=?,version=version+1 "
                "WHERE task_id=? AND version=?",
                (canonicalize(checkpoint).decode(), task_id, version),
            )
            closed = {
                "schema_version": "1",
                "event_id": "evt_" + secrets.token_hex(16),
                "task_id": task_id,
                "run_id": run["run_id"],
                "parent_event_id": None,
                "kind": "RUN_CLOSED",
                "occurred_at_ms": retired["finished_at_ms"],
                "config_revision": run["config_revision"],
                "data": {"status": status},
            }
            self._event(
                db,
                aggregate="AgentRun",
                aggregate_id=run["run_id"],
                revision=1,
                kind="RUN_CLOSED",
                task_id=task_id,
                receipt=closed,
                request_id=req,
                fingerprint=fingerprint,
                event_id=closed["event_id"],
            )
            return canonicalize({"task_id": task_id, "retired": True, **retired})

        return self._write(req, {"task_id": task_id, "status": status}, apply)

    def record(
        self, task_id: str, kind: str, data: dict[str, Any], *, parent_event_id: str | None = None
    ) -> dict[str, Any]:
        if kind not in _KINDS or set(data) - _DATA_KEYS:
            raise ContractError("TRACE_FIELDS_INVALID")
        safe: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                safe[key] = self.redactor.sanitize_sink(
                    sink="ui_event", text=value, data_class="WORKSPACE"
                ).sanitized_text[:4096]
            elif type(value) in {bool, int} or value is None:
                safe[key] = value
            else:
                raise ContractError("TRACE_DATA_TYPE_INVALID")
        req, event_id = "trace:" + secrets.token_hex(16), "evt_" + secrets.token_hex(16)

        def apply(db: sqlite3.Connection, fingerprint: str) -> bytes:
            run = self._run(db, task_id)
            if not run:
                raise PermissionError("RUN_NOT_STARTED")
            if (
                parent_event_id
                and not db.execute(
                    "SELECT 1 FROM events WHERE event_id=? AND task_id=? AND aggregate_id=?",
                    (parent_event_id, task_id, run["run_id"]),
                ).fetchone()
            ):
                raise ContractError("TRACE_PARENT_NOT_IN_RUN")
            event = {
                "schema_version": "1",
                "event_id": event_id,
                "task_id": task_id,
                "run_id": run["run_id"],
                "parent_event_id": parent_event_id,
                "kind": kind,
                "occurred_at_ms": time.time_ns() // 1_000_000,
                "config_revision": run["config_revision"],
                "data": safe,
            }
            seq = self._event(
                db,
                aggregate="AgentRun",
                aggregate_id=run["run_id"],
                revision=0,
                kind=kind,
                task_id=task_id,
                receipt=event,
                request_id=req,
                fingerprint=fingerprint,
                event_id=event_id,
            )
            return canonicalize(event | {"global_seq": seq})

        return self._write(req, [task_id, kind, safe, parent_event_id], apply)

    def trace(self, task_id: str, after_seq: int = 0) -> dict[str, Any]:
        if type(after_seq) is not int or after_seq < 0:
            raise ContractError("TRACE_CURSOR_INVALID")

        def query(db: sqlite3.Connection) -> dict[str, Any]:
            run = self._run(db, task_id)
            rows = db.execute(
                "SELECT seq,event_id,event_type,created_at,payload_json FROM events "
                "WHERE task_id=? AND aggregate_kind='AgentRun' AND seq>? "
                "ORDER BY seq LIMIT 128",
                (task_id, after_seq),
            ).fetchall()
            events = []
            for seq, event_id, kind, created_at, raw in rows:
                receipt = strict_json(raw)["receipt"]
                if kind == "RUN_STARTED":
                    event = {
                        "schema_version": "1",
                        "event_id": event_id,
                        "task_id": task_id,
                        "run_id": receipt["run_id"],
                        "parent_event_id": None,
                        "kind": kind,
                        "occurred_at_ms": created_at,
                        "config_revision": receipt["config_revision"],
                        "data": {"status": "STARTED", "source": receipt.get("source", "LOCAL")},
                    }
                else:
                    event = receipt
                events.append(event | {"global_seq": seq})
            return {
                "task_id": task_id,
                "run_id": run.get("run_id"),
                "events": events,
                "last_seq": events[-1]["global_seq"] if events else after_seq,
            }

        return self.writer.read(query)
