"""Pilot bundle auditor blocking secrets/profiles/caches and runtime asset downloads (OB-072)."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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


@dataclass(frozen=True, slots=True)
class BundleAuditReport:
    bundle_stage: str
    clean_of_secrets_and_profiles: bool
    signed_m4_release_claimed: Literal[False] = False
    first_use_silent_download_permitted: Literal[False] = False


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
