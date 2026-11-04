"""Authenticated loopback CLI for OpenBot tasks, approvals, and reconciliation (OB-028)."""

import argparse
import json
import re
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from openbot import __version__
from openbot.adapters.local_api.server import ApiRequest, ApiResponse

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
    if argv[0] == "health" and session is None:
        return 0, json.dumps(
            {
                "version": __version__,
                "daemon_running": False,
                "isolation": "CAPABILITY_UNAVAILABLE",
                "stage": "M0",
            }
        )

    if session is None:
        return 2, _format_output(
            {"code": "DAEMON_UNAVAILABLE", "message": "No active CLI API session configured."},
            as_json=as_json,
        )

    try:
        return _dispatch_authenticated(argv, session=session, as_json=as_json)
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
    parser = argparse.ArgumentParser(prog="openbot", add_help=False)
    sub = parser.add_subparsers(dest="group")

    # task group
    p_task = sub.add_parser("task", add_help=False)
    task_sub = p_task.add_subparsers(dest="action")

    p_tc = task_sub.add_parser("create", add_help=False)
    p_tc.add_argument("--workspace", required=True)
    p_tc.add_argument("--goal", required=True)
    p_tc.add_argument("--idempotency-key", default=None)
    p_tc.add_argument("--json", action="store_true")

    p_ts = task_sub.add_parser("show", add_help=False)
    p_ts.add_argument("--task-id", required=True)
    p_ts.add_argument("--json", action="store_true")

    p_tcan = task_sub.add_parser("cancel", add_help=False)
    p_tcan.add_argument("--task-id", required=True)
    p_tcan.add_argument("--expected-version", type=int, required=True)
    p_tcan.add_argument("--idempotency-key", default=None)
    p_tcan.add_argument("--json", action="store_true")

    p_tres = task_sub.add_parser("resume", add_help=False)
    p_tres.add_argument("--task-id", required=True)
    p_tres.add_argument("--expected-version", type=int, required=True)
    p_tres.add_argument("--idempotency-key", default=None)
    p_tres.add_argument("--json", action="store_true")

    # approval group
    p_apr = sub.add_parser("approval", add_help=False)
    apr_sub = p_apr.add_subparsers(dest="action")

    p_aprev = apr_sub.add_parser("preview", add_help=False)
    p_aprev.add_argument("--approval-id", required=True)
    p_aprev.add_argument("--json", action="store_true")

    p_adec = apr_sub.add_parser("decide", add_help=False)
    p_adec.add_argument("--approval-id", required=True)
    p_adec.add_argument("--expected-version", type=int, required=True)
    p_adec.add_argument("--binding-hash", required=True)
    p_adec.add_argument("--decision", choices=("APPROVE", "DENY"), required=True)
    p_adec.add_argument("--reason", default="cli_owner_decision")
    p_adec.add_argument("--idempotency-key", default=None)
    p_adec.add_argument("--json", action="store_true")

    # operation group
    p_op = sub.add_parser("operation", add_help=False)
    op_sub = p_op.add_subparsers(dest="action")

    p_orec = op_sub.add_parser("reconcile", add_help=False)
    p_orec.add_argument("--operation-id", required=True)
    p_orec.add_argument("--expected-version", type=int, required=True)
    p_orec.add_argument(
        "--outcome",
        choices=("CONFIRMED_SUCCEEDED", "CONFIRMED_NOT_EXECUTED"),
        required=True,
    )
    p_orec.add_argument("--evidence-content", required=True)
    p_orec.add_argument("--idempotency-key", default=None)
    p_orec.add_argument("--json", action="store_true")

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


def main(argv: Sequence[str] | None = None) -> int:
    if argv is not None and len(argv) == 1 and argv[0] in {"version", "health"}:
        code, out = run_cli_command(argv)
        print(out)
        return code
    parser = argparse.ArgumentParser(prog="openbot")
    parser.add_argument("command", choices=("version", "health"))
    args = parser.parse_args(argv)
    code, out = run_cli_command([args.command])
    print(out)
    return code
