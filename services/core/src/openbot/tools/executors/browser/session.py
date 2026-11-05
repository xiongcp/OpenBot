"""Dedicated browser profile lock, Chromium sandbox guard, and cookie redaction (OB-057)."""

import os
import secrets
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

if sys.platform != "win32":
    import fcntl

_FORBIDDEN_BROWSER_ARGS = frozenset(
    {
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-web-security",
        "--remote-debugging-port",
    }
)


@dataclass(frozen=True, slots=True)
class BrowserIsolationAttestation:
    os_name: str
    chromium_sandbox_enabled: bool
    outer_isolation_verified: bool


@dataclass(frozen=True, slots=True)
class BrowserSessionSpec:
    profile_name: str
    user_data_dir: Path
    launch_args: tuple[str, ...]
    cdp_attach_url: str | None
    decrypt_system_cookies: bool
    isolation: BrowserIsolationAttestation


@dataclass(frozen=True, slots=True)
class BrowserSessionLease:
    session_id: str
    task_id: str
    profile_name: str
    user_data_dir: Path
    os_name: str
    chromium_sandbox_enabled: Literal[True] = True
    dedicated_profile_is_os_sandbox_proof: Literal[False] = False


class BrowserProfileSessionManager:
    """Enforce OpenBot-dedicated browser profile directories, sandbox args, and session locks."""

    def __init__(self, *, dedicated_root: Path) -> None:
        self._root = dedicated_root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._active_by_profile: dict[str, BrowserSessionLease] = {}
        self._active_by_id: dict[str, BrowserSessionLease] = {}
        self._lock_fds: dict[str, int] = {}

    def acquire_session(self, *, task_id: str, spec: BrowserSessionSpec) -> BrowserSessionLease:
        if spec.cdp_attach_url is not None:
            raise PermissionError("Attaching to arbitrary CDP ports is forbidden")
        if spec.decrypt_system_cookies:
            raise PermissionError("Decrypting user browser cookies is forbidden")
        if (
            not spec.isolation.chromium_sandbox_enabled
            or not spec.isolation.outer_isolation_verified
        ):
            raise PermissionError(
                "CAPABILITY_UNAVAILABLE: Chromium sandbox and outer isolation are both required"
            )
        for arg in spec.launch_args:
            flag = arg.split("=", 1)[0].strip().lower()
            if flag in _FORBIDDEN_BROWSER_ARGS:
                raise PermissionError(f"Forbidden browser launch flag: {arg}")

        resolved_dir = spec.user_data_dir.resolve()
        if resolved_dir == self._root or not resolved_dir.is_relative_to(self._root):
            raise PermissionError(
                "Browser user_data_dir must reside inside OpenBot dedicated profile root"
            )
        if spec.profile_name in self._active_by_profile:
            raise PermissionError(f"BROWSER_PROFILE_LOCKED: {spec.profile_name}")

        resolved_dir.mkdir(parents=True, exist_ok=True)
        lock_file = resolved_dir / ".openbot_profile.lock"
        if lock_file.is_symlink():
            raise PermissionError("Browser profile lock file must not be a symlink")
        fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if sys.platform != "win32":
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise PermissionError(f"BROWSER_PROFILE_LOCKED: {spec.profile_name}") from exc
        except BaseException:
            os.close(fd)
            raise

        lease = BrowserSessionLease(
            session_id="bsn_" + secrets.token_hex(10),
            task_id=task_id,
            profile_name=spec.profile_name,
            user_data_dir=resolved_dir,
            os_name=spec.isolation.os_name,
        )
        self._active_by_profile[spec.profile_name] = lease
        self._active_by_id[lease.session_id] = lease
        self._lock_fds[lease.session_id] = fd
        return lease

    def release_session(self, session_id: str) -> None:
        lease = self._active_by_id.pop(session_id, None)
        if lease is not None:
            self._active_by_profile.pop(lease.profile_name, None)
        fd = self._lock_fds.pop(session_id, None)
        if fd is not None:
            try:
                if sys.platform != "win32":
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    @staticmethod
    def discover_chromium_binary() -> Path | None:
        pw_cache = Path.home() / "Library/Caches/ms-playwright"
        if pw_cache.is_dir():
            for candidate in sorted(pw_cache.rglob("chrome-headless-shell")):
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return candidate
        chrome_app = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if chrome_app.is_file() and os.access(chrome_app, os.X_OK):
            return chrome_app
        return None

    def run_headless_dom_dump(
        self,
        lease: BrowserSessionLease,
        *,
        target_url: str,
        allowed_hosts: frozenset[str],
        binary_path: Path | None = None,
        timeout_seconds: float = 15.0,
    ) -> dict[str, Any]:
        if lease.session_id not in self._active_by_id:
            raise PermissionError("Browser session lease is not active")
        parsed = urlsplit(target_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or host not in {h.lower() for h in allowed_hosts}:
            raise PermissionError(f"EGRESS_HOST_FORBIDDEN: {target_url}")

        eff_bin = binary_path or self.discover_chromium_binary()
        if eff_bin is None or not eff_bin.is_file():
            raise PermissionError("BROWSER_BINARY_UNAVAILABLE")

        argv = [
            str(eff_bin),
            "--headless",
            f"--user-data-dir={lease.user_data_dir}",
            "--disable-background-networking",
            "--no-first-run",
            "--no-default-browser-check",
            "--dump-dom",
            target_url,
        ]
        for arg in argv:
            if arg.split("=", 1)[0].strip().lower() in _FORBIDDEN_BROWSER_ARGS:
                raise PermissionError(f"Forbidden browser launch flag: {arg}")

        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        worker_pid = proc.pid
        try:
            out, err = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            proc.wait(timeout=5)
            raise TimeoutError(f"Browser worker timed out (pid={worker_pid})") from exc
        if proc.returncode != 0:
            raise PermissionError(
                f"BROWSER_LAUNCH_OR_SANDBOX_FAILED (exit={proc.returncode}): {err[:160]}"
            )
        return {
            "session_id": lease.session_id,
            "worker_pid": worker_pid,
            "dom": out,
            "chromium_sandbox_enabled": True,
        }

    def export_artifact_safe_metadata(
        self, lease: BrowserSessionLease, *, raw_cookies: tuple[dict[str, Any], ...] = ()
    ) -> dict[str, Any]:
        return {
            "session_id": lease.session_id,
            "task_id": lease.task_id,
            "profile_name": lease.profile_name,
            "os_name": lease.os_name,
            "cookie_names_only": [str(c.get("name", "")) for c in raw_cookies],
            "cookie_values_redacted": True,
        }
