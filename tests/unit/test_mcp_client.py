import pytest
from openbot.tools.mcp.client import (
    McpCompatibilityManifest,
    McpStdioLifecycleClient,
)


def test_mcp_client_negotiates_protocol_rejects_uvx_npx_and_caps_output() -> None:
    manifest = McpCompatibilityManifest(
        server_id="mcp_sqlite_ro",
        pinned_package_digest="sha256:" + "a" * 64,
        executable="/opt/openbot/mcp/sqlite-server",
        argv=("/opt/openbot/mcp/sqlite-server", "--readonly"),
        transport="stdio",
        supported_protocol_versions=("2024-11-05",),
        init_timeout_ms=3000,
        max_output_bytes=256,
    )
    client = McpStdioLifecycleClient(manifest)

    # 1. Rejects npx / uvx / pipx or '@latest' dynamic package runners
    for bad_exe, bad_argv in (
        ("npx", ("npx", "-y", "@modelcontextprotocol/server-everything@latest")),
        ("uvx", ("uvx", "mcp-server-git")),
    ):
        with pytest.raises(PermissionError, match="DYNAMIC_MCP_PACKAGE_RUNNER_FORBIDDEN"):
            McpStdioLifecycleClient(
                McpCompatibilityManifest(
                    server_id="bad",
                    pinned_package_digest="sha256:" + "a" * 64,
                    executable=bad_exe,
                    argv=bad_argv,
                    transport="stdio",
                    supported_protocol_versions=("2024-11-05",),
                )
            )

    # 2. Protocol mismatch fails immediately without infinite wait or silent SSE downgrade
    with pytest.raises(PermissionError, match="MCP_PROTOCOL_VERSION_MISMATCH"):
        client.negotiate_initialize(server_protocol_version="1999-01-01")

    neg = client.negotiate_initialize(server_protocol_version="2024-11-05")
    assert neg["negotiated_version"] == "2024-11-05"
    assert neg["silent_transport_downgrade"] is False

    # 3. Output is bounded at max_output_bytes
    bounded, trunc = client.bound_response_bytes(b"X" * 1024)
    assert len(bounded) == 256
    assert trunc is True
