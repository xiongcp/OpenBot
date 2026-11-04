"""CLI entrypoint for running OpenBot task quality benchmark evaluations (OB-076)."""

import json

from openbot.application.evals import BenchmarkEvalRunner, EvalTrialSample


def main() -> int:
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
                latency_ms=10,
            ),
        )
    )
    print(
        json.dumps(
            {
                "sample_count": summary.sample_count,
                "verdicts": summary.verdicts_by_scenario,
                "mock_accepted_as_intelligence_proof": summary.mock_accepted_as_intelligence_proof,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
