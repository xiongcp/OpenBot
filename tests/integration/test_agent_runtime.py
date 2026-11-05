import hashlib
import json
import os
import time

import pytest
from openbot.adapters.local_api.server import ApiRequest
from openbot.domain.providers import ModelResponse, Text, ToolCall, ToolResult
from openbot.storage.writer import RequestConflict

from tests.contracts.local_api.test_local_api_contracts import _headers, local_api_env
from tests.integration.test_client_state import apply_config, service

__all__ = ["local_api_env"]


def wait_for(check, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = check()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError("Expected durable runtime condition did not arrive")


class SyntheticModel:
    def __init__(self, budget, *, tool=True, on_request=None):
        self.budget, self.tool, self.on_request = budget, tool, on_request
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        self.last_request = request
        self.budget.reserve(request.request_id, request.reserved_cost_units)
        if self.on_request:
            self.on_request()
        self.budget.settle(request.request_id, 10, 10)
        blocks = (
            (ToolCall("call_demo", "mcp_read_text", b'{"path":"demo.txt"}'),)
            if self.calls == 1 and self.tool
            else (Text("已读取合成文件。 / Read the synthetic file."),)
        )
        return ModelResponse(blocks, 10, 10, False)

    async def cancel(self, request_id):
        pass

    async def close(self):
        pass


class SyntheticRead:
    server_id = "synthetic-test"

    def __init__(self, *, fail=False):
        self.calls = 0
        self.fail = fail

    def available(self):
        return True

    def read(self, arguments, ownership, *, workspace, expected_sha256):
        self.calls += 1
        if self.fail:
            raise TimeoutError("synthetic timeout")
        text = (workspace / arguments["path"]).read_text()
        assert hashlib.sha256(text.encode()).hexdigest() == expected_sha256
        return {
            "text": text,
            "sha256": expected_sha256,
            "cleanup_verified": True,
            "container_id": "synthetic",
        }


def make_runtime(env, root, *, tool=None, model_tool=True, on_request=None):
    from openbot.application.agent_runtime import AgentRuntime

    state = service(env)
    apply_config(state, mode="CONNECTED", mcp_enabled=True)
    (root / "demo.txt").write_text("Dedicated synthetic fixture")
    model_instances = []

    def factory(config, budget):
        model = SyntheticModel(
            budget, tool=model_tool and not model_instances, on_request=on_request
        )
        model_instances.append(model)
        return model

    runtime = AgentRuntime(
        state=state,
        tasks=env[3],
        operations=env[4],
        dispatcher=env[5],
        artifacts=env[0]._artifacts,
        registry=env[0]._registry,
        model_factory=factory,
        tool=tool or SyntheticRead(),
        workspace=root,
        runtime_epoch="ep_1",
    )
    return runtime, state, model_instances


def submit(env):
    return (
        env[0]
        .handle(
            ApiRequest(
                "POST",
                "/v1/tasks",
                headers=_headers(env[7]),
                body=json.dumps(
                    {
                        "workspace_id": "wsp_test1",
                        "goal": "Read demo.txt using the MCP tool and summarize bilingually",
                        "network_mode": "CONNECTED",
                    }
                ),
            )
        )
        .json()["task_id"]
    )


def decide(env, state, task_id, decision="APPROVE"):
    events = wait_for(
        lambda: [e for e in state.trace(task_id)["events"] if e["kind"] == "WAITING_APPROVAL"]
    )
    approval = events[-1]["data"]["approval_id"]
    preview = (
        env[0]
        .handle(ApiRequest("GET", f"/v1/approvals/{approval}/preview", headers=_headers(env[7])))
        .json()
    )
    challenge = (
        env[0]
        .handle(ApiRequest("POST", f"/v1/approvals/{approval}/challenge", headers=_headers(env[7])))
        .json()
    )
    body = {
        "decision": decision,
        "nonce": challenge["nonce"],
        "expected_binding_hash": preview["binding_hash"],
        "expected_version": preview["version"],
    }
    response = env[0].handle(
        ApiRequest(
            "POST",
            f"/v1/approvals/{approval}/decide",
            headers=_headers(env[7]),
            body=json.dumps(body),
        )
    )
    assert response.status_code == 200, response.body


@pytest.mark.skipif(
    not hasattr(os, "O_NOFOLLOW"), reason="Requires POSIX demo-file guards; Windows is unqualified"
)
def test_runtime_uses_real_core_approval_claim_dispatch_and_verified_artifact(
    local_api_env, tmp_path
):
    runtime, state, models = make_runtime(local_api_env, tmp_path)
    task = submit(local_api_env)
    try:
        runtime.start(task)
        decide(local_api_env, state, task)
        wait_for(
            lambda: any(event["kind"] == "RUN_FINISHED" for event in state.trace(task)["events"])
        )
        assert local_api_env[3].snapshot(local_api_env[1], task)["state"] == "SUCCEEDED"
        events = state.trace(task)["events"]
        kinds = [e["kind"] for e in events]
        assert all(
            k in kinds
            for k in [
                "SKILL_LOADED",
                "MODEL_REQUESTED",
                "TOOL_PROPOSED",
                "TOOL_DISPATCHED",
                "TOOL_RETURNED",
                "OUTCOME_VERIFIED",
                "RUN_FINISHED",
            ]
        )
        assert sum(model.calls for model in models) == 2
        assert any(isinstance(b, ToolResult) for b in models[1].last_request.blocks)
        assert runtime.tool.calls == 1
        assert (
            local_api_env[2].read(
                lambda db: db.execute("SELECT status FROM approvals").fetchone()[0]
            )
            == "CONSUMED"
        )
        assert (
            local_api_env[2].read(
                lambda db: db.execute("SELECT state FROM operations").fetchone()[0]
            )
            == "SUCCEEDED"
        )
        assert local_api_env[3].snapshot(local_api_env[1], task)["outcome"]["artifact_ids"]
        before = len(events)
        state.trace(task)
        assert len(state.trace(task)["events"]) == before and runtime.tool.calls == 1
        with pytest.raises(RequestConflict):
            runtime.start(task)
    finally:
        runtime.close()


def test_permission_restriction_inflight_prevents_next_tool_proposal(local_api_env, tmp_path):
    runtime, state, _ = make_runtime(
        local_api_env,
        tmp_path,
        on_request=lambda: apply_config(service(local_api_env), mode="OFFLINE"),
    )
    task = submit(local_api_env)
    try:
        runtime.start(task)
        wait_for(lambda: any(e["kind"] == "RUN_INTERRUPTED" for e in state.trace(task)["events"]))
        assert runtime.tool.calls == 0
        assert not local_api_env[2].read(
            lambda db: db.execute("SELECT 1 FROM operations").fetchone()
        )
    finally:
        runtime.close()


@pytest.mark.skipif(
    not hasattr(os, "O_NOFOLLOW"), reason="Requires POSIX demo-file guards; Windows is unqualified"
)
def test_tool_timeout_remains_unknown_without_replay(local_api_env, tmp_path):
    runtime, state, _ = make_runtime(local_api_env, tmp_path, tool=SyntheticRead(fail=True))
    task = submit(local_api_env)
    try:
        runtime.start(task)
        decide(local_api_env, state, task)
        wait_for(
            lambda: local_api_env[3].snapshot(local_api_env[1], task)["state"] == "RECONCILING"
        )
        assert (
            local_api_env[2].read(
                lambda db: db.execute("SELECT state FROM operations").fetchone()[0]
            )
            == "UNKNOWN"
        )
        assert runtime.tool.calls == 1
    finally:
        runtime.close()


def test_persisted_run_never_silently_restarts_model_after_process_recreation(
    local_api_env, tmp_path
):
    runtime, state, models = make_runtime(local_api_env, tmp_path)
    task = submit(local_api_env)
    state.start_run(task)
    try:
        with pytest.raises(RequestConflict):
            runtime.start(task)
        assert not models
        assert runtime.tool.calls == 0
    finally:
        runtime.close()


@pytest.mark.skipif(
    not hasattr(os, "O_NOFOLLOW"), reason="Requires POSIX demo-file guards; Windows is unqualified"
)
def test_denial_never_calls_tool(local_api_env, tmp_path):
    runtime, state, _ = make_runtime(local_api_env, tmp_path)
    task = submit(local_api_env)
    try:
        runtime.start(task)
        decide(local_api_env, state, task, "DENY")
        wait_for(lambda: any(e["kind"] == "RUN_INTERRUPTED" for e in state.trace(task)["events"]))
        assert runtime.tool.calls == 0
        assert local_api_env[2].read(
            lambda db: db.execute(
                "SELECT state FROM operations WHERE task_id=?", (task,)
            ).fetchone()
        ) == ("REJECTED",)
    finally:
        runtime.close()


def test_cancel_while_model_returns_blocks_proposal(local_api_env, tmp_path):
    def cancel():
        snap = local_api_env[3].snapshot(local_api_env[1], task)
        response = local_api_env[0].handle(
            ApiRequest(
                "POST",
                f"/v1/tasks/{task}/cancel",
                headers=_headers(local_api_env[7]),
                body=json.dumps({"expected_version": snap["version"]}),
            )
        )
        assert response.status_code == 200

    runtime, state, _ = make_runtime(local_api_env, tmp_path, on_request=cancel)
    task = submit(local_api_env)
    try:
        runtime.start(task)
        wait_for(lambda: any(e["kind"] == "RUN_INTERRUPTED" for e in state.trace(task)["events"]))
        assert runtime.tool.calls == 0
        assert (
            local_api_env[2].read(
                lambda db: db.execute(
                    "SELECT count(*) FROM operations WHERE task_id=?", (task,)
                ).fetchone()[0]
            )
            == 0
        )
    finally:
        runtime.close()


def test_missing_isolation_fails_before_operation(local_api_env, tmp_path):
    tool = SyntheticRead()
    tool.available = lambda: False
    runtime, state, _ = make_runtime(local_api_env, tmp_path, tool=tool)
    task = submit(local_api_env)
    try:
        runtime.start(task)
        wait_for(lambda: any(e["kind"] == "RUN_INTERRUPTED" for e in state.trace(task)["events"]))
        assert tool.calls == 0
        assert not any(e["kind"] == "TOOL_PROPOSED" for e in state.trace(task)["events"])
    finally:
        runtime.close()


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="Requires POSIX demo-file guards")
def test_repeated_completed_read_is_not_dispatched_again(local_api_env, tmp_path):
    runtime, state, _ = make_runtime(local_api_env, tmp_path)
    runtime.model_factory = lambda config, budget: SyntheticModel(budget, tool=True)
    task = submit(local_api_env)
    try:
        runtime.start(task)
        decide(local_api_env, state, task)
        wait_for(
            lambda: any(e["kind"] == "RUN_INTERRUPTED" for e in state.trace(task)["events"]),
            timeout=1,
        )
        assert runtime.tool.calls == 1
    finally:
        runtime.close()
