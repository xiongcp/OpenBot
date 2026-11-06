import json

import pytest
from openbot.adapters.local_api.server import ApiRequest

from tests.contracts.local_api.test_local_api_contracts import _headers, local_api_env
from tests.integration.test_agent_runtime import SyntheticModel, wait_for
from tests.integration.test_client_state import service

__all__ = ["local_api_env"]


@pytest.fixture
def client_env(local_api_env, tmp_path):
    from openbot.adapters.local_api.client_routes import ClientRoutes
    from openbot.application.agent_runtime import AgentRuntime

    api, ctx, writer, tasks, ops, dispatch = local_api_env[:6]
    state = service(local_api_env)
    runtime = AgentRuntime(
        state=state,
        tasks=tasks,
        operations=ops,
        dispatcher=dispatch,
        artifacts=api._artifacts,
        registry=api._registry,
        workspace=tmp_path,
        runtime_epoch="ep_1",
        tool=None,
        model_factory=lambda config, budget: SyntheticModel(budget, tool=False),
    )
    api._client = ClientRoutes(state, runtime)
    try:
        yield local_api_env, state, runtime
    finally:
        runtime.close()


def call(env, method, path, body=None, *, token=None, query=None, headers=None):
    return env[0].handle(
        ApiRequest(
            method,
            path,
            body=json.dumps(body) if body is not None else b"",
            headers=_headers(token or env[7], **(headers or {})),
            query=query or {},
        )
    )


def test_settings_preview_apply_is_owner_only_and_scoped(client_env):
    env, state, _ = client_env
    settings = call(env, "GET", "/v1/client/settings").json()
    assert settings["revision"] == 0
    body = {"expected_revision": 0, "config": {**settings["config"], "mode": "CONNECTED"}}
    preview = call(env, "POST", "/v1/client/settings/preview", body)
    assert preview.status_code == 200
    for token in (env[8], env[9]):
        assert (
            call(
                env,
                "POST",
                "/v1/client/settings/apply",
                {**preview.json(), "confirm": True},
                token=token,
            ).status_code
            == 403
        )
    applied = call(
        env,
        "POST",
        "/v1/client/settings/apply",
        {**preview.json(), "confirm": True},
    )
    assert applied.status_code == 200
    assert state.settings()["revision"] == 1
    assert call(env, "GET", "/v1/client/settings", token=env[9]).status_code == 200
    other = env[0]._tokens.issue(
        profile_id="pro_test1", principal_id="pri_other", scope="owner_cli"
    )
    assert call(env, "GET", "/v1/client/runs", token=other).status_code == 403


def test_client_run_start_trace_and_readonly_replay(client_env):
    env, state, runtime = client_env
    from tests.integration.test_client_state import apply_config

    apply_config(state, mode="CONNECTED")
    created = call(
        env,
        "POST",
        "/v1/tasks",
        {"workspace_id": "wsp_test1", "goal": "合成 / synthetic", "network_mode": "CONNECTED"},
    )
    task = created.json()["task_id"]
    started = call(env, "POST", f"/v1/client/tasks/{task}/start", {})
    assert started.status_code == 202
    wait_for(lambda: env[3].snapshot(env[1], task)["state"] == "SUCCEEDED")
    runs = call(env, "GET", "/v1/client/runs").json()["runs"]
    assert runs[0]["run_id"] == started.json()["run_id"]
    wait_for(
        lambda: state.trace(task)["events"][-1]["kind"] == "RUN_CLOSED",
    )
    trace = call(env, "GET", f"/v1/client/tasks/{task}/trace", token=env[9]).json()
    assert [e["kind"] for e in trace["events"][-2:]] == ["RUN_FINISHED", "RUN_CLOSED"]
    assert trace["events"][-2]["data"] == {"status": "SUCCEEDED"}
    assert trace["events"][-1]["data"] == {"status": "SUCCEEDED"}
    assert trace["run_id"] is None, "a retired run must not keep holding the active-run slot"
    assert (
        call(
            env,
            "GET",
            f"/v1/client/tasks/{task}/trace",
            query={"after_seq": str(trace["last_seq"])},
        ).json()["events"]
        == []
    )
    assert call(env, "POST", f"/v1/client/tasks/{task}/start", {}).status_code == 409
    runtime.model_factory = None
    assert call(env, "GET", "/v1/client/health").json()["credentials_configured"] is False


@pytest.mark.parametrize("cursor", ["-1", "abc", "9" * 30])
def test_invalid_trace_cursor_is_rejected(client_env, cursor):
    env, _, _ = client_env
    response = call(env, "GET", "/v1/client/tasks/tsk_unknown/trace", query={"after_seq": cursor})
    assert response.status_code == 400


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.test"},
        {"X-OpenBot-Profile": "pro_other"},
        {"Host": "127.0.0.1.evil.test"},
    ],
)
def test_client_rejects_untrusted_origin_profile_or_host(client_env, headers):
    env, _, _ = client_env
    assert call(env, "GET", "/v1/client/settings", headers=headers).status_code == 403
