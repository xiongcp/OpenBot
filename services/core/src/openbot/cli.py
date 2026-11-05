"""Authenticated loopback CLI for OpenBot tasks, approvals, and reconciliation (OB-028)."""

import argparse
import hashlib
import http.client
import json
import os
import re
import secrets
import signal
import socket
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from openbot import __version__
from openbot.adapters.local_api.server import (
    ApiRequest,
    ApiResponse,
    LocalControlApiServer,
    LoopbackHttpDaemon,
    ScopedTokenStore,
)

_ANSI_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_ANSI_OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_ANSI_OTHER_RE = re.compile(r"\x1b[@-Z\\-_]")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_RICH_TAG_RE = re.compile(r"\[[/a-zA-Z0-9_=#. -]+\]")

_FORBIDDEN_FLAGS = frozenset(
    {
        "--ignore-and-rerun",
        "--force-success",
        "--revive-consumed",
        "--token",
        "--bearer",
        "--api-key",
    }
)


def sanitize_terminal_text(text: str) -> str:
    """Strip ANSI escape sequences, control characters, and Rich markup tags from untrusted text."""
    cleaned = _ANSI_OSC_RE.sub("", text)
    cleaned = _ANSI_CSI_RE.sub("", cleaned)
    cleaned = _ANSI_OTHER_RE.sub("", cleaned)
    cleaned = _CONTROL_CHARS_RE.sub("", cleaned)
    cleaned = _RICH_TAG_RE.sub("", cleaned)
    return cleaned


class CliTransport(Protocol):
    def request(self, req: ApiRequest) -> ApiResponse: ...


class LoopbackHttpTransport:
    """Real loopback HTTP client transport connecting to 127.0.0.1/<port> without proxy bypass."""

    def __init__(self, host: str, *, timeout_seconds: float = 5.0) -> None:
        if not host.startswith(("127.0.0.1:", "localhost:", "[::1]:")):
            raise PermissionError(f"CLI transport only permits loopback hosts, got {host}")
        self._host = host
        self._timeout = timeout_seconds

    def request(self, req: ApiRequest) -> ApiResponse:
        raw_body = req.body.encode("utf-8") if isinstance(req.body, str) else req.body
        conn = http.client.HTTPConnection(self._host, timeout=self._timeout)
        try:
            conn.request(req.method, req.path, body=raw_body, headers=req.headers)
            resp = conn.getresponse()
            data = resp.read()
            ctype = resp.getheader("Content-Type", "application/json")
            return ApiResponse(resp.status, data, ctype)
        except TimeoutError as exc:
            raise TimeoutError(str(exc)) from exc
        except (ConnectionRefusedError, OSError, http.client.HTTPException) as exc:
            if isinstance(exc, socket.timeout):
                raise TimeoutError(str(exc)) from exc
            raise ConnectionRefusedError(str(exc)) from exc
        finally:
            conn.close()


