from pathlib import Path

import pytest
from openbot.tools.executors.browser.network_policy import (
    BrowserNetworkBoundaryConfig,
    BrowserNetworkPolicyEnforcer,
)


def test_browser_network_policy_blocks_ssrf_redirects_service_workers_and_unapproved_uploads(
    tmp_path: Path,
) -> None:
    dl_dir = tmp_path / "downloads"
    enforcer = BrowserNetworkPolicyEnforcer(
        BrowserNetworkBoundaryConfig(
            allowed_hosts=frozenset({"docs.example.com"}),
            service_workers_blocked=True,
            outer_network_namespace_verified=True,
            download_quarantine_dir=dl_dir,
            approved_upload_paths=frozenset({str((tmp_path / "approved.txt").resolve())}),
        )
    )
    assert enforcer.page_route_alone_is_complete_isolation is False

    # 1. Enabling Service Workers without outer network isolation is rejected
    with pytest.raises(PermissionError, match="SERVICE_WORKER_BYPASS_RISK"):
        BrowserNetworkPolicyEnforcer(
            BrowserNetworkBoundaryConfig(
                allowed_hosts=frozenset({"docs.example.com"}),
                service_workers_blocked=False,
                outer_network_namespace_verified=False,
                download_quarantine_dir=dl_dir,
                approved_upload_paths=frozenset(),
            )
        )

    # 2. Navigation, redirect, iframe, and subrequest to file/localhost/metadata are blocked
    for kind, bad_url in (
        ("navigation", "file:///etc/passwd"),
        ("redirect", "http://127.0.0.1:8080/admin"),
        ("subrequest", "http://169.254.169.254/latest/meta-data/"),
        ("iframe", "https://evil.example.org/frame"),
    ):
        with pytest.raises(PermissionError):
            enforcer.check_request(request_kind=kind, url=bad_url)

    assert (
        enforcer.check_request(request_kind="navigation", url="https://docs.example.com/guide")[
            "allowed"
        ]
        is True
    )

    # 3. Download filename traversal is sanitized into quarantine dir; unapproved upload is blocked
    safe_dl = enforcer.validate_download_target(suggested_filename="../../.bashrc")
    assert safe_dl.parent == dl_dir.resolve()
    assert ".." not in safe_dl.name

    with pytest.raises(PermissionError, match="UNAPPROVED_UPLOAD_FILE"):
        enforcer.validate_upload_path(tmp_path / "secret.key")
