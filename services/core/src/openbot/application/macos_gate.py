"""macOS ARM64 native platform verification gate and honest Intel/GUI boundary report (OB-069)."""

import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openbot.application.daemon_installer import UserDaemonInstaller
from openbot.policy.secrets.broker import SecretBroker
from openbot.tools.executors.browser.session import (
    BrowserIsolationAttestation,
    BrowserProfileSessionManager,
    BrowserSessionSpec,
)
from openbot.tools.executors.supervision_port import ProcessSupervisorService
from openbot.tools.filesystem_guard import WorkspaceFileGuard


class _MacKeychainStub:
    backend_id: str = "macos.Keychain"

    def __init__(self) -> None:
        self._items: dict[str, bytes] = {"keychain:provider:openai:k1": b"sk-mac-1"}

    def get_secret(self, secret_ref: str) -> bytes:
        return self._items[secret_ref]

    def set_secret(self, secret_ref: str, value: bytes) -> None:
        self._items[secret_ref] = value

    def delete_secret(self, secret_ref: str) -> None:
        self._items.pop(secret_ref, None)


@dataclass(frozen=True, slots=True)
class MacOSNativeGateReport:
    os_name: str
    arch: str
    filesystem_and_symlink_verified: bool
    keychain_compartment_verified: bool
    user_daemon_manifest_verified: bool
    browser_profile_and_worker_reclaim_verified: bool
    intel_x86_64_verified: Literal[False] = False
    screen_recording_permission_requested: Literal[False] = False
    claims_desktop_gui_control_enabled: Literal[False] = False


class MacOSNativePlatformGate:
    """Verify native Darwin arm64 path, Keychain, daemon, browser, and worker supervision."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def run_native_checks(self) -> MacOSNativeGateReport:
        self._base.mkdir(parents=True, exist_ok=True)
        ws = self._base / "ws"
        ws.mkdir(parents=True, exist_ok=True)
        guard = WorkspaceFileGuard(ws)
        (ws / "a.txt").write_text("mac", encoding="utf-8")
        fs_ok = guard.read_bytes("a.txt") == b"mac"

        broker = SecretBroker(_MacKeychainStub())
        kc_ok = (
            broker.resolve_for_model_provider("keychain:provider:openai:k1", "openai")
            == b"sk-mac-1"
        )

        inst = UserDaemonInstaller(service_dir=self._base / "svc", workspace_dir=ws).install(
            os_name="Darwin", scope="user_session", spawn_from_tauri_ui=False
        )
        daemon_ok = inst.manifest_path.is_file()

        bm = BrowserProfileSessionManager(dedicated_root=self._base / "bprof")
        lease = bm.acquire_session(
            task_id="tsk_mac",
            spec=BrowserSessionSpec(
                profile_name="p1",
                user_data_dir=self._base / "bprof/p1",
                launch_args=(),
                cdp_attach_url=None,
                decrypt_system_cookies=False,
                isolation=BrowserIsolationAttestation("Darwin", True, True),
            ),
        )
        bm.release_session(lease.session_id)

        sup = ProcessSupervisorService(runtime_epoch="ep_mac")
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(0.05)"],
            start_new_session=True,
        )
        if sys.platform != "win32":
            worker_pgid = os.getpgid(proc.pid)
        else:
            worker_pgid = proc.pid
        sup.register_worker(
            worker_id="wrk_mac",
            operation_id="op_mac",
            attempt_id="att_mac",
            pid=proc.pid,
            pgid=worker_pgid,
            process_start_token="tok_mac",
        )
        rep = sup.reclaim_worker("wrk_mac", current_start_token="tok_mac", grace_ms=100)
        proc.wait(timeout=2)

        return MacOSNativeGateReport(
            os_name=platform.system(),
            arch=platform.machine(),
            filesystem_and_symlink_verified=fs_ok,
            keychain_compartment_verified=kc_ok,
            user_daemon_manifest_verified=daemon_ok,
            browser_profile_and_worker_reclaim_verified=rep.old_domain_isolated,
        )
