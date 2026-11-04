import pytest
from openbot.observability.redaction import RedactionPipeline
from openbot.tools.executors.process import (
    ControlledProcessExecutor,
    ProcessExecutionPlan,
    ProcessResourceLimits,
    RawWorkerOutcome,
    classify_command_security,
)


class FakeIsolatedWorker:
    def __init__(self, outcome: RawWorkerOutcome) -> None:
        self.outcome = outcome
        self.executed_plans: list[ProcessExecutionPlan] = []

    def run_isolated(self, plan: ProcessExecutionPlan) -> RawWorkerOutcome:
        self.executed_plans.append(plan)
        return self.outcome


def _valid_plan(**overrides: object) -> ProcessExecutionPlan:
    defaults: dict[str, object] = {
        "operation_id": "op_proc_1",
        "attempt_id": "att_proc_1",
        "dispatch_id": "dsp_proc_1",
        "action_label": "test.run",
        "executable": "/usr/bin/python3",
        "argv": ("/usr/bin/python3", "-m", "pytest", "-q"),
        "workspace_snapshot_digest": "a" * 64,
        "execution_backend": "ISOLATED_CONTAINER",
        "image_digest": "sha256:" + ("b" * 64),
        "network_mode": "NONE",
        "isolated_home": "/workspace/.isolated_home",
        "isolated_tmpdir": "/workspace/.isolated_tmp",
        "env": {"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"},
        "limits": ProcessResourceLimits(max_output_bytes=64),
    }
    defaults.update(overrides)
    return ProcessExecutionPlan(**defaults)  # type: ignore[arg-type]


def test_shell_wrappers_read_only_bypass_and_unqualified_backend_are_rejected():
    # 1. pytest, python, npm, git, rg --pre are ALWAYS classified as CODE_EXECUTION
    # even if action_label pretends to be 'search', 'snapshot', or 'read_only_lint'
    for label, argv in (
        ("read_only_test", ("pytest", "-q")),
        ("lint", ("python3", "-m", "ruff")),
        ("snapshot", ("git", "worktree", "add")),
        ("search", ("rg", "--pre=/bin/sh", "pattern")),
        ("build", ("npm", "test")),
    ):
        assert classify_command_security(label, argv) == "CODE_EXECUTION"

    # 2. Raw shell strings or sh -c / bash -c wrappers are rejected
    for shell_argv in (
        ("sh", "-c", "echo hi"),
        ("/bin/bash", "-c", "ls"),
        ("cmd.exe", "/c", "dir"),
    ):
        with pytest.raises(PermissionError, match="shell"):
            _valid_plan(executable=shell_argv[0], argv=shell_argv).validate()

    # 3. Host backend or unqualified isolation backend refuses execution (no host fallback!)
    worker = FakeIsolatedWorker(
        RawWorkerOutcome(
            client_pid=101,
            container_id="cnt_1",
            exit_code=0,
            signal=None,
            timed_out=False,
            cancelled=False,
            container_confirmed_stopped=True,
            stdout_chunks=(b"ok",),
            stderr_chunks=(),
        )
    )
    unqualified = ControlledProcessExecutor(
        worker=worker,
        isolation_backend_qualified=False,
        redactor=RedactionPipeline(),
    )
    with pytest.raises(PermissionError, match="not qualified"):
        unqualified.execute(_valid_plan())
    assert worker.executed_plans == []


def test_output_flood_redaction_and_exit_signal_timeout_cancel_unknown_mapping():
    canary = "sk_proc_canary_998877665544"
    redactor = RedactionPipeline(registered_secrets=(canary,))

    # 1. Output flood is capped at max_output_bytes (64) and redacted before return
    flood_worker = FakeIsolatedWorker(
        RawWorkerOutcome(
            client_pid=201,
            container_id="cnt_flood",
            exit_code=0,
            signal=None,
            timed_out=False,
            cancelled=False,
            container_confirmed_stopped=True,
            stdout_chunks=(f"leak={canary} ".encode(), b"X" * 200),
            stderr_chunks=(),
        )
    )
    exec_ok = ControlledProcessExecutor(
        worker=flood_worker, isolation_backend_qualified=True, redactor=redactor
    )
    res_ok = exec_ok.execute(_valid_plan())
    assert res_ok.status == "SUCCEEDED"
    assert canary not in res_ok.stdout
    assert res_ok.output_truncated is True
    assert len(res_ok.stdout.encode("utf-8")) <= 64

    # 2. Client exited or timed out while container is NOT confirmed stopped -> UNKNOWN!
    unconfirmed_worker = FakeIsolatedWorker(
        RawWorkerOutcome(
            client_pid=202,
            container_id="cnt_still_running",
            exit_code=None,
            signal=None,
            timed_out=True,
            cancelled=False,
            container_confirmed_stopped=False,
            stdout_chunks=(b"partial",),
            stderr_chunks=(),
        )
    )
    res_unk = ControlledProcessExecutor(
        worker=unconfirmed_worker, isolation_backend_qualified=True, redactor=redactor
    ).execute(_valid_plan())
    assert res_unk.status == "UNKNOWN"
    assert res_unk.container_id == "cnt_still_running"
    assert res_unk.container_confirmed_stopped is False

    # 3. Signal kill (e.g. SIGKILL=9) with confirmed container stop -> FAILED with signal recorded
    sig_worker = FakeIsolatedWorker(
        RawWorkerOutcome(
            client_pid=203,
            container_id="cnt_killed",
            exit_code=137,
            signal="SIGKILL",
            timed_out=False,
            cancelled=True,
            container_confirmed_stopped=True,
            stdout_chunks=(),
            stderr_chunks=(b"OOMKilled",),
        )
    )
    res_sig = ControlledProcessExecutor(
        worker=sig_worker, isolation_backend_qualified=True, redactor=redactor
    ).execute(_valid_plan())
    assert res_sig.status == "FAILED"
    assert res_sig.signal == "SIGKILL"
