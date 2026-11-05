"""M3 MVP release acceptance gate and risk auditor (OB-080)."""

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from openbot.application.supply_chain import ReleaseSupplyChainVerifier

type EvidenceProvenanceKind = Literal["SOURCE", "SYNTHETIC", "NATIVE", "LIVE_EXTERNAL"]
type RunLifecycleState = Literal["IN_PROGRESS", "COMPLETE", "FAILED"]


@dataclass(frozen=True, slots=True)
class PlatformQualificationClaim:
    os_name: Literal["Darwin", "Windows", "Linux"]
    arch: str
    contracts_passed: bool
    native_installer_verified: bool
    native_supervision_verified: bool
    native_keychain_verified: bool


@dataclass(frozen=True, slots=True)
class V1ScopeEvaluation:
    release_target: Literal["v1.0.0-macos-arm64"]
    supported_platforms: tuple[str, ...]
    original_m3_three_os_complete: Literal[False]
    deferred_platforms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceRunRecord:
    run_id: str
    source_sha: str
    tree_sha: str
    dirty_worktree: bool
    lockfile_sha256: str
    artifact_sha256: str | None
    provenance_kind: EvidenceProvenanceKind
    machine_id: str
    lifecycle_state: RunLifecycleState
    exit_code: int | None
    log_sha256: str
    test_ids: tuple[str, ...]
    client_self_reported_pass: bool = False


