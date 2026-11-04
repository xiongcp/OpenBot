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
