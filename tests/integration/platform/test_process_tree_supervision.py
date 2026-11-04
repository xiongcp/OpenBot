import subprocess
import sys
import time

import pytest
from openbot.tools.executors.supervision_port import (
    PLATFORM_CAPABILITY_BOUNDARIES,
    ProcessSupervisorService,
    validate_windows_job_spawn_order,
)


def test_platform_boundaries_windows_job_order_and_ui_close_preserves_daemon():
    # 1. Platform capability table explicitly documents cooperative vs forced cleanup limits
    darwin_cap = PLATFORM_CAPABILITY_BOUNDARIES["Darwin"]
    assert darwin_cap.cooperative_eof_or_drop_is_100_percent is False
    assert "setsid" in darwin_cap.escape_limitation_note
    assert "command-group" in darwin_cap.rejected_crates

    # 2. Windows spawn order: CREATE_SUSPENDED -> AssignProcessToJobObject -> ResumeThread;
    # if job assignment fails, process must be terminated before resume!
    order_ok = validate_windows_job_spawn_order(job_assigned=True)
    assert order_ok == (
        "CreateProcessW(CREATE_SUSPENDED)",
        "AssignProcessToJobObject(KILL_ON_JOB_CLOSE)",
        "ResumeThread",
    )
    order_fail = validate_windows_job_spawn_order(job_assigned=False)
    assert "TerminateProcess_before_ResumeThread" in order_fail
    assert "ResumeThread" not in order_fail

    # 3. Closing UI window never stops the daemon or active workers
    sup = ProcessSupervisorService(runtime_epoch="ep_1")
    ui_event = sup.on_ui_window_closed("ui_win_main")
    assert ui_event["daemon_running"] is True
    assert ui_event["workers_stopped"] == 0


def test_real_posix_process_group_reclaim_pid_reuse_guard_and_unconfirmed_escape_quarantine(
    tmp_path,
):
    sup = ProcessSupervisorService(runtime_epoch="ep_1")

    # 1. Spawn a real process group that forks a child process and writes child PID to a file
    child_pid_file = tmp_path / "child.pid"
    script = (
        "import os, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        f"open({str(child_pid_file)!r}, 'w').write(str(child.pid))\n"
        "time.sleep(30)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        start_new_session=True,
    )
    try:
        for _ in range(50):
            if child_pid_file.exists() and child_pid_file.read_text().strip():
                break
            time.sleep(0.05)
        grandchild_pid = int(child_pid_file.read_text().strip())

        reg = sup.register_worker(
            worker_id="wrk_real_1",
            operation_id="op_1",
            attempt_id="att_1",
            pid=proc.pid,
            pgid=proc.pid,
            process_start_token="tok_real_1",
            known_descendant_pids=(grandchild_pid,),
        )
        assert reg.worker_id == "wrk_real_1"

        # Reclaim kills both the leader and the grandchild in the process group
        report = sup.reclaim_worker("wrk_real_1", current_start_token="tok_real_1", grace_ms=100)
        proc.wait(timeout=5)
        assert report.old_domain_isolated is True
        assert report.quarantine_required is False
        assert report.residual_pids == ()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)

    # 2. PID reuse protection: if current_start_token differs from registered token, refuses to kill
    sup.register_worker(
        worker_id="wrk_reused_pid",
        operation_id="op_2",
        attempt_id="att_2",
        pid=999991,
        pgid=999991,
        process_start_token="tok_original",
    )
    with pytest.raises(PermissionError, match="PID reuse"):
        sup.reclaim_worker("wrk_reused_pid", current_start_token="tok_different_process")

    # 3. Unregistered worker ID is refused
    with pytest.raises(PermissionError, match="Unregistered"):
        sup.reclaim_worker("wrk_unknown", current_start_token="tok_any")

    # 4. If an escaped descendant or unstopped container remains, old_domain_isolated=False
    # and quarantine_required=True (blocks new dispatch!)
    sup.register_worker(
        worker_id="wrk_escaped",
        operation_id="op_3",
        attempt_id="att_3",
        pid=999992,
        pgid=999992,
        process_start_token="tok_esc",
        container_id="cnt_unstopped",
    )
    esc_report = sup.reclaim_worker(
        "wrk_escaped",
        current_start_token="tok_esc",
        simulated_residual_pids=(888881,),
        container_reclaimed=False,
    )
    assert esc_report.old_domain_isolated is False
    assert esc_report.quarantine_required is True
    assert esc_report.new_dispatch_allowed is False
