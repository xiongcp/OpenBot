import asyncio
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from openbot.adapters.local_api.server import ApiRequest
from openbot.application.budgets import BudgetService, TaskBudgetPolicy
from openbot.application.runtime_budget import RuntimeBudget
from openbot.application.runtime_factory import model_factory
from openbot.domain.providers import ModelRequest, ModelResponse, Text, ToolCall, ToolResult
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


def submit(env, goal="Read demo.txt using the MCP tool and summarize bilingually"):
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
                        "goal": goal,
                        "network_mode": "CONNECTED",
                    }
                ),
            )
        )
        .json()["task_id"]
    )


def default_model_runtime(env, root, monkeypatch, *, usage=True, on_http=None):
    """Real factory/SDK with only HTTP replaced; no external network or credentials."""
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("openai")
    requests = []

    async def handle(request):
        requests.append(request)
        if on_http:
            on_http(request)
        frame = {
            "choices": [
                {"index": 0, "delta": {"content": "Synthetic answer"}, "finish_reason": "stop"}
            ],
        }
        if usage:
            frame["usage"] = {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"data: " + json.dumps(frame).encode() + b"\n\ndata: [DONE]\n\n",
        )

    def transport(**kwargs):
        assert kwargs == {"retries": 0, "trust_env": False}
        return httpx.MockTransport(handle)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    runtime, state, _ = make_runtime(env, root)
    runtime.model_factory = model_factory(
        ("https://budget.invalid/v1", "synthetic-not-a-real-key"),
        lambda: state.settings()["config"]["mode"],
    )
    return runtime, state, requests


def configure_budget(env, task, *, limit=5000, policy=None, request_id="configure-budget"):
    budgets = BudgetService(env[2])
    env[2].submit(
        budgets.configure_limits(
            env[1],
            task,
            amount_limit_micros=0,
            token_limit=limit,
            policy=policy or TaskBudgetPolicy(),
            request_id=request_id,
            deadline_monotonic_ms=int(time.monotonic() * 1000) + 5000,
        )
    ).result(5)
    return budgets


def reservation_rows(env):
    return env[2].read(
        lambda db: db.execute(
            "SELECT call_ref,status,reserved_tokens,actual_tokens FROM budget_reservations"
        ).fetchall()
    )


def assert_budget_paused(env, task, reason):
    assert env[3].snapshot(env[1], task)["state"] == "PAUSED"
    checkpoint = env[2].read(
        lambda db: db.execute(
            "SELECT checkpoint_json FROM tasks WHERE task_id=?", (task,)
        ).fetchone()[0]
    )
    assert json.loads(checkpoint)["paused_reason"] == "BUDGET_EXHAUSTED:" + reason


@pytest.mark.parametrize("gate", ["tokens", "duration", "calls", "unicode"])
def test_default_factory_budget_gate_prevents_http(local_api_env, tmp_path, monkeypatch, gate):
    runtime, state, requests = default_model_runtime(local_api_env, tmp_path, monkeypatch)
    task = submit(local_api_env, "长历史" * 3000 if gate == "unicode" else "Synthetic goal")
    policy = TaskBudgetPolicy(max_model_calls=0) if gate == "calls" else TaskBudgetPolicy()
    if gate == "duration":
        policy = replace(policy, max_duration_ms=1)
        now = time.time_ns() + 60_000_000_000
        monkeypatch.setattr("openbot.application.budgets.time.time_ns", lambda: now)
    configure_budget(local_api_env, task, limit=0 if gate == "tokens" else 5000, policy=policy)
    try:
        runtime.start(task)
        wait_for(
            lambda: any(
                e["kind"] in {"RUN_INTERRUPTED", "RUN_FINISHED"}
                for e in state.trace(task)["events"]
            )
        )
        assert requests == []
        assert reservation_rows(local_api_env) == []
        reason = {"duration": "MAX_DURATION_MS", "calls": "MAX_MODEL_CALLS"}.get(
            gate, "TOKEN_LIMIT"
        )
        assert_budget_paused(local_api_env, task, reason)
    finally:
        runtime.close()


@pytest.mark.parametrize("usage", [True, False])
def test_default_factory_reserves_before_http_and_accounts_once(
    local_api_env, tmp_path, monkeypatch, usage
):
    during_http = []
    runtime, state, requests = default_model_runtime(
        local_api_env,
        tmp_path,
        monkeypatch,
        usage=usage,
        on_http=lambda _: during_http.extend(reservation_rows(local_api_env)),
    )
    task = submit(local_api_env)
    budgets = configure_budget(local_api_env, task, limit=2048)
    try:
        runtime.start(task)
        wait_for(
            lambda: any(
                e["kind"] in {"RUN_FINISHED", "RUN_INTERRUPTED"}
                for e in state.trace(task)["events"]
            )
        )
        assert len(requests) == len(during_http) == 1
        assert during_http[0][1] == "RESERVED"
        reserved = during_http[0][2]
        payload = json.loads(requests[0].content)
        assert payload["max_completion_tokens"] == 256
        assert reserved >= len(requests[0].content) + 256
        rows = reservation_rows(local_api_env)
        assert rows == [
            (during_http[0][0], "SETTLED" if usage else "UNKNOWN", reserved, 20 if usage else None)
        ]
        snapshot = budgets.snapshot(local_api_env[1], task)
        assert snapshot["tokens_spent"] == (20 if usage else 0)
        assert snapshot["tokens_reserved"] == (0 if usage else reserved)
        events = local_api_env[2].read(
            lambda db: db.execute(
                "SELECT event_type FROM events WHERE aggregate_kind='Budget'"
            ).fetchall()
        )
        assert events.count(("BUDGET_RESERVED",)) == 1
        assert events.count(("BUDGET_SETTLED",)) == (1 if usage else 0)
        assert events.count(("BUDGET_UNKNOWN",)) == (0 if usage else 1)
    finally:
        runtime.close()


