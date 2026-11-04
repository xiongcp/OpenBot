from pathlib import Path

import pytest
from openbot.application.packaging_auditor import PackagingBundleAuditor

ROOT = Path(__file__).resolve().parents[2]


def test_packaging_auditor_blocks_secrets_and_caches_and_forbids_first_use_downloads(
    tmp_path: Path,
) -> None:
    assert (ROOT / "packaging/runtime-assets.json").is_file()
    assert (ROOT / "docs/runtime-dependencies.md").is_file()
    assert (ROOT / "scripts/build/build_pilot_bundle.py").is_file()

    auditor = PackagingBundleAuditor(ROOT / "packaging/runtime-assets.json")
    clean_bundle = tmp_path / "bundle_clean"
    clean_bundle.mkdir(parents=True, exist_ok=True)
    (clean_bundle / "openbot-cli").write_text("#!/bin/sh\n", encoding="utf-8")

    rep = auditor.audit_bundle_directory(clean_bundle)
    assert rep.signed_m4_release_claimed is False
    assert rep.first_use_silent_download_permitted is False
    assert rep.clean_of_secrets_and_profiles is True

    # Dirty bundle with .env, profile sqlite, or cache is rejected
    dirty_bundle = tmp_path / "bundle_dirty"
    dirty_bundle.mkdir(parents=True, exist_ok=True)
    (dirty_bundle / ".env").write_text("OPENAI_API_KEY=sk-123", encoding="utf-8")
    with pytest.raises(PermissionError, match="BUNDLE_CONTAINS_FORBIDDEN_ARTIFACT"):
        auditor.audit_bundle_directory(dirty_bundle)
