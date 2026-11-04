from pathlib import Path

from openbot.tools.browser.verifier import BrowserOutcomeRegressionHarness


def test_browser_outcome_regression_verifies_real_effect_counts_and_rejects_model_self_claim(
    tmp_path: Path,
) -> None:
    harness = BrowserOutcomeRegressionHarness(tmp_path / "browser_reg")
    report = harness.run_all_fixture_scenarios()
    assert report.model_text_or_driver_no_error_accepted_as_proof is False
    assert report.route_only_accepted_for_strict_network_mode is False
    assert set(report.scenarios_verified) == {
        "checkout_amount_drift_blocked",
        "form_submit_receipt_lost_marked_unknown",
        "download_quarantine_and_sha256_verified",
        "redirect_to_metadata_blocked",
        "expired_login_session_rejected_even_if_model_claims_done",
    }
