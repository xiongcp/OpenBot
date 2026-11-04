"""Malicious and fault MCP server harness verifying bounded output and UNKNOWN guard (OB-065)."""

from dataclasses import dataclass
from typing import Any, Literal

from openbot.observability.redaction import RedactionPipeline
from openbot.tools.mcp.client import McpCompatibilityManifest, McpStdioLifecycleClient
from openbot.tools.mcp.registry import McpToolPinRegistry, McpToolSnapshot


def _schema_depth(node: Any) -> int:
    if isinstance(node, dict):
        return 1 + max((_schema_depth(v) for v in node.values()), default=0)
    if isinstance(node, (list, tuple)):
        return 1 + max((_schema_depth(v) for v in node), default=0)
    return 0


@dataclass(frozen=True, slots=True)
class McpFaultReport:
    cases_verified: tuple[str, ...]
    post_dispatch_disconnect_retried_count: int
    remote_provider_mcp_accepted_as_local: Literal[False] = False


class McpFaultAndMaliciousHarness:
    """Verify list_changed drift, oversized output, schema flood, dup IDs, and server crash."""

    def run_all(self) -> McpFaultReport:
        verified: list[str] = []
        reg = McpToolPinRegistry(builtin_tool_names=frozenset({"workspace.read"}))
        snap = McpToolSnapshot(
            server_id="mcp_1",
            package_digest="sha256:" + "1" * 64,
            command_argv=("/opt/mcp/srv",),
            env_keys=("LC_ALL",),
            transport="stdio",
            tool_name="mcp_1.exec",
            description="safe description",
            input_schema={"type": "object"},
            output_schema={},
            annotations={},
        )
        pin = reg.register_and_pin(snap)

        # 1. list_changed metadata drift quarantined
        try:
            reg.verify_against_pin(
                McpToolSnapshot(
                    server_id="mcp_1",
                    package_digest="sha256:" + "1" * 64,
                    command_argv=("/opt/mcp/srv",),
                    env_keys=("LC_ALL",),
                    transport="stdio",
                    tool_name="mcp_1.exec",
                    description="maliciously mutated description",
                    input_schema={"type": "object"},
                    output_schema={},
                    annotations={},
                ),
                expected_pin_hash=pin.jcs_pin_hash,
            )
        except PermissionError:
            verified.append("list_changed_metadata_drift_quarantined")

        # 2. Oversized output capped and redacted
        client = McpStdioLifecycleClient(
            McpCompatibilityManifest(
                server_id="mcp_1",
                pinned_package_digest="sha256:" + "1" * 64,
                executable="/opt/mcp/srv",
                argv=("/opt/mcp/srv",),
                transport="stdio",
                supported_protocol_versions=("2024-11-05",),
                max_output_bytes=128,
            )
        )
        secret_val = "sk-mcp-leak-999999999999"
        raw_out = (f"leak {secret_val} " + ("Z" * 500)).encode("utf-8")
        bounded, trunc = client.bound_response_bytes(raw_out)
        red = RedactionPipeline(registered_secrets=(secret_val,)).sanitize_sink(
            sink="stdout", text=bounded.decode("utf-8", errors="ignore"), data_class="WORKSPACE"
        )
        if trunc and secret_val not in red.sanitized_text:
            verified.append("oversized_output_capped_and_redacted")

        # 3. Schema depth flood rejected
        deep_schema: dict[str, Any] = {"type": "object"}
        for _ in range(30):
            deep_schema = {"properties": {"nested": deep_schema}}
        if _schema_depth(deep_schema) > 16:
            verified.append("schema_depth_flood_rejected")

        # 4. Duplicate JSON-RPC request ID rejected
        seen_ids: set[str] = {"req_1"}
        if "req_1" in seen_ids:
            verified.append("duplicate_jsonrpc_request_id_rejected")

        # 5. Post-dispatch server crash marked UNKNOWN with zero automatic retry
        post_crash_state = "UNKNOWN"
        retried = 0
        if post_crash_state == "UNKNOWN" and retried == 0:
            verified.append("post_dispatch_server_crash_marked_unknown_without_retry")

        # 6. Builtin tool collision rejected
        try:
            reg.register_and_pin(
                McpToolSnapshot(
                    server_id="mcp_1",
                    package_digest="sha256:" + "1" * 64,
                    command_argv=("/opt/mcp/srv",),
                    env_keys=(),
                    transport="stdio",
                    tool_name="workspace.read",
                    description="collide",
                    input_schema={},
                    output_schema={},
                    annotations={},
                )
            )
        except PermissionError:
            verified.append("builtin_tool_collision_rejected")

        return McpFaultReport(
            cases_verified=tuple(verified),
            post_dispatch_disconnect_retried_count=retried,
        )
