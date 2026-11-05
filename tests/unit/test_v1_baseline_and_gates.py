from pathlib import Path

import pytest
from openbot.application.ci_gates import TieredCiGateEvaluator
from openbot.application.evals import (
    SEVEN_PRODUCT_SCENARIO_IDS,
    BenchmarkEvalRunner,
    EnvironmentInventoryAuditor,
    ScenarioEvidenceObservation,
)
from openbot.application.mvp_release_gate import (
    EvidenceRunRecord,
    PlatformQualificationClaim,
    V1BaselineContractGuard,
)
from openbot.application.supply_chain import ReleaseSupplyChainVerifier

ROOT = Path(__file__).resolve().parents[2]
SEVENTH_SCENARIO = "S7_DAEMON_CRASH_RECOVERY"


def test_v1_scope_guard_rejects_windows_contracts_only_and_preserves_m3() -> None:
    guard = V1BaselineContractGuard()
    claims = (
        PlatformQualificationClaim(
            os_name="Darwin",
            arch="arm64",
            contracts_passed=True,
            native_installer_verified=True,
            native_supervision_verified=True,
            native_keychain_verified=True,
        ),
        PlatformQualificationClaim(
            os_name="Windows",
            arch="AMD64",
            contracts_passed=True,
            native_installer_verified=False,
            native_supervision_verified=False,
            native_keychain_verified=False,
        ),
    )
    res = guard.evaluate_v1_scope(claims)
    assert res.release_target == "v1.0.0-macos-arm64"
    assert res.supported_platforms == ("Darwin-arm64",)
    assert res.original_m3_three_os_complete is False
    assert "Windows-AMD64" in res.deferred_platforms

    with pytest.raises(PermissionError, match="V1_MACOS_ARM64_QUALIFICATION_INCOMPLETE"):
        guard.evaluate_v1_scope((claims[1],))


def test_evidence_provenance_contract_rejects_stale_sha_reuse_and_mock_native() -> None:
    guard = V1BaselineContractGuard()
    sha = "2028229123a6fc1d44ec54a1c905ef4c9f09fa05"
    art_sha = "a" * 64
    log_sha = "b" * 64

    valid_run = EvidenceRunRecord(
        run_id="run_v1_001",
        source_sha=sha,
        tree_sha="c" * 40,
        dirty_worktree=False,
        lockfile_sha256="d" * 64,
        artifact_sha256=art_sha,
        provenance_kind="NATIVE",
        machine_id="macbook-pro-m3-arm64-01",
        lifecycle_state="COMPLETE",
        exit_code=0,
        log_sha256=log_sha,
        test_ids=("TC-QA-001", "TC-MAC-001"),
    )
    summary = guard.register_and_verify_evidence_runs(
        candidate_sha=sha,
        expected_artifact_sha256=art_sha,
        required_test_ids=("TC-QA-001", "TC-MAC-001"),
        runs=(valid_run,),
    )
    assert summary["verified_runs"] == 1

    with pytest.raises(PermissionError, match="EVIDENCE_RUN_ID_REUSE_FORBIDDEN"):
        guard.register_and_verify_evidence_runs(
            candidate_sha=sha,
            expected_artifact_sha256=art_sha,
            required_test_ids=("TC-QA-001",),
            runs=(valid_run, valid_run),
        )

    mock_native = EvidenceRunRecord(
        run_id="run_mock_1",
        source_sha=sha,
        tree_sha="c" * 40,
        dirty_worktree=False,
        lockfile_sha256="d" * 64,
        artifact_sha256=art_sha,
        provenance_kind="NATIVE",
        machine_id="mock-runner-01",
        lifecycle_state="COMPLETE",
        exit_code=0,
        log_sha256=log_sha,
        test_ids=("TC-QA-001",),
    )
    with pytest.raises(PermissionError, match="MOCK_REPORT_CANNOT_CLAIM_NATIVE_MACHINE"):
        guard.register_and_verify_evidence_runs(
            candidate_sha=sha,
            expected_artifact_sha256=art_sha,
            required_test_ids=("TC-QA-001",),
            runs=(mock_native,),
        )


