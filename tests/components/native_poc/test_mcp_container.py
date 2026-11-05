import hashlib
import os
from pathlib import Path

import pytest
from openbot.tools.executors.sandbox import ContainerOwnership
from openbot.tools.mcp.container_read import ContainerReadTool


@pytest.mark.native_container
def test_real_mcp_read_has_hash_receipt_and_reclaims_container(tmp_path):
    if os.environ.get("OPENBOT_NATIVE_MCP") != "1":
        pytest.skip("Requires explicit prepared native MCP container test")
    root = Path(__file__).resolve().parents[3]
    server = root / "services/mcp_fixture/read_server.py"
    tool = ContainerReadTool(
        image="python@sha256:848ba4413eb897e225159b8fc1b02094576cbae4aa73fc13142608ae2c8c0e32",
        server=server,
        server_sha256=hashlib.sha256(server.read_bytes()).hexdigest(),
    )
    (tmp_path / "demo.txt").write_text("Dedicated synthetic MCP fixture / 合成测试\n")
    raw = (tmp_path / "demo.txt").read_bytes()
    receipt = tool.read(
        {"path": "demo.txt"},
        ContainerOwnership("pro_mcp_test", "op_test", "att_test", "ep_test"),
        workspace=tmp_path,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
    )
    assert receipt["text"].encode() == raw
    assert receipt["cleanup_verified"] is True
    assert receipt["sha256"] == hashlib.sha256(raw).hexdigest()
