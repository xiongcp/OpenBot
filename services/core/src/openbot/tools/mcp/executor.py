"""Isolated MCP process executor ignoring untrusted hints and blocking sampling (OB-064)."""

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class ReviewedLocalMcpManifest:
    server_id: str
    tool_name: str
    reviewed_retry_class: str
    requires_approval: bool
    allowed_env_keys: frozenset[str]
    network_mode: Literal["NONE", "RESTRICTED_EGRESS"]


@dataclass(frozen=True, slots=True)
class McpDispatchPlan:
    server_id: str
    tool_name: str
    effective_retry_class: str
    requires_approval: bool
    child_env: dict[str, str]
    network_mode: str
    sampling_enabled: Literal[False] = False


class McpIsolatedExecutor:
    """Enforce isolated MCP execution, clean env, local retry_class, and sampling prohibition."""

    def __init__(
        self,
        *,
        reviewed_manifests: dict[str, ReviewedLocalMcpManifest],
        isolation_backend_qualified: bool,
    ) -> None:
        self._manifests = dict(reviewed_manifests)
        self._qualified = isolation_backend_qualified

    def prepare_dispatch(
        self,
        *,
        tool_name: str,
        server_annotations: dict[str, Any],
        parent_env: dict[str, str],
        sampling_requested: bool,
    ) -> McpDispatchPlan:
        del server_annotations  # Third-party readOnlyHint/idempotentHint NEVER grant authority!
        if not self._qualified:
            raise PermissionError(
                "CAPABILITY_UNAVAILABLE: isolated execution backend required for MCP stdio server"
            )
        if sampling_requested:
            raise PermissionError("MCP_SAMPLING_FORBIDDEN_IN_MVP")
        manifest = self._manifests.get(tool_name)
        if manifest is None:
            raise PermissionError(f"UNREVIEWED_MCP_TOOL: {tool_name}")

        clean_env = {k: v for k, v in parent_env.items() if k in manifest.allowed_env_keys}
        return McpDispatchPlan(
            server_id=manifest.server_id,
            tool_name=manifest.tool_name,
            effective_retry_class=manifest.reviewed_retry_class,
            requires_approval=manifest.requires_approval,
            child_env=clean_env,
            network_mode=manifest.network_mode,
            sampling_enabled=False,
        )
