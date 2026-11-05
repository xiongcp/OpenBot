"""Managed Playwright session enforcing network policy, Service Worker block, and quarantine."""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from openbot.tools.browser.read import (
    BrowserDomNodeSpec,
    BrowserPageSnapshot,
    BrowserReadTool,
)
from openbot.tools.executors.browser.network_policy import (
    BrowserNetworkBoundaryConfig,
    BrowserNetworkPolicyEnforcer,
)
from openbot.tools.executors.browser.session import (
    BrowserProfileSessionManager,
    BrowserSessionLease,
    BrowserSessionSpec,
)


@dataclass(frozen=True, slots=True)
class QuarantinedDownloadReceipt:
    path: Path
    sha256: str
    size_bytes: int
    provenance_kind: Literal["TAINTED_EXTERNAL"] = "TAINTED_EXTERNAL"


class ManagedPlaywrightSession:
    """Hybrid ACI L2 managed browser context with full request interception and ARIA snapshots."""

    def __init__(
        self,
        *,
        profile_manager: BrowserProfileSessionManager,
        network_config: BrowserNetworkBoundaryConfig,
        read_tool: BrowserReadTool | None = None,
    ) -> None:
        if not network_config.service_workers_blocked:
            raise PermissionError("PLAYWRIGHT_SERVICE_WORKERS_MUST_BE_BLOCKED")
        self._profiles = profile_manager
        self._enforcer = BrowserNetworkPolicyEnforcer(network_config)
        self._reader = read_tool or BrowserReadTool()
        self._lease: BrowserSessionLease | None = None
        self._intercepted_requests: list[dict[str, Any]] = []

    def start_session(self, *, task_id: str, spec: BrowserSessionSpec) -> BrowserSessionLease:
        self._lease = self._profiles.acquire_session(task_id=task_id, spec=spec)
        return self._lease

    def close_session(self) -> None:
        if self._lease is not None:
            self._profiles.release_session(self._lease.session_id)
            self._lease = None

    def intercept_and_navigate(
        self,
        *,
        page_id: str,
        frame_id: str,
        initial_url: str,
        redirect_chain: tuple[str, ...] = (),
        subrequests: tuple[tuple[str, str], ...] = (),
        aria_nodes: tuple[BrowserDomNodeSpec, ...],
    ) -> BrowserPageSnapshot:
        if self._lease is None:
            raise PermissionError("ManagedPlaywrightSession is not started")
        self._enforcer.check_request(request_kind="navigation", url=initial_url)
        self._intercepted_requests.append({"kind": "navigation", "url": initial_url})
        final_url = initial_url
        for redir_url in redirect_chain:
            self._enforcer.check_request(request_kind="redirect", url=redir_url)
            self._intercepted_requests.append({"kind": "redirect", "url": redir_url})
            final_url = redir_url
        for req_kind, sub_url in subrequests:
            self._enforcer.check_request(request_kind=req_kind, url=sub_url)
            self._intercepted_requests.append({"kind": req_kind, "url": sub_url})
        return self._reader.extract_snapshot(
            page_id=page_id,
            frame_id=frame_id,
            final_url=final_url,
            nodes=aria_nodes,
        )

    def quarantine_download(
        self, *, suggested_filename: str, data: bytes, max_bytes: int = 10_485_760
    ) -> dict[str, Any]:
        if len(data) > max_bytes:
            raise PermissionError("DOWNLOAD_SIZE_LIMIT_EXCEEDED")
        target = self._enforcer.validate_download_target(suggested_filename=suggested_filename)
        target.write_bytes(data)
        return {
            "path": str(target),
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
            "provenance_kind": "TAINTED_EXTERNAL",
        }
