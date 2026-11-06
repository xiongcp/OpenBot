import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest
from openbot.adapters.local_api.server import ApiRequest
from openbot.application.agent_runtime import AgentRuntime
from openbot.domain.providers import ModelRequest, ModelResponse, Text, ToolCall
from openbot.policy.egress import EgressGuard
from openbot.providers.openai import ProviderFailure
from openbot.providers.openai_compatible import OpenAICompatibleAdapter

from tests.contracts.local_api.test_local_api_contracts import _headers, local_api_env
from tests.integration.test_agent_runtime import decide, submit, wait_for
from tests.integration.test_client_state import apply_config, service

__all__ = ["local_api_env"]


class _MultiStepWorkspaceModel:
    def __init__(self, budget: Any, steps: list[ToolCall | Text], *, on_before_apply: Any = None):
        self.budget = budget
        self.steps = steps
        self.on_before_apply = on_before_apply
        self.idx = 0

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.budget.reserve(request.request_id, request.reserved_cost_units)
        self.budget.settle(request.request_id, 12, 12)
        # Determine step index from number of ToolResult blocks in request.blocks
        from openbot.domain.providers import ToolResult

        completed_tools = sum(1 for b in request.blocks if isinstance(b, ToolResult))
        step_item = self.steps[min(completed_tools, len(self.steps) - 1)]
        if (
            isinstance(step_item, ToolCall)
            and step_item.tool_name == "workspace.apply_patch"
            and self.on_before_apply is not None
        ):
            self.on_before_apply()
        return ModelResponse((step_item,), 12, 12, False)

    async def cancel(self, request_id: str) -> None:
        pass

    async def close(self) -> None:
        pass


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="Requires POSIX O_NOFOLLOW")
def test_v1_075_multi_tool_orchestration_search_read_propose_approve_apply(
    local_api_env: Any, tmp_path: Path
) -> None:
    state = service(local_api_env)
    apply_config(
        state, mode="CONNECTED", mcp_enabled=True, max_steps=6, workspace_tools="READ_WRITE"
    )
    target_file = tmp_path / "app_config.py"
    target_file.write_text("MAX_WORKERS = 2\nLOG_LEVEL = 'INFO'\n", encoding="utf-8")

    steps: list[ToolCall | Text] = [
        ToolCall(
            "call_1",
            "workspace.search",
            json.dumps({"pattern": "MAX_WORKERS"}).encode(),
        ),
        ToolCall(
            "call_2",
            "workspace.read",
            json.dumps({"path": "app_config.py", "start_line": 1, "end_line": 2}).encode(),
        ),
        ToolCall(
            "call_3",
            "workspace.propose_patch",
            json.dumps(
                {
                    "path": "app_config.py",
                    "old_snippet": "MAX_WORKERS = 2\n",
                    "new_snippet": "MAX_WORKERS = 8\n",
                }
            ).encode(),
        ),
        ToolCall(
            "call_4",
            "workspace.apply_patch",
            json.dumps(
                {
                    "path": "app_config.py",
                    "old_snippet": "MAX_WORKERS = 2\n",
                    "new_snippet": "MAX_WORKERS = 8\n",
                }
            ).encode(),
        ),
        Text("已完成配置搜索、读取与补丁更新。 / Completed search, read, and patch update."),
    ]

    runtime = AgentRuntime(
        state=state,
        tasks=local_api_env[3],
        operations=local_api_env[4],
        dispatcher=local_api_env[5],
        artifacts=local_api_env[0]._artifacts,
        registry=local_api_env[0]._registry,
        workspace=tmp_path,
        runtime_epoch="ep_1",
        model_factory=lambda cfg, b: _MultiStepWorkspaceModel(b, steps),
        tool=None,
    )
    admitted = runtime.load_admitted_tool_manifests()
    assert {
        "workspace.list",
        "workspace.read",
        "workspace.search",
        "workspace.propose_patch",
        "workspace.apply_patch",
    } <= set(admitted)

    task = submit(local_api_env)
    try:
        runtime.start(task)
        # Approve search, read, and apply_patch
        for idx in range(3):
            wait_for(
                lambda n=idx + 1: len(
                    [e for e in state.trace(task)["events"] if e["kind"] == "WAITING_APPROVAL"]
                )
                >= n
            )
            decide(local_api_env, state, task, "APPROVE")
        wait_for(lambda: any(e["kind"] == "RUN_FINISHED" for e in state.trace(task)["events"]))
        assert local_api_env[3].snapshot(local_api_env[1], task)["state"] == "SUCCEEDED"
        assert target_file.read_text(encoding="utf-8") == "MAX_WORKERS = 8\nLOG_LEVEL = 'INFO'\n"
    finally:
        runtime.close()


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="Requires POSIX O_NOFOLLOW")
def test_v1_075_rejects_sensitive_or_symlink_patch_and_user_edit_conflict(
    local_api_env: Any, tmp_path: Path
) -> None:
    state = service(local_api_env)
    apply_config(state, mode="CONNECTED", mcp_enabled=True, workspace_tools="READ_WRITE")
    outside = tmp_path.parent / "outside_secret.txt"
    outside.write_text("secret", encoding="utf-8")
    symlink_file = tmp_path / "link_escape.txt"
    if symlink_file.exists() or symlink_file.is_symlink():
        symlink_file.unlink()
    symlink_file.symlink_to(outside)

    for forbidden_path in (".git/config", ".env", "link_escape.txt"):
        bad_steps: list[ToolCall | Text] = [
            ToolCall(
                "call_bad",
                "workspace.propose_patch",
                json.dumps(
                    {"path": forbidden_path, "old_snippet": "a", "new_snippet": "b"}
                ).encode(),
            )
        ]
        runtime = AgentRuntime(
            state=state,
            tasks=local_api_env[3],
            operations=local_api_env[4],
            dispatcher=local_api_env[5],
            artifacts=local_api_env[0]._artifacts,
            registry=local_api_env[0]._registry,
            workspace=tmp_path,
            runtime_epoch="ep_1",
            model_factory=lambda cfg, b, s=bad_steps: _MultiStepWorkspaceModel(b, s),
            tool=None,
        )
        task = (
            local_api_env[0]
            .handle(
                ApiRequest(
                    "POST",
                    "/v1/tasks",
                    headers=_headers(local_api_env[7]),
                    body=json.dumps(
                        {
                            "workspace_id": "wsp_test1",
                            "goal": f"Attempt forbidden patch on {forbidden_path}",
                            "network_mode": "CONNECTED",
                        }
                    ),
                )
            )
            .json()["task_id"]
        )
        try:
            runtime.start(task)
            wait_for(
                lambda t=task: any(e["kind"] == "RUN_INTERRUPTED" for e in state.trace(t)["events"])
            )
            interrupted = next(
                e for e in state.trace(task)["events"] if e["kind"] == "RUN_INTERRUPTED"
            )
            assert interrupted["data"]["error_code"] == "FORBIDDEN_PATCH_TARGET"
            snap_t = local_api_env[3].snapshot(local_api_env[1], task)
            local_api_env[0].handle(
                ApiRequest(
                    "POST",
                    f"/v1/tasks/{task}/cancel",
                    headers=_headers(local_api_env[7]),
                    body=json.dumps({"expected_version": snap_t["version"]}),
                )
            )
        finally:
            runtime.close()

    # User manual edit after approval refuses overwrite
    user_file = tmp_path / "editable.py"
    user_file.write_text("v = 1\n", encoding="utf-8")
    conflict_steps: list[ToolCall | Text] = [
        ToolCall(
            "call_apply",
            "workspace.apply_patch",
            json.dumps(
                {"path": "editable.py", "old_snippet": "v = 1\n", "new_snippet": "v = 2\n"}
            ).encode(),
        ),
        Text("Done"),
    ]
    runtime2 = AgentRuntime(
        state=state,
        tasks=local_api_env[3],
        operations=local_api_env[4],
        dispatcher=local_api_env[5],
        artifacts=local_api_env[0]._artifacts,
        registry=local_api_env[0]._registry,
        workspace=tmp_path,
        runtime_epoch="ep_1",
        model_factory=lambda cfg, b: _MultiStepWorkspaceModel(b, conflict_steps),
        tool=None,
    )
    task2 = (
        local_api_env[0]
        .handle(
            ApiRequest(
                "POST",
                "/v1/tasks",
                headers=_headers(local_api_env[7]),
                body=json.dumps(
                    {
                        "workspace_id": "wsp_test1",
                        "goal": "Conflict edit test",
                        "network_mode": "CONNECTED",
                    }
                ),
            )
        )
        .json()["task_id"]
    )
    try:
        runtime2.start(task2)
        wait_for(
            lambda: [e for e in state.trace(task2)["events"] if e["kind"] == "WAITING_APPROVAL"]
        )
        # User edits file right before approving
        user_file.write_text("v = 999  # user manual edit\n", encoding="utf-8")
        decide(local_api_env, state, task2, "APPROVE")
        wait_for(lambda: any(e["kind"] == "RUN_INTERRUPTED" for e in state.trace(task2)["events"]))
        interrupted2 = next(
            e for e in state.trace(task2)["events"] if e["kind"] == "RUN_INTERRUPTED"
        )
        assert interrupted2["data"]["error_code"] == "PATCH_PRECONDITION_CHANGED"
        assert user_file.read_text(encoding="utf-8") == "v = 999  # user manual edit\n"
    finally:
        runtime2.close()


