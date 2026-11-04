"""User-session daemon installer forbidding system services and preserving workspaces (OB-068)."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_OS_SERVICE_KINDS = {
    "Darwin": "macos_launchd_user_agent",
    "Linux": "linux_systemd_user_unit",
    "Windows": "windows_user_logon_task",
}


@dataclass(frozen=True, slots=True)
class InstalledUserServiceRecord:
    os_name: str
    kind: str
    manifest_path: Path
    scope: str


class UserDaemonInstaller:
    """Install/uninstall user-session daemon manifests while preserving workspaces."""

    def __init__(self, *, service_dir: Path, workspace_dir: Path) -> None:
        self._service_dir = service_dir.resolve()
        self._workspace_dir = workspace_dir.resolve()

    def install(
        self, *, os_name: str, scope: str, spawn_from_tauri_ui: bool
    ) -> InstalledUserServiceRecord:
        if scope != "user_session":
            raise PermissionError(f"SYSTEM_SERVICE_SCOPE_FORBIDDEN: {scope}")
        if spawn_from_tauri_ui:
            raise PermissionError("TAURI_DIRECT_DAEMON_SPAWN_FORBIDDEN")
        kind = _OS_SERVICE_KINDS.get(os_name)
        if kind is None:
            raise ValueError(f"Unsupported OS: {os_name}")
        self._service_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self._service_dir / "openbot-user-daemon.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "label": "com.openbot.user-daemon",
                    "os_name": os_name,
                    "kind": kind,
                    "scope": "user_session",
                    "workspace_dir": str(self._workspace_dir),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return InstalledUserServiceRecord(
            os_name=os_name,
            kind=kind,
            manifest_path=manifest_path,
            scope=scope,
        )

    def uninstall(self) -> dict[str, Any]:
        manifest_path = self._service_dir / "openbot-user-daemon.json"
        removed = False
        if manifest_path.is_file():
            manifest_path.unlink()
            removed = True
        return {
            "manifest_removed": removed,
            "workspace_preserved": self._workspace_dir.is_dir(),
        }
