from pathlib import Path

import pytest
from openbot.application.ci_gates import TieredCiGateEvaluator

ROOT = Path(__file__).resolve().parents[2]


def test_tiered_ci_gates_run_security_in_pr_and_block_on_injected_failure_or_skip() -> None:
    assert (ROOT / ".github/workflows/pull_request/gate.yml").is_file()
    assert (ROOT / ".github/workflows/nightly/soak.yml").is_file()
    assert (ROOT / ".github/workflows/release/supply_chain.yml").is_file()

    evaluator = TieredCiGateEvaluator(ROOT)
    pr_plan = evaluator.evaluate_tier(
        tier="pull_request", inject_security_failure=False, allow_skip_failed=False
    )
    assert pr_plan.security_tests_included is True
    assert pr_plan.installs_all_catalog_components_globally is False
    assert pr_plan.gate_passed is True

    with pytest.raises(PermissionError, match="CI_SKIP_FAILED_TESTS_FORBIDDEN"):
        evaluator.evaluate_tier(
            tier="pull_request", inject_security_failure=False, allow_skip_failed=True
        )

    blocked = evaluator.evaluate_tier(
        tier="pull_request", inject_security_failure=True, allow_skip_failed=False
    )
    assert blocked.gate_passed is False
