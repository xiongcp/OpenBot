import json

from openbot.adapters.local_api.server import ApiRequest, ApiResponse
from openbot.cli import (
    CliApiSession,
    run_cli_command,
    sanitize_terminal_text,
)

from tests.contracts.local_api.test_local_api_contracts import local_api_env

__all__ = ["local_api_env"]


class InProcessApiTransport:
    def __init__(
        self, server, *, simulate_timeout: bool = False, daemon_down: bool = False
    ) -> None:
        self._server = server
        self.simulate_timeout = simulate_timeout
        self.daemon_down = daemon_down

    def request(self, req: ApiRequest) -> ApiResponse:
        if self.daemon_down:
            raise ConnectionRefusedError("Daemon is not running")
        if self.simulate_timeout:
            raise TimeoutError("Client timed out waiting for response")
        return self._server.handle(req)


def test_cli_full_task_approval_cancel_reconcile_resume_workflow_without_sqlite_bypass(
    local_api_env,
):
    api, context, writer, tasks, ops, dispatcher, recovery, owner_token, gw_token, _ = local_api_env
    from openbot.application.resources import ResourceRequest

    session = CliApiSession(
        profile_id="pro_test1",
        token=owner_token,
        transport=InProcessApiTransport(api),
    )

    # 1. Create task via CLI (--json)
    code, out = run_cli_command(
        [
            "task",
            "create",
            "--workspace",
            "wsp_test1",
            "--goal",
            "cli-e2e",
            "--idempotency-key",
            "cli-k1",
            "--json",
        ],
        session=session,
    )
    assert code == 0
    task_id = json.loads(out)["task_id"]

    # Advance task to RUNNING and propose operation
    writer.submit(tasks.command(context, task_id, 0, "RUNNING", "cli-run-1", 999999999999)).result(
        5
    )
    proposed = json.loads(
        ops.propose(
            context,
            task_id,
            "gui.click",
            '{"arg":"btn"}',
            {"workspace_generation": 1, "files": []},
            "WORKSPACE",
            {"kind": "LOCAL", "resource_ref": context.workspace_id},
            "cli-prop-1",
            999999999999,
        )
    )
    op_id, apr_id = proposed["operation_id"], proposed["approval_id"]

    # 2. Preview approval and submit APPROVE decision via CLI
    code_prev, out_prev = run_cli_command(
        ["approval", "preview", "--approval-id", apr_id, "--json"],
        session=session,
    )
    assert code_prev == 0
    prev_doc = json.loads(out_prev)
    assert prev_doc["approval_id"] == apr_id

    # Gateway token is rejected from CLI approval decide because challenge is owner-only
    gw_session = CliApiSession(
        profile_id="pro_test1",
        token=gw_token,
        transport=InProcessApiTransport(api),
    )
    code_gw, _ = run_cli_command(
        [
            "approval",
            "decide",
            "--approval-id",
            apr_id,
            "--expected-version",
            "1",
            "--binding-hash",
            proposed["binding_hash"],
            "--decision",
            "APPROVE",
            "--json",
        ],
        session=gw_session,
    )
    assert code_gw == 3

    code_dec, out_dec = run_cli_command(
        [
            "approval",
            "decide",
            "--approval-id",
            apr_id,
            "--expected-version",
            "1",
            "--binding-hash",
            proposed["binding_hash"],
            "--decision",
            "APPROVE",
            "--idempotency-key",
            "cli-apr-k1",
            "--json",
        ],
        session=session,
    )
    assert code_dec == 0
    assert json.loads(out_dec)["operation_state"] == "READY"

    # 3. Claim, dispatch, crash -> UNKNOWN -> CLI reconcile with inline evidence -> CLI resume
    writer.submit(tasks.command(context, task_id, 3, "RUNNING", "cli-run-2", 999999999999)).result(
        5
    )
    claimed = json.loads(
        writer.submit(
            dispatcher.claim(
                context,
                op_id,
                "ep_1",
                "exec_1",
                [ResourceRequest("WORKSPACE", "wsp_test1", expected_generation=1)],
                30_000,
                "cli-claim-1",
                999999999999,
            )
        ).result(5)
    )
    writer.submit(
        dispatcher.begin_dispatch(
            context, op_id, claimed["attempt_id"], "ep_1", "exec_1", "cli-disp-1", 999999999999
        )
    ).result(5)
    writer.submit(
        recovery.recover_epoch(
            context,
            "ep_2",
            "boot_2",
            "sup_2",
            old_epoch_isolated=True,
            request_id="cli-rec-ep2",
            deadline_monotonic_ms=999999999999,
        )
    ).result(5)

    code_rec, out_rec = run_cli_command(
        [
            "operation",
            "reconcile",
            "--operation-id",
            op_id,
            "--expected-version",
            "4",
            "--outcome",
            "CONFIRMED_SUCCEEDED",
            "--evidence-content",
            "cli verified receipt",
            "--idempotency-key",
            "cli-rec-k1",
            "--json",
        ],
        session=session,
    )
    assert code_rec == 0
    assert json.loads(out_rec)["operation_state"] == "SUCCEEDED"

    # Resume task from RECONCILING -> QUEUED via CLI, then cancel via CLI
    code_show, out_show = run_cli_command(
        ["task", "show", "--task-id", task_id, "--json"], session=session
    )
    assert code_show == 0
    t_ver = json.loads(out_show)["version"]

    code_res, out_res = run_cli_command(
        [
            "task",
            "resume",
            "--task-id",
            task_id,
            "--expected-version",
            str(t_ver),
            "--idempotency-key",
            "cli-res-k1",
            "--json",
        ],
        session=session,
    )
    assert code_res == 0
    assert json.loads(out_res)["state"] == "QUEUED"

    code_can, out_can = run_cli_command(
        [
            "task",
            "cancel",
            "--task-id",
            task_id,
            "--expected-version",
            str(t_ver + 1),
            "--idempotency-key",
            "cli-can-k1",
            "--json",
        ],
        session=session,
    )
    assert code_can == 0
    assert json.loads(out_can)["state"] == "CANCELLED"


