"""Generic pinned-digest MCP container executor with pre-create intent log and drift quarantine."""

import hashlib
import json
import os
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openbot.contracts import canonicalize, strict_json
from openbot.tools.executors.sandbox import ContainerOwnership
from openbot.tools.mcp.registry import McpToolPinRegistry, McpToolSnapshot


@dataclass(frozen=True, slots=True)
class AdmittedMcpContainerToolSpec:
    tool_id: str
    server_id: str
    tool_name: str
    description: str
    image: str
    script_sha256: str
    network_mode: str
    read_only_rootfs: bool
    user: str
    input_schema: dict[str, Any]

    def to_snapshot(self, *, override_description: str | None = None) -> McpToolSnapshot:
        return McpToolSnapshot(
            server_id=self.server_id,
            package_digest="sha256:" + self.script_sha256,
            command_argv=("python", "-I", "-B", "/server.py"),
            env_keys=("HOME", "PATH"),
            transport="stdio",
            tool_name=self.tool_name,
            description=override_description or self.description,
            input_schema=self.input_schema,
            output_schema={"type": "object"},
            annotations={"readOnlyHint": True, "authoritative_grants": False},
        )


class ContainerIntentLedger:
    """Durable pre-creation container intent log for 100% SIGKILL orphan reaping (V1-068/076)."""

    def __init__(self, ledger_path: Path) -> None:
        self._path = ledger_path.resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.is_file():
            self._write({"intents": {}})

    def _read(self) -> dict[str, Any]:
        return dict(strict_json(self._path.read_bytes()))

    def _write(self, doc: dict[str, Any]) -> None:
        tmp = self._path.with_name(f".{self._path.name}.{secrets.token_hex(6)}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, canonicalize(doc))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, self._path)

    def record_intent(
        self, *, container_name: str, ownership: ContainerOwnership, tool_id: str
    ) -> None:
        doc = self._read()
        intents = dict(doc.get("intents", {}))
        intents[container_name] = {
            "container_name": container_name,
            "tool_id": tool_id,
            "labels": ownership.labels(),
            "state": "CREATING",
            "created_at_ms": time.time_ns() // 1_000_000,
        }
        doc["intents"] = intents
        self._write(doc)

    def mark_reclaimed(self, container_name: str) -> None:
        doc = self._read()
        intents = dict(doc.get("intents", {}))
        if container_name in intents:
            intents[container_name]["state"] = "RECLAIMED"
            doc["intents"] = intents
            self._write(doc)

    def pending_intents(self) -> dict[str, dict[str, Any]]:
        doc = self._read()
        return {
            k: dict(v)
            for k, v in dict(doc.get("intents", {})).items()
            if v.get("state") != "RECLAIMED"
        }


class McpContainerExecutor:
    """Execute admitted read-only MCP container tools with JCS pin check and orphan reaping."""

    def __init__(
        self,
        *,
        catalog_path: Path,
        intent_ledger: ContainerIntentLedger,
        pin_registry: McpToolPinRegistry | None = None,
    ) -> None:
        doc = dict(strict_json(catalog_path.read_bytes()))
        self._tools: dict[str, AdmittedMcpContainerToolSpec] = {}
        self._registry = pin_registry or McpToolPinRegistry(
            builtin_tool_names=frozenset(
                {
                    "workspace.list",
                    "workspace.read",
                    "workspace.search",
                    "workspace.propose_patch",
                    "workspace.apply_patch",
                }
            )
        )
        self._pins: dict[str, str] = {}
        for raw_item in doc.get("tools", []):
            spec = AdmittedMcpContainerToolSpec(
                tool_id=str(raw_item["tool_id"]),
                server_id=str(raw_item["server_id"]),
                tool_name=str(raw_item["tool_name"]),
                description=str(raw_item["description"]),
                image=str(raw_item["image"]),
                script_sha256=str(raw_item["script_sha256"]),
                network_mode=str(raw_item["network_mode"]),
                read_only_rootfs=bool(raw_item["read_only_rootfs"]),
                user=str(raw_item["user"]),
                input_schema=dict(raw_item["input_schema"]),
            )
            if not re.fullmatch(r"python@sha256:[0-9a-f]{64}", spec.image):
                raise PermissionError(f"MCP_UNPINNED_IMAGE_FORBIDDEN: {spec.tool_id}")
            if spec.network_mode != "none" or not spec.read_only_rootfs:
                raise PermissionError(f"MCP_CONTAINER_ISOLATION_INVALID: {spec.tool_id}")
            snap = spec.to_snapshot()
            pin = self._registry.register_and_pin(snap)
            self._tools[spec.tool_id] = spec
            self._pins[spec.tool_id] = pin.jcs_pin_hash
        self._intents = intent_ledger

    def admitted_tools(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def build_container_create_argv(
        self, tool_id: str, ownership: ContainerOwnership, *, container_name: str
    ) -> tuple[str, ...]:
        if tool_id not in self._tools:
            raise PermissionError(f"UNADMITTED_MCP_CONTAINER_TOOL: {tool_id}")
        spec = self._tools[tool_id]
        labels = [x for k, v in ownership.labels().items() for x in ("--label", f"{k}={v}")]
        return (
            "container",
            "create",
            "--name",
            container_name,
            "--interactive",
            "--pull=never",
            f"--network={spec.network_mode}",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--user={spec.user}",
            "--memory=64m",
            "--cpus=0.25",
            "--pids-limit=32",
            "--env=HOME=/nonexistent",
            *labels,
            spec.image,
            "python",
            "-I",
            "-B",
            "/server.py",
        )

    def execute_tool(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        ownership: ContainerOwnership,
        *,
        runtime_runner: Callable[[AdmittedMcpContainerToolSpec, dict[str, Any]], dict[str, Any]],
        observed_tool_description: str | None = None,
        simulate_sigkill_before_reclaim: bool = False,
    ) -> dict[str, Any]:
        if tool_id not in self._tools:
            raise PermissionError(f"UNADMITTED_MCP_CONTAINER_TOOL: {tool_id}")
        spec = self._tools[tool_id]
        live_snap = spec.to_snapshot(override_description=observed_tool_description)
        self._registry.verify_against_pin(live_snap, expected_pin_hash=self._pins[tool_id])

        container_name = f"openbot_mcp_{ownership.attempt_id}_{secrets.token_hex(4)}"
        self._intents.record_intent(
            container_name=container_name, ownership=ownership, tool_id=tool_id
        )
        argv = self.build_container_create_argv(tool_id, ownership, container_name=container_name)
        if simulate_sigkill_before_reclaim:
            raise RuntimeError("SIMULATED_SIGKILL_AFTER_CONTAINER_CREATE")
        try:
            out = runtime_runner(spec, arguments)
            raw_json = json.dumps(out, sort_keys=True)
            return {
                "tool_id": tool_id,
                "server_id": spec.server_id,
                "container_name": container_name,
                "create_argv": argv,
                "result": out,
                "sha256": hashlib.sha256(raw_json.encode("utf-8")).hexdigest(),
                "cleanup_verified": True,
                "provenance_kind": "TAINTED_EXTERNAL",
            }
        finally:
            self._intents.mark_reclaimed(container_name)

    def reap_orphan_containers(
        self, *, docker_rm_callback: Callable[[str], bool] | None = None
    ) -> tuple[str, ...]:
        reaped: list[str] = []
        for cname in list(self._intents.pending_intents()):
            ok = True if docker_rm_callback is None else docker_rm_callback(cname)
            if ok:
                self._intents.mark_reclaimed(cname)
                reaped.append(cname)
        return tuple(reaped)
