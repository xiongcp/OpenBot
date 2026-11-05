import io
from pathlib import Path

import pytest
from openbot.tools.mcp.client import McpCompatibilityManifest, McpStdioLifecycleClient
from openbot.tools.mcp.fault_harness import McpFaultAndMaliciousHarness


def test_mcp_malicious_and_fault_server_suite_verifies_all_boundaries(
    tmp_path: Path,
) -> None:
    harness = McpFaultAndMaliciousHarness(tmp_path / "mcp_faults")
    report = harness.run_all()
    assert report.post_dispatch_disconnect_retried_count == 0
    assert report.remote_provider_mcp_accepted_as_local is False
    assert report.real_stdio_handshake_verified is True
    assert report.server_pid > 0
    assert report.external_effect_count_on_disconnect == 1
    assert set(report.cases_verified) == {
        "list_changed_metadata_drift_quarantined",
        "oversized_output_capped_and_redacted",
        "schema_depth_flood_rejected",
        "duplicate_jsonrpc_request_id_rejected",
        "post_dispatch_server_crash_marked_unknown_without_retry",
        "builtin_tool_collision_rejected",
    }

    # Verify streaming reader stops at max_output_bytes + 1 without reading the rest of the stream
    manifest = McpCompatibilityManifest(
        server_id="mcp_stream",
        pinned_package_digest="sha256:" + "2" * 64,
        executable="/bin/echo",
        argv=("/bin/echo",),
        transport="stdio",
        supported_protocol_versions=("2024-11-05",),
        max_output_bytes=64,
    )
    client = McpStdioLifecycleClient(manifest)
    huge_stream = io.BytesIO(b"A" * 10_000)
    chunk, truncated = client.read_bounded_stream(huge_stream)
    assert truncated is True
    assert len(chunk) == 64
    assert huge_stream.tell() == 65

    with pytest.raises(PermissionError, match="MCP_PROTOCOL_VERSION_MISMATCH"):
        client.negotiate_initialize(server_protocol_version="1999-01-01")
