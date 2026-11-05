"""Pinned stdio MCP protocol negotiation, dynamic runner rejection, and output bounds (OB-062)."""

import io
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Literal

_DYNAMIC_RUNNERS = frozenset({"npx", "uvx", "pipx", "pnpx", "bunx"})


@dataclass(frozen=True, slots=True)
class McpCompatibilityManifest:
    server_id: str
    pinned_package_digest: str
    executable: str
    argv: tuple[str, ...]
    transport: Literal["stdio"]
    supported_protocol_versions: tuple[str, ...]
    init_timeout_ms: int = 3000
    max_output_bytes: int = 65_536

    def validate(self) -> None:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.pinned_package_digest):
            raise PermissionError("MCP server requires pinned sha256 package digest")
        exe_name = Path(self.executable).name.lower()
        if exe_name in _DYNAMIC_RUNNERS or any("@latest" in a.lower() for a in self.argv):
            raise PermissionError("DYNAMIC_MCP_PACKAGE_RUNNER_FORBIDDEN")
        if self.transport != "stdio" or not self.supported_protocol_versions:
            raise PermissionError(
                "Only pinned stdio MCP with explicit protocol versions is allowed"
            )


class McpStdioLifecycleClient:
    """Negotiate pinned MCP protocol versions without dynamic installs or transport downgrades."""

    def __init__(self, manifest: McpCompatibilityManifest) -> None:
        manifest.validate()
        self._manifest = manifest
        self._proc: subprocess.Popen[bytes] | None = None
        self._seen_req_ids: set[str] = set()

    def negotiate_initialize(self, *, server_protocol_version: str) -> dict[str, Any]:
        if server_protocol_version not in self._manifest.supported_protocol_versions:
            raise PermissionError(f"MCP_PROTOCOL_VERSION_MISMATCH: {server_protocol_version}")
        return {
            "server_id": self._manifest.server_id,
            "negotiated_version": server_protocol_version,
            "transport": self._manifest.transport,
            "silent_transport_downgrade": False,
        }

    def read_bounded_stream(self, stream: IO[bytes]) -> tuple[bytes, bool]:
        """Read a single frame or up to max_output_bytes + 1 from a binary stream without OOM."""
        limit = self._manifest.max_output_bytes
        buf = bytearray()
        while len(buf) <= limit:
            ch = stream.read(1)
            if not ch:
                break
            if ch == b"\n":
                break
            buf.extend(ch)
        if len(buf) > limit:
            return bytes(buf[:limit]), True
        return bytes(buf), False

    def bound_response_bytes(self, raw: bytes) -> tuple[bytes, bool]:
        return self.read_bounded_stream(io.BytesIO(raw))

    def start_and_handshake(self) -> dict[str, Any]:
        if self._proc is not None:
            raise PermissionError("MCP stdio server already started")
        proc = subprocess.Popen(
            list(self._manifest.argv),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8", "PYTHONNOUSERSITE": "1"},
            start_new_session=True,
        )
        self._proc = proc
        assert proc.stdin is not None and proc.stdout is not None
        init_req = {
            "jsonrpc": "2.0",
            "id": "init_1",
            "method": "initialize",
            "params": {
                "protocolVersion": self._manifest.supported_protocol_versions[0],
                "capabilities": {},
                "clientInfo": {"name": "openbot", "version": "0.1.0"},
            },
        }
        self._seen_req_ids.add("init_1")
        proc.stdin.write((json.dumps(init_req) + "\n").encode("utf-8"))
        proc.stdin.flush()
        raw_line, trunc = self.read_bounded_stream(proc.stdout)
        if trunc or not raw_line:
            self.close()
            raise PermissionError("MCP_INITIALIZE_HANDSHAKE_FAILED")
        resp = json.loads(raw_line.decode("utf-8"))
        if resp.get("id") != "init_1" or "result" not in resp:
            self.close()
            raise PermissionError("MCP_INITIALIZE_INVALID_RESPONSE")
        srv_ver = str(resp["result"].get("protocolVersion", ""))
        neg = self.negotiate_initialize(server_protocol_version=srv_ver)
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        proc.stdin.write((json.dumps(notif) + "\n").encode("utf-8"))
        proc.stdin.flush()
        return {
            **neg,
            "server_pid": proc.pid,
            "initialized_notification_sent": True,
        }

    def call_tool_stdio(
        self, *, req_id: str, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        if req_id in self._seen_req_ids:
            raise PermissionError(f"DUPLICATE_JSONRPC_REQUEST_ID: {req_id}")
        self._seen_req_ids.add(req_id)
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise PermissionError("MCP stdio server is not running")
        req = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        try:
            self._proc.stdin.write((json.dumps(req) + "\n").encode("utf-8"))
            self._proc.stdin.flush()
        except BrokenPipeError:
            self.close()
            return {
                "status": "UNKNOWN",
                "task_state": "RECONCILING",
                "retried_count": 0,
                "truncated": False,
                "raw_bytes": b"",
            }
        raw_line, trunc = self.read_bounded_stream(self._proc.stdout)
        if trunc:
            # Drain remainder of oversized line in small discarded chunks to resync frame boundary
            drained = 0
            while drained < 65_536:
                b_ch = self._proc.stdout.read(1)
                if not b_ch or b_ch == b"\n":
                    break
                drained += 1
        if not raw_line:
            self.close()
            return {
                "status": "UNKNOWN",
                "task_state": "RECONCILING",
                "retried_count": 0,
                "truncated": False,
                "raw_bytes": b"",
            }
        return {
            "status": "OK",
            "task_state": "RUNNING",
            "retried_count": 0,
            "truncated": trunc,
            "raw_bytes": raw_line,
        }

    def close(self) -> None:
        if self._proc is not None:
            if self._proc.poll() is None:
                self._proc.kill()
                self._proc.wait(timeout=5)
            if self._proc.stdin:
                self._proc.stdin.close()
            if self._proc.stdout:
                self._proc.stdout.close()
            if self._proc.stderr:
                self._proc.stderr.close()
            self._proc = None
