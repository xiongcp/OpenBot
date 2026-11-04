"""Browser network, redirect, Service Worker, download, and upload policy (OB-058)."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

_FORBIDDEN_HOSTS = frozenset(
    {
        "127.0.0.1",
        "::1",
        "localhost",
        "0.0.0.0",
        "169.254.169.254",
        "metadata.google.internal",
    }
)


@dataclass(frozen=True, slots=True)
class BrowserNetworkBoundaryConfig:
    allowed_hosts: frozenset[str]
    service_workers_blocked: bool
    outer_network_namespace_verified: bool
    download_quarantine_dir: Path
    approved_upload_paths: frozenset[str]


class BrowserNetworkPolicyEnforcer:
    """Enforce browser navigation/redirect/download/upload guards and Service Worker blocking."""

    page_route_alone_is_complete_isolation: Literal[False] = False

    def __init__(self, config: BrowserNetworkBoundaryConfig) -> None:
        # BrowserContext.route / Page.route cannot intercept all Service Worker traffic!
        if not config.service_workers_blocked and not config.outer_network_namespace_verified:
            raise PermissionError(
                "SERVICE_WORKER_BYPASS_RISK: block Service Workers or verify outer isolation"
            )
        self._cfg = config
        self._dl_dir = config.download_quarantine_dir.resolve()
        self._dl_dir.mkdir(parents=True, exist_ok=True)

    def check_request(self, *, request_kind: str, url: str) -> dict[str, Any]:
        parsed = urlparse(url)
        scheme = (parsed.scheme or "").lower()
        host = (parsed.hostname or "").lower()
        if scheme not in {"https", "http"}:
            raise PermissionError(f"Forbidden URL scheme '{scheme}' in {request_kind}")
        if not host or host in _FORBIDDEN_HOSTS or host.startswith(("10.", "192.168.", "169.254.")):
            raise PermissionError(f"Forbidden internal/metadata host '{host}' in {request_kind}")
        if host not in self._cfg.allowed_hosts:
            raise PermissionError(f"Host '{host}' not in browser allowlist for {request_kind}")
        return {"allowed": True, "request_kind": request_kind, "host": host}

    def validate_download_target(self, *, suggested_filename: str) -> Path:
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(suggested_filename).name).lstrip(".")
        if not safe_name:
            safe_name = "download.bin"
        target = (self._dl_dir / safe_name).resolve()
        if target.parent != self._dl_dir:
            raise PermissionError("Download target escaped quarantine directory")
        return target

    def validate_upload_path(self, path: Path) -> Path:
        resolved = str(path.resolve())
        if resolved not in self._cfg.approved_upload_paths:
            raise PermissionError(f"UNAPPROVED_UPLOAD_FILE: {resolved}")
        return Path(resolved)