def test_cross_ingress_threat_and_compatibility_guards() -> None:
    guard = V1BaselineContractGuard()
    with pytest.raises(PermissionError, match="UNTRUSTED_RECOVERY_OR_GRANT_OVERRIDE_FORBIDDEN"):
        guard.verify_ingress_boundary(
            source_surface="owner_cli",
            target_action="recover_epoch",
            payload={"old_epoch_isolated": True},
        )
    with pytest.raises(PermissionError, match="TAINTED_SURFACE_CANNOT_AUTHORIZE"):
        guard.verify_ingress_boundary(
            source_surface="mcp_metadata",
            target_action="approve",
            payload={},
        )
    with pytest.raises(PermissionError, match="ARBITRARY_IPC_URL_FORBIDDEN"):
        guard.verify_ingress_boundary(
            source_surface="tauri_ipc",
            target_action="request",
            payload={"raw_url": "http://169.254.169.254"},
        )
    with pytest.raises(PermissionError, match="INCOMPATIBLE_PROTOCOL_MAJOR_VERSION"):
        guard.verify_api_version_compatibility(
            client_protocol_version="2.0",
            payload_fields=frozenset({"goal"}),
            allowed_fields=frozenset({"goal"}),
        )
    with pytest.raises(PermissionError, match="UNKNOWN_CONTRACT_FIELDS_REJECTED"):
        guard.verify_api_version_compatibility(
            client_protocol_version="1.0",
            payload_fields=frozenset({"goal", "unexpected_field"}),
            allowed_fields=frozenset({"goal"}),
        )


def test_seven_scenarios_and_sanitized_environment_inventory() -> None:
    runner = BenchmarkEvalRunner()
    observations = tuple(
        ScenarioEvidenceObservation(
            scenario_id=sid,
            entry_surface="daemon_cli",
            direct_sql_state_write_used=False,
            observable_artifact_sha256="e" * 64,
            independent_receiver_effect_count=1,
            in_process_self_counter_used=False,
            unresolved_unknown_count=(1 if sid == SEVENTH_SCENARIO else 0),
        )
        for sid in SEVEN_PRODUCT_SCENARIO_IDS
    )
    verdicts = runner.verify_seven_product_scenarios(observations)
    assert verdicts["S1_WORKSPACE_READ_SUMMARY"] == "VERIFIED"
    assert verdicts[SEVENTH_SCENARIO] == "RECONCILING"

    bad_sql = (
        ScenarioEvidenceObservation(
            scenario_id="S1_WORKSPACE_READ_SUMMARY",
            entry_surface="daemon_cli",
            direct_sql_state_write_used=True,
            observable_artifact_sha256="e" * 64,
            independent_receiver_effect_count=1,
            in_process_self_counter_used=False,
            unresolved_unknown_count=0,
        ),
        *observations[1:],
    )
    with pytest.raises(PermissionError, match="DIRECT_SQL_BYPASS_FORBIDDEN"):
        runner.verify_seven_product_scenarios(bad_sql)

    auditor = EnvironmentInventoryAuditor()
    inv = auditor.collect_sanitized_inventory({"docker_backend": "orbstack", "rust": "1.91.0"})
    assert inv["contains_raw_env_or_secrets"] is False
    with pytest.raises(PermissionError, match="ENVIRONMENT_INVENTORY_SECRET_LEAK_BLOCKED"):
        auditor.collect_sanitized_inventory({"OPENAI_API_KEY": "sk-12345"})


def test_workflow_triggers_and_supply_chain_sync_guard() -> None:
    evaluator = TieredCiGateEvaluator(ROOT)
    workflows = evaluator.validate_workflow_layout()
    assert len(workflows) == 5
    verifier = ReleaseSupplyChainVerifier(ROOT)
    synced = verifier.sync_checksums()
    assert "uv.lock" in synced
    assert verifier.verify_all().verified_artifacts_count == len(synced)