@dataclass(frozen=True, slots=True)
class CliApiSession:
    profile_id: str
    token: str
    transport: CliTransport
    host: str = "127.0.0.1:41931"

    def call(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> ApiResponse:
        headers = {
            "Host": self.host,
            "Authorization": f"Bearer {self.token}",
            "X-OpenBot-Profile": self.profile_id,
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        raw_body = (
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if body is not None
            else b""
        )
        return self.transport.request(
            ApiRequest(method=method, path=path, headers=headers, body=raw_body)
        )


def _format_output(payload: dict[str, Any], *, as_json: bool) -> str:
    if as_json:
        return json.dumps(payload, sort_keys=True)
    lines = [
        f"{sanitize_terminal_text(str(k))}: {sanitize_terminal_text(str(v))}"
        for k, v in sorted(payload.items())
    ]
    return "\n".join(lines)


def _map_http_error(resp: ApiResponse, *, as_json: bool) -> tuple[int, str]:
    try:
        doc = resp.json()
    except Exception:
        doc = {"code": f"HTTP_{resp.status_code}"}
    if resp.status_code in {401, 403}:
        return 3, _format_output(
            {"code": "AUTH_OR_PERMISSION_ERROR", "detail": doc}, as_json=as_json
        )
    if resp.status_code == 409:
        return 4, _format_output(
            {"code": "VERSION_OR_STATE_CONFLICT", "detail": doc}, as_json=as_json
        )
    return 6, _format_output({"code": "CLI_REQUEST_ERROR", "detail": doc}, as_json=as_json)


def discover_cli_session(
    profile_dir: Path | None = None, *, timeout_seconds: float = 5.0
) -> CliApiSession | None:
    """Discover authenticated CLI session from a protected profile directory."""
    effective_dir = profile_dir
    if effective_dir is None:
        env_dir = os.environ.get("OPENBOT_PROFILE_DIR")
        if env_dir:
            effective_dir = Path(env_dir)
    if effective_dir is None:
        return None
    if effective_dir.is_symlink() or not effective_dir.is_dir():
        raise ConnectionRefusedError(f"Profile directory unavailable: {effective_dir}")
    session_file = effective_dir / "daemon_session.json"
    token_file = effective_dir / "owner_cli.token"
    if not session_file.is_file() or not token_file.is_file():
        raise ConnectionRefusedError(f"Daemon session metadata missing in {effective_dir}")
    if session_file.is_symlink() or token_file.is_symlink():
        raise PermissionError("SESSION_OR_TOKEN_SYMLINK_FORBIDDEN")
    if sys.platform != "win32":
        st = os.lstat(token_file)
        if (st.st_mode & 0o077) != 0:
            raise PermissionError("INSECURE_TOKEN_FILE_PERMISSIONS")
    meta = json.loads(session_file.read_text(encoding="utf-8"))
    token = token_file.read_text(encoding="utf-8").strip()
    host = str(meta["host"])
    profile_id = str(meta["profile_id"])
    return CliApiSession(
        profile_id=profile_id,
        token=token,
        transport=LoopbackHttpTransport(host, timeout_seconds=timeout_seconds),
        host=host,
    )


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openbot")
    parser.add_argument("--profile-dir", type=Path, default=None)
    parser.add_argument("--timeout-ms", type=int, default=5000)
    sub = parser.add_subparsers(dest="group")

    sub.add_parser("version")
    p_health = sub.add_parser("health")
    p_health.add_argument("--profile-dir", type=Path, default=None)
    p_health.add_argument("--require-daemon", action="store_true")
    p_health.add_argument("--json", action="store_true")

    p_daemon = sub.add_parser("daemon")
    daemon_sub = p_daemon.add_subparsers(dest="action", required=True)
    p_dserve = daemon_sub.add_parser("serve")
    p_dserve.add_argument("--profile-dir", type=Path, required=True)
    p_dserve.add_argument("--profile-id", default="pro_test1")
    p_dserve.add_argument("--workspace-id", default="wsp_test1")
    p_dserve.add_argument("--port", type=int, default=0)
    p_dserve.add_argument("--epoch", default="ep_1")
    p_dserve.add_argument("--workspace-root", type=Path, default=None)
    p_dserve.add_argument("--model-credentials", action="store_true")

    # task group
    p_task = sub.add_parser("task")
    task_sub = p_task.add_subparsers(dest="action", required=True)

    p_tc = task_sub.add_parser("create")
    p_tc.add_argument("--workspace", required=True)
    p_tc.add_argument("--goal", required=True)
    p_tc.add_argument("--idempotency-key", default=None)
    p_tc.add_argument("--profile-dir", type=Path, default=None)
    p_tc.add_argument("--timeout-ms", type=int, default=5000)
    p_tc.add_argument("--json", action="store_true")

    p_ts = task_sub.add_parser("show")
    p_ts.add_argument("--task-id", required=True)
    p_ts.add_argument("--profile-dir", type=Path, default=None)
    p_ts.add_argument("--timeout-ms", type=int, default=5000)
    p_ts.add_argument("--json", action="store_true")

    p_tcan = task_sub.add_parser("cancel")
    p_tcan.add_argument("--task-id", required=True)
    p_tcan.add_argument("--expected-version", type=int, required=True)
    p_tcan.add_argument("--idempotency-key", default=None)
    p_tcan.add_argument("--profile-dir", type=Path, default=None)
    p_tcan.add_argument("--timeout-ms", type=int, default=5000)
    p_tcan.add_argument("--json", action="store_true")

    p_tres = task_sub.add_parser("resume")
    p_tres.add_argument("--task-id", required=True)
    p_tres.add_argument("--expected-version", type=int, required=True)
    p_tres.add_argument("--idempotency-key", default=None)
    p_tres.add_argument("--profile-dir", type=Path, default=None)
    p_tres.add_argument("--timeout-ms", type=int, default=5000)
    p_tres.add_argument("--json", action="store_true")

    # approval group
    p_apr = sub.add_parser("approval")
    apr_sub = p_apr.add_subparsers(dest="action", required=True)

    p_aprev = apr_sub.add_parser("preview")
    p_aprev.add_argument("--approval-id", required=True)
    p_aprev.add_argument("--profile-dir", type=Path, default=None)
    p_aprev.add_argument("--timeout-ms", type=int, default=5000)
    p_aprev.add_argument("--json", action="store_true")

    p_adec = apr_sub.add_parser("decide")
    p_adec.add_argument("--approval-id", required=True)
    p_adec.add_argument("--expected-version", type=int, required=True)
    p_adec.add_argument("--binding-hash", required=True)
    p_adec.add_argument("--decision", choices=("APPROVE", "DENY"), required=True)
    p_adec.add_argument("--reason", default="cli_owner_decision")
    p_adec.add_argument("--idempotency-key", default=None)
    p_adec.add_argument("--profile-dir", type=Path, default=None)
    p_adec.add_argument("--timeout-ms", type=int, default=5000)
    p_adec.add_argument("--json", action="store_true")

    # operation group
    p_op = sub.add_parser("operation")
    op_sub = p_op.add_subparsers(dest="action", required=True)

    p_oshow = op_sub.add_parser("show")
    p_oshow.add_argument("--operation-id", required=True)
    p_oshow.add_argument("--profile-dir", type=Path, default=None)
    p_oshow.add_argument("--timeout-ms", type=int, default=5000)
    p_oshow.add_argument("--json", action="store_true")

    p_orec = op_sub.add_parser("reconcile")
    p_orec.add_argument("--operation-id", required=True)
    p_orec.add_argument("--expected-version", type=int, required=True)
    p_orec.add_argument(
        "--outcome",
        choices=("CONFIRMED_SUCCEEDED", "CONFIRMED_NOT_EXECUTED"),
        required=True,
    )
    p_orec.add_argument("--evidence-content", required=True)
    p_orec.add_argument("--idempotency-key", default=None)
    p_orec.add_argument("--profile-dir", type=Path, default=None)
    p_orec.add_argument("--timeout-ms", type=int, default=5000)
    p_orec.add_argument("--json", action="store_true")
    return parser


def run_cli_command(
    argv: Sequence[str], *, session: CliApiSession | None = None
) -> tuple[int, str]:
    """Execute a CLI command via the authenticated local API without touching SQLite directly."""
    as_json = "--json" in argv
    for arg in argv:
        flag_name = arg.split("=", 1)[0]
        if flag_name in _FORBIDDEN_FLAGS:
            return 6, _format_output(
                {
                    "code": "FORBIDDEN_CLI_FLAG",
                    "flag": flag_name,
                    "message": "Client bypass flags are forbidden by OpenBot safety invariants.",
                },
                as_json=True,
            )

    if not argv:
        return 6, _format_output({"code": "EMPTY_COMMAND"}, as_json=as_json)

    if argv[0] == "version":
        return 0, __version__
    if argv[0] == "health":
        require_daemon = "--require-daemon" in argv
        eff_session = session
        if eff_session is None:
            p_dir: Path | None = None
            for i, tok in enumerate(argv):
                if tok == "--profile-dir" and i + 1 < len(argv):
                    p_dir = Path(argv[i + 1])
                elif tok.startswith("--profile-dir="):
                    p_dir = Path(tok.split("=", 1)[1])
            try:
                eff_session = discover_cli_session(p_dir)
            except (ConnectionRefusedError, PermissionError):
                eff_session = None
        if eff_session is not None:
            try:
                resp = eff_session.call("GET", "/v1/health")
                if resp.status_code == 200:
                    doc = resp.json()
                    return 0, json.dumps(
                        {
                            "version": __version__,
                            "daemon_running": True,
                            "profile_id": doc.get("profile_id", eff_session.profile_id),
                            "status": doc.get("status", "ok"),
                        }
                    )
            except (ConnectionRefusedError, TimeoutError):
                pass
        return (2 if require_daemon else 0), json.dumps(
            {
                "version": __version__,
                "daemon_running": False,
                "isolation": "CAPABILITY_UNAVAILABLE",
                "stage": "M0",
            }
        )

    eff_session = session
    if eff_session is None:
        prof_dir: Path | None = None
        timeout_ms = 5000
        for i, tok in enumerate(argv):
            if tok == "--profile-dir" and i + 1 < len(argv):
                prof_dir = Path(argv[i + 1])
            elif tok.startswith("--profile-dir="):
                prof_dir = Path(tok.split("=", 1)[1])
            elif tok == "--timeout-ms" and i + 1 < len(argv):
                timeout_ms = int(argv[i + 1])
            elif tok.startswith("--timeout-ms="):
                timeout_ms = int(tok.split("=", 1)[1])
        try:
            eff_session = discover_cli_session(
                prof_dir, timeout_seconds=max(0.05, timeout_ms / 1000.0)
            )
        except PermissionError as exc:
            return 3, _format_output(
                {"code": "AUTH_OR_PERMISSION_ERROR", "message": sanitize_terminal_text(str(exc))},
                as_json=as_json,
            )
        except ConnectionRefusedError as exc:
            return 2, _format_output(
                {"code": "DAEMON_UNAVAILABLE", "message": sanitize_terminal_text(str(exc))},
                as_json=as_json,
            )

    if eff_session is None:
        return 2, _format_output(
            {"code": "DAEMON_UNAVAILABLE", "message": "No active CLI API session configured."},
            as_json=as_json,
        )

    try:
        return _dispatch_authenticated(argv, session=eff_session, as_json=as_json)
    except ConnectionRefusedError as exc:
        return 2, _format_output(
            {"code": "DAEMON_UNAVAILABLE", "message": sanitize_terminal_text(str(exc))},
            as_json=as_json,
        )
    except TimeoutError as exc:
        return 5, _format_output(
            {
                "code": "WAIT_TIMEOUT_OUTCOME_UNKNOWN",
                "action_guaranteed_not_executed": False,
                "requery_required": True,
                "message": sanitize_terminal_text(
                    f"Wait timed out ({exc}); action may still execute. Re-query state."
                ),
            },
            as_json=as_json,
        )


def _dispatch_authenticated(
    argv: Sequence[str], *, session: CliApiSession, as_json: bool
) -> tuple[int, str]:
    parser = build_cli_parser()
    args = parser.parse_args(argv)
    idem = getattr(args, "idempotency_key", None) or f"cli_{secrets.token_hex(8)}"

    if args.group == "task" and args.action == "create":
        resp = session.call(
            "POST",
            "/v1/tasks",
            body={
                "workspace_id": args.workspace,
                "goal": args.goal,
                "network_mode": "OFFLINE",
            },
            idempotency_key=idem,
        )
    elif args.group == "task" and args.action == "show":
        resp = session.call("GET", f"/v1/tasks/{args.task_id}")
    elif args.group == "task" and args.action == "cancel":
        resp = session.call(
            "POST",
            f"/v1/tasks/{args.task_id}/cancel",
            body={"expected_version": args.expected_version},
            idempotency_key=idem,
        )
    elif args.group == "task" and args.action == "resume":
        resp = session.call(
            "POST",
            f"/v1/tasks/{args.task_id}/resume",
            body={"expected_version": args.expected_version},
            idempotency_key=idem,
        )
    elif args.group == "approval" and args.action == "preview":
        resp = session.call("GET", f"/v1/approvals/{args.approval_id}/preview")
    elif args.group == "approval" and args.action == "decide":
        nonce = ""
        if args.decision == "APPROVE":
            chal_resp = session.call(
                "POST", f"/v1/approvals/{args.approval_id}/challenge", idempotency_key=f"{idem}_ch"
            )
            if chal_resp.status_code >= 400:
                return _map_http_error(chal_resp, as_json=as_json)
            nonce = str(chal_resp.json()["nonce"])
        body: dict[str, Any] = {
            "expected_version": args.expected_version,
            "expected_binding_hash": args.binding_hash,
            "decision": args.decision,
        }
        if nonce:
            body["nonce"] = nonce
        resp = session.call(
            "POST", f"/v1/approvals/{args.approval_id}/decide", body=body, idempotency_key=idem
        )
    elif args.group == "operation" and args.action == "show":
        resp = session.call("GET", f"/v1/operations/{args.operation_id}")
    elif args.group == "operation" and args.action == "reconcile":
        ev_resp = session.call(
            "POST",
            f"/v1/operations/{args.operation_id}/evidence",
            body={"content": args.evidence_content, "mime": "text/plain"},
            idempotency_key=f"{idem}_ev",
        )
        if ev_resp.status_code >= 400:
            return _map_http_error(ev_resp, as_json=as_json)
        art_id = str(ev_resp.json()["object_id"])
        resp = session.call(
            "POST",
            f"/v1/operations/{args.operation_id}/reconcile",
            body={
                "expected_version": args.expected_version,
                "outcome": args.outcome,
                "evidence_artifact_ids": [art_id],
            },
            idempotency_key=idem,
        )
    else:
        return 6, _format_output({"code": "UNKNOWN_CLI_COMMAND"}, as_json=as_json)

    if resp.status_code >= 400:
        return _map_http_error(resp, as_json=as_json)
    return 0, _format_output(resp.json(), as_json=as_json)


class _PersistentChallengeStore:
    """File-backed challenge nonce store surviving daemon restarts within a profile."""

    def __init__(self, store_path: Path) -> None:
        self._path = store_path
        if not self._path.is_file():
            self._write({})

    def _read(self) -> dict[str, str]:
        if not self._path.is_file():
            return {}
        return dict(json.loads(self._path.read_text(encoding="utf-8")))

    def _write(self, data: dict[str, str]) -> None:
        tmp = self._path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, json.dumps(data, sort_keys=True).encode("utf-8"))
        finally:
            os.close(fd)
        os.replace(tmp, self._path)

    def put(self, approval_id: str, nonce: bytes) -> None:
        data = self._read()
        data[approval_id] = nonce.decode("utf-8")
        self._write(data)

    def get(self, approval_id: str) -> bytes | None:
        val = self._read().get(approval_id)
        return val.encode("utf-8") if val is not None else None


def _seed_daemon_profile_db(
    db: sqlite3.Connection, *, profile_id: str, workspace_id: str, runtime_epoch: str
) -> None:
    from openbot.contracts import canonicalize

    row = db.execute("SELECT count(*) FROM profile_config").fetchone()
    if row and int(row[0]) > 0:
        return
    db.execute("INSERT INTO policy_revisions VALUES(1, ?, '{}', 1000, 1000)", ("a" * 64,))
    db.execute(
        "INSERT INTO runtime_instances("
        "runtime_epoch,boot_id,supervisor_ref,state,started_at,heartbeat_at) "
        "VALUES(?, 'boot_1', 'sup_1', 'ACTIVE', 1000, 1000)",
        (runtime_epoch,),
    )
    db.execute(
        "INSERT INTO profile_config("
        "singleton,profile_id,schema_version,policy_version,identity_epoch,"
        "privacy_mode,active_runtime_epoch,last_fencing_token,created_at,updated_at) "
        "VALUES(1, ?, 1, 1, 1, 'OFFLINE', ?, 0, 1000, 1000)",
        (profile_id, runtime_epoch),
    )
    db.execute(
        "INSERT INTO principals(principal_id,role,status,display_name,created_at) "
        "VALUES('pri_test1','OWNER','ACTIVE','local owner',1000)"
    )
    db.execute(
        "INSERT INTO workspaces("
        "workspace_id,root_ref,generation,status,version,created_at,updated_at) "
        "VALUES(?, 'local-workspace', 1, 'ACTIVE', 0, 1000, 1000)",
        (workspace_id,),
    )
    db.execute(
        "INSERT INTO sessions(session_id,owner_id,workspace_id,status,created_at,updated_at) "
        "VALUES('ses_test1','pri_test1',?,'OPEN',1000,1000)",
        (workspace_id,),
    )
    for name, effect, retry_class in (
        ("fs.patch", "LOCAL_WRITE", "IDEMPOTENT_WRITE"),
        ("gui.click", "EXTERNAL_WRITE", "RECONCILE_ONLY"),
        ("test.run", "LOCAL_WRITE", "SAFE_READ"),
    ):
        manifest = {
            "name": name,
            "version": "1.0.0",
            "effect": effect,
            "retry_class": retry_class,
            "input_schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {"arg": {"type": "string"}},
                "required": ["arg"],
                "additionalProperties": False,
            },
        }
        raw = canonicalize(manifest)
        db.execute(
            "INSERT INTO tool_registry VALUES(?, '1.0.0', ?, NULL, 'builtin', ?, 'ACTIVE', 1000)",
            (name, hashlib.sha256(raw).hexdigest(), raw.decode()),
        )


