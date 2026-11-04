"""Tiered CI gate evaluator for pull_request, nightly, and release workflows (OB-077)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

type CiTier = Literal["pull_request", "nightly", "release"]


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

    def evaluate_tier(
        self,
        *,
        tier: CiTier,
        inject_security_failure: bool,
        allow_skip_failed: bool,
    ) -> CiTierEvaluation:
        if allow_skip_failed:
            raise PermissionError("CI_SKIP_FAILED_TESTS_FORBIDDEN")
        pr_wf = (self._root / ".github/workflows/pull_request/gate.yml").read_text("utf-8")
        sec_included = "security" in pr_wf.lower() or "verify.py" in pr_wf
        return CiTierEvaluation(
            tier=tier,
            security_tests_included=sec_included,
            gate_passed=(sec_included and not inject_security_failure),
        )
