"""Audited synthetic MCP server: one bounded demo file, no network or code execution."""

import hashlib
import json
import os
import stat
import sys
from pathlib import Path

PROTOCOL = "2025-03-26"
TOOL = {
    "name": "read_text",
    "description": "Read the dedicated synthetic demo.txt fixture, at most 4096 bytes.",
    "inputSchema": {
        "type": "object",
        "properties": {"path": {"type": "string", "enum": ["demo.txt"]}},
        "required": ["path"],
        "additionalProperties": False,
    },
}


def unique(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError("DUPLICATE_KEY")
        result[k] = v
    return result


def main():
    root = Path(sys.argv[1]) if len(sys.argv) == 2 else Path("/input")
    initialized = False
    seen = set()
    for _ in range(128):
        line = sys.stdin.buffer.readline(16385)
        if not line or len(line) > 16384:
            break
        request_id = None
        try:
            req = json.loads(line, object_pairs_hook=unique)
            request_id = req.get("id")
            if request_id is None:
                continue
            if req.get("jsonrpc") != "2.0" or request_id in seen:
                raise ValueError("INVALID_REQUEST")
            seen.add(request_id)
            method, params = req.get("method"), req.get("params", {})
            if method == "initialize" and not initialized:
                if params.get("protocolVersion") != PROTOCOL:
                    raise ValueError("PROTOCOL_UNSUPPORTED")
                initialized = True
                result = {
                    "protocolVersion": PROTOCOL,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "openbot-demo-read", "version": "1.0.0"},
                }
            elif initialized and method == "tools/list":
                result = {"tools": [TOOL]}
            elif initialized and method == "tools/call":
                if params != {"name": "read_text", "arguments": {"path": "demo.txt"}}:
                    raise ValueError("DEMO_FILE_ONLY")
                fd = os.open(root / "demo.txt", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
                        raise ValueError("FILE_BOUNDARY_INVALID")
                    raw = os.read(fd, 4097)
                    if len(raw) > 4096:
                        raise ValueError("FILE_LIMIT")
                finally:
                    os.close(fd)
                data = {
                    "path": "demo.txt",
                    "text": raw.decode("utf-8"),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
                result = {
                    "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                    "isError": False,
                }
            else:
                raise ValueError("METHOD_UNAVAILABLE")
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except (ValueError, TypeError, AttributeError, OSError):
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": "FIXTURE_REQUEST_REJECTED"},
            }
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
