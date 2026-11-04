"""Loopback HTTP and SSE control API with Host/Origin/proxy guards and scoped tokens."""

import hmac
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from openbot.application.cancellation import CancellationService
from openbot.application.operations import ChallengeStore, OperationService
from openbot.application.recovery import RecoveryService
from openbot.application.state_machine import TaskStateService
from openbot.artifacts.store import ArtifactStore
from openbot.contracts import ContractError, SchemaRegistry, canonicalize, strict_json
from openbot.policy.approvals import ApprovalService
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.writer import RequestConflict, Writer

type ApiScope = Literal["owner_cli", "feishu_gateway", "webview_readonly"]

_LOOPBACK_IPS = frozenset({"127.0.0.1", "::1"})
_ALLOWED_HOST_PREFIXES = ("127.0.0.1", "[::1]", "localhost")
_PROXY_HEADERS = frozenset({"x-forwarded-for", "x-real-ip", "forwarded", "x-forwarded-host"})


@dataclass(frozen=True, slots=True)
class TokenGrant:
    token: str
    profile_id: str
    principal_id: str
    scope: ApiScope


class ScopedTokenStore:
    """Protected in-memory scoped session token registry."""

    def __init__(self) -> None:
        self._tokens: dict[str, TokenGrant] = {}

    def issue(self, *, profile_id: str, principal_id: str, scope: ApiScope) -> str:
        tok = f"obt_{scope}_{secrets.token_hex(24)}"
        self._tokens[tok] = TokenGrant(tok, profile_id, principal_id, scope)
        return tok

    def verify(self, bearer: str) -> TokenGrant | None:
        for stored, grant in self._tokens.items():
            if hmac.compare_digest(stored, bearer):
                return grant
        return None


@dataclass(frozen=True, slots=True)
class ApiRequest:
    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    body: str | bytes = b""
    client_ip: str = "127.0.0.1"


@dataclass(frozen=True, slots=True)
class ApiResponse:
    status_code: int
    body: bytes
    content_type: str = "application/json"

    def json(self) -> dict[str, Any]:
        return dict(strict_json(self.body))


def _json_resp(status: int, payload: dict[str, Any]) -> ApiResponse:
    return ApiResponse(status, canonicalize(payload), "application/json")