def test_v1_011_012_streaming_inflight_cancellation_terminates_active_task() -> None:
    class _SlowStreamingResponse:
        def __init__(self, entered: asyncio.Event) -> None:
            self._entered = entered

        async def iter_bytes(self):  # type: ignore[no-untyped-def]
            self._entered.set()
            yield b'data: {"choices":[{"index":0,"delta":{"content":"Hel"}}]}\n\n'
            await asyncio.sleep(10)

    class _SlowTransport:
        def __init__(self, entered: asyncio.Event) -> None:
            self.entered = entered
            self.requests = 0

        async def stream_chat(self, payload: dict[str, Any]) -> Any:
            self.requests += 1
            return _SlowStreamingResponse(self.entered)

    class _TrackBudget:
        def __init__(self) -> None:
            self.reserved: list[str] = []
            self.unknown_refs: list[str] = []

        def reserve(self, ref: str, units: int) -> None:
            self.reserved.append(ref)

        def settle(self, ref: str, p: int, c: int) -> None:
            pass

        def unknown(self, ref: str) -> None:
            self.unknown_refs.append(ref)

    async def _run() -> None:
        entered = asyncio.Event()
        transport = _SlowTransport(entered)
        budget = _TrackBudget()
        egress = EgressGuard(
            profile_network_mode="CONNECTED",
            profile_allowed_domains=frozenset({"api.openai.com"}),
            workspace_allowed_domains=frozenset({"api.openai.com"}),
        )
        adapter = OpenAICompatibleAdapter(
            endpoint="https://api.openai.com/v1",
            model="gpt-4o-mini",
            egress_guard=egress,
            budget=budget,
            manifests={},
            stream_transport=transport,
            max_gateway_retries=2,
        )
        req = ModelRequest(
            "req_cancel_inflight",
            "gpt-4o-mini",
            (Text("Hello"),),
            int(asyncio.get_running_loop().time() * 1000) + 30_000,
            100,
        )
        gen_task = asyncio.create_task(adapter.generate(req))
        await asyncio.wait_for(entered.wait(), timeout=2.0)
        await adapter.cancel("req_cancel_inflight")
        with pytest.raises(ProviderFailure, match="cancelled|UNKNOWN"):
            await asyncio.wait_for(gen_task, timeout=1.0)
        assert transport.requests == 1
        assert budget.unknown_refs == ["req_cancel_inflight:try_1"]

    asyncio.run(_run())
