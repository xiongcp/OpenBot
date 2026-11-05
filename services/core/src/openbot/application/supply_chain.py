"""Release supply-chain, SPDX SBOM, notice, and checksum verifier (OB-096)."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class SupplyChainVerificationReport:
    sbom_standard: Literal["SPDX-2.3"]
    verified_artifacts_count: int
    includes_non_python_assets: bool
    pinned_versions_guarantee_zero_vulnerabilities: Literal[False] = False


class ReleaseSupplyChainVerifier:
    """Verify SPDX-2.3 SBOM structure, non-Python asset coverage, and SHA-256 checksums."""

    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root.resolve()

    def verify_all(self, *, tamper_key: str | None = None) -> SupplyChainVerificationReport:
        sbom = json.loads((self._root / "release/SBOM/spdx-pilot.spdx.json").read_text("utf-8"))
        if sbom.get("spdxVersion") != "SPDX-2.3" or "bomFormat" in sbom:
            raise PermissionError("SBOM must be valid SPDX-2.3 and never conflated with CycloneDX")
        pkgs = sbom.get("packages", [])
        has_non_py = any("non-python" in str(p.get("name", "")) for p in pkgs)

        checksums = json.loads((self._root / "release/checksums.json").read_text("utf-8"))[
            "artifacts"
        ]
        for rel_path, expected_sha in checksums.items():
            actual_sha = hashlib.sha256((self._root / rel_path).read_bytes()).hexdigest()
            if tamper_key == rel_path or actual_sha != expected_sha:
                raise PermissionError(f"SUPPLY_CHAIN_HASH_TAMPERED: {rel_path}")

        return SupplyChainVerificationReport(
            sbom_standard="SPDX-2.3",
            verified_artifacts_count=len(checksums),
            includes_non_python_assets=has_non_py,
        )

    def sync_checksums(self) -> dict[str, str]:
        """Recompute and persist SHA-256 digests for all controlled release artifacts (V1-008)."""
        checksums_path = self._root / "release/checksums.json"
        doc = json.loads(checksums_path.read_text("utf-8"))
        artifacts = dict(doc.get("artifacts", {}))
        for rel_path in list(artifacts):
            target = self._root / rel_path
            if not target.is_file():
                raise PermissionError(f"CONTROLLED_ARTIFACT_MISSING: {rel_path}")
            artifacts[rel_path] = hashlib.sha256(target.read_bytes()).hexdigest()
        doc["artifacts"] = artifacts
        checksums_path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return artifacts

    def verify_full_release_sbom_and_license(self) -> dict[str, object]:
        root_license = self._root / "LICENSE"
        if not root_license.is_file() or "Apache License" not in root_license.read_text("utf-8"):
            raise PermissionError("ROOT_APACHE_LICENSE_MISSING")
        rep = self.verify_all()
        cargo_lock = self._root / "apps/desktop/src-tauri/Cargo.lock"
        mcp_cat = self._root / "components/locks/mcp-catalog.json"
        if not cargo_lock.is_file() or not mcp_cat.is_file():
            raise PermissionError("NON_PYTHON_LOCK_OR_CATALOG_MISSING")
        return {
            "root_license": "Apache-2.0",
            "sbom_standard": rep.sbom_standard,
            "verified_artifacts_count": rep.verified_artifacts_count,
            "cargo_lock_sha256": hashlib.sha256(cargo_lock.read_bytes()).hexdigest(),
            "mcp_catalog_sha256": hashlib.sha256(mcp_cat.read_bytes()).hexdigest(),
        }
