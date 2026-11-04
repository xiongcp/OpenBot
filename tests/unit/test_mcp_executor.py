import pytest
from openbot.tools.mcp.executor import (
    McpIsolatedExecutor,
    ReviewedLocalMcpManifest,
)


def test_mcp_executor_ignores_untrusted_hints_requires_isolation_and_blocks_sampling() -> None:
    manifest = ReviewedLocalMcpManifest(
        server_id="mcp_1",
        tool_name="mcp_1.write_row",
        reviewed_retry_class="RECONCILE_ONLY",
        requires_approval=True,
        allowed_env_keys=frozenset({"LC_ALL"}),
        network_mode="NONE",
    )
    executor = McpIsolatedExecutor(
        reviewed_manifests={"mcp_1.write_row": manifest},
        isolation_backend_qualified=True,
    )

    # 1. Untrusted server annotations NEVER override local manifest!
    plan = executor.prepare_dispatch(
        tool_name="mcp_1.write_row",
        server_annotations={"readOnlyHint": True, "idempotentHint": True},
        parent_env={"OPENAI_API_KEY": "sk-secret", "HOME": "/Users/admin", "LC_ALL": "C.UTF-8"},
        sampling_requested=False,
    )
    assert plan.effective_retry_class == "RECONCILE_ONLY"
    assert plan.requires_approval is True
    assert "OPENAI_API_KEY" not in plan.child_env
    assert "HOME" not in plan.child_env
    assert plan.sampling_enabled is False

    # 2. Server sampling request, unreviewed server, or unqualified sandbox is rejected
    with pytest.raises(PermissionError, match="MCP_SAMPLING_FORBIDDEN_IN_MVP"):
        executor.prepare_dispatch(
            tool_name="mcp_1.write_row",
            server_annotations={},
            parent_env={},
            sampling_requested=True,
        )
    with pytest.raises(PermissionError, match="UNREVIEWED_MCP_TOOL"):
        executor.prepare_dispatch(
            tool_name="mcp_unknown.tool",
            server_annotations={"readOnlyHint": True},
            parent_env={},
            sampling_requested=False,
        )
    unqualified = McpIsolatedExecutor(
        reviewed_manifests={"mcp_1.write_row": manifest},
        isolation_backend_qualified=False,
    )
    with pytest.raises(PermissionError, match="CAPABILITY_UNAVAILABLE"):
        unqualified.prepare_dispatch(
            tool_name="mcp_1.write_row",
            server_annotations={},
            parent_env={},
            sampling_requested=False,
        )
