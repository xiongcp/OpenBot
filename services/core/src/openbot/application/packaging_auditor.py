"""Pilot bundle auditor blocking secrets/profiles/caches and runtime asset downloads (OB-072)."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

_FORBIDDEN_BUNDLE_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        "profile.sqlite",
        "slice.sqlite",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
    }
)
_FORBIDDEN_RELEASE_ENTITLEMENTS = frozenset(
    {
        "com.apple.security.cs.disable-library-validation",
        "com.apple.security.cs.allow-unsigned-executable-memory",
        "com.apple.security.cs.allow-dyld-environment-variables",
        "com.apple.security.get-task-allow",
    }
)


@dataclass(frozen=True, slots=True)
class BundleAuditReport:
    bundle_stage: str
    clean_of_secrets_and_profiles: bool
    signed_m4_release_claimed: Literal[False] = False
    first_use_silent_download_permitted: Literal[False] = False


@dataclass(frozen=True, slots=True)
class OnDemandAssetDownloadSpec:
    asset_id: str
    https_url: str
    expected_sha256: str
    user_explicitly_confirmed: bool


@dataclass(frozen=True, slots=True)
class SignedUpdateCandidate:
    version: str
    channel: Literal["beta", "stable"]
    archive_sha256: str
    signature_verified: bool
    is_revoked: bool = False


class PackagingBundleAuditor:
    """Verify bundle directory cleanliness and offline-first asset manifest."""

    def __init__(self, manifest_path: Path) -> None:
        self._manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    def audit_bundle_directory(self, bundle_dir: Path) -> BundleAuditReport:
        for p in bundle_dir.rglob("*"):
            if p.name in _FORBIDDEN_BUNDLE_NAMES or p.suffix in {".sqlite", ".key", ".pem"}:
                raise PermissionError(f"BUNDLE_CONTAINS_FORBIDDEN_ARTIFACT: {p.name}")
        return BundleAuditReport(
            bundle_stage=str(self._manifest.get("bundle_stage", "M3_UNSIGNED_PILOT")),
            clean_of_secrets_and_profiles=True,
        )

    def verify_core_dmg_and_ondemand_asset_boundary(
        self,
        *,
        core_dmg_size_mb: int,
        ondemand_spec: OnDemandAssetDownloadSpec | None = None,
        downloaded_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        if not 50 <= core_dmg_size_mb <= 160:
            raise PermissionError(f"CORE_DMG_SIZE_OUT_OF_BOUNDS: {core_dmg_size_mb}MB")
        if ondemand_spec is not None:
            if not ondemand_spec.user_explicitly_confirmed:
                raise PermissionError("SILENT_FIRST_USE_DOWNLOAD_FORBIDDEN")
            if not ondemand_spec.https_url.startswith("https://"):
                raise PermissionError("ONDEMAND_ASSET_HTTPS_REQUIRED")
            if downloaded_bytes is not None:
                actual = hashlib.sha256(downloaded_bytes).hexdigest()
                if actual != ondemand_spec.expected_sha256:
                    raise PermissionError("ONDEMAND_ASSET_SHA256_MISMATCH")
        return {"core_dmg_size_mb": core_dmg_size_mb, "boundary_verified": True}

    def verify_codesign_and_quarantine_gatekeeper(
        self,
        *,
        entitlements: dict[str, bool],
        hardened_runtime_enabled: bool,
        notarization_stapled: bool,
        quarantine_xattr_preserved: bool,
    ) -> dict[str, bool]:
        forbidden = {
            k for k, v in entitlements.items() if v and k in _FORBIDDEN_RELEASE_ENTITLEMENTS
        }
        if forbidden:
            raise PermissionError(f"FORBIDDEN_RELEASE_ENTITLEMENTS: {sorted(forbidden)}")
        if (
            not hardened_runtime_enabled
            or not notarization_stapled
            or not quarantine_xattr_preserved
        ):
            raise PermissionError("CODESIGN_NOTARIZATION_OR_QUARANTINE_UNVERIFIED")
        return {
            "hardened_runtime": True,
            "notarization_stapled": True,
            "quarantine_first_open_verified": True,
        }


class SignedReleaseChannelUpdater:
    """Verify signed update candidates, channel rules, downgrade block, and revocation (V1-034)."""

    def verify_update_candidate(
        self,
        *,
        current_version: tuple[int, int, int],
        target_version: tuple[int, int, int],
        candidate: SignedUpdateCandidate,
        actual_archive_bytes: bytes,
    ) -> dict[str, Any]:
        if candidate.is_revoked:
            raise PermissionError(f"UPDATE_VERSION_REVOKED: {candidate.version}")
        if not candidate.signature_verified:
            raise PermissionError("UPDATE_SIGNATURE_INVALID")
        if target_version <= current_version:
            raise PermissionError("UPDATE_DOWNGRADE_OR_REPLAY_FORBIDDEN")
        actual_sha = hashlib.sha256(actual_archive_bytes).hexdigest()
        if actual_sha != candidate.archive_sha256:
            raise PermissionError("UPDATE_ARCHIVE_SHA256_MISMATCH")
        return {
            "version": candidate.version,
            "channel": candidate.channel,
            "sha256": actual_sha,
            "verified": True,
        }
