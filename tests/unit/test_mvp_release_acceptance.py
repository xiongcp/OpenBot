from pathlib import Path

from openbot.application.mvp_release_gate import MvpReleaseAcceptanceGate

ROOT = Path(__file__).resolve().parents[2]


def test_mvp_release_gate_blocks_release_when_three_os_or_live_feishu_unverified() -> None:
    assert (ROOT / "docs/releases/mvp-acceptance.md").is_file()
    assert (ROOT / "docs/risks.md").is_file()

    gate = MvpReleaseAcceptanceGate(ROOT)
    decision = gate.evaluate_release_readiness(
        security_critical_failures=0,
        darwin_arm64_verified=True,
        windows_native_verified=False,
        linux_native_verified=False,
        real_feishu_tenant_verified=False,
    )
    assert decision.m4_signing_is_reverse_prerequisite is False
    assert decision.darwin_arm64_pilot_ready is True
    assert decision.full_three_os_mvp_release_approved is False
    assert "windows_native_unverified" in decision.blocking_reasons
    assert "linux_native_unverified" in decision.blocking_reasons
    assert "real_feishu_tenant_unverified" in decision.blocking_reasons
