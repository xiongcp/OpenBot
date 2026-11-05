"""Pinned read-only MCP fixture over real, independently reclaimed Docker containers."""

import hashlib
import os
import re
import selectors
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from openbot.contracts import canonicalize, strict_json
from openbot.tools.executors.sandbox import ContainerOwnership


class ContainerReadTool:
    server_id = "openbot-demo-read"

    def __init__(self, *, image: str, server: Path, server_sha256: str):
        if not re.fullmatch(r"python@sha256:[0-9a-f]{64}", image):
            raise PermissionError("MCP_PINNED_IMAGE_REQUIRED")
        if (
            not server.is_file()
            or server.is_symlink()
            or hashlib.sha256(server.read_bytes()).hexdigest() != server_sha256
        ):
            raise PermissionError("MCP_SERVER_HASH_MISMATCH")
        self.image, self.server, self.server_sha256 = image, server, server_sha256
        self.binary = next(
            (
                str(p)
                for p in (Path("/opt/homebrew/bin/docker"), Path("/usr/local/bin/docker"))
                if p.is_file()
            ),
            "",
        )
        self.socket = next(
            (
                p
                for p in (
                    Path.home() / ".orbstack/run/docker.sock",
                    Path.home() / ".docker/run/docker.sock",
                )
                if p.exists()
            ),
            None,
        )

    def available(self) -> bool:
        if not self.binary or self.socket is None:
            return False
        try:
            self._command(["image", "inspect", self.image], Path("/tmp"))
            return True
        except (PermissionError, OSError, subprocess.TimeoutExpired):
            return False

    def _argv(self, args: list[str], home: Path) -> list[str]:
        if not self.binary or self.socket is None:
            raise PermissionError("MCP_ISOLATION_UNAVAILABLE")
        return [self.binary, "--host", "unix://" + str(self.socket), "--config", str(home), *args]

    @staticmethod
    def _env(home: Path) -> dict[str, str]:
        return {"PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin", "HOME": str(home)}

    def _command(self, args: list[str], home: Path) -> bytes:
        result = subprocess.run(
            self._argv(args, home),
            env=self._env(home),
            capture_output=True,
            timeout=10,
            check=False,
        )
        if result.returncode or len(result.stdout) > 262144:
            raise PermissionError("MCP_CONTAINER_COMMAND_FAILED")
        return result.stdout

    @staticmethod
    def _frame(proc: subprocess.Popen[bytes], deadline: float) -> dict[str, Any]:
        assert proc.stdout is not None
        data = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            while b"\n" not in data:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError("MCP_FRAME_DEADLINE")
                piece = os.read(proc.stdout.fileno(), 4096)
                if not piece:
                    raise PermissionError("MCP_STREAM_CLOSED")
                data.extend(piece)
                if len(data) > 16384:
                    raise PermissionError("MCP_FRAME_TOO_LARGE")
        if data.count(b"\n") != 1 or not data.endswith(b"\n"):
            raise PermissionError("MCP_UNEXPECTED_EXTRA_FRAME")
        return dict(strict_json(bytes(data)))

    def read(
        self,
        arguments: dict[str, Any],
        ownership: ContainerOwnership,
        *,
        workspace: Path,
        expected_sha256: str,
    ) -> dict[str, Any]:
        if arguments != {"path": "demo.txt"} or not self.available():
            raise PermissionError("MCP_DEMO_READ_UNAVAILABLE")
        server_bytes = self.server.read_bytes()
        if hashlib.sha256(server_bytes).hexdigest() != self.server_sha256:
            raise PermissionError("MCP_SERVER_CHANGED")
        fd = os.open(workspace / "demo.txt", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
                raise PermissionError("MCP_INPUT_BOUNDARY_INVALID")
            content = os.read(fd, 4097)
        finally:
            os.close(fd)
        if len(content) > 4096 or hashlib.sha256(content).hexdigest() != expected_sha256:
            raise PermissionError("MCP_INPUT_CHANGED")
        with tempfile.TemporaryDirectory(prefix="openbot-mcp-", dir="/tmp") as tmp:
            root = Path(tmp)
            inputs = root / "input"
            inputs.mkdir(mode=0o755)
            (inputs / "demo.txt").write_bytes(content)
            (inputs / "demo.txt").chmod(0o444)
            script = root / "read_server.py"
            script.write_bytes(server_bytes)
            script.chmod(0o444)
            labels = [x for k, v in ownership.labels().items() for x in ("--label", k + "=" + v)]
            args = [
                "container",
                "create",
                "--interactive",
                "--pull=never",
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--user=65532:65532",
                "--memory=64m",
                "--cpus=0.25",
                "--pids-limit=32",
                "--env=HOME=/nonexistent",
                "--mount",
                f"type=bind,src={inputs},dst=/input,readonly",
                "--mount",
                f"type=bind,src={script},dst=/server.py,readonly",
                *labels,
                self.image,
                "python",
                "-I",
                "-B",
                "/server.py",
            ]
            cid = self._command(args, root).decode().strip()
            if not re.fullmatch(r"[0-9a-f]{64}", cid):
                raise PermissionError("MCP_INVALID_CONTAINER_ID")
            proc: subprocess.Popen[bytes] | None = None
            result: dict[str, Any] | None = None
            try:
                inspected = strict_json(self._command(["inspect", cid], root))[0]
                hc = inspected["HostConfig"]
                if (
                    hc["NetworkMode"] != "none"
                    or not hc["ReadonlyRootfs"]
                    or hc["Privileged"]
                    or inspected["Config"]["Labels"] != ownership.labels()
                ):
                    raise PermissionError("MCP_CONTAINER_BOUNDARY_MISMATCH")
                proc = subprocess.Popen(
                    self._argv(["container", "start", "--attach", "--interactive", cid], root),
                    env=self._env(root),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                assert proc.stdin is not None

                def rpc(req_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
                    assert proc is not None and proc.stdin is not None
                    proc.stdin.write(
                        canonicalize(
                            {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
                        )
                        + b"\n"
                    )
                    proc.stdin.flush()
                    reply = self._frame(proc, time.monotonic() + 10)
                    if reply.get("id") != req_id or "error" in reply or "result" not in reply:
                        raise PermissionError("MCP_REPLY_INVALID")
                    return dict(reply["result"])

                init = rpc(
                    1,
                    "initialize",
                    {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "OpenBot", "version": "0.1"},
                    },
                )
                if init.get("protocolVersion") != "2025-03-26":
                    raise PermissionError("MCP_PROTOCOL_MISMATCH")
                proc.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
                proc.stdin.flush()
                listed = rpc(2, "tools/list", {})
                if len(listed.get("tools", [])) != 1 or listed["tools"][0]["name"] != "read_text":
                    raise PermissionError("MCP_TOOL_METADATA_MISMATCH")
                reply = rpc(3, "tools/call", {"name": "read_text", "arguments": arguments})
                if reply.get("isError") is not False or len(reply.get("content", [])) != 1:
                    raise PermissionError("MCP_TOOL_RESULT_INVALID")
                result = dict(strict_json(reply["content"][0]["text"]))
                if (
                    set(result) != {"path", "text", "sha256"}
                    or result["path"] != "demo.txt"
                    or result["sha256"] != expected_sha256
                    or hashlib.sha256(result["text"].encode()).hexdigest() != expected_sha256
                ):
                    raise PermissionError("MCP_RESULT_HASH_MISMATCH")
            finally:
                if proc is not None:
                    if proc.stdin:
                        proc.stdin.close()
                    if proc.poll() is None:
                        proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=3)
                    if proc.stdout:
                        proc.stdout.close()
                own = strict_json(self._command(["inspect", cid], root))[0]
                if own["Config"]["Labels"] != ownership.labels():
                    raise PermissionError("MCP_CLEANUP_OWNERSHIP_CHANGED")
                if own["State"]["Running"]:
                    self._command(["container", "stop", "--time", "2", cid], root)
                self._command(["container", "wait", cid], root)
                if strict_json(self._command(["inspect", cid], root))[0]["State"]["Running"]:
                    raise PermissionError("MCP_CONTAINER_STILL_RUNNING")
                self._command(["container", "rm", cid], root)
            assert result is not None
            return result | {
                "container_id": cid,
                "cleanup_verified": True,
                "server_id": self.server_id,
            }