def test_cli_rejects_forbidden_flags_escapes_ansi_and_never_claims_unexecuted_on_timeout(
    local_api_env,
):
    api, _, _, _, _, _, _, owner_token, _, _ = local_api_env
    session = CliApiSession(
        profile_id="pro_test1",
        token=owner_token,
        transport=InProcessApiTransport(api),
    )

    # 1. Forbidden bypass flags (--ignore-and-rerun, --force-success, --revive-consumed)
    for bad_flag in ("--ignore-and-rerun", "--force-success", "--revive-consumed"):
        code_bad, out_bad = run_cli_command(
            ["operation", "reconcile", "--operation-id", "op_1", bad_flag],
            session=session,
        )
        assert code_bad == 6
        assert "FORBIDDEN_CLI_FLAG" in out_bad

    # 2. ANSI / terminal control injection in untrusted text is stripped in human view
    raw_malicious = "Goal \x1b[31m\x1b]0;FAKE APPROVAL PROMPT\x07[bold]click approve[/bold]"
    sanitized = sanitize_terminal_text(raw_malicious)
    assert "\x1b" not in sanitized
    assert "\x07" not in sanitized
    assert "[bold]" not in sanitized

    # 3. Daemon down returns exit code 2; client wait timeout returns exit code 5 and
    # NEVER claims the action was not executed!
    down_session = CliApiSession(
        profile_id="pro_test1",
        token=owner_token,
        transport=InProcessApiTransport(api, daemon_down=True),
    )
    c_down, out_down = run_cli_command(
        ["task", "show", "--task-id", "tsk_1", "--json"], session=down_session
    )
    assert c_down == 2
    assert json.loads(out_down)["code"] == "DAEMON_UNAVAILABLE"

    timeout_session = CliApiSession(
        profile_id="pro_test1",
        token=owner_token,
        transport=InProcessApiTransport(api, simulate_timeout=True),
    )
    c_to, out_to = run_cli_command(
        ["task", "show", "--task-id", "tsk_1", "--json"], session=timeout_session
    )
    assert c_to == 5
    to_doc = json.loads(out_to)
    assert to_doc["action_guaranteed_not_executed"] is False
    assert to_doc["requery_required"] is True
