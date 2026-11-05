"""Task quality benchmark evaluator enforcing OutcomeVerifier and UNKNOWN checks (OB-076)."""

import platform
import sys
from dataclasses import dataclass
from typing import Any, Literal

type EvalVerdict = Literal["SUCCEEDED", "PARTIAL", "FAILED", "RECONCILING"]

SEVEN_PRODUCT_SCENARIO_IDS: tuple[str, ...] = (
    "S1_WORKSPACE_READ_SUMMARY",
    "S2_WORKSPACE_PATCH_DIFF",
    "S3_BROWSER_READ_WRITE",
    "S4_ISOLATED_MCP_READ",
    "S5_FEISHU_INGRESS_APPROVAL",
    "S6_CLOUD_AND_LOCAL_PROVIDER",
    "S7_DAEMON_CRASH_RECOVERY",
)


@dataclass(frozen=True, slots=True)
class ScenarioEvidenceObservation:
    scenario_id: str
    entry_surface: Literal["daemon_cli", "desktop_ui", "feishu_gateway"]
    direct_sql_state_write_used: bool
    observable_artifact_sha256: str | None
    independent_receiver_effect_count: int
    in_process_self_counter_used: bool
    unresolved_unknown_count: int


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

    def verify_seven_product_scenarios(
        self, observations: tuple[ScenarioEvidenceObservation, ...]
    ) -> dict[str, str]:
        by_id = {obs.scenario_id: obs for obs in observations}
        missing = [sid for sid in SEVEN_PRODUCT_SCENARIO_IDS if sid not in by_id]
        if missing:
            raise PermissionError(f"SCENARIO_COVERAGE_INCOMPLETE: {missing}")
        verdicts: dict[str, str] = {}
        for sid in SEVEN_PRODUCT_SCENARIO_IDS:
            obs = by_id[sid]
            if obs.direct_sql_state_write_used:
                raise PermissionError(f"DIRECT_SQL_BYPASS_FORBIDDEN: {sid}")
            if obs.in_process_self_counter_used:
                raise PermissionError(f"IN_PROCESS_SELF_COUNTER_FORBIDDEN: {sid}")
            if obs.unresolved_unknown_count > 0:
                verdicts[sid] = "RECONCILING"
            elif obs.observable_artifact_sha256:
                verdicts[sid] = "VERIFIED"
            else:
                raise PermissionError(f"MISSING_OBSERVABLE_ARTIFACT: {sid}")
        return verdicts


class EnvironmentInventoryAuditor:
    """Build sanitized Mac/integration environment inventory without leaking secrets (V1-007)."""

    _FORBIDDEN_KEYS = ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "RAW_TENANT_MESSAGE")

    def collect_sanitized_inventory(self, raw_metadata: dict[str, str]) -> dict[str, Any]:
        for k, v in raw_metadata.items():
            upper_k = k.upper()
            if any(tok in upper_k for tok in self._FORBIDDEN_KEYS) or "sk-" in v:
                raise PermissionError(f"ENVIRONMENT_INVENTORY_SECRET_LEAK_BLOCKED: {k}")
        return {
            "os_name": platform.system(),
            "arch": platform.machine(),
            "python_version": sys.version.split()[0],
            "metadata": dict(sorted(raw_metadata.items())),
            "contains_raw_env_or_secrets": False,
        }
