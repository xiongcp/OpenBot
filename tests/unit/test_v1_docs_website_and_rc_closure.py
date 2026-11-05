from pathlib import Path

import pytest
from openbot.application.mvp_release_gate import V1BaselineContractGuard

ROOT = Path(__file__).resolve().parents[2]


def test_v1_040_to_060_publication_consistency_website_and_templates(
    tmp_path: Path,
) -> None:
    guard = V1BaselineContractGuard()
    rep = guard.verify_publication_consistency(ROOT)
    assert rep["license"] == "Apache-2.0"
    assert rep["capabilities_count"] == 10
    assert rep["bilingual_website_verified"] is True

    for rel in (
        "LICENSE",
        "CONTRIBUTING.md",
        "SUPPORT.md",
        "CODE_OF_CONDUCT.md",
        "docs/project-status.json",
        "docs/project-status.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/PULL_REQUEST_TEMPLATE.md",
        "apps/website/package.json",
        "apps/website/astro.config.mjs",
        "apps/website/public/releases.manifest.json",
        "apps/website/public/robots.txt",
        "apps/website/public/sitemap.xml",
        "apps/website/src/pages/zh/index.html",
        "apps/website/src/pages/en/index.html",
    ):
        assert (ROOT / rel).is_file(), f"Missing deliverable: {rel}"

    with pytest.raises(PermissionError, match="PUBLICATION_SOURCE_OF_TRUTH_MISSING"):
        guard.verify_publication_consistency(tmp_path)
