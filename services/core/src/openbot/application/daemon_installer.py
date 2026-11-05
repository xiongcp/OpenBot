"""User-session daemon installer forbidding system services and preserving workspaces (OB-068)."""

import json
import os
import plistlib
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openbot.cli import discover_cli_session

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
    label: str = "com.openbot.user-daemon"
    plist_path: Path | None = None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform != "win32":
        try:
            waited_pid, _ = os.waitpid(pid, os.WNOHANG)
            if waited_pid == pid:
                return False
        except ChildProcessError:
            pass
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class UserDaemonInstaller:
    """Install/uninstall user-session daemon manifests while preserving workspaces."""

    def __init__(self, *, service_dir: Path, workspace_dir: Path) -> None:
        self._service_dir = service_dir.resolve()
        self._workspace_dir = workspace_dir.resolve()
        self._profile_dir = self._service_dir / "profile"
        self._active_proc: subprocess.Popen[str] | None = None

    def install(
        self,
        *,
        os_name: str,
        scope: str,
        spawn_from_tauri_ui: bool,
        profile_id: str = "pro_test1",
    ) -> InstalledUserServiceRecord:
        if scope != "user_session":
            raise PermissionError(f"SYSTEM_SERVICE_SCOPE_FORBIDDEN: {scope}")
        if spawn_from_tauri_ui:
            raise PermissionError("TAURI_DIRECT_DAEMON_SPAWN_FORBIDDEN")
        kind = _OS_SERVICE_KINDS.get(os_name)
        if kind is None:
            raise ValueError(f"Unsupported OS: {os_name}")
        self._service_dir.mkdir(parents=True, exist_ok=True)
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        label = f"com.openbot.user-daemon.{profile_id}"
        manifest_path = self._service_dir / "openbot-user-daemon.json"
        plist_path: Path | None = None
        if os_name == "Darwin":
            plist_path = self._service_dir / f"{label}.plist"
            plist_doc = {
                "Label": label,
                "ProgramArguments": [
                    sys.executable,
                    "-m",
                    "openbot",
                    "daemon",
                    "serve",
                    "--profile-dir",
                    str(self._profile_dir),
                    "--profile-id",
                    profile_id,
                ],
                "WorkingDirectory": str(self._workspace_dir),
                "StandardOutPath": str(self._service_dir / "daemon.stdout.log"),
                "StandardErrorPath": str(self._service_dir / "daemon.stderr.log"),
                "RunAtLoad": False,
                "KeepAlive": False,
                "EnvironmentVariables": {
                    "PATH": "/usr/bin:/bin",
                    "PYTHONNOUSERSITE": "1",
                },
            }
            plist_path.write_bytes(plistlib.dumps(plist_doc))
            if Path("/usr/bin/plutil").is_file() and sys.platform == "darwin":
                chk = subprocess.run(
                    ["/usr/bin/plutil", "-lint", str(plist_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if chk.returncode != 0:
                    raise RuntimeError(f"Invalid launchd plist: {chk.stdout} {chk.stderr}")

        manifest_path.write_text(
            json.dumps(
                {
                    "label": label,
                    "profile_id": profile_id,
                    "os_name": os_name,
                    "kind": kind,
                    "scope": "user_session",
                    "workspace_dir": str(self._workspace_dir),
                    "profile_dir": str(self._profile_dir),
                    "plist_path": str(plist_path) if plist_path else None,
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
            label=label,
            plist_path=plist_path,
        )

    def status(self) -> dict[str, Any]:
        manifest_path = self._service_dir / "openbot-user-daemon.json"
        manifest_present = manifest_path.is_file()
        session_path = self._profile_dir / "daemon_session.json"
        if not session_path.is_file():
            return {
                "manifest_present": manifest_present,
                "running": False,
                "pid": None,
                "health_ok": False,
            }
        meta = json.loads(session_path.read_text(encoding="utf-8"))
        pid = int(meta.get("pid", 0))
        alive = _pid_alive(pid)
        health_ok = False
        if alive:
            try:
                ses = discover_cli_session(self._profile_dir, timeout_seconds=1.5)
                if ses is not None:
                    resp = ses.call("GET", "/v1/health")
                    health_ok = resp.status_code == 200
            except Exception:
                health_ok = False
        return {
            "manifest_present": manifest_present,
            "running": alive and health_ok,
            "pid": pid if alive else None,
            "host": meta.get("host"),
            "runtime_epoch": meta.get("runtime_epoch"),
            "health_ok": health_ok,
        }

    def start_daemon(
        self,
        *,
        profile_id: str = "pro_test1",
        workspace_id: str = "wsp_test1",
        runtime_epoch: str = "ep_1",
    ) -> dict[str, Any]:
        cur = self.status()
        if cur["running"]:
            raise PermissionError(f"PROFILE_LOCK_HELD: daemon already running (pid={cur['pid']})")
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "openbot",
                "daemon",
                "serve",
                "--profile-dir",
                str(self._profile_dir),
                "--profile-id",
                profile_id,
                "--workspace-id",
                workspace_id,
                "--epoch",
                runtime_epoch,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        self._active_proc = proc
        assert proc.stdout is not None
        line = proc.stdout.readline().strip()
        if not line:
            err = proc.stderr.read() if proc.stderr else ""
            proc.wait(timeout=5)
            raise PermissionError(f"Daemon failed to start: {err}")
        meta = json.loads(line)
        if meta.get("code") == "DAEMON_LOCK_OR_PERMISSION_ERROR":
            proc.wait(timeout=5)
            raise PermissionError(str(meta.get("message", "PROFILE_LOCK_HELD")))
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            st = self.status()
            if st["running"] and st["pid"] == proc.pid:
                return {
                    "running": True,
                    "pid": proc.pid,
                    "host": meta["host"],
                    "runtime_epoch": runtime_epoch,
                }
            time.sleep(0.02)
        raise RuntimeError("Daemon process started but health endpoint did not become ready")

    def stop_daemon(self) -> dict[str, Any]:
        st = self.status()
        pid = st.get("pid")
        stopped = False
        if pid is not None and _pid_alive(int(pid)):
            try:
                os.kill(int(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if not _pid_alive(int(pid)):
                    break
                time.sleep(0.02)
            if _pid_alive(int(pid)):
                if sys.platform != "win32":
                    hard_sig: int = signal.SIGKILL
                else:
                    hard_sig = signal.SIGTERM
                try:
                    os.kill(int(pid), hard_sig)
                except ProcessLookupError:
                    pass
            stopped = True
        if self._active_proc is not None:
            try:
                self._active_proc.wait(timeout=2)
            except Exception:
                pass
            self._active_proc = None
        session_path = self._profile_dir / "daemon_session.json"
        if session_path.is_file():
            session_path.unlink()
            stopped = True
        return {
            "stopped": stopped,
            "pid": pid,
            "workspace_preserved": self._workspace_dir.is_dir(),
        }

    def restart_daemon(
        self,
        *,
        profile_id: str = "pro_test1",
        workspace_id: str = "wsp_test1",
        new_epoch: str,
    ) -> dict[str, Any]:
        self.stop_daemon()
        res = self.start_daemon(
            profile_id=profile_id, workspace_id=workspace_id, runtime_epoch=new_epoch
        )
        ses = discover_cli_session(self._profile_dir, timeout_seconds=2.0)
        if ses is not None:
            ses.call(
                "POST",
                "/v1/runtime/recover-epoch",
                body={"new_epoch": new_epoch, "old_epoch_isolated": True},
            )
        return res

    def uninstall(self) -> dict[str, Any]:
        self.stop_daemon()
        manifest_path = self._service_dir / "openbot-user-daemon.json"
        removed = False
        if manifest_path.is_file():
            manifest_path.unlink()
            removed = True
        for plist in self._service_dir.glob("*.plist"):
            plist.unlink()
        return {
            "manifest_removed": removed,
            "workspace_preserved": self._workspace_dir.is_dir(),
        }
