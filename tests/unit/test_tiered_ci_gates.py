import ast
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

    bad_py_repo = tmp_path / "bad_py_repo"
    wf_dir3 = bad_py_repo / ".github/workflows"
    wf_dir3.mkdir(parents=True)
    for name in (
        "pr.yml",
        "pr-gate.yml",
        "platform-macos.yml",
        "nightly-soak.yml",
        "release-supply-chain.yml",
    ):
        (wf_dir3 / name).write_text(
            "runs-on: macos-15\npython-version: '3.12.12'\nuv sync --locked",
            encoding="utf-8",
        )
    with pytest.raises(PermissionError, match="SETUP_PYTHON_UNAVAILABLE_PATCH_BUILD"):
        TieredCiGateEvaluator(bad_py_repo).validate_workflow_layout()

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

    for rel_path in (
        "services/core/src/openbot/application/scheduler.py",
        "services/core/src/openbot/tools/executors/supervision_port.py",
        "services/core/src/openbot/application/macos_gate.py",
        "services/core/src/openbot/application/vertical_slice.py",
    ):
        src = (ROOT / rel_path).read_text(encoding="utf-8")
        assert 'sys.platform != "win32"' in src, f"Missing win32 platform narrowing in {rel_path}"

    for val_path in ("validation/verify_design.py", "validation/verify_components.py"):
        tree = ast.parse((ROOT / val_path).read_text(encoding="utf-8"), filename=val_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "read_text":
                    has_enc = bool(node.args) or any(kw.arg == "encoding" for kw in node.keywords)
                    assert has_enc, f"Unencoded read_text() in {val_path}:{node.lineno}"

    gitattributes = ROOT / ".gitattributes"
    assert gitattributes.is_file()
    attr_text = gitattributes.read_text(encoding="utf-8")
    assert "eol=lf" in attr_text
    assert "filter=" not in attr_text
