import json
import os
import sys
from pathlib import Path

import pytest
from openbot.cli import run_cli_command
from openbot.domain.clock import ClockSnapshot, SleepWakeDetector
from openbot.observability.diagnostics import (
    ObservabilityHub,
    RotatingRedactedLogWriter,
    TraceCorrelationContext,
)
from openbot.observability.redaction import RedactionPipeline
from openbot.providers.circuit_breaker import AdaptiveCircuitBreaker, StepCheckpointResumer
from openbot.storage.maintenance import DiskWaterlineGuard
from openbot.tools.executors.supervision_port import SupervisorCrashStormWatchdog


def test_v1_068_069_crash_storm_watchdog_and_sleep_wake_detector() -> None:
    # 1. Crash storm watchdog trips into SAFE_MAINTENANCE_MODE on 4th crash within 5 min
    wd = SupervisorCrashStormWatchdog(window_ms=300_000, max_crashes=3, base_backoff_ms=1000)
    s1 = wd.record_crash(now_ms=10_000)
    s2 = wd.record_crash(now_ms=20_000)
    s3 = wd.record_crash(now_ms=30_000)
    assert s1.auto_restart_allowed is True and s1.next_backoff_ms == 1000
    assert s2.auto_restart_allowed is True and s2.next_backoff_ms == 2000
    assert s3.auto_restart_allowed is True and s3.next_backoff_ms == 4000
    s4 = wd.record_crash(now_ms=40_000)
    assert s4.mode == "SAFE_MAINTENANCE_MODE"
    assert s4.auto_restart_allowed is False

    # 2. Sleep/Wake detector identifies 30-min lid sleep jump and reconnects surfaces in <3s
    reconnected: list[str] = []
    det = SleepWakeDetector(ClockSnapshot(100_000, 10_000, "boot_1"))
    det.register_reconnect_hook("feishu_ws", lambda: reconnected.append("feishu_ws"))
    det.register_reconnect_hook("model_pool", lambda: reconnected.append("model_pool"))
    rep = det.observe_and_heal(ClockSnapshot(1_900_000, 12_000, "boot_1"))
    assert rep.sleep_detected is True
    assert rep.estimated_sleep_ms >= 1_790_000
    assert rep.reconnected_surfaces == ("feishu_ws", "model_pool")
    assert rep.recovery_elapsed_ms < 3000


def test_v1_070_071_disk_waterline_ring_buffer_and_rotating_redacted_logs(
    tmp_path: Path,
) -> None:
    # 1. DiskWaterlineGuard blocks when free space < 512MB
    guard = DiskWaterlineGuard(tmp_path)
    assert guard.check_writable(simulated_free_bytes=1024 * 1024 * 1024)["writable"] is True
    with pytest.raises(PermissionError, match="DISK_LOW_WATERLINE_TRIPPED"):
        guard.check_writable(simulated_free_bytes=100 * 1024 * 1024)

    # 2. ObservabilityHub ring buffer caps at maxlen and strips secrets
    canary = "sk-secret-diag-canary-999"
    redactor = RedactionPipeline(registered_secrets=(canary,))
    hub = ObservabilityHub(redactor=redactor, max_entries=5)
    ctx = TraceCorrelationContext("tsk_1", "op_1", "att_1")
    for i in range(10):
        hub.record_log(
            context=ctx,
            event=f"EV_{i}",
            message=f"step {i} with {canary}",
            hidden_reasoning="secret chain of thought",
        )
    bundle = hub.export_explicit_diagnostic_bundle()
    assert len(bundle["logs"]) == 5
    assert bundle["ring_buffer_maxlen"] == 5
    assert canary not in json.dumps(bundle)
    assert "secret chain of thought" not in json.dumps(bundle)
    prev = hub.preview_diagnostic_bundle()
    assert prev["redaction_hits"] == 10
    assert prev["remote_upload_enabled"] is False

    # 3. RotatingRedactedLogWriter rotates and never writes secret
    log_file = tmp_path / "openbot.log"
    rot = RotatingRedactedLogWriter(log_file, redactor=redactor, max_bytes=120, backup_count=3)
    for i in range(8):
        rot.write_line(f"line-{i}-secret={canary}-padding-xxxx")
    assert log_file.is_file()
    assert (tmp_path / "openbot.log.1").is_file()
    for p in tmp_path.glob("openbot.log*"):
        assert canary not in p.read_text(encoding="utf-8")


def test_v1_072_074_circuit_breaker_step_resume_and_doctor_fix_safe(tmp_path: Path) -> None:
    # 1. Three-state circuit breaker + Retry-After
    cb = AdaptiveCircuitBreaker("openai", failure_threshold=2, default_cooldown_ms=5000)
    assert cb.allow_request(now_ms=1000).state == "CLOSED"
    cb.record_failure(now_ms=1000)
    snap_open = cb.record_failure(now_ms=1100, retry_after_seconds=10)
    assert snap_open.state == "OPEN" and snap_open.reopen_not_before_ms == 11_100
    with pytest.raises(PermissionError, match="CIRCUIT_BREAKER_OPEN"):
        cb.allow_request(now_ms=5000)
    # Cooldown elapsed -> HALF_OPEN -> success -> CLOSED
    assert cb.allow_request(now_ms=11_100).state == "HALF_OPEN"
    assert cb.record_success().state == "CLOSED"

    # 2. StepCheckpointResumer resumes at step N without re-running 0..N-1
    resumer = StepCheckpointResumer()
    resumer.record_completed_step("tsk_1", step_index=0, receipt={"ok": True})
    resumer.record_completed_step("tsk_1", step_index=1, receipt={"ok": True})
    assert resumer.next_resume_step("tsk_1") == 2

    # 3. openbot doctor --fix-safe repairs insecure token permissions and stale PID
    prof = tmp_path / "prof_doc"
    prof.mkdir(mode=0o700)
    tok = prof / "owner_cli.token"
    tok.write_text("obt_owner_cli_123456", encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(tok, 0o644)
    (prof / "stale_daemon.pid").write_text("999999", encoding="utf-8")

    code_fail, out_fail = run_cli_command(["doctor", "--profile-dir", str(prof), "--json"])
    if sys.platform != "win32":
        assert code_fail == 1
    code_fix, out_fix = run_cli_command(
        ["doctor", "--profile-dir", str(prof), "--fix-safe", "--json"]
    )
    assert code_fix == 0
    doc_fix = json.loads(out_fix)
    assert doc_fix["status"] == "PASS"
    assert doc_fix["fix_safe_applied"] is True
    assert doc_fix["probe_count"] == 10
    if sys.platform != "win32":
        assert (os.lstat(tok).st_mode & 0o077) == 0
    assert not (prof / "stale_daemon.pid").exists()