def running_model_request(env, runtime, state, task, *, blocks, floor=0, ref="budget-request"):
    snapshot = env[3].snapshot(env[1], task)
    if snapshot["state"] != "RUNNING":
        env[2].submit(
            env[3].command(
                env[1],
                task,
                snapshot["version"],
                "RUNNING",
                "start-budget-test",
                int(time.monotonic() * 1000) + 5000,
            )
        ).result(5)
    config = state.settings()["config"]
    model = runtime.model_factory(config, RuntimeBudget(env[2], env[1], task))
    request = ModelRequest(ref, config["model"], blocks, int(time.monotonic() * 1000) + 5000, floor)
    return model, request


@pytest.mark.parametrize("large_part", ["history", "tool_result", "schema"])
def test_default_factory_sizes_full_payload_before_admission(
    local_api_env, tmp_path, monkeypatch, large_part
):
    runtime, state, requests = default_model_runtime(local_api_env, tmp_path, monkeypatch)
    task = submit(local_api_env)
    configure_budget(local_api_env, task)
    blocks = (Text("Synthetic goal"),)
    if large_part == "history":
        blocks = tuple(Text("多轮历史" * 60) for _ in range(10))
    elif large_part == "tool_result":
        blocks += (
            ToolCall("read_1", "mcp_read_text", b'{"path":"demo.txt"}'),
            ToolResult("read_1", ("工具结果" * 600).encode()),
            Text("Summarize"),
        )
    else:
        from openbot.application import runtime_factory

        manifest = runtime_factory.DEMO_MANIFEST
        schema = json.loads(manifest.input_schema)
        schema["description"] = "工具说明" * 600
        monkeypatch.setattr(
            runtime_factory,
            "DEMO_MANIFEST",
            replace(
                manifest,
                input_schema=json.dumps(schema, ensure_ascii=False).encode(),
            ),
        )
    model, request = running_model_request(
        local_api_env,
        runtime,
        state,
        task,
        blocks=blocks,
        floor=4096,
    )
    try:
        with pytest.raises(PermissionError, match="^BUDGET_ADMISSION_DENIED$"):
            asyncio.run(model.generate(request))
        assert requests == []
        assert reservation_rows(local_api_env) == []
        assert_budget_paused(local_api_env, task, "TOKEN_LIMIT")
    finally:
        asyncio.run(model.close())
        runtime.close()


@pytest.mark.parametrize("initial_limit", [5000, 10000])
def test_default_factory_concurrent_reservation_exhaustion_prevents_second_http(
    local_api_env, tmp_path, monkeypatch, initial_limit
):
    entered, release = threading.Event(), threading.Event()

    def hold_first(request):
        if json.loads(request.content)["messages"][0]["content"] == "First":
            entered.set()
            assert release.wait(5)

    runtime, state, requests = default_model_runtime(
        local_api_env,
        tmp_path,
        monkeypatch,
        on_http=hold_first,
    )
    task = submit(local_api_env)
    budgets = configure_budget(local_api_env, task, limit=initial_limit)
    first, req1 = running_model_request(
        local_api_env,
        runtime,
        state,
        task,
        blocks=(Text("First"),),
        floor=5000,
        ref="first",
    )
    second, req2 = running_model_request(
        local_api_env,
        runtime,
        state,
        task,
        blocks=(Text("Second"),),
        floor=5000,
        ref="second",
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, first.generate(req1))
        try:
            assert entered.wait(5)
            assert budgets.snapshot(local_api_env[1], task)["tokens_reserved"] == 5000
            if initial_limit > 5000:
                configure_budget(local_api_env, task, limit=5000, request_id="shrink-inflight")
            with pytest.raises(PermissionError, match="^BUDGET_ADMISSION_DENIED$"):
                asyncio.run(second.generate(req2))
            assert len(requests) == 1
            assert_budget_paused(local_api_env, task, "TOKEN_LIMIT")
        finally:
            release.set()
            future.result(5)
            asyncio.run(first.close())
            asyncio.run(second.close())
            runtime.close()
    assert len(reservation_rows(local_api_env)) == 1
    assert budgets.snapshot(local_api_env[1], task)["tokens_spent"] == 20


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
        interrupted = next(e for e in state.trace(task)["events"] if e["kind"] == "RUN_INTERRUPTED")
        assert interrupted["data"]["error_code"] == "MCP_CAPABILITY_UNAVAILABLE"
        assert not any(e["kind"] == "TOOL_PROPOSED" for e in state.trace(task)["events"])
    finally:
        runtime.close()


