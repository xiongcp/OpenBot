import json

import pytest
from openbot.contracts import ContractError, strict_json
from openbot.observability.redaction import RedactionPipeline
from openbot.storage.writer import RequestConflict

from tests.contracts.local_api.test_local_api_contracts import local_api_env

__all__ = ["local_api_env"]


def service(env, *, secrets=()):
    from openbot.application.client_state import ClientState

    return ClientState(env[2], env[1], RedactionPipeline(registered_secrets=secrets))


def apply_config(state, **updates):
    old = state.settings()
    raw = json.dumps({"expected_revision": old["revision"], "config": old["config"] | updates})
    preview = state.preview(raw)
    return state.apply(json.dumps(preview | {"confirm": True}), "settings-" + str(old["revision"]))


def new_task(env, goal="synthetic task"):
    import time

    return strict_json(
        env[0]
        ._inbox.submit(
            env[1],
            goal,
            json.dumps({"workspace_id": "wsp_test1", "goal": goal, "network_mode": "OFFLINE"}),
            int(time.monotonic() * 1000) + 5000,
        )
        .result()
    )["task_id"]


def test_config_cas_is_durable_and_replay_changes_nothing(local_api_env):
    state = service(local_api_env)
    assert state.settings()["revision"] == 0
    preview = state.preview(
        json.dumps(
            {
                "expected_revision": 0,
                "config": state.settings()["config"] | {"model": "another-model"},
            }
        )
    )
    assert state.settings()["revision"] == 0
    receipt = state.apply(json.dumps(preview | {"confirm": True}), "apply-once")
    assert receipt["revision"] == 1
    assert state.apply(json.dumps(preview | {"confirm": True}), "apply-once") == receipt
    assert service(local_api_env).settings()["config"]["model"] == "another-model"
    with pytest.raises(RequestConflict):
        state.apply(json.dumps(preview | {"confirm": True}), "stale-preview")
    assert state.settings()["revision"] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"api_key": "synthetic"},
        {"max_steps": 0},
        {"max_steps": True},
        {"mode": "OFFLINE", "feishu_enabled": True},
        {"model": "https://unapproved.invalid"},
    ],
)
def test_invalid_config_preserves_all_state(local_api_env, change):
    state = service(local_api_env)
    before = state.settings()
    with pytest.raises(ContractError):
        state.preview(json.dumps({"expected_revision": 0, "config": before["config"] | change}))
    assert state.settings() == before


def test_duplicate_keys_and_tampered_preview_are_rejected(local_api_env):
    state = service(local_api_env)
    with pytest.raises(ContractError):
        state.preview('{"expected_revision":0,"expected_revision":1,"config":{}}')
    p = state.preview(json.dumps({"expected_revision": 0, "config": state.settings()["config"]}))
    p["config"]["model"] = "changed"
    with pytest.raises(RequestConflict):
        state.apply(json.dumps(p | {"confirm": True}), "tamper")
    assert state.settings()["revision"] == 0


def test_mode_change_revises_authoritative_policy_and_existing_run_stays_pinned(local_api_env):
    state = service(local_api_env)
    task = new_task(local_api_env)
    run = state.start_run(task)
    assert state.start_run(task) == run
    apply_config(state, mode="CONNECTED", mcp_enabled=True)
    assert state.run(task)["config_revision"] == 0
    assert state.run(task)["config"]["mode"] == "OFFLINE"
    row = local_api_env[2].read(
        lambda db: db.execute("SELECT privacy_mode,policy_version FROM profile_config").fetchone()
    )
    assert row == ("CONNECTED", 2)
    assert state.settings()["revision"] == 1


def test_trace_is_persistent_parent_scoped_redacted_and_readonly(local_api_env):
    canary = "registered-canary-private-value"
    state = service(local_api_env, secrets=(canary,))
    task = new_task(local_api_env)
    run = state.start_run(task)
    first = state.record(task, "SKILL_LOADED", {"skill_id": "summary", "sha256": "a" * 64})
    second = state.record(
        task, "MODEL_RETURNED", {"text": canary + " safe"}, parent_event_id=first["event_id"]
    )
    assert second["parent_event_id"] == first["event_id"]
    doc = service(local_api_env).trace(task)
    assert doc["run_id"] == run["run_id"]
    assert canary not in json.dumps(doc)
    assert "[REDACTED]" in json.dumps(doc)
    assert state.trace(task, after_seq=first["global_seq"])["events"] == [second]
    assert state.trace(task) == doc
    with pytest.raises(ContractError):
        state.record(task, "MODEL_RETURNED", {"hidden_reasoning": "forbidden"})
    with pytest.raises(ContractError):
        state.record(task, "TOOL_RETURNED", {}, parent_event_id="evt_other_run")
    assert state.trace(task) == doc


def test_owner_revocation_prevents_read_and_write(local_api_env):
    state = service(local_api_env)
    local_api_env[2].read(lambda db: None)
    from openbot.storage.migrate import connect

    db = connect(local_api_env[2]._path)
    db.execute(
        "UPDATE principals SET status='REVOKED',revoked_at=2000 WHERE principal_id='pri_test1'"
    )
    db.close()
    with pytest.raises(PermissionError):
        state.settings()
    with pytest.raises(PermissionError):
        state.start_run("tsk_invalid")


@pytest.mark.parametrize("field,value", [("mode", []), ("locale", {}), ("model", None)])
def test_untrusted_field_types_have_safe_contract_errors(local_api_env, field, value):
    state = service(local_api_env)
    config = state.settings()["config"] | {field: value}
    with pytest.raises(ContractError):
        state.preview(json.dumps({"expected_revision": 0, "config": config}))


def test_run_started_is_a_replayable_fact_and_second_active_run_is_rejected(local_api_env):
    state = service(local_api_env)
    task = new_task(local_api_env)
    state.start_run(task)
    assert state.trace(task)["events"][0]["kind"] == "RUN_STARTED"
    other = new_task(local_api_env, "second synthetic task")
    with pytest.raises(RequestConflict):
        state.start_run(other)
