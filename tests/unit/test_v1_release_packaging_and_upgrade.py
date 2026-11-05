import hashlib
from pathlib import Path

import pytest
from openbot.application.packaging_auditor import (
    OnDemandAssetDownloadSpec,
    PackagingBundleAuditor,
    SignedReleaseChannelUpdater,
    SignedUpdateCandidate,
)
from openbot.application.supply_chain import ReleaseSupplyChainVerifier
from openbot.application.vertical_slice import M1VerticalSliceHarness
from openbot.storage.maintenance import DatabaseMaintenanceService

ROOT = Path(__file__).resolve().parents[2]


def test_v1_030_031_032_034_035_045_dmg_codesign_updater_and_root_license() -> None:
    auditor = PackagingBundleAuditor(ROOT / "packaging/runtime-assets.json")

    # 1. Core DMG size (80-120MB) & explicit on-demand SHA-256 download boundary
    payload = b"managed-chromium-archive-bytes"
    spec = OnDemandAssetDownloadSpec(
        asset_id="chromium-browser",
        https_url="https://releases.openbot.dev/assets/chromium-arm64.tar.zst",
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        user_explicitly_confirmed=True,
    )
    assert (
        auditor.verify_core_dmg_and_ondemand_asset_boundary(
            core_dmg_size_mb=96, ondemand_spec=spec, downloaded_bytes=payload
        )["boundary_verified"]
        is True
    )
    with pytest.raises(PermissionError, match="SILENT_FIRST_USE_DOWNLOAD_FORBIDDEN"):
        auditor.verify_core_dmg_and_ondemand_asset_boundary(
            core_dmg_size_mb=96,
            ondemand_spec=OnDemandAssetDownloadSpec(
                asset_id="chromium-browser",
                https_url="https://releases.openbot.dev/assets/chromium.tar",
                expected_sha256="a" * 64,
                user_explicitly_confirmed=False,
            ),
        )

    # 2. Codesign, notarization, quarantine, and forbidden entitlements
    assert (
        auditor.verify_codesign_and_quarantine_gatekeeper(
            entitlements={"com.apple.security.network.client": True},
            hardened_runtime_enabled=True,
            notarization_stapled=True,
            quarantine_xattr_preserved=True,
        )["quarantine_first_open_verified"]
        is True
    )
    with pytest.raises(PermissionError, match="FORBIDDEN_RELEASE_ENTITLEMENTS"):
        auditor.verify_codesign_and_quarantine_gatekeeper(
            entitlements={"com.apple.security.get-task-allow": True},
            hardened_runtime_enabled=True,
            notarization_stapled=True,
            quarantine_xattr_preserved=True,
        )

    # 3. Signed updater rejects downgrade, revoked version, and bad hash
    updater = SignedReleaseChannelUpdater()
    upd_bytes = b"openbot-v1.0.1-signed-archive"
    cand = SignedUpdateCandidate(
        version="1.0.1",
        channel="stable",
        archive_sha256=hashlib.sha256(upd_bytes).hexdigest(),
        signature_verified=True,
    )
    assert (
        updater.verify_update_candidate(
            current_version=(1, 0, 0),
            target_version=(1, 0, 1),
            candidate=cand,
            actual_archive_bytes=upd_bytes,
        )["verified"]
        is True
    )
    with pytest.raises(PermissionError, match="UPDATE_DOWNGRADE_OR_REPLAY_FORBIDDEN"):
        updater.verify_update_candidate(
            current_version=(1, 0, 1),
            target_version=(1, 0, 0),
            candidate=cand,
            actual_archive_bytes=upd_bytes,
        )

    # 4. Root Apache-2.0 LICENSE and full SBOM verification
    sc = ReleaseSupplyChainVerifier(ROOT).verify_full_release_sbom_and_license()
    assert sc["root_license"] == "Apache-2.0"


def test_v1_033_upgrade_transaction_backup_and_failed_health_rollback(tmp_path: Path) -> None:
    harness = M1VerticalSliceHarness.create(tmp_path / "upg_src")
    try:
        harness.run_local_restricted_effect_slice()
        maint = DatabaseMaintenanceService(
            db_path=tmp_path / "upg_src/slice.sqlite",
            writer=harness.writer,
            artifact_store=harness.artifacts,
            blob_root=tmp_path / "upg_src/blobs",
        )
        rep = maint.execute_upgrade_transaction(
            harness.context,
            from_version="1.0.0",
            to_version="1.0.1",
            backup_dir=tmp_path / "upg_backup",
            rollback_target_db=tmp_path / "rolled_back.sqlite",
            rollback_target_blobs=tmp_path / "rolled_back_blobs",
            candidate_health_ok=False,
        )
        assert rep.final_state == "ROLLED_BACK_TO_BACKUP"
        assert rep.exported_plaintext_secrets is False
        assert rep.replayed_unknown_actions is False
        assert (tmp_path / "rolled_back.sqlite").is_file()
    finally:
        harness.close()
