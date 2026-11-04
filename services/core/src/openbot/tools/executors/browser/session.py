"""Dedicated browser profile lock, Chromium sandbox guard, and cookie redaction (OB-057)."""

import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

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
        lease = BrowserSessionLease(
            session_id="bsn_" + secrets.token_hex(10),
            task_id=task_id,
            profile_name=spec.profile_name,
            user_data_dir=resolved_dir,
            os_name=spec.isolation.os_name,
        )
        self._active_by_profile[spec.profile_name] = lease
        self._active_by_id[lease.session_id] = lease
        return lease

    def release_session(self, session_id: str) -> None:
        lease = self._active_by_id.pop(session_id, None)
        if lease is not None:
            self._active_by_profile.pop(lease.profile_name, None)

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
