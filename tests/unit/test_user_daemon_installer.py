from pathlib import Path

import pytest
from openbot.application.daemon_installer import UserDaemonInstaller


def test_user_daemon_installer_forbids_system_service_and_preserves_workspace_on_uninstall(
    tmp_path: Path,
) -> None:
    service_dir = tmp_path / "user_services"
    workspace_dir = tmp_path / "user_workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "important.py").write_text("keep = True\n", encoding="utf-8")

    installer = UserDaemonInstaller(service_dir=service_dir, workspace_dir=workspace_dir)

    # 1. System-level / root / LocalSystem service scope is strictly forbidden
    for bad_scope in ("system", "root", "LocalSystem"):
        with pytest.raises(PermissionError, match="SYSTEM_SERVICE_SCOPE_FORBIDDEN"):
            installer.install(os_name="Darwin", scope=bad_scope, spawn_from_tauri_ui=False)

    # 2. Tauri UI window is forbidden from spawning its own second daemon
    with pytest.raises(PermissionError, match="TAURI_DIRECT_DAEMON_SPAWN_FORBIDDEN"):
        installer.install(os_name="Darwin", scope="user_session", spawn_from_tauri_ui=True)

    # 3. Install user-session manifest and verify uninstall preserves workspace
    rec = installer.install(os_name="Darwin", scope="user_session", spawn_from_tauri_ui=False)
    assert rec.manifest_path.is_file()
    assert rec.kind == "macos_launchd_user_agent"

    uninst = installer.uninstall()
    assert uninst["manifest_removed"] is True
    assert uninst["workspace_preserved"] is True
    assert (workspace_dir / "important.py").is_file()


def test_user_daemon_real_lifecycle_start_status_restart_stop_and_plist_validation(
    tmp_path: Path,
) -> None:
    service_dir = tmp_path / "svc_live"
    workspace_dir = tmp_path / "ws_live"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "keep.txt").write_text("user data\n", encoding="utf-8")

    installer = UserDaemonInstaller(service_dir=service_dir, workspace_dir=workspace_dir)
    rec = installer.install(
        os_name="Darwin",
        scope="user_session",
        spawn_from_tauri_ui=False,
        profile_id="pro_mac_svc",
    )
    assert rec.plist_path is not None and rec.plist_path.is_file()

    # Manifest existence alone does NOT mean the daemon is running!
    st_before = installer.status()
    assert st_before["manifest_present"] is True
    assert st_before["running"] is False

    started = installer.start_daemon(
        profile_id="pro_mac_svc", workspace_id="wsp_test1", runtime_epoch="ep_svc_1"
    )
    try:
        assert started["running"] is True
        pid1 = int(started["pid"])
        assert pid1 > 0

        st_up = installer.status()
        assert st_up["running"] is True
        assert st_up["pid"] == pid1
        assert st_up["health_ok"] is True

        # Second start while running is rejected by single-instance profile lock
        with pytest.raises(PermissionError, match="PROFILE_LOCK_HELD|already running"):
            installer.start_daemon(
                profile_id="pro_mac_svc", workspace_id="wsp_test1", runtime_epoch="ep_svc_dup"
            )

        # Restart transitions to new epoch and new PID
        restarted = installer.restart_daemon(
            profile_id="pro_mac_svc", workspace_id="wsp_test1", new_epoch="ep_svc_2"
        )
        assert restarted["running"] is True
        assert int(restarted["pid"]) != pid1
        assert restarted["runtime_epoch"] == "ep_svc_2"
    finally:
        stopped = installer.stop_daemon()
        assert stopped["stopped"] is True
        assert stopped["workspace_preserved"] is True

    st_after = installer.status()
    assert st_after["running"] is False
    uninst = installer.uninstall()
    assert uninst["workspace_preserved"] is True
    assert (workspace_dir / "keep.txt").read_text(encoding="utf-8") == "user data\n"
