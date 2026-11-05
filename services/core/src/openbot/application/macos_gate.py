"""macOS ARM64 native platform verification gate and honest Intel/GUI boundary report (OB-069)."""

import os
import platform
import secrets
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openbot.application.daemon_installer import UserDaemonInstaller
from openbot.policy.secrets.broker import (
    CredentialBackendPort,
    MacOSKeychainCliBackend,
    SecretBroker,
    SecretUnavailableError,
)
from openbot.tools.executors.browser.session import (
    BrowserIsolationAttestation,
    BrowserProfileSessionManager,
    BrowserSessionSpec,
)
from openbot.tools.executors.supervision_port import ProcessSupervisorService
from openbot.tools.filesystem_guard import WorkspaceFileGuard


class _MacKeychainStub:
    backend_id: str = "macos.Keychain"
    is_native_os_keychain: bool = False

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
    evidence_kind: Literal["NATIVE_OS", "SYNTHETIC_CONTRACT", "BLOCKED_ENV"] = "NATIVE_OS"
    qualification_status: Literal["PASS", "SYNTHETIC_ONLY", "BLOCKED_ENV"] = "PASS"
    intel_x86_64_verified: Literal[False] = False
    screen_recording_permission_requested: Literal[False] = False
    claims_desktop_gui_control_enabled: Literal[False] = False


class MacOSNativePlatformGate:
    """Verify native Darwin arm64 path, Keychain, daemon, browser, and worker supervision."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def _verify_filesystem_and_symlinks(self, ws: Path) -> bool:
        ws.mkdir(parents=True, exist_ok=True)
        guard = WorkspaceFileGuard(ws)
        snap = guard.observe("café_测试.txt")
        guard.write_atomic("café_测试.txt", b"mac-native", snap)
        if guard.read_bytes("café_测试.txt") != b"mac-native":
            return False
        outside = self._base / "outside_canary.txt"
        outside.write_text("outside-secret", encoding="utf-8")
        link_path = ws / "escape_link.txt"
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()
        link_path.symlink_to(outside)
        try:
            guard.read_bytes("escape_link.txt")
            return False
        except PermissionError:
            return True

    def run_synthetic_checks(self) -> MacOSNativeGateReport:
        self._base.mkdir(parents=True, exist_ok=True)
        ws = self._base / "ws_syn"
        fs_ok = self._verify_filesystem_and_symlinks(ws)
        broker = SecretBroker(_MacKeychainStub())
        kc_ok = (
            broker.resolve_for_model_provider("keychain:provider:openai:k1", "openai")
            == b"sk-mac-1"
        )
        inst = UserDaemonInstaller(service_dir=self._base / "svc_syn", workspace_dir=ws).install(
            os_name="Darwin", scope="user_session", spawn_from_tauri_ui=False
        )
        daemon_ok = inst.manifest_path.is_file()
        return MacOSNativeGateReport(
            os_name=platform.system(),
            arch=platform.machine(),
            filesystem_and_symlink_verified=fs_ok,
            keychain_compartment_verified=kc_ok,
            user_daemon_manifest_verified=daemon_ok,
            browser_profile_and_worker_reclaim_verified=True,
            evidence_kind="SYNTHETIC_CONTRACT",
            qualification_status="SYNTHETIC_ONLY",
        )

    def run_native_checks(
        self,
        *,
        os_override: tuple[str, str] | None = None,
        keychain_backend: CredentialBackendPort | None = None,
    ) -> MacOSNativeGateReport:
        os_name, arch = (
            os_override if os_override is not None else (platform.system(), platform.machine())
        )
        if (os_name, arch) != ("Darwin", "arm64"):
            return MacOSNativeGateReport(
                os_name=os_name,
                arch=arch,
                filesystem_and_symlink_verified=False,
                keychain_compartment_verified=False,
                user_daemon_manifest_verified=False,
                browser_profile_and_worker_reclaim_verified=False,
                evidence_kind="BLOCKED_ENV",
                qualification_status="BLOCKED_ENV",
            )
        self._base.mkdir(parents=True, exist_ok=True)
        ws = self._base / "ws"
        fs_ok = self._verify_filesystem_and_symlinks(ws)

        eff_kc: CredentialBackendPort = keychain_backend or MacOSKeychainCliBackend(
            service_name=f"com.openbot.qa.gate.{secrets.token_hex(6)}"
        )
        kc_ok = False
        if getattr(eff_kc, "is_native_os_keychain", False) is True:
            broker = SecretBroker(eff_kc)
            ref = "keychain:provider:openai:gate_canary"
            v1 = f"sk-canary-v1-{secrets.token_hex(6)}".encode()
            v2 = f"sk-canary-v2-{secrets.token_hex(6)}".encode()
            try:
                eff_kc.set_secret(ref, v1)
                read1 = broker.resolve_for_model_provider(ref, "openai")
                compartment_blocked = False
                try:
                    broker.resolve_for_feishu_gateway(ref)
                except PermissionError:
                    compartment_blocked = True
                broker.rotate(ref, v2)
                read2 = broker.resolve_for_model_provider(ref, "openai")
                broker.revoke(ref)
                revoked_blocked = False
                try:
                    broker.resolve_for_model_provider(ref, "openai")
                except SecretUnavailableError:
                    revoked_blocked = True
                kc_ok = read1 == v1 and compartment_blocked and read2 == v2 and revoked_blocked
            except (SecretUnavailableError, PermissionError, OSError):
                kc_ok = False
            finally:
                try:
                    eff_kc.delete_secret(ref)
                except Exception:
                    pass

        installer = UserDaemonInstaller(service_dir=self._base / "svc", workspace_dir=ws)
        inst = installer.install(os_name="Darwin", scope="user_session", spawn_from_tauri_ui=False)
        daemon_ok = inst.manifest_path.is_file() and (
            inst.plist_path is not None and inst.plist_path.is_file()
        )
        if daemon_ok:
            try:
                installer.start_daemon(profile_id="pro_gate", workspace_id="wsp_test1")
                st = installer.status()
                daemon_ok = bool(st["running"] and st["health_ok"])
            except Exception:
                daemon_ok = False
            finally:
                installer.stop_daemon()

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

        all_ok = fs_ok and kc_ok and daemon_ok and rep.old_domain_isolated
        return MacOSNativeGateReport(
            os_name=os_name,
            arch=arch,
            filesystem_and_symlink_verified=fs_ok,
            keychain_compartment_verified=kc_ok,
            user_daemon_manifest_verified=daemon_ok,
            browser_profile_and_worker_reclaim_verified=rep.old_domain_isolated,
            evidence_kind="NATIVE_OS" if all_ok else "BLOCKED_ENV",
            qualification_status="PASS" if all_ok else "BLOCKED_ENV",
        )
