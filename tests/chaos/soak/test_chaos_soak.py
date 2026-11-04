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
    assert set(report.fault_classes_verified) == {
        "dns_stall_and_tcp_half_open",
        "system_sleep_wake_clock_jump",
        "sigkill_daemon_and_worker_recovery",
        "sqlite_backup_and_disk_full_guard",
    }
