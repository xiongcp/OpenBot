import hashlib
import os
from pathlib import Path

import pytest
from openbot.tools.executors.sandbox import ContainerOwnership
from openbot.tools.mcp.container_read import ContainerReadTool


@pytest.mark.parametrize("flag", ["O_NOFOLLOW", "O_NONBLOCK"])
def test_missing_native_file_guard_refuses_before_docker(monkeypatch, tmp_path, flag):
    server = Path(__file__).resolve().parents[2] / "services/mcp_fixture/read_server.py"
    tool = ContainerReadTool(
        image="python@sha256:" + "a" * 64,
        server=server,
        server_sha256=hashlib.sha256(server.read_bytes()).hexdigest(),
    )
    monkeypatch.delattr(os, flag, raising=False)
    monkeypatch.setattr(tool, "available", lambda: True)
    with pytest.raises(PermissionError, match="MCP_FILE_GUARD_UNAVAILABLE"):
        tool.read(
            {"path": "demo.txt"},
            ContainerOwnership("pro_test", "op_test", "att_test", "ep_test"),
            workspace=tmp_path,
            expected_sha256="a" * 64,
        )
