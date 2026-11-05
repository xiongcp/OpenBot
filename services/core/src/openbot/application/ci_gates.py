"""Tiered CI gate evaluator for pull_request, nightly, and release workflows (OB-077)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

type CiTier = Literal["pull_request", "nightly", "release"]

_RETIRED_RUNNER_LABELS = ("macos-14", "macos-13", "macos-12", "ubuntu-20.04")


@dataclass(frozen=True, slots=True)
class CiTierEvaluation:
    tier: CiTier
    security_tests_included: bool
    gate_passed: bool
    installs_all_catalog_components_globally: Literal[False] = False


class TieredCiGateEvaluator:
    """Enforce security regression in PR tier and forbid skipping failed tests."""

    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root.resolve()

    def validate_workflow_layout(self) -> tuple[str, ...]:
        wf_dir = self._root / ".github/workflows"
        nested = [
            p.relative_to(wf_dir).as_posix()
            for p in wf_dir.rglob("*")
            if p.is_file() and p.suffix in {".yml", ".yaml"} and p.parent != wf_dir
        ]
        if nested:
            raise PermissionError(f"UNSUPPORTED_WORKFLOW_SUBDIRECTORY: {', '.join(sorted(nested))}")
        required = (
            "pr.yml",
            "pr-gate.yml",
            "platform-macos.yml",
            "nightly-soak.yml",
            "release-supply-chain.yml",
        )
        missing = [name for name in required if not (wf_dir / name).is_file()]
        if missing:
            raise PermissionError(f"MISSING_REQUIRED_WORKFLOWS: {', '.join(missing)}")
        for name in required:
            text = (wf_dir / name).read_text("utf-8")
            for label in _RETIRED_RUNNER_LABELS:
                if label in text:
                    raise PermissionError(f"RETIRED_RUNNER_LABEL_FORBIDDEN: {name} uses {label}")
        return required

    def evaluate_tier(
        self,
        *,
        tier: CiTier,
        inject_security_failure: bool,
        allow_skip_failed: bool,
    ) -> CiTierEvaluation:
        if allow_skip_failed:
            raise PermissionError("CI_SKIP_FAILED_TESTS_FORBIDDEN")
        self.validate_workflow_layout()
        pr_wf = (self._root / ".github/workflows/pr-gate.yml").read_text("utf-8")
        sec_included = "security" in pr_wf.lower() or "verify.py" in pr_wf
        return CiTierEvaluation(
            tier=tier,
            security_tests_included=sec_included,
            gate_passed=(sec_included and not inject_security_failure),
        )
