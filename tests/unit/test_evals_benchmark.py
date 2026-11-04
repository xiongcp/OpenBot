from pathlib import Path

from openbot.application.evals import BenchmarkEvalRunner, EvalTrialSample

ROOT = Path(__file__).resolve().parents[2]


def test_evals_benchmark_requires_outcome_verifier_and_rejects_unknown_or_mock() -> None:
    assert (ROOT / "evals/scenarios/mvp_tasks.json").is_file()
    assert (ROOT / "evals/rubrics/outcome_rubric.md").is_file()
    assert (ROOT / "evals/run.py").is_file()

    runner = BenchmarkEvalRunner()
    summary = runner.evaluate_trials(
        trials=(
            EvalTrialSample(
                scenario_id="scn_patch_1",
                provider_kind="MOCK_OFFLINE",
                model_claimed_done=True,
                outcome_verifier_passed=True,
                has_unresolved_unknown_operation=False,
                cost_micro_usd=0,
                latency_ms=45,
            ),
            EvalTrialSample(
                scenario_id="scn_send_unknown",
                provider_kind="MOCK_OFFLINE",
                model_claimed_done=True,
                outcome_verifier_passed=True,
                has_unresolved_unknown_operation=True,
                cost_micro_usd=0,
                latency_ms=80,
            ),
        )
    )
    assert summary.sample_count == 2
    assert summary.mock_accepted_as_intelligence_proof is False
    assert summary.fixed_loc_or_speedup_promised is False
    # Second trial has unresolved UNKNOWN operation, so it is RECONCILING, NOT SUCCEEDED!
    assert summary.verdicts_by_scenario["scn_patch_1"] == "SUCCEEDED"
    assert summary.verdicts_by_scenario["scn_send_unknown"] == "RECONCILING"
