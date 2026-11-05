from pathlib import Path

import pytest
from openbot.application.ci_gates import TieredCiGateEvaluator

ROOT = Path(__file__).resolve().parents[2]


def test_tiered_ci_gates_run_security_in_pr_and_block_on_injected_failure_or_skip(
    tmp_path: Path,
) -> None:
    evaluator = TieredCiGateEvaluator(ROOT)
    workflows = evaluator.validate_workflow_layout()
    assert "pr-gate.yml" in workflows
    assert "nightly-soak.yml" in workflows
    assert "release-supply-chain.yml" in workflows
    assert not list((ROOT / ".github/workflows").glob("*/*.yml"))

    bad_repo = tmp_path / "bad_repo"
    (bad_repo / ".github/workflows/sub").mkdir(parents=True)
    (bad_repo / ".github/workflows/sub/nested.yml").write_text("name: bad", encoding="utf-8")
    with pytest.raises(PermissionError, match="UNSUPPORTED_WORKFLOW_SUBDIRECTORY"):
        TieredCiGateEvaluator(bad_repo).validate_workflow_layout()

    retired_repo = tmp_path / "retired_repo"
    wf_dir = retired_repo / ".github/workflows"
    wf_dir.mkdir(parents=True)
    for name in (
        "pr.yml",
        "pr-gate.yml",
        "platform-macos.yml",
        "nightly-soak.yml",
        "release-supply-chain.yml",
    ):
        (wf_dir / name).write_text("runs-on: macos-14", encoding="utf-8")
    with pytest.raises(PermissionError, match="RETIRED_RUNNER_LABEL_FORBIDDEN"):
        TieredCiGateEvaluator(retired_repo).validate_workflow_layout()

    unsynced_repo = tmp_path / "unsynced_repo"
    wf_dir2 = unsynced_repo / ".github/workflows"
    wf_dir2.mkdir(parents=True)
    for name in (
        "pr.yml",
        "pr-gate.yml",
        "platform-macos.yml",
        "nightly-soak.yml",
        "release-supply-chain.yml",
    ):
        (wf_dir2 / name).write_text("runs-on: macos-15", encoding="utf-8")
    with pytest.raises(PermissionError, match="WORKFLOW_MISSING_LOCKED_SYNC"):
        TieredCiGateEvaluator(unsynced_repo).validate_workflow_layout()

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