def _serve_daemon_process(
    *,
    profile_dir: Path,
    profile_id: str,
    workspace_id: str,
    port: int,
    runtime_epoch: str,
    workspace_root: Path | None = None,
    model_credentials: tuple[str, str] | None = None,
) -> int:
    from openbot.application.cancellation import CancellationService
    from openbot.application.dispatch import DispatchService
    from openbot.application.operations import OperationService
    from openbot.application.recovery import RecoveryService
    from openbot.application.scheduler import SingleInstanceSupervisorLock
    from openbot.application.state_machine import TaskStateService
    from openbot.artifacts.store import ArtifactStore
    from openbot.contracts import SchemaRegistry
    from openbot.policy.approvals import ApprovalService
    from openbot.storage.inbox import InboundContext, Inbox
    from openbot.storage.migrate import connect, load_migrations, migrate
    from openbot.storage.writer import Writer

    profile_dir = profile_dir.resolve()
    profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    repo_root = Path(__file__).resolve().parents[4]

    sup_lock = SingleInstanceSupervisorLock(profile_dir / "daemon.lock", profile_id=profile_id)
    sup_lock.acquire_and_mint_handoff(runtime_epoch=runtime_epoch, boot_id="boot_daemon")

    db_path = profile_dir / "state.sqlite"
    migrate(db_path, load_migrations(repo_root / "db/migrations"))
    db = connect(db_path)
    try:
        _seed_daemon_profile_db(
            db, profile_id=profile_id, workspace_id=workspace_id, runtime_epoch=runtime_epoch
        )
        if workspace_root is not None:
            workspace_root = workspace_root.resolve(strict=True)
            if not workspace_root.is_dir():
                raise PermissionError("CLIENT_WORKSPACE_REQUIRED")
            binding = "sha256:" + hashlib.sha256(str(workspace_root).encode()).hexdigest()
            old = db.execute(
                "SELECT root_ref FROM workspaces WHERE workspace_id=?", (workspace_id,)
            ).fetchone()
            if old is None or (
                old[0] != binding and db.execute("SELECT count(*) FROM tasks").fetchone()[0]
            ):
                raise PermissionError("CLIENT_WORKSPACE_BINDING_CHANGED")
            if old[0] != binding:
                db.execute(
                    "UPDATE workspaces SET root_ref=?,generation=generation+1,"
                    "version=version+1 WHERE workspace_id=?",
                    (binding, workspace_id),
                )
    finally:
        db.close()

    context = InboundContext(
        profile_id, "pri_test1", 1, "local", "tenant1", "app1", "ses_test1", workspace_id
    )
    registry = SchemaRegistry.from_directory(repo_root / "contracts")
    challenges = _PersistentChallengeStore(profile_dir / "challenges.json")
    writer = Writer(db_path)
    inbox = Inbox(writer, registry)
    tasks = TaskStateService(writer)
    ops = OperationService(writer, challenges, registry)
    approvals = ApprovalService(writer, challenges, registry)
    dispatcher = DispatchService(writer, registry)
    recovery = RecoveryService(writer, registry)
    cancellation = CancellationService(writer)
    artifacts = ArtifactStore(writer, profile_dir / "blobs")

    client_routes = None
    runtime = None
    if workspace_root is not None:
        from openbot.adapters.local_api.client_routes import ClientRoutes
        from openbot.application.agent_runtime import AgentRuntime
        from openbot.application.client_state import ClientState
        from openbot.application.feishu_ingress import FeishuIngress
        from openbot.application.runtime_factory import model_factory
        from openbot.observability.redaction import RedactionPipeline
        from openbot.tools.mcp.container_read import ContainerReadTool

        redactor = RedactionPipeline(registered_secrets=model_credentials or ())
        state = ClientState(writer, context, redactor)
        lock = json.loads((repo_root / "components/locks/mcp-demo.json").read_text())
        tool = ContainerReadTool(
            image=lock["image"],
            server=repo_root / lock["server_path"],
            server_sha256=lock["server_sha256"],
        )
        runtime = AgentRuntime(
            state=state,
            tasks=tasks,
            operations=ops,
            dispatcher=dispatcher,
            artifacts=artifacts,
            registry=registry,
            workspace=workspace_root,
            runtime_epoch=runtime_epoch,
            tool=tool,
            model_factory=model_factory(
                model_credentials, lambda: state.settings()["config"]["mode"]
            ),
        )
        client_routes = ClientRoutes(state, runtime, FeishuIngress(state, inbox, runtime))

    tokens = ScopedTokenStore()
    token_path = profile_dir / "owner_cli.token"
    owner_token = tokens.issue(profile_id=profile_id, principal_id="pri_test1", scope="owner_cli")
    if token_path.is_file() and not token_path.is_symlink():
        saved = token_path.read_text(encoding="utf-8").strip()
        if saved:
            from openbot.adapters.local_api.server import TokenGrant

            tokens._tokens[saved] = TokenGrant(saved, profile_id, "pri_test1", "owner_cli")
            owner_token = saved

    fd_tok = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd_tok, (owner_token + "\n").encode("utf-8"))
    finally:
        os.close(fd_tok)

    if client_routes is not None and hasattr(os, "O_NOFOLLOW"):
        gateway_token = tokens.issue(
            profile_id=profile_id, principal_id=context.principal_id, scope="feishu_gateway"
        )
        gateway_path = profile_dir / "feishu_gateway.token"
        fd_gateway = os.open(
            gateway_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600
        )
        try:
            os.fchmod(fd_gateway, 0o600)
            os.write(fd_gateway, (gateway_token + "\n").encode())
        finally:
            os.close(fd_gateway)

    api = LocalControlApiServer(
        profile_id=profile_id,
        default_context=context,
        writer=writer,
        registry=registry,
        tokens=tokens,
        inbox=inbox,
        tasks=tasks,
        operations=ops,
        approvals=approvals,
        recovery=recovery,
        cancellation=cancellation,
        artifacts=artifacts,
        challenges=challenges,
        dispatcher=dispatcher,
        client_routes=client_routes,
    )
    daemon = LoopbackHttpDaemon(api, host="127.0.0.1", port=port)
    session_meta = {
        "profile_id": profile_id,
        "workspace_id": workspace_id,
        "host": daemon.address,
        "pid": os.getpid(),
        "runtime_epoch": runtime_epoch,
    }
    session_path = profile_dir / "daemon_session.json"
    fd_ses = os.open(session_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd_ses, (json.dumps(session_meta, sort_keys=True) + "\n").encode("utf-8"))
    finally:
        os.close(fd_ses)

    def _handle_stop(signum: int, _frame: object) -> None:
        del signum
        threading.Thread(target=daemon.close, daemon=True).start()

    import threading

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    print(json.dumps(session_meta, sort_keys=True), flush=True)
    try:
        daemon.serve_forever()
    finally:
        if runtime is not None:
            runtime.close()
        writer.close()
        sup_lock.release()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    eff_argv = list(sys.argv[1:] if argv is None else argv)
    for arg in eff_argv:
        flag_name = arg.split("=", 1)[0]
        if flag_name in _FORBIDDEN_FLAGS:
            code, out = run_cli_command(eff_argv)
            print(out)
            return code
    parser = build_cli_parser()
    args = parser.parse_args(eff_argv)
    if args.group is None:
        parser.print_help()
        return 2
    if args.group == "daemon" and args.action == "serve":
        try:
            from openbot.application.runtime_factory import read_model_credentials

            if args.model_credentials and args.workspace_root is None:
                raise PermissionError("MODEL_CREDENTIALS_REQUIRE_CLIENT_WORKSPACE")
            credentials = read_model_credentials() if args.model_credentials else None
            return _serve_daemon_process(
                profile_dir=args.profile_dir,
                profile_id=args.profile_id,
                workspace_id=args.workspace_id,
                port=args.port,
                runtime_epoch=args.epoch,
                workspace_root=args.workspace_root,
                model_credentials=credentials,
            )
        except PermissionError as exc:
            print(json.dumps({"code": "DAEMON_LOCK_OR_PERMISSION_ERROR", "message": str(exc)}))
            return 3
    code, out = run_cli_command(eff_argv)
    if out:
        print(out)
    return code
