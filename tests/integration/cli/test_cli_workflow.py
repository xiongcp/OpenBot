import json
import os
import subprocess
import sys
from pathlib import Path

from openbot.adapters.local_api.server import ApiRequest, ApiResponse
from openbot.cli import (
    CliApiSession,
    discover_cli_session,
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


def test_installed_openbot_console_script_and_loopback_daemon_subprocess_e2e(
    tmp_path: Path,
) -> None:
    openbot_bin = Path(sys.executable).with_name("openbot")
    assert openbot_bin.is_file()

    # 1. Subprocess --help works on all product command groups
    for grp in ("task", "approval", "operation", "daemon"):
        res_help = subprocess.run(
            [str(openbot_bin), grp, "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert res_help.returncode == 0, res_help.stderr

    # 2. Without running daemon, --require-daemon returns exit code 2
    prof_dir = tmp_path / "prof_e2e"
    prof_dir.mkdir(parents=True, exist_ok=True)
    res_h_down = subprocess.run(
        [str(openbot_bin), "health", "--profile-dir", str(prof_dir), "--require-daemon"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert res_h_down.returncode == 2
    assert json.loads(res_h_down.stdout)["daemon_running"] is False

    # 3. Start real daemon subprocess listening on 127.0.0.1 ephemeral port
    daemon_proc = subprocess.Popen(
        [
            str(openbot_bin),
            "daemon",
            "serve",
            "--profile-dir",
            str(prof_dir),
            "--profile-id",
            "pro_test1",
            "--workspace-id",
            "wsp_test1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert daemon_proc.stdout is not None
        ready_line = daemon_proc.stdout.readline().strip()
        assert ready_line, daemon_proc.stderr.read() if daemon_proc.stderr else ""
        meta = json.loads(ready_line)
        assert meta["host"].startswith("127.0.0.1:")
        assert meta["profile_id"] == "pro_test1"

        # Second daemon on same profile is rejected by SingleInstanceSupervisorLock
        dup_daemon = subprocess.run(
            [
                str(openbot_bin),
                "daemon",
                "serve",
                "--profile-dir",
                str(prof_dir),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert dup_daemon.returncode == 3
        assert "PROFILE_LOCK_HELD" in dup_daemon.stdout

        # Health check with active daemon returns daemon_running=True
        res_h_up = subprocess.run(
            [str(openbot_bin), "health", "--profile-dir", str(prof_dir), "--require-daemon"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert res_h_up.returncode == 0
        h_doc = json.loads(res_h_up.stdout)
        assert h_doc["daemon_running"] is True
        assert h_doc["profile_id"] == "pro_test1"

        # Passing token on CLI argv is forbidden
        res_tok_flag = subprocess.run(
            [
                str(openbot_bin),
                "task",
                "show",
                "--task-id",
                "tsk_1",
                "--token=secret",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert res_tok_flag.returncode == 6
        assert "FORBIDDEN_CLI_FLAG" in res_tok_flag.stdout

        # Create task via subprocess console script (and verify idempotency)
        cmd_create = [
            str(openbot_bin),
            "task",
            "create",
            "--profile-dir",
            str(prof_dir),
            "--workspace",
            "wsp_test1",
            "--goal",
            "subprocess-cli-e2e",
            "--idempotency-key",
            "sub-idem-1",
            "--json",
        ]
        c1 = subprocess.run(cmd_create, capture_output=True, text=True, timeout=10, check=False)
        c2 = subprocess.run(cmd_create, capture_output=True, text=True, timeout=10, check=False)
        assert c1.returncode == 0, c1.stderr
        assert c2.returncode == 0, c2.stderr
        task_id = json.loads(c1.stdout)["task_id"]
        assert task_id == json.loads(c2.stdout)["task_id"]

        # Drive operation proposal, approval preview/decide, claim/dispatch, epoch recovery,
        # and reconcile over the real loopback HTTP session
        ses = discover_cli_session(prof_dir)
        assert ses is not None
        assert (
            ses.call(
                "POST",
                f"/v1/tasks/{task_id}/transition",
                body={"expected_version": 0, "target_state": "RUNNING"},
            ).status_code
            == 200
        )
        prop_resp = ses.call(
            "POST",
            "/v1/operations/propose",
            body={"task_id": task_id, "tool_id": "gui.click", "args": {"arg": "ok"}},
        )
        assert prop_resp.status_code == 201
        prop_doc = prop_resp.json()
        op_id, apr_id = str(prop_doc["operation_id"]), str(prop_doc["approval_id"])

        res_prev = subprocess.run(
            [
                str(openbot_bin),
                "approval",
                "preview",
                "--profile-dir",
                str(prof_dir),
                "--approval-id",
                apr_id,
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert res_prev.returncode == 0
        assert json.loads(res_prev.stdout)["approval_id"] == apr_id

        res_dec = subprocess.run(
            [
                str(openbot_bin),
                "approval",
                "decide",
                "--profile-dir",
                str(prof_dir),
                "--approval-id",
                apr_id,
                "--expected-version",
                "1",
                "--binding-hash",
                str(prop_doc["binding_hash"]),
                "--decision",
                "APPROVE",
                "--idempotency-key",
                "sub-apr-1",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert res_dec.returncode == 0
        assert json.loads(res_dec.stdout)["operation_state"] == "READY"

        # Advance task, claim, dispatch, recover epoch -> UNKNOWN -> reconcile via CLI subprocess
        assert (
            ses.call(
                "POST",
                f"/v1/tasks/{task_id}/transition",
                body={"expected_version": 3, "target_state": "RUNNING"},
            ).status_code
            == 200
        )
        claim_doc = ses.call("POST", f"/v1/operations/{op_id}/claim", body={}).json()
        assert (
            ses.call(
                "POST",
                f"/v1/operations/{op_id}/dispatch",
                body={"attempt_id": claim_doc["attempt_id"]},
            ).status_code
            == 200
        )
        assert (
            ses.call(
                "POST",
                "/v1/runtime/recover-epoch",
                body={"new_epoch": "ep_2", "old_epoch_isolated": True},
            ).status_code
            == 200
        )

        res_rec = subprocess.run(
            [
                str(openbot_bin),
                "operation",
                "reconcile",
                "--profile-dir",
                str(prof_dir),
                "--operation-id",
                op_id,
                "--expected-version",
                "4",
                "--outcome",
                "CONFIRMED_SUCCEEDED",
                "--evidence-content",
                "subprocess receipt",
                "--idempotency-key",
                "sub-rec-1",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert res_rec.returncode == 0
        assert json.loads(res_rec.stdout)["operation_state"] == "SUCCEEDED"

        # Insecure token permissions are rejected on POSIX
        if sys.platform != "win32":
            os.chmod(prof_dir / "owner_cli.token", 0o644)
            res_insec = subprocess.run(
                [
                    str(openbot_bin),
                    "task",
                    "show",
                    "--profile-dir",
                    str(prof_dir),
                    "--task-id",
                    task_id,
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            assert res_insec.returncode == 3
            assert "INSECURE_TOKEN_FILE_PERMISSIONS" in res_insec.stdout
            os.chmod(prof_dir / "owner_cli.token", 0o600)
    finally:
        daemon_proc.terminate()
        daemon_proc.wait(timeout=5)

    # 4. After daemon stops, CLI reports DAEMON_UNAVAILABLE (exit code 2)
    res_after_stop = subprocess.run(
        [
            str(openbot_bin),
            "task",
            "show",
            "--profile-dir",
            str(prof_dir),
            "--task-id",
            task_id,
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert res_after_stop.returncode == 2
    assert json.loads(res_after_stop.stdout)["code"] == "DAEMON_UNAVAILABLE"
