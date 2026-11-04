"""Pinned stdio MCP protocol negotiation, dynamic runner rejection, and output bounds (OB-062)."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

_DYNAMIC_RUNNERS = frozenset({"npx", "uvx", "pipx", "pnpx", "bunx"})


@dataclass(frozen=True, slots=True)
class McpCompatibilityManifest:
    server_id: str
    pinned_package_digest: str
    executable: str
    argv: tuple[str, ...]
    transport: Literal["stdio"]
    supported_protocol_versions: tuple[str, ...]
    init_timeout_ms: int = 3000
    max_output_bytes: int = 65_536

    def validate(self) -> None:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.pinned_package_digest):
            raise PermissionError("MCP server requires pinned sha256 package digest")
        exe_name = Path(self.executable).name.lower()
        if exe_name in _DYNAMIC_RUNNERS or any("@latest" in a.lower() for a in self.argv):
            raise PermissionError("DYNAMIC_MCP_PACKAGE_RUNNER_FORBIDDEN")
        if self.transport != "stdio" or not self.supported_protocol_versions:
            raise PermissionError(
                "Only pinned stdio MCP with explicit protocol versions is allowed"
            )


class McpStdioLifecycleClient:
    """Negotiate pinned MCP protocol versions without dynamic installs or transport downgrades."""

    def __init__(self, manifest: McpCompatibilityManifest) -> None:
        manifest.validate()
        self._manifest = manifest

    def negotiate_initialize(self, *, server_protocol_version: str) -> dict[str, Any]:
        if server_protocol_version not in self._manifest.supported_protocol_versions:
            raise PermissionError(f"MCP_PROTOCOL_VERSION_MISMATCH: {server_protocol_version}")
        return {
            "server_id": self._manifest.server_id,
            "negotiated_version": server_protocol_version,
            "transport": self._manifest.transport,
            "silent_transport_downgrade": False,
        }

    def bound_response_bytes(self, raw: bytes) -> tuple[bytes, bool]:
        limit = self._manifest.max_output_bytes
        if len(raw) > limit:
            return raw[:limit], True
        return raw, False
