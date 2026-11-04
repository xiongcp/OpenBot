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
