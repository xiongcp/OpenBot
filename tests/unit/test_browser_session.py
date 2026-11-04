from pathlib import Path

import pytest
from openbot.tools.executors.browser.session import (
    BrowserIsolationAttestation,
    BrowserProfileSessionManager,
    BrowserSessionSpec,
)


def test_browser_session_enforces_dedicated_profile_rejects_no_sandbox_and_cdp_attach(
    tmp_path: Path,
) -> None:
    dedicated_root = tmp_path / "openbot_browser_profiles"
    user_chrome_dir = tmp_path / "Library/Application Support/Google/Chrome"
    user_chrome_dir.mkdir(parents=True, exist_ok=True)

    mgr = BrowserProfileSessionManager(dedicated_root=dedicated_root)
    valid_att = BrowserIsolationAttestation(
        os_name="Darwin",
        chromium_sandbox_enabled=True,
        outer_isolation_verified=True,
    )

    # 1. Rejects user default Chrome profile, CDP attach URL, cookie decryption, or --no-sandbox
    for bad_spec in (
        BrowserSessionSpec(
            profile_name="default",
            user_data_dir=user_chrome_dir,
            launch_args=(),
            cdp_attach_url=None,
            decrypt_system_cookies=False,
            isolation=valid_att,
        ),
        BrowserSessionSpec(
            profile_name="p1",
            user_data_dir=dedicated_root / "p1",
            launch_args=("--no-sandbox",),
            cdp_attach_url=None,
            decrypt_system_cookies=False,
            isolation=valid_att,
        ),
        BrowserSessionSpec(
            profile_name="p1",
            user_data_dir=dedicated_root / "p1",
            launch_args=(),
            cdp_attach_url="http://127.0.0.1:9222",
            decrypt_system_cookies=False,
            isolation=valid_att,
        ),
        BrowserSessionSpec(
            profile_name="p1",
            user_data_dir=dedicated_root / "p1",
            launch_args=(),
            cdp_attach_url=None,
            decrypt_system_cookies=True,
            isolation=valid_att,
        ),
        BrowserSessionSpec(
            profile_name="p1",
            user_data_dir=dedicated_root / "p1",
            launch_args=(),
            cdp_attach_url=None,
            decrypt_system_cookies=False,
            isolation=BrowserIsolationAttestation(
                os_name="Darwin",
                chromium_sandbox_enabled=False,
                outer_isolation_verified=True,
            ),
        ),
    ):
        with pytest.raises(PermissionError):
            mgr.acquire_session(task_id="tsk_1", spec=bad_spec)

    # 2. Valid dedicated profile acquires lock; concurrent task on same profile gets PROFILE_LOCKED
    good_spec = BrowserSessionSpec(
        profile_name="work_p1",
        user_data_dir=dedicated_root / "work_p1",
        launch_args=("--disable-background-networking",),
        cdp_attach_url=None,
        decrypt_system_cookies=False,
        isolation=valid_att,
    )
    lease = mgr.acquire_session(task_id="tsk_1", spec=good_spec)
    assert lease.chromium_sandbox_enabled is True
    assert lease.dedicated_profile_is_os_sandbox_proof is False

    with pytest.raises(PermissionError, match="BROWSER_PROFILE_LOCKED"):
        mgr.acquire_session(task_id="tsk_2", spec=good_spec)

    # 3. Exporting session state for Artifact strips sensitive cookies/storage tokens
    safe_meta = mgr.export_artifact_safe_metadata(
        lease, raw_cookies=({"name": "SID", "value": "secret_cookie_123"},)
    )
    assert "secret_cookie_123" not in str(safe_meta)
    mgr.release_session(lease.session_id)
