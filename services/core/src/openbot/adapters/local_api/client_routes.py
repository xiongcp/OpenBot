"""Additive, scoped client DTOs; all effects stay in the existing core services."""

import difflib
import hashlib
import re
import sqlite3
from typing import Any

from openbot.application.agent_runtime import AgentRuntime
from openbot.application.client_state import ClientState
from openbot.application.feishu_ingress import FeishuIngress
from openbot.application.operations import task_record
from openbot.contracts import ContractError, strict_json


class ClientRoutes:
    def __init__(
        self, state: ClientState, runtime: AgentRuntime, feishu: FeishuIngress | None = None
    ):
        self.state, self.runtime = state, runtime
        self.feishu = feishu

    def _safe(self, text: str) -> str:
        return self.state.redactor.sanitize_sink(
            sink="ui_event", text=text, data_class="WORKSPACE"
        ).sanitized_text[:4096]

    def runs(self) -> dict[str, Any]:
        ctx = self.state.context
        rows = self.state.writer.read(
            lambda db: db.execute(
                "SELECT task_id,goal,state,version,checkpoint_json,updated_at FROM tasks "
                "WHERE owner_id=? AND session_id=? "
                "ORDER BY updated_at DESC,task_id DESC LIMIT 100",
                (ctx.principal_id, ctx.session_id),
            ).fetchall()
        )
        runs = []
        active = self.runtime.health()["active_task_id"]
        for task, goal, status, version, checkpoint, updated in rows:
            stored = strict_json(checkpoint)
            # A retired marker still names the run; only a live one can need reconciliation.
            live = stored.get("agent_run")
            run = live or stored.get("last_agent_run") or {}
            runs.append(
                {
                    "task_id": task,
                    "goal": self._safe(goal),
                    "state": status,
                    "version": version,
                    "run_id": run.get("run_id"),
                    "config_revision": run.get("config_revision"),
                    "updated_at": updated,
                    "requires_reconciliation": bool(
                        live
                        and task != active
                        and status not in {"SUCCEEDED", "FAILED", "CANCELLED", "PARTIAL"}
                    ),
                }
            )
        return {"runs": runs}

    def preview(self, approval_id: str) -> dict[str, Any]:
        def query(db: sqlite3.Connection) -> dict[str, Any]:
            row = db.execute(
                "SELECT a.operation_id,a.status,a.version,a.binding_hash,a.expires_at,"
                "o.task_id,o.workspace_id,o.tool_id,o.data_class,o.destination_json,"
                "o.canonical_args_json,t.manifest_json,o.resource_snapshot_json,"
                "o.workspace_generation FROM approvals a "
                "JOIN operations o ON o.operation_id=a.operation_id "
                "JOIN tool_registry t ON t.tool_id=o.tool_id AND t.tool_version=o.tool_version "
                "AND t.manifest_digest=o.tool_manifest_digest WHERE a.approval_id=?",
                (approval_id,),
            ).fetchone()
            if not row:
                raise PermissionError("APPROVAL_UNAVAILABLE")
            task_record(db, self.state.context, row[5])
            manifest = strict_json(row[11])
            raw_args = strict_json(row[10]) if row[10] else {}
            res_snap = strict_json(row[12]) if row[12] else {}
            ws_gen_row = db.execute(
                "SELECT generation FROM workspaces WHERE workspace_id=?", (row[6],)
            ).fetchone()
            current_gen = int(ws_gen_row[0]) if ws_gen_row else int(row[13])
            drift = current_gen != int(row[13])
            diff_lines: list[str] = []
            old_sha: str | None = None
            new_sha: str | None = None
            target_path = ""
            if row[8] != "SECRET" and isinstance(raw_args, dict):
                target_path = str(raw_args.get("path", raw_args.get("subpath", "")))
                files_snap = res_snap.get("files", []) if isinstance(res_snap, dict) else []
                if files_snap and isinstance(files_snap[0], dict):
                    old_sha = str(files_snap[0].get("sha256", "")).removeprefix("sha256:")
                if "old_snippet" in raw_args and "new_snippet" in raw_args:
                    old_s = str(raw_args["old_snippet"])
                    new_s = str(raw_args["new_snippet"])
                    if old_sha is None:
                        old_sha = hashlib.sha256(old_s.encode("utf-8")).hexdigest()
                    new_sha = hashlib.sha256(new_s.encode("utf-8")).hexdigest()
                    diff_lines = [
                        self._safe(ln.rstrip("\r\n"))
                        for ln in difflib.unified_diff(
                            old_s.splitlines(keepends=True),
                            new_s.splitlines(keepends=True),
                            fromfile=f"a/{target_path or 'file'}",
                            tofile=f"b/{target_path or 'file'}",
                        )
                    ]
            return {
                "schema_version": "1.1",
                "approval_id": approval_id,
                "operation_id": row[0],
                "task_id": row[5],
                "workspace_id": row[6],
                "status": row[1],
                "version": row[2] + 1,
                "binding_hash": "sha256:" + row[3],
                "expires_at_ms": row[4],
                "tool_name": row[7],
                "effect": manifest["effect"],
                "data_class": "SENSITIVE" if row[8] == "SECRET" else row[8],
                "destination_summary": self._safe(row[9]),
                "resource_summary": row[6],
                "args_preview": "[REDACTED_SECRET]" if row[8] == "SECRET" else self._safe(row[10]),
                "truncated": len(row[10]) > 4096,
                "target_path": target_path,
                "old_sha256": old_sha,
                "new_sha256": new_sha,
                "diff_lines": diff_lines,
                "precondition_drift": drift,
            }

        return self.state.writer.read(query)

    def handle(
        self,
        *,
        method: str,
        path: str,
        body: str | bytes,
        query: dict[str, str],
        scope: str,
        principal_id: str,
        request_id: str,
        min_retained_seq: int,
    ) -> tuple[int, dict[str, Any]] | None:
        if self.feishu and (path.startswith("/v1/feishu/") or path.startswith("/v1/client/feishu")):
            self.state.settings()
            if principal_id != self.state.context.principal_id:
                raise PermissionError("CLIENT_OWNER_MISMATCH")
            if path.startswith("/v1/feishu/"):
                if scope != "feishu_gateway":
                    raise PermissionError("FEISHU_GATEWAY_SCOPE_REQUIRED")
                if method == "GET" and path == "/v1/feishu/config":
                    return 200, self.feishu.config()
                if method == "POST" and path == "/v1/feishu/events":
                    return 201, self.feishu.receive(body)
                if method == "POST" and path == "/v1/feishu/health":
                    return 200, self.feishu.heartbeat(body)
            else:
                if scope != "owner_cli":
                    raise PermissionError("FEISHU_LOCAL_OWNER_REQUIRED")
                if method == "GET" and path == "/v1/client/feishu":
                    return 200, self.feishu.snapshot()
                doc = strict_json(body)
                if (
                    method == "POST"
                    and path == "/v1/client/feishu/configure"
                    and set(doc) == {"app_id"}
                ):
                    return 200, self.feishu.configure(doc["app_id"], request_id)
                if (
                    method == "POST"
                    and path == "/v1/client/feishu/confirm"
                    and set(doc) == {"candidate_id", "confirm"}
                    and doc["confirm"] is True
                ):
                    return 200, self.feishu.confirm(doc["candidate_id"], request_id)
            raise ContractError("FEISHU_ROUTE_OR_BODY_INVALID")
        if not path.startswith("/v1/client/"):
            return None
        if principal_id != self.state.context.principal_id:
            raise PermissionError("CLIENT_OWNER_MISMATCH")
        self.state.settings()  # Recheck the trusted owner/session even for reads.
        if method != "GET" and scope != "owner_cli":
            raise PermissionError("CLIENT_OWNER_SCOPE_REQUIRED")
        if method == "GET" and path == "/v1/client/settings":
            return 200, self.state.settings()
        if method == "POST" and path == "/v1/client/settings/preview":
            return 200, self.state.preview(body)
        if method == "POST" and path == "/v1/client/settings/apply":
            return 200, self.state.apply(body, request_id)
        if method == "GET" and path == "/v1/client/health":
            health = self.runtime.health()
            if self.feishu:
                health["gateway"] = self.feishu.snapshot()["stage"]
            return 200, health
        if method == "GET" and path == "/v1/client/runs":
            return 200, self.runs()
        if method == "GET" and path == "/v1/client/approvals":
            ctx = self.state.context
            ids = self.state.writer.read(
                lambda db: db.execute(
                    "SELECT a.approval_id FROM approvals a JOIN operations o "
                    "ON o.operation_id=a.operation_id JOIN tasks t ON t.task_id=o.task_id "
                    "WHERE a.status='PENDING' AND a.allowed_actor_id=? AND t.session_id=? "
                    "ORDER BY a.requested_at LIMIT 100",
                    (ctx.principal_id, ctx.session_id),
                ).fetchall()
            )
            return 200, {"approvals": [self.preview(row[0]) for row in ids]}
        match = re.fullmatch(r"/v1/client/tasks/(tsk_[A-Za-z0-9_-]{1,80})/(start|trace)", path)
        if match:
            task, action = match.groups()
            if method == "POST" and action == "start":
                if strict_json(body) != {}:
                    raise ContractError("CLIENT_START_BODY_MUST_BE_EMPTY_OBJECT")
                return 202, self.runtime.start(task)
            if method == "GET" and action == "trace":
                cursor = query.get("after_seq", "0")
                if set(query) - {"after_seq"} or not re.fullmatch(r"[0-9]{1,18}", cursor):
                    raise ContractError("CLIENT_TRACE_CURSOR_INVALID")
                after = int(cursor)
                self.state.run(task)
                if after and after < min_retained_seq:
                    return 410, {"code": "EVENT_CURSOR_EXPIRED", "recover": "reload_trace"}
                return 200, self.state.trace(task, after_seq=after)
        return 404, {"code": "CLIENT_ROUTE_NOT_FOUND"}
