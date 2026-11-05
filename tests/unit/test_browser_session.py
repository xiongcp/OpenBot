import subprocess
import sys
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


def test_cross_process_browser_profile_lock_and_headless_worker_launch(
    tmp_path: Path,
) -> None:
    dedicated_root = tmp_path / "cross_proc_profiles"
    dedicated_root.mkdir(parents=True, exist_ok=True)

    child_code = """
import sys
from pathlib import Path
from openbot.tools.executors.browser.session import (
    BrowserIsolationAttestation,
    BrowserProfileSessionManager,
    BrowserSessionSpec,
)
root = Path(sys.argv[1])
mgr = BrowserProfileSessionManager(dedicated_root=root)
lease = mgr.acquire_session(
    task_id="tsk_child",
    spec=BrowserSessionSpec(
        profile_name="p_shared",
        user_data_dir=root / "p_shared",
        launch_args=(),
        cdp_attach_url=None,
        decrypt_system_cookies=False,
        isolation=BrowserIsolationAttestation("Darwin", True, True),
    ),
)
print("LOCKED:" + lease.session_id, flush=True)
sys.stdin.read()
"""
    holder = subprocess.Popen(
        [sys.executable, "-c", child_code, str(dedicated_root)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        line = holder.stdout.readline().strip()
        assert line.startswith("LOCKED:")

        # Second OS process (this process) must be blocked by OS flock on p_shared
        mgr = BrowserProfileSessionManager(dedicated_root=dedicated_root)
        spec = BrowserSessionSpec(
            profile_name="p_shared",
            user_data_dir=dedicated_root / "p_shared",
            launch_args=(),
            cdp_attach_url=None,
            decrypt_system_cookies=False,
            isolation=BrowserIsolationAttestation("Darwin", True, True),
        )
        with pytest.raises(PermissionError, match="BROWSER_PROFILE_LOCKED"):
            mgr.acquire_session(task_id="tsk_parent", spec=spec)

        # Kill holder process (simulating crash) -> OS releases flock without deleting lock file
        holder.kill()
        holder.wait(timeout=5)

        lease2 = mgr.acquire_session(task_id="tsk_parent_after_crash", spec=spec)
        try:
            # Unauthorized egress URL is blocked before launching worker
            with pytest.raises(PermissionError, match="EGRESS_HOST_FORBIDDEN"):
                mgr.run_headless_dom_dump(
                    lease2,
                    target_url="http://evil.example.com/",
                    allowed_hosts=frozenset({"127.0.0.1"}),
                )

            # Failing browser binary raises PermissionError without --no-sandbox downgrade
            bad_bin = tmp_path / "bad_chromium.sh"
            bad_bin.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            bad_bin.chmod(0o755)
            with pytest.raises(PermissionError, match="BROWSER_LAUNCH_OR_SANDBOX_FAILED"):
                mgr.run_headless_dom_dump(
                    lease2,
                    target_url="http://127.0.0.1:80/",
                    allowed_hosts=frozenset({"127.0.0.1"}),
                    binary_path=bad_bin,
                )
        finally:
            mgr.release_session(lease2.session_id)
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait(timeout=5)
