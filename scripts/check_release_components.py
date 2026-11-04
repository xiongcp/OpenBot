"""CLI gate verifying release SBOM, third-party notices, and artifact SHA-256 checksums (OB-096)."""

import json
from pathlib import Path

from openbot.application.supply_chain import ReleaseSupplyChainVerifier

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    rep = ReleaseSupplyChainVerifier(ROOT).verify_all()
    zero_vuln = rep.pinned_versions_guarantee_zero_vulnerabilities
    print(
        json.dumps(
            {
                "sbom_standard": rep.sbom_standard,
                "verified_artifacts_count": rep.verified_artifacts_count,
                "includes_non_python_assets": rep.includes_non_python_assets,
                "pinned_versions_guarantee_zero_vulnerabilities": zero_vuln,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
