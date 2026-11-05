from pathlib import Path

from openbot.application.mvp_release_gate import (
    CandidateEvidenceBundle,
    MvpReleaseAcceptanceGate,
)

ROOT = Path(__file__).resolve().parents[2]


def test_mvp_release_gate_blocks_release_when_three_os_or_live_feishu_unverified() -> None:
    assert (ROOT / "docs/releases/mvp-acceptance.md").is_file()
    assert (ROOT / "docs/risks.md").is_file()

    gate = MvpReleaseAcceptanceGate(ROOT)
    decision = gate.evaluate_release_readiness(
        security_critical_failures=0,
        darwin_arm64_verified=True,
        windows_native_verified=False,
        linux_native_verified=False,
        real_feishu_tenant_verified=False,
    )
    assert decision.m4_signing_is_reverse_prerequisite is False
    assert decision.darwin_arm64_pilot_ready is True
    assert decision.full_three_os_mvp_release_approved is False
    assert "windows_native_unverified" in decision.blocking_reasons
    assert "linux_native_unverified" in decision.blocking_reasons
    assert "real_feishu_tenant_unverified" in decision.blocking_reasons

    # Supply-chain tampering or stale candidate SHA must block darwin_arm64_pilot_ready!
    tampered = gate.evaluate_release_readiness(
        security_critical_failures=0,
        darwin_arm64_verified=True,
        windows_native_verified=False,
        linux_native_verified=False,
        real_feishu_tenant_verified=False,
        tamper_artifact_key="uv.lock",
    )
    assert tampered.darwin_arm64_pilot_ready is False
    assert "darwin_arm64_or_supply_chain_unverified" in tampered.blocking_reasons

    stale_sha = gate.evaluate_release_readiness(
        security_critical_failures=0,
        darwin_arm64_verified=True,
        windows_native_verified=False,
        linux_native_verified=False,
        real_feishu_tenant_verified=False,
        candidate_sha="a" * 40,
        evidence_sha="b" * 40,
    )
    assert stale_sha.darwin_arm64_pilot_ready is False
    assert "candidate_sha_mismatch" in stale_sha.blocking_reasons


def test_macos_mvp_candidate_evaluator_rejects_missing_evidence_and_blockers() -> None:
    gate = MvpReleaseAcceptanceGate(ROOT)
    cand_sha = "c" * 40
    valid_bundle = CandidateEvidenceBundle(
        candidate_sha=cand_sha,
        remote_reachable=True,
        required_case_ids=("TC-QA-001", "TC-CORE-001", "TC-MAC-001", "TC-INT-001"),
        passed_case_ids=("TC-QA-001", "TC-CORE-001", "TC-MAC-001", "TC-INT-001"),
        required_gate_ids=("G00", "G01", "G08", "G09", "G10", "G14"),
        passed_gate_ids=("G00", "G01", "G08", "G09", "G10", "G14"),
        expected_artifact_ids=(
            "uv.lock",
            "THIRD_PARTY_NOTICES.md",
            "packaging/runtime-assets.json",
        ),
        evidence_verified_on_shas=(cand_sha,),
        ci_checkout_shas=(cand_sha,),
        ci_all_passed=True,
        real_cloud_provider_verified=True,
        real_ollama_local_verified=True,
        real_feishu_verified=True,
        native_macos_verified=True,
        open_s0_count=0,
        open_s1_count=0,
        unexplained_skip_count=0,
        collection_error_count=0,
        explicit_blocking_reasons=(),
    )
    res_ok = gate.evaluate_macos_mvp_candidate(valid_bundle)
    assert res_ok["status"] == "PASS_MACOS_MVP"
    assert res_ok["ready"] is True
    assert res_ok["blocking_reasons"] == ()

    for mut_field, mut_val, expected_reason in (
        ("real_ollama_local_verified", False, "missing_real_ollama_local_provider"),
        ("real_cloud_provider_verified", False, "missing_real_cloud_provider"),
        ("evidence_verified_on_shas", ("d" * 40,), "evidence_sha_mismatch"),
        ("ci_checkout_shas", ("e" * 40,), "ci_checkout_sha_mismatch"),
        ("required_case_ids", (), "empty_required_sets"),
        ("explicit_blocking_reasons", ("manual_hold",), "manual_hold"),
    ):
        bad_bundle = valid_bundle.with_override(**{mut_field: mut_val})
        res_bad = gate.evaluate_macos_mvp_candidate(bad_bundle)
        assert res_bad["ready"] is False
        assert res_bad["status"] != "PASS_MACOS_MVP"
        assert expected_reason in res_bad["blocking_reasons"]
