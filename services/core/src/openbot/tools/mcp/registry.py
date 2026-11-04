"""MCP tool metadata JCS pinning, remote $ref blocking, and list_changed quarantine (OB-063)."""

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from openbot.contracts import canonicalize


def _contains_remote_ref(obj: Any) -> bool:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "$ref" and isinstance(v, str) and not v.startswith("#"):
                return True
            if _contains_remote_ref(v):
                return True
    elif isinstance(obj, (list, tuple)):
        return any(_contains_remote_ref(item) for item in obj)
    return False


@dataclass(frozen=True, slots=True)
class McpToolSnapshot:
    server_id: str
    package_digest: str
    command_argv: tuple[str, ...]
    env_keys: tuple[str, ...]
    transport: str
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    annotations: dict[str, Any]

    def to_jcs_pin_hash(self) -> str:
        raw = canonicalize(
            {
                "server_id": self.server_id,
                "package_digest": self.package_digest,
                "command_argv": list(self.command_argv),
                "env_keys": list(self.env_keys),
                "transport": self.transport,
                "tool_name": self.tool_name,
                "description": self.description,
                "input_schema": self.input_schema,
                "output_schema": self.output_schema,
                "annotations": self.annotations,
            }
        )
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class PinnedMcpToolRecord:
    tool_name: str
    jcs_pin_hash: str
    status: Literal["PINNED_ACTIVE", "QUARANTINED_ON_DRIFT"]
    jcs_hash_proves_server_code_safe: Literal[False] = False


class McpToolPinRegistry:
    """Pin full MCP tool metadata with JCS and quarantine tools on list_changed drift."""

    def __init__(self, *, builtin_tool_names: frozenset[str]) -> None:
        self._builtins = builtin_tool_names
        self._pins: dict[str, PinnedMcpToolRecord] = {}

    def register_and_pin(self, snapshot: McpToolSnapshot) -> PinnedMcpToolRecord:
        if snapshot.tool_name in self._builtins:
            raise PermissionError(f"BUILTIN_TOOL_SHADOWING_FORBIDDEN: {snapshot.tool_name}")
        if _contains_remote_ref(snapshot.input_schema) or _contains_remote_ref(
            snapshot.output_schema
        ):
            raise PermissionError("REMOTE_SCHEMA_REF_FORBIDDEN")
        rec = PinnedMcpToolRecord(
            tool_name=snapshot.tool_name,
            jcs_pin_hash=snapshot.to_jcs_pin_hash(),
            status="PINNED_ACTIVE",
        )
        self._pins[snapshot.tool_name] = rec
        return rec

    def verify_against_pin(
        self, current: McpToolSnapshot, *, expected_pin_hash: str
    ) -> PinnedMcpToolRecord:
        stored = self._pins.get(current.tool_name)
        actual_hash = current.to_jcs_pin_hash()
        if (
            stored is None
            or stored.status != "PINNED_ACTIVE"
            or stored.jcs_pin_hash != expected_pin_hash
            or actual_hash != expected_pin_hash
        ):
            self._pins[current.tool_name] = PinnedMcpToolRecord(
                tool_name=current.tool_name,
                jcs_pin_hash=actual_hash,
                status="QUARANTINED_ON_DRIFT",
            )
            raise PermissionError("MCP_METADATA_DRIFT_QUARANTINED")
        return stored
