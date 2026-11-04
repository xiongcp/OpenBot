from pathlib import Path

from openbot_feishu.e2e_harness import FeishuM2EndToEndHarness


def test_feishu_m2_e2e_harness_verifies_main_flow_and_six_failure_scenarios_honestly(
    tmp_path: Path,
) -> None:
    harness = FeishuM2EndToEndHarness(tmp_path / "feishu_e2e")
    report = harness.run_all()
    assert report.main_flow_passed is True
    assert report.real_feishu_tenant_verified is False
    assert report.claims_full_mvp_complete is False
    assert set(report.failure_scenarios_verified) == {
        "disconnect_and_jittered_reconnect",
        "daemon_restart_recovery",
        "duplicate_approval_callback",
        "stale_card_on_cancelled_task",
        "revoked_owner_rejected",
        "dual_consumer_spawn_blocked",
    }
