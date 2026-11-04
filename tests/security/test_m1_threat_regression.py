from pathlib import Path

from openbot.policy.threat_regression import M1ThreatRegressionSuite


def test_m1_security_tool_threat_regression_corpus_blocks_all_unauthorized_side_effects(
    tmp_path: Path,
) -> None:
    suite = M1ThreatRegressionSuite(tmp_path)
    report = suite.run_all()
    assert report.total_unauthorized_side_effects == 0
    assert report.all_blocked is True
    assert set(report.cases_verified) == {
        "jcs_deep_mutation_and_duplicate_key",
        "path_traversal_and_symlink_escape",
        "rg_and_git_malicious_config_injection",
        "parser_runtime_download_and_crash_isolation",
        "secret_leak_and_offline_scanner_enforcement",
        "output_flood_truncation_and_shell_metachar_rejection",
        "unisolated_worker_residual_blocks_new_dispatch",
    }