def test_unknown_interruption_detail_is_not_persisted(local_api_env, tmp_path):
    def fail():
        raise PermissionError("synthetic-private-detail-should-never-persist")

    runtime, state, _ = make_runtime(local_api_env, tmp_path, on_request=fail)
    task = submit(local_api_env)
    try:
        runtime.start(task)
        wait_for(lambda: any(e["kind"] == "RUN_INTERRUPTED" for e in state.trace(task)["events"]))
        trace = state.trace(task)
        assert "synthetic-private-detail" not in json.dumps(trace)
        interrupted = next(e for e in trace["events"] if e["kind"] == "RUN_INTERRUPTED")
        assert interrupted["data"]["error_code"] == "PermissionError"
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


def outcome_row(env, task_id):
    raw = env[2].read(
        lambda db: db.execute(
            "SELECT outcome_json FROM tasks WHERE task_id=?", (task_id,)
        ).fetchone()[0]
    )
    return None if raw is None else json.loads(raw)


@pytest.mark.skipif(
    not hasattr(os, "O_NOFOLLOW"), reason="Requires POSIX demo-file guards; Windows is unqualified"
)
def test_chat_outcome_claims_no_evidence_and_releases_the_run(local_api_env, tmp_path):
    runtime, state, _ = make_runtime(local_api_env, tmp_path, model_tool=False)
    task = submit(local_api_env)
    try:
        runtime.start(task)
        wait_for(lambda: local_api_env[3].snapshot(local_api_env[1], task)["state"] == "SUCCEEDED")
        wait_for(lambda: state.run(task) == {})
        outcome = outcome_row(local_api_env, task)
        assert outcome["task_kind"] == "CHAT"
        assert outcome["source_refs"] == []
        assert "RUN_CLOSED" in [e["kind"] for e in state.trace(task)["events"]]
        # A finished run must not keep holding the profile's single active-run slot.
        second = submit(local_api_env, goal="Read demo.txt using the MCP tool and summarize again")
        assert runtime.start(second)["run_id"]
        wait_for(lambda: state.run(second) == {})
    finally:
        runtime.close()


@pytest.mark.skipif(
    not hasattr(os, "O_NOFOLLOW"), reason="Requires POSIX demo-file guards; Windows is unqualified"
)
def test_denied_approval_releases_the_active_run_slot(local_api_env, tmp_path):
    runtime, state, _ = make_runtime(local_api_env, tmp_path)
    task = submit(local_api_env)
    try:
        runtime.start(task)
        decide(local_api_env, state, task, "DENY")
        wait_for(lambda: state.run(task) == {})
        assert local_api_env[3].snapshot(local_api_env[1], task)["state"] == "QUEUED"
        assert any(e["kind"] == "RUN_CLOSED" for e in state.trace(task)["events"])
        # Denial must not strand the queued task: a fresh run is startable without recovery.
        second_run = runtime.start(task)["run_id"]
        wait_for(
            lambda: any(
                e["kind"] == "RUN_CLOSED" and e["run_id"] == second_run
                for e in state.trace(task)["events"]
            )
        )
        # Effects of the earlier run cannot launder the resumed run's outcome claim.
        assert outcome_row(local_api_env, task)["task_kind"] == "CHAT"
    finally:
        runtime.close()


@pytest.mark.skipif(
    not hasattr(os, "O_NOFOLLOW"), reason="Requires POSIX demo-file guards; Windows is unqualified"
)
def test_verified_effect_binds_outcome_source_refs(local_api_env, tmp_path):
    runtime, state, _ = make_runtime(local_api_env, tmp_path)
    task = submit(local_api_env)
    try:
        runtime.start(task)
        decide(local_api_env, state, task)
        wait_for(
            lambda: local_api_env[3].snapshot(local_api_env[1], task)["state"] == "SUCCEEDED",
            timeout=8,
        )
    finally:
        runtime.close()
    events = state.trace(task)["events"]
    returned = [e for e in events if e["kind"] == "TOOL_RETURNED"]
    assert returned, "a verified tool effect must be recorded before completion"
    expected = []
    for event in returned:
        for key, prefix in (("operation_id", "operation:"), ("artifact_id", "artifact:")):
            if key in event["data"] and prefix + event["data"][key] not in expected:
                expected.append(prefix + event["data"][key])
    outcome = outcome_row(local_api_env, task)
    assert outcome["source_refs"] == expected
    assert not any(ref.startswith("task:") for ref in outcome["source_refs"])
    verified_at = max(i for i, e in enumerate(events) if e["kind"] == "TOOL_RETURNED")
    assert [e["kind"] for e in events].index("OUTCOME_VERIFIED") > verified_at
