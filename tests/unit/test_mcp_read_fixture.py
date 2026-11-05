import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "services/mcp_fixture/read_server.py"
pytestmark = pytest.mark.skipif(os.name != "posix", reason="Linux container fixture file guards")


def exchange(root, requests):
    assert SERVER.is_file(), "Pinned read-only MCP fixture server is missing"
    run = subprocess.run(
        [sys.executable, str(SERVER), str(root)],
        input="\n".join(json.dumps(r) for r in requests) + "\n",
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    return [json.loads(line) for line in run.stdout.splitlines()]


def init():
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-03-26"},
    }


def call(path="demo.txt"):
    return {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "read_text", "arguments": {"path": path}},
    }


def test_fixture_negotiates_then_returns_verifiable_readonly_result(tmp_path):
    import hashlib

    p = tmp_path / "demo.txt"
    p.write_text("OpenBot 合成内容\n")
    before = p.read_bytes()
    data = exchange(tmp_path, [init(), call()])
    assert data[0]["result"]["protocolVersion"] == "2025-03-26"
    result = json.loads(data[1]["result"]["content"][0]["text"])
    assert result["sha256"] == hashlib.sha256(before).hexdigest()
    assert result["text"] == before.decode()
    assert p.read_bytes() == before


@pytest.mark.parametrize("path", ["../outside", "/etc/passwd", ".env", "other.txt"])
def test_fixture_refuses_any_file_outside_explicit_demo(tmp_path, path):
    (tmp_path / "demo.txt").write_text("synthetic")
    data = exchange(tmp_path, [init(), call(path)])
    assert "error" in data[1]
    assert "result" not in data[1]


def test_fixture_rejects_symlink_oversize_and_call_before_initialize(tmp_path):
    other = tmp_path / "other.txt"
    other.write_text("private")
    (tmp_path / "demo.txt").symlink_to(other)
    assert "error" in exchange(tmp_path, [init(), call()])[1]
    (tmp_path / "demo.txt").unlink()
    (tmp_path / "demo.txt").write_text("x" * 5000)
    assert "error" in exchange(tmp_path, [init(), call()])[1]
    assert "error" in exchange(tmp_path, [call()])[0]


def test_container_read_requires_pinned_image_and_matching_server_hash(tmp_path):
    from openbot.tools.mcp.container_read import ContainerReadTool

    with pytest.raises(PermissionError):
        ContainerReadTool(image="python:latest", server=SERVER, server_sha256="a" * 64)
    with pytest.raises(PermissionError):
        ContainerReadTool(image="python@sha256:" + "a" * 64, server=SERVER, server_sha256="a" * 64)
