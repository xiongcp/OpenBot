from pathlib import Path

from openbot.application.mvp_regression import MvpCapabilityRegressionSuite


def test_mvp_capability_regression_verifies_all_subsystems_and_reports_honest_boundaries(
    tmp_path: Path,
) -> None:
    suite = MvpCapabilityRegressionSuite(tmp_path / "mvp_reg")
    report = suite.run_all()
    assert report.security_critical_failures == 0
    assert report.reference_only_or_deferred_claimed_as_active is False
    assert report.claims_three_os_release_complete is False
    assert set(report.subsystems_verified) == {
        "cloud_and_local_providers",
        "feishu_controlled_gateway",
        "workspace_aci_and_isolated_process",
        "browser_structured_tools",
        "mcp_stdio_and_fault_guards",
        "readonly_skills_loader",
    }
