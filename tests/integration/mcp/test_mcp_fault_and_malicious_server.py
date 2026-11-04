from openbot.tools.mcp.fault_harness import McpFaultAndMaliciousHarness


def test_mcp_malicious_and_fault_server_suite_verifies_all_boundaries() -> None:
    harness = McpFaultAndMaliciousHarness()
    report = harness.run_all()
    assert report.post_dispatch_disconnect_retried_count == 0
    assert report.remote_provider_mcp_accepted_as_local is False
    assert set(report.cases_verified) == {
        "list_changed_metadata_drift_quarantined",
        "oversized_output_capped_and_redacted",
        "schema_depth_flood_rejected",
        "duplicate_jsonrpc_request_id_rejected",
        "post_dispatch_server_crash_marked_unknown_without_retry",
        "builtin_tool_collision_rejected",
    }
