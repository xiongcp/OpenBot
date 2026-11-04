from pathlib import Path

import pytest
from openbot.application.supply_chain import ReleaseSupplyChainVerifier

ROOT = Path(__file__).resolve().parents[2]


def test_release_supply_chain_verifies_spdx_notices_and_checksums_and_rejects_tampering() -> None:
    assert (ROOT / "scripts/check_release_components.py").is_file()
    assert (ROOT / "docs/releases/component-supply-chain.md").is_file()
    assert (ROOT / "release/SBOM/spdx-pilot.spdx.json").is_file()
    assert (ROOT / "release/THIRD_PARTY_NOTICES.md").is_file()
    assert (ROOT / "release/checksums.json").is_file()

    verifier = ReleaseSupplyChainVerifier(ROOT)
    report = verifier.verify_all()
    assert report.sbom_standard == "SPDX-2.3"
    assert report.includes_non_python_assets is True
    assert report.pinned_versions_guarantee_zero_vulnerabilities is False

    with pytest.raises(PermissionError, match="SUPPLY_CHAIN_HASH_TAMPERED"):
        verifier.verify_all(tamper_key="uv.lock")
