from pathlib import Path

from openbot.application.chaos_soak import ChaosSoakHarness

ROOT = Path(__file__).resolve().parents[3]


def test_chaos_soak_separates_fault_classes_and_avoids_100_percent_claims(
    tmp_path: Path,
) -> None:
    assert (ROOT / "docs/soak-report-template.md").is_file()
    harness = ChaosSoakHarness(tmp_path / "soak")
    report = harness.run_soak_samples()
    assert report.dangerous_blind_retry_count == 0
    assert report.claims_100_percent_lossless_guarantee is False
    assert report.physical_power_loss_tested is False
    assert report.backup_manifest_verified is True
    assert report.disk_full_pre_dispatch_blocked is True
    assert set(report.fault_classes_verified) == {
        "dns_stall_and_tcp_half_open",
        "system_sleep_wake_clock_jump",
        "sigkill_daemon_and_worker_recovery",
        "sqlite_backup_and_disk_full_guard",
    }

    # Negative check: injected blind retry is counted in dangerous_blind_retry_count
    bad_harness = ChaosSoakHarness(tmp_path / "soak_bad")
    bad_rep = bad_harness.run_soak_samples(simulate_blind_retry_fault=True)
    assert bad_rep.dangerous_blind_retry_count == 1
    assert "sigkill_daemon_and_worker_recovery" not in bad_rep.fault_classes_verified