class V1BaselineContractGuard:
    """Enforce V1-001..006 scope, evidence provenance, threat boundaries, and API compatibility."""

    def evaluate_v1_scope(
        self, claims: tuple[PlatformQualificationClaim, ...]
    ) -> V1ScopeEvaluation:
        supported: list[str] = []
        deferred: list[str] = ["Darwin-x86_64", "Windows-AMD64", "Linux-x86_64"]
        for claim in claims:
            key = f"{claim.os_name}-{claim.arch}"
            full_native = (
                claim.contracts_passed
                and claim.native_installer_verified
                and claim.native_supervision_verified
                and claim.native_keychain_verified
            )
            if claim.os_name in {"Windows", "Linux"} and not (
                claim.native_installer_verified
                and claim.native_supervision_verified
                and claim.native_keychain_verified
            ):
                if full_native:
                    raise PermissionError("CONTRACTS_ONLY_CANNOT_CLAIM_NATIVE_OS_SUPPORT")
                continue
            if key == "Darwin-arm64" and full_native:
                supported.append(key)
        if not supported:
            raise PermissionError("V1_MACOS_ARM64_QUALIFICATION_INCOMPLETE")
        return V1ScopeEvaluation(
            release_target="v1.0.0-macos-arm64",
            supported_platforms=tuple(supported),
            original_m3_three_os_complete=False,
            deferred_platforms=tuple(deferred),
        )

    def register_and_verify_evidence_runs(
        self,
        *,
        candidate_sha: str,
        expected_artifact_sha256: str,
        required_test_ids: tuple[str, ...],
        runs: tuple[EvidenceRunRecord, ...],
        require_distinct_native_machines: int = 1,
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-f]{40}", candidate_sha):
            raise PermissionError("INVALID_CANDIDATE_SHA")
        seen_run_ids: set[str] = set()
        covered_tests: set[str] = set()
        native_machines: set[str] = set()

        for rec in runs:
            if rec.run_id in seen_run_ids:
                raise PermissionError(f"EVIDENCE_RUN_ID_REUSE_FORBIDDEN: {rec.run_id}")
            seen_run_ids.add(rec.run_id)
            if rec.client_self_reported_pass:
                raise PermissionError("SELF_REPORTED_BOOLEAN_EVIDENCE_FORBIDDEN")
            if rec.lifecycle_state != "COMPLETE" or rec.exit_code != 0:
                raise PermissionError(f"EVIDENCE_RUN_NOT_COMPLETE_AND_PASSING: {rec.run_id}")
            if rec.dirty_worktree or rec.source_sha != candidate_sha:
                raise PermissionError(f"EVIDENCE_STALE_OR_DIRTY_SHA: {rec.run_id}")
            if rec.artifact_sha256 is not None and rec.artifact_sha256 != expected_artifact_sha256:
                raise PermissionError(f"EVIDENCE_ARTIFACT_DIGEST_MISMATCH: {rec.run_id}")
            if not re.fullmatch(r"[0-9a-f]{64}", rec.log_sha256):
                raise PermissionError(f"EVIDENCE_LOG_DIGEST_INVALID: {rec.run_id}")
            if rec.provenance_kind == "NATIVE":
                if rec.machine_id.startswith("mock") or rec.machine_id.startswith("synthetic"):
                    raise PermissionError("MOCK_REPORT_CANNOT_CLAIM_NATIVE_MACHINE")
                native_machines.add(rec.machine_id)
            covered_tests.update(rec.test_ids)

        missing_tests = set(required_test_ids) - covered_tests
        if missing_tests:
            raise PermissionError(f"EVIDENCE_MISSING_REQUIRED_TESTS: {sorted(missing_tests)}")
        if len(native_machines) < require_distinct_native_machines:
            raise PermissionError("INSUFFICIENT_DISTINCT_NATIVE_MACHINES")
        return {
            "candidate_sha": candidate_sha,
            "verified_runs": len(runs),
            "covered_test_count": len(covered_tests),
            "native_machines": tuple(sorted(native_machines)),
        }

    def verify_ingress_boundary(
        self,
        *,
        source_surface: str,
        target_action: str,
        payload: dict[str, Any],
    ) -> None:
        if "old_epoch_isolated" in payload or "revive_consumed_grant" in payload:
            raise PermissionError("UNTRUSTED_RECOVERY_OR_GRANT_OVERRIDE_FORBIDDEN")
        if source_surface in {"model_output", "tool_output", "mcp_metadata", "web_dom", "memory"}:
            raise PermissionError(f"TAINTED_SURFACE_CANNOT_AUTHORIZE: {source_surface}")
        if source_surface == "worker_ipc" and target_action.startswith("owner_"):
            raise PermissionError("RESTRICTED_WORKER_CANNOT_CALL_OWNER_ADMIN_API")
        if source_surface == "tauri_ipc" and "raw_url" in payload:
            raise PermissionError("ARBITRARY_IPC_URL_FORBIDDEN")

    def verify_api_version_compatibility(
        self,
        *,
        client_protocol_version: str,
        server_protocol_version: str = "1.0",
        payload_fields: frozenset[str],
        allowed_fields: frozenset[str],
    ) -> dict[str, str]:
        c_parts = client_protocol_version.split(".")
        s_parts = server_protocol_version.split(".")
        if len(c_parts) != 2 or c_parts[0] != s_parts[0]:
            raise PermissionError(f"INCOMPATIBLE_PROTOCOL_MAJOR_VERSION: {client_protocol_version}")
        unknown = payload_fields - allowed_fields
        if unknown:
            raise PermissionError(f"UNKNOWN_CONTRACT_FIELDS_REJECTED: {sorted(unknown)}")
        return {"protocol": server_protocol_version, "compatibility": "VERIFIED"}

    def verify_publication_consistency(self, repo_root: Path) -> dict[str, Any]:
        root = repo_root.resolve()
        status_path = root / "docs/project-status.json"
        manifest_path = root / "apps/website/public/releases.manifest.json"
        license_path = root / "LICENSE"
        if not status_path.is_file() or not manifest_path.is_file() or not license_path.is_file():
            raise PermissionError("PUBLICATION_SOURCE_OF_TRUTH_MISSING")
        status_doc = json.loads(status_path.read_text(encoding="utf-8"))
        manifest_doc = json.loads(manifest_path.read_text(encoding="utf-8"))
        if status_doc.get("license") != "Apache-2.0":
            raise PermissionError("PROJECT_LICENSE_MISMATCH")
        if status_doc.get("primary_platform", {}).get("os") != "Darwin":
            raise PermissionError("PRIMARY_PLATFORM_MISMATCH")
        if manifest_doc.get("project") != status_doc.get("project"):
            raise PermissionError("WEBSITE_MANIFEST_PROJECT_MISMATCH")
        zh_page = (root / "apps/website/src/pages/zh/index.html").read_text(encoding="utf-8")
        en_page = (root / "apps/website/src/pages/en/index.html").read_text(encoding="utf-8")
        if "Apache-2.0" not in zh_page or "Apache-2.0" not in en_page:
            raise PermissionError("WEBSITE_LICENSE_DECLARATION_MISMATCH")
        return {
            "project": status_doc["project"],
            "license": status_doc["license"],
            "capabilities_count": len(status_doc.get("capabilities", [])),
            "bilingual_website_verified": True,
        }


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
