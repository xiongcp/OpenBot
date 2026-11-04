from pathlib import Path

from openbot.application.local_prototype import LocalAlphaPrototypeRunner


def test_local_alpha_prototype_runs_from_empty_config_and_reports_honest_capability_boundaries(
    tmp_path: Path,
) -> None:
    runner = LocalAlphaPrototypeRunner(tmp_path / "alpha_proto")
    report = runner.run_from_empty_config()
    assert report.read_file_verified is True
    assert report.patch_proposed_and_approved is True
    assert report.isolated_test_executed is True
    assert report.restart_requery_verified is True
    assert report.pilot_os == "Darwin-arm64"
    assert "Windows-native" in report.unsupported_or_unverified_capabilities
    assert "Linux-native" in report.unsupported_or_unverified_capabilities
    assert "real_feishu_tenant" in report.unsupported_or_unverified_capabilities
    assert report.claims_full_mvp_complete is False
