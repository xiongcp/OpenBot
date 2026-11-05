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
    assert report.provider_qualifications["synthetic_provider_contract"] == "PASS"
    assert report.provider_qualifications["real_cloud_provider"] == "BLOCKED_CREDENTIALS"
    assert report.provider_qualifications["real_local_ollama_runner"] == "BLOCKED_ENV"
    assert report.both_real_providers_verified is False
    assert "cloud_and_local_providers" not in report.subsystems_verified
    assert set(report.subsystems_verified) == {
        "provider_contract_guards",
        "feishu_controlled_gateway",
        "workspace_aci_and_isolated_process",
        "browser_structured_tools",
        "mcp_stdio_and_fault_guards",
        "readonly_skills_loader",
    }
