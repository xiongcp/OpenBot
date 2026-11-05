"""M3 MVP release acceptance gate and risk auditor (OB-080)."""

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from openbot.application.supply_chain import ReleaseSupplyChainVerifier


@dataclass(frozen=True, slots=True)
class MvpReleaseDecision:
    darwin_arm64_pilot_ready: bool
    full_three_os_mvp_release_approved: bool
    blocking_reasons: tuple[str, ...]
    m4_signing_is_reverse_prerequisite: Literal[False] = False


@dataclass(frozen=True, slots=True)
class CandidateEvidenceBundle:
    candidate_sha: str
    remote_reachable: bool
    required_case_ids: tuple[str, ...]
    passed_case_ids: tuple[str, ...]
    required_gate_ids: tuple[str, ...]
    passed_gate_ids: tuple[str, ...]
    expected_artifact_ids: tuple[str, ...]
    evidence_verified_on_shas: tuple[str, ...]
    ci_checkout_shas: tuple[str, ...]
    ci_all_passed: bool
    real_cloud_provider_verified: bool
    real_ollama_local_verified: bool
    real_feishu_verified: bool
    native_macos_verified: bool
    open_s0_count: int = 0
    open_s1_count: int = 0
    unexplained_skip_count: int = 0
    collection_error_count: int = 0
    explicit_blocking_reasons: tuple[str, ...] = ()

    def with_override(self, **kwargs: Any) -> "CandidateEvidenceBundle":
        return replace(self, **kwargs)


class MvpReleaseAcceptanceGate:
    """Evaluate M3 MVP release readiness without relaxing three-OS or live-tenant gates."""

    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root.resolve()

    def evaluate_release_readiness(
        self,
        *,
        security_critical_failures: int,
        darwin_arm64_verified: bool,
        windows_native_verified: bool,
        linux_native_verified: bool,
        real_feishu_tenant_verified: bool,
        tamper_artifact_key: str | None = None,
        candidate_sha: str | None = None,
        evidence_sha: str | None = None,
    ) -> MvpReleaseDecision:
        supply_chain_ok = False
        try:
            sc = ReleaseSupplyChainVerifier(self._root).verify_all(tamper_key=tamper_artifact_key)
            supply_chain_ok = sc.verified_artifacts_count > 0 and sc.includes_non_python_assets
        except PermissionError:
            supply_chain_ok = False

        reasons: list[str] = []
        if security_critical_failures > 0:
            reasons.append("security_critical_failures_present")
        if not darwin_arm64_verified or not supply_chain_ok:
            reasons.append("darwin_arm64_or_supply_chain_unverified")
        if candidate_sha is not None and evidence_sha is not None and candidate_sha != evidence_sha:
            reasons.append("candidate_sha_mismatch")
        if not windows_native_verified:
            reasons.append("windows_native_unverified")
        if not linux_native_verified:
            reasons.append("linux_native_unverified")
        if not real_feishu_tenant_verified:
            reasons.append("real_feishu_tenant_unverified")

        pilot_blockers = {
            "security_critical_failures_present",
            "darwin_arm64_or_supply_chain_unverified",
            "candidate_sha_mismatch",
        }
        pilot_ok = (
            security_critical_failures == 0
            and darwin_arm64_verified
            and supply_chain_ok
            and not (set(reasons) & pilot_blockers)
        )
        full_ok = len(reasons) == 0
        return MvpReleaseDecision(
            darwin_arm64_pilot_ready=pilot_ok,
            full_three_os_mvp_release_approved=full_ok,
            blocking_reasons=tuple(reasons),
        )

    def evaluate_macos_mvp_candidate(self, bundle: CandidateEvidenceBundle) -> dict[str, Any]:
        reasons: list[str] = list(bundle.explicit_blocking_reasons)
        if (
            not bundle.required_case_ids
            or not bundle.required_gate_ids
            or not bundle.expected_artifact_ids
        ):
            reasons.append("empty_required_sets")
        if not re.fullmatch(r"[0-9a-f]{40}", bundle.candidate_sha) or not bundle.remote_reachable:
            reasons.append("invalid_or_unreachable_candidate_sha")
        if not bundle.evidence_verified_on_shas or any(
            s != bundle.candidate_sha for s in bundle.evidence_verified_on_shas
        ):
            reasons.append("evidence_sha_mismatch")
        if (
            not bundle.ci_checkout_shas
            or any(s != bundle.candidate_sha for s in bundle.ci_checkout_shas)
            or not bundle.ci_all_passed
        ):
            reasons.append("ci_checkout_sha_mismatch")
        if set(bundle.required_case_ids) - set(bundle.passed_case_ids):
            reasons.append("required_cases_not_all_passed")
        if set(bundle.required_gate_ids) - set(bundle.passed_gate_ids):
            reasons.append("required_gates_not_all_passed")
        if bundle.open_s0_count > 0 or bundle.open_s1_count > 0:
            reasons.append("open_s0_or_s1_defects_present")
        if bundle.unexplained_skip_count > 0 or bundle.collection_error_count > 0:
            reasons.append("unexplained_skips_or_collection_errors")
        if not bundle.real_cloud_provider_verified:
            reasons.append("missing_real_cloud_provider")
        if not bundle.real_ollama_local_verified:
            reasons.append("missing_real_ollama_local_provider")
        if not bundle.real_feishu_verified:
            reasons.append("missing_real_feishu_tenant")
        if not bundle.native_macos_verified:
            reasons.append("missing_native_macos_verification")

        try:
            sc = ReleaseSupplyChainVerifier(self._root).verify_all()
            if sc.verified_artifacts_count < len(bundle.expected_artifact_ids):
                reasons.append("supply_chain_artifacts_incomplete")
        except PermissionError:
            reasons.append("supply_chain_verification_failed")

        ready = len(reasons) == 0
        return {
            "candidate_sha": bundle.candidate_sha,
            "ready": ready,
            "status": "PASS_MACOS_MVP" if ready else "BLOCKED",
            "blocking_reasons": tuple(reasons),
        }
