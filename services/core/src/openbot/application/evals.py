"""Task quality benchmark evaluator enforcing OutcomeVerifier and UNKNOWN checks (OB-076)."""

from dataclasses import dataclass
from typing import Literal

type EvalVerdict = Literal["SUCCEEDED", "PARTIAL", "FAILED", "RECONCILING"]


@dataclass(frozen=True, slots=True)
class EvalTrialSample:
    scenario_id: str
    provider_kind: Literal["REAL_PROVIDER", "MOCK_OFFLINE"]
    model_claimed_done: bool
    outcome_verifier_passed: bool
    has_unresolved_unknown_operation: bool
    cost_micro_usd: int
    latency_ms: int


@dataclass(frozen=True, slots=True)
class EvalBenchmarkSummary:
    sample_count: int
    verdicts_by_scenario: dict[str, EvalVerdict]
    mock_accepted_as_intelligence_proof: Literal[False] = False
    fixed_loc_or_speedup_promised: Literal[False] = False


class BenchmarkEvalRunner:
    """Grade trials using OutcomeVerifier and unresolved-UNKNOWN checks."""

    def evaluate_trials(self, *, trials: tuple[EvalTrialSample, ...]) -> EvalBenchmarkSummary:
        verdicts: dict[str, EvalVerdict] = {}
        for tr in trials:
            if tr.has_unresolved_unknown_operation:
                verdicts[tr.scenario_id] = "RECONCILING"
            elif tr.outcome_verifier_passed:
                verdicts[tr.scenario_id] = "SUCCEEDED"
            elif tr.model_claimed_done:
                verdicts[tr.scenario_id] = "FAILED"
            else:
                verdicts[tr.scenario_id] = "PARTIAL"
        return EvalBenchmarkSummary(
            sample_count=len(trials),
            verdicts_by_scenario=verdicts,
        )
