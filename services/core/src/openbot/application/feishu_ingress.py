"""Daemon-owned Feishu pairing and durable Inbox ingress; no SDK or tool execution here."""

import re
import secrets
import sqlite3
import threading
import time
from dataclasses import replace
from typing import Any

from openbot.application.agent_runtime import AgentRuntime
from openbot.application.client_state import ClientState
from openbot.contracts import canonicalize, strict_json
from openbot.storage.inbox import Inbox
from openbot.storage.writer import RequestConflict


class FeishuIngress:
    def __init__(self, state: ClientState, inbox: Inbox, runtime: AgentRuntime):
        self.state, self.inbox, self.runtime = state, inbox, runtime
        self._pending: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._health: dict[str, Any] = {"stage": "NOT_CONNECTED", "at": 0.0}

    def _setup(self, db: sqlite3.Connection) -> dict[str, Any]:
        row = db.execute(
            "SELECT payload_json FROM events WHERE aggregate_kind='FeishuSetup' "
            "AND aggregate_id=? ORDER BY seq DESC LIMIT 1",
            (self.state.context.profile_id,),
        ).fetchone()
        return dict(strict_json(row[0])["receipt"]) if row else {"app_id": ""}

    def configure(self, app_id: str, request_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"cli_[A-Za-z0-9_-]{1,96}", app_id):
            raise ValueError("FEISHU_APP_ID_INVALID")

        def apply(db: sqlite3.Connection, fingerprint: str) -> bytes:
            receipt = {"app_id": app_id}
            self._event(
                db,
                "FeishuSetup",
                self.state.context.profile_id,
                "FEISHU_CONFIGURED",
                receipt,
                request_id,
                fingerprint,
            )
            return canonicalize(receipt)

        return self.state._write(request_id, ["feishu-configure", app_id], apply)

    def _event(
        self,
        db: sqlite3.Connection,
        aggregate: str,
        aggregate_id: str,
        kind: str,
        receipt: dict[str, Any],
        request_id: str,
        fingerprint: str,
    ) -> None:
        self.state._event(
            db,
            aggregate=aggregate,
            aggregate_id=aggregate_id,
            revision=1,
            kind=kind,
            task_id=None,
            receipt=receipt,
            request_id=request_id,
            fingerprint=fingerprint,
            event_id="evt_" + secrets.token_hex(16),
        )

    def config(self) -> dict[str, Any]:
        def query(db: sqlite3.Connection) -> dict[str, Any]:
            config = self.state._settings(db)["config"]
            setup = self._setup(db)
            return {
                **setup,
                "connect_allowed": bool(
                    setup["app_id"] and config["mode"] == "CONNECTED" and config["feishu_enabled"]
                ),
            }

        return self.state.writer.read(query)

    def heartbeat(self, raw: str | bytes) -> dict[str, Any]:
        doc = strict_json(raw)
        allowed_keys = {"stage", "task_ids"}
        if (
            not isinstance(doc, dict)
            or not ({"stage"} <= set(doc) <= allowed_keys)
            or doc["stage"] not in {"CONNECTING", "CONNECTED", "STOPPED", "FAILED"}
        ):
            raise ValueError("FEISHU_HEALTH_INVALID")
        task_ids = doc.get("task_ids")
        if task_ids is not None:
            if (
                type(task_ids) is not list
                or len(task_ids) > 64
                or any(
                    type(t) is not str or not re.fullmatch(r"tsk_[A-Za-z0-9_-]{1,80}", t)
                    for t in task_ids
                )
            ):
                raise ValueError("FEISHU_HEALTH_INVALID")
        with self._lock:
            self._health = {"stage": doc["stage"], "at": time.monotonic()}
        finished: dict[str, str] = {}
        if task_ids:

            def query(db: sqlite3.Connection) -> dict[str, str]:
                res = {}
                for t in task_ids:
                    row = db.execute("SELECT state FROM tasks WHERE task_id=?", (t,)).fetchone()
                    if row and row[0] in {
                        "SUCCEEDED",
                        "FAILED",
                        "CANCELLED",
                        "PARTIAL",
                        "PAUSED",
                    }:
                        res[t] = str(row[0])
                return res

            finished = self.state.writer.read(query)
        return {"status": "RECORDED", "finished": finished}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._prune()
            health = (
                self._health["stage"]
                if time.monotonic() - self._health["at"] < 10
                else "NOT_CONNECTED"
            )
            return {
                **self.config(),
                "stage": health,
                "candidates": [
                    {k: v for k, v in c.items() if k != "expires_at"}
                    for c in self._pending.values()
                ],
            }

    def _prune(self) -> None:
        now = time.monotonic()
        self._pending = {
            key: value for key, value in self._pending.items() if value["expires_at"] > now
        }

    def confirm(self, candidate_id: str, request_id: str) -> dict[str, Any]:
        with self._lock:

            def apply(db: sqlite3.Connection, fingerprint: str) -> bytes:
                candidate = self._pending.get(candidate_id)
                if not candidate or candidate["expires_at"] <= time.monotonic():
                    raise PermissionError("FEISHU_CANDIDATE_EXPIRED")
                if self._setup(db)["app_id"] != candidate["app_id"]:
                    raise PermissionError("FEISHU_APP_CHANGED")
                row = db.execute(
                    "SELECT account_id FROM channel_accounts WHERE "
                    "channel='feishu' AND tenant_id=? AND app_id=? AND status='ACTIVE'",
                    (candidate["tenant_key"], candidate["app_id"]),
                ).fetchone()
                now = time.time_ns() // 1_000_000
                account = str(row[0]) if row else "cac_" + secrets.token_hex(10)
                if not row:
                    db.execute(
                        "INSERT INTO channel_accounts(account_id,channel,tenant_id,"
                        "app_id,secret_ref,status,created_at) "
                        "VALUES(?,'feishu',?,?,'memory:feishu', 'ACTIVE',?)",
                        (account, candidate["tenant_key"], candidate["app_id"], now),
                    )
                row = db.execute(
                    "SELECT identity_id,principal_id,status FROM channel_identities "
                    "WHERE account_id=? AND external_user_id=?",
                    (account, candidate["open_id"]),
                ).fetchone()
                if row and row[1:] != (self.state.context.principal_id, "ACTIVE"):
                    raise PermissionError("FEISHU_IDENTITY_CONFLICT")
                identity = str(row[0]) if row else "cid_" + secrets.token_hex(10)
                if not row:
                    db.execute(
                        "INSERT INTO channel_identities(identity_id,account_id,"
                        "external_user_id,principal_id,status,linked_at) "
                        "VALUES(?,?,?,?,'ACTIVE',?)",
                        (
                            identity,
                            account,
                            candidate["open_id"],
                            self.state.context.principal_id,
                            now,
                        ),
                    )
                receipt = {
                    k: candidate[k]
                    for k in ("candidate_id", "tenant_key", "app_id", "open_id", "chat_id")
                }
                receipt.update(
                    identity_id=identity,
                    principal_id=self.state.context.principal_id,
                    status="ACTIVE_OWNER",
                )
                self._event(
                    db,
                    "FeishuPair",
                    "feishu-pair:" + candidate_id,
                    "FEISHU_PAIRED",
                    receipt,
                    request_id,
                    fingerprint,
                )
                return canonicalize(receipt)

            receipt = self.state._write(request_id, ["feishu-confirm", candidate_id], apply)
            self._pending.pop(candidate_id, None)
            return receipt

    def _admit(self, db: sqlite3.Connection, doc: dict[str, Any], *, paired: bool = True) -> None:
        config = self.state._settings(db)["config"]
        if config["mode"] != "CONNECTED" or not config["feishu_enabled"]:
            raise PermissionError("FEISHU_DISABLED_OR_OFFLINE")
        if self._setup(db)["app_id"] != doc["app_id"]:
            raise PermissionError("FEISHU_APP_MISMATCH")
        if paired and not self._paired(db, doc):
            raise PermissionError("FEISHU_UNPAIRED")

    def _paired(self, db: sqlite3.Connection, doc: dict[str, Any]) -> bool:
        row = db.execute(
            "SELECT 1 FROM channel_identities i JOIN channel_accounts a "
            "ON a.account_id=i.account_id "
            "JOIN events e ON json_extract(e.payload_json,'$.receipt.identity_id')=i.identity_id "
            "WHERE i.status='ACTIVE' AND a.status='ACTIVE' AND a.channel='feishu' "
            "AND i.principal_id=? AND a.tenant_id=? AND a.app_id=? AND i.external_user_id=? "
            "AND e.event_type='FEISHU_PAIRED' AND e.actor_principal_id=? "
            "AND json_extract(e.payload_json,'$.receipt.chat_id')=? LIMIT 1",
            (
                self.state.context.principal_id,
                doc["tenant_key"],
                doc["app_id"],
                doc["open_id"],
                self.state.context.principal_id,
                doc["chat_id"],
            ),
        ).fetchone()
        return row is not None

    def receive(self, raw: str | bytes) -> dict[str, Any]:
        doc = strict_json(raw)
        fields = {"event_id", "tenant_key", "app_id", "open_id", "chat_id", "text"}
        if (
            not isinstance(doc, dict)
            or set(doc) != fields
            or any(
                type(doc[k]) is not str
                or not doc[k].strip()
                or len(doc[k]) > (4096 if k == "text" else 200)
                for k in fields
            )
            or any(not re.fullmatch(r"[A-Za-z0-9_-]+", doc[k]) for k in fields - {"text"})
        ):
            raise ValueError("FEISHU_EVENT_INVALID")
        with self._lock:
            self.state.writer.read(lambda db: self._admit(db, doc, paired=False))
            paired = self.state.writer.read(lambda db: self._paired(db, doc))
            if not paired:
                self._prune()
                scope = {k: doc[k] for k in ("tenant_key", "app_id", "open_id", "chat_id")}
                for candidate in self._pending.values():
                    if all(candidate[k] == v for k, v in scope.items()):
                        return {
                            "status": "PENDING_LOCAL_CONFIRMATION",
                            "candidate_id": candidate["candidate_id"],
                        }
                if len(self._pending) >= 16:
                    return {"status": "PENDING_LIMIT_REACHED"}
                candidate_id = "pcn_" + secrets.token_hex(12)
                self._pending[candidate_id] = {
                    **scope,
                    "candidate_id": candidate_id,
                    "expires_at": time.monotonic() + 300,
                    "status": "PENDING_LOCAL_CONFIRMATION",
                }
                return {"status": "PENDING_LOCAL_CONFIRMATION", "candidate_id": candidate_id}
            context = replace(
                self.state.context,
                channel="feishu",
                tenant_id=doc["tenant_key"],
                app_id=doc["app_id"],
            )
            goal = self.state.redactor.sanitize_sink(
                sink="model_input", text=doc["text"], data_class="WORKSPACE"
            ).sanitized_text
            body = canonicalize(
                {"workspace_id": context.workspace_id, "goal": goal, "network_mode": "CONNECTED"}
            )
            receipt = dict(
                strict_json(
                    self.inbox.submit(
                        context,
                        doc["event_id"],
                        body,
                        int(time.monotonic() * 1000) + 5000,
                        admission=lambda db: self._admit(db, doc),
                    ).result(timeout=5)
                )
            )
            # Delivery/replay does not restart existing runs. Busy Tasks remain visibly queued.
            if not self.state.run(receipt["task_id"]) and self.runtime.model_factory is not None:
                try:
                    self.runtime.start(receipt["task_id"])
                except RequestConflict:
                    pass
            return receipt