class LocalControlApiServer:
    """Authenticated local control API enforcing loopback, Host/Origin, profile, and scopes."""

    def __init__(
        self,
        *,
        profile_id: str,
        default_context: InboundContext,
        writer: Writer,
        registry: SchemaRegistry,
        tokens: ScopedTokenStore,
        inbox: Inbox,
        tasks: TaskStateService,
        operations: OperationService,
        approvals: ApprovalService,
        recovery: RecoveryService,
        cancellation: CancellationService,
        artifacts: ArtifactStore,
        challenges: ChallengeStore,
        min_retained_event_seq: int = 1,
        max_body_bytes: int = 65_536,
    ) -> None:
        self._profile_id = profile_id
        self._ctx = default_context
        self._writer = writer
        self._registry = registry
        self._tokens = tokens
        self._inbox = inbox
        self._tasks = tasks
        self._operations = operations
        self._approvals = approvals
        self._recovery = recovery
        self._cancellation = cancellation
        self._artifacts = artifacts
        self._challenges = challenges
        self._min_seq = min_retained_event_seq
        self._max_body = max_body_bytes

    def _authenticate(self, req: ApiRequest) -> tuple[TokenGrant | None, ApiResponse | None]:
        # 1. Loopback IP check & proxy header rejection
        if req.client_ip not in _LOOPBACK_IPS:
            return None, _json_resp(403, {"code": "NON_LOOPBACK_FORBIDDEN"})
        lower_headers = {k.lower(): v for k, v in req.headers.items()}
        if set(lower_headers) & _PROXY_HEADERS:
            return None, _json_resp(403, {"code": "PROXY_HEADER_FORBIDDEN"})

        # 2. Host & Origin validation (DNS rebinding & cross-origin browser defense)
        host = lower_headers.get("host", "").lower()
        if not host or not host.startswith(_ALLOWED_HOST_PREFIXES):
            return None, _json_resp(403, {"code": "INVALID_HOST_HEADER"})
        origin = lower_headers.get("origin")
        if origin is not None and origin not in {"http://127.0.0.1", "tauri://localhost"}:
            return None, _json_resp(403, {"code": "FORBIDDEN_ORIGIN"})

        # 3. Body size limit
        raw_len = len(req.body.encode("utf-8") if isinstance(req.body, str) else req.body)
        if raw_len > self._max_body:
            return None, _json_resp(413, {"code": "PAYLOAD_TOO_LARGE"})

        # 4. Bearer token & profile binding
        auth = lower_headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return None, _json_resp(401, {"code": "UNAUTHORIZED"})
        grant = self._tokens.verify(auth.removeprefix("Bearer ").strip())
        if grant is None:
            return None, _json_resp(401, {"code": "INVALID_TOKEN"})
        prof_hdr = lower_headers.get("x-openbot-profile", self._profile_id)
        if prof_hdr != self._profile_id or grant.profile_id != self._profile_id:
            return None, _json_resp(403, {"code": "PROFILE_MISMATCH"})
        return grant, None

    def handle(self, req: ApiRequest) -> ApiResponse:
        grant, err = self._authenticate(req)
        if err is not None or grant is None:
            return err or _json_resp(401, {"code": "UNAUTHORIZED"})

        if req.method != "GET" and grant.scope == "webview_readonly":
            return _json_resp(403, {"code": "READONLY_SCOPE_FORBIDDEN"})

        lower_headers = {k.lower(): v for k, v in req.headers.items()}
        idem_key = lower_headers.get("idempotency-key", f"req_{secrets.token_hex(12)}")
        deadline = int(time.monotonic() * 1000) + 5000

        try:
            if req.method == "GET" and req.path == "/v1/health":
                return _json_resp(
                    200,
                    {"status": "ok", "profile_id": self._profile_id},
                )

            if req.method == "POST" and req.path == "/v1/tasks":
                raw = self._inbox.submit(self._ctx, idem_key, req.body, deadline).result(timeout=5)
                return ApiResponse(201, raw)

            m_task = re.fullmatch(r"/v1/tasks/([A-Za-z0-9_-]+)", req.path)
            if req.method == "GET" and m_task:
                snap = self._tasks.snapshot(self._ctx, m_task.group(1))
                return _json_resp(200, snap)

            m_cancel = re.fullmatch(r"/v1/tasks/([A-Za-z0-9_-]+)/cancel", req.path)
            if req.method == "POST" and m_cancel:
                body_doc = dict(strict_json(req.body)) if req.body else {}
                exp_ver = int(body_doc.get("expected_version", 0))
                res = self._cancellation.propagate_cancel(
                    self._ctx,
                    m_cancel.group(1),
                    expected_version=exp_ver,
                    request_id=f"api_cancel:{idem_key}",
                    deadline_monotonic_ms=deadline,
                )
                return _json_resp(200, res)

            m_resume = re.fullmatch(r"/v1/tasks/([A-Za-z0-9_-]+)/resume", req.path)
            if req.method == "POST" and m_resume:
                body_doc = dict(strict_json(req.body))
                raw = self._writer.submit(
                    self._tasks.resume_reconciled(
                        self._ctx,
                        m_resume.group(1),
                        int(body_doc["expected_version"]),
                        f"api_resume:{idem_key}",
                        deadline,
                    )
                ).result(timeout=5)
                return ApiResponse(200, raw)

            m_events = re.fullmatch(r"/v1/tasks/([A-Za-z0-9_-]+)/events", req.path)
            if req.method == "GET" and m_events:
                return self._handle_sse_events(m_events.group(1), req, lower_headers)

            m_prev = re.fullmatch(r"/v1/approvals/([A-Za-z0-9_-]+)/preview", req.path)
            if req.method == "GET" and m_prev:
                return self._handle_approval_preview(m_prev.group(1))

            m_chal = re.fullmatch(r"/v1/approvals/([A-Za-z0-9_-]+)/challenge", req.path)
            if req.method == "POST" and m_chal:
                if grant.scope != "owner_cli":
                    return _json_resp(403, {"code": "CHALLENGE_OWNER_SCOPE_ONLY"})
                return self._handle_approval_challenge(m_chal.group(1))

            m_dec = re.fullmatch(r"/v1/approvals/([A-Za-z0-9_-]+)/decide", req.path)
            if req.method == "POST" and m_dec:
                raw = self._approvals.decide(
                    self._ctx, m_dec.group(1), req.body, f"api_decide:{idem_key}", deadline
                )
                return ApiResponse(200, raw)

            m_op = re.fullmatch(r"/v1/operations/([A-Za-z0-9_-]+)", req.path)
            if req.method == "GET" and m_op:
                return self._handle_operation_snapshot(m_op.group(1))

            m_ev = re.fullmatch(r"/v1/operations/([A-Za-z0-9_-]+)/evidence", req.path)
            if req.method == "POST" and m_ev:
                return self._handle_upload_evidence(m_ev.group(1), req.body, idem_key, deadline)

            m_rec = re.fullmatch(r"/v1/operations/([A-Za-z0-9_-]+)/reconcile", req.path)
            if req.method == "POST" and m_rec:
                raw = self._writer.submit(
                    self._recovery.reconcile_unknown(
                        self._ctx,
                        m_rec.group(1),
                        req.body,
                        provenance_kind="USER_ATTESTED",
                        request_id=f"api_rec:{idem_key}",
                        deadline_monotonic_ms=deadline,
                    )
                ).result(timeout=5)
                return ApiResponse(200, raw)

            return _json_resp(404, {"code": "NOT_FOUND"})
        except ContractError as exc:
            return _json_resp(400, {"code": "CONTRACT_ERROR", "message": str(exc)})
        except RequestConflict as exc:
            return _json_resp(409, {"code": "CONFLICT", "message": str(exc)})
        except PermissionError as exc:
            return _json_resp(403, {"code": "FORBIDDEN", "message": str(exc)})

    def _handle_approval_preview(self, approval_id: str) -> ApiResponse:
        def query(db: sqlite3.Connection) -> dict[str, Any]:
            row = db.execute(
                "SELECT a.operation_id,a.status,a.version,a.binding_hash,a.expires_at,"
                "o.task_id,o.workspace_id,o.tool_id,o.data_class,o.destination_json "
                "FROM approvals a JOIN operations o ON o.operation_id=a.operation_id "
                "WHERE a.approval_id=?",
                (approval_id,),
            ).fetchone()
            if not row:
                raise PermissionError("Approval not found")
            # SECRET is NEVER exposed in any ApprovalPreview
            raw_dc = str(row[8])
            safe_dc = "SENSITIVE" if raw_dc == "SECRET" else raw_dc
            dest = (
                strict_json(str(row[9]))
                if row[9]
                else {"kind": "LOCAL", "resource_ref": str(row[6])}
            )
            return {
                "schema_version": "1.1",
                "approval_id": approval_id,
                "operation_id": str(row[0]),
                "task_id": str(row[5]),
                "workspace_id": str(row[6]),
                "status": str(row[1]),
                "version": int(row[2]) + 1,
                "binding_hash": str(row[3]),
                "expires_at_ms": int(row[4]),
                "tool_name": str(row[7]),
                "effect": "EXTERNAL_WRITE",
                "data_class": safe_dc,
                "destination_summary": f"{dest['kind']}:{dest['resource_ref']}",
                "resource_summary": str(row[6]),
                "args_preview": "[REDACTED_SECRET]" if raw_dc == "SECRET" else "preview",
                "truncated": False,
            }

        preview = self._writer.read(query)
        return _json_resp(200, preview)

    def _handle_approval_challenge(self, approval_id: str) -> ApiResponse:
        def query(db: sqlite3.Connection) -> tuple[str, int]:
            row = db.execute(
                "SELECT status,expires_at FROM approvals "
                "WHERE approval_id=? AND allowed_actor_id=?",
                (approval_id, self._ctx.principal_id),
            ).fetchone()
            if not row:
                raise PermissionError("Approval not found for owner")
            return str(row[0]), int(row[1])

        status, expires_at = self._writer.read(query)
        now = time.time_ns() // 1_000_000
        if status != "PENDING" or now >= expires_at:
            return _json_resp(409, {"code": "APPROVAL_NOT_PENDING_OR_EXPIRED"})
        nonce = self._challenges.get(approval_id)
        if nonce is None:
            return _json_resp(404, {"code": "CHALLENGE_UNAVAILABLE"})
        return _json_resp(200, {"approval_id": approval_id, "nonce": nonce.decode("utf-8")})

    def _handle_operation_snapshot(self, operation_id: str) -> ApiResponse:
        def query(db: sqlite3.Connection) -> dict[str, Any]:
            row = db.execute(
                "SELECT operation_id,task_id,state,version,retry_class,tool_id,binding_hash "
                "FROM operations WHERE operation_id=? AND requested_by=?",
                (operation_id, self._ctx.principal_id),
            ).fetchone()
            if not row:
                raise PermissionError("Operation not found")
            return {
                "operation_id": str(row[0]),
                "task_id": str(row[1]),
                "state": str(row[2]),
                "version": int(row[3]),
                "retry_class": str(row[4]),
                "tool_id": str(row[5]),
                "binding_hash": str(row[6]),
            }

        return _json_resp(200, self._writer.read(query))

    def _handle_upload_evidence(
        self, operation_id: str, raw_body: str | bytes, idem_key: str, deadline: int
    ) -> ApiResponse:
        doc = dict(strict_json(raw_body))
        if "host_path" in doc or "path" in doc:
            raise ContractError("Evidence upload refuses host_path; supply inline content only")
        content = str(doc.get("content", "")).encode("utf-8")
        mime = str(doc.get("mime", "text/plain"))
        if not content:
            raise ContractError("Evidence content must be non-empty")
        rec = self._artifacts.put(
            self._ctx,
            data=content,
            mime=mime,
            classification="WORKSPACE",
            scope_kind="OPERATION",
            operation_id=operation_id,
            purpose="reconciliation",
            request_id=f"api_ev:{idem_key}",
            deadline_monotonic_ms=deadline,
        )
        return _json_resp(201, {"object_id": rec.object_id, "sha256": rec.sha256})

    def _handle_sse_events(
        self, task_id: str, req: ApiRequest, lower_headers: dict[str, str]
    ) -> ApiResponse:
        q_seq = req.query.get("after_seq")
        h_seq = lower_headers.get("last-event-id")
        if q_seq is not None and h_seq is not None and q_seq != h_seq:
            return _json_resp(400, {"code": "SSE_CURSOR_CONFLICT"})
        cursor_str = q_seq if q_seq is not None else h_seq
        after_seq = 0 if cursor_str is None else int(cursor_str)
        if after_seq > 0 and after_seq < self._min_seq:
            return _json_resp(
                410,
                {"code": "CURSOR_EXPIRED_FETCH_SNAPSHOT", "min_retained_seq": self._min_seq},
            )
        all_events = self._tasks.replay(self._ctx, task_id)
        filtered = [e for e in all_events if int(str(e["seq"])) > after_seq][:64]
        return _json_resp(200, {"task_id": task_id, "events": filtered})
