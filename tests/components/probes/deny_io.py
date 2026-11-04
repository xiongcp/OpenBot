"""Python audit probe; native/unmanaged network calls remain outside coverage."""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
allowed = [
    ROOT / "services/core/src",
    Path(sys.prefix).resolve(),
    Path(sys.base_prefix).resolve(),
]
# SDK platform headers read this public OS version file on macOS.
system_metadata = {Path("/System/Library/CoreServices/SystemVersion.plist")}
violations = []
observed = {"open": 0, "network": 0, "process": 0}


def audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.bind"}:
        observed["network"] += 1
        violations.append(event)
        raise PermissionError("Network denied by Python audit probe")
    if event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
        observed["process"] += 1
        violations.append(event)
        raise PermissionError("Process denied by Python audit probe")
    if event == "open":
        observed["open"] += 1
        path = args[0]
        if isinstance(path, (str, bytes)):
            resolved = Path(os.fsdecode(path)).resolve()
            read_only = not args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
            if not (
                any(resolved.is_relative_to(base) for base in allowed)
                or resolved in system_metadata
                and read_only
            ):
                violations.append("open:outside-allowlist:" + resolved.name)
                raise PermissionError("File access denied by Python audit probe")


sys.addaudithook(audit)
try:
    if sys.argv[1] == "imports":
        for name in [
            "openbot",
            "openbot.domain",
            "openbot.config",
            "openbot.boundaries",
            "openai",
            "httpx",
        ]:
            importlib.import_module(name)
    elif sys.argv[1] == "network-canary":
        import socket

        socket.getaddrinfo("example.invalid", 443)
    elif sys.argv[1] == "process-canary":
        subprocess.run([sys.executable, "-c", "pass"], check=True)
    elif sys.argv[1] == "file-canary":
        Path(sys.argv[2]).read_text()
    else:
        raise ValueError("Unknown probe")
except PermissionError:
    pass
print(
    json.dumps(
        {
            "scope": "Python audit events after interpreter startup only",
            "observed": observed,
            "violations": violations,
        }
    )
)
raise SystemExit(4 if violations else 0)
