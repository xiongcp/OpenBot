import json
import sys
import time
from dataclasses import replace

import pytest
from openbot.contracts import canonicalize

from tests.contracts.local_api.test_local_api_contracts import local_api_env
from tests.integration.test_agent_runtime import make_runtime, wait_for
from tests.integration.test_client_state import apply_config

__all__ = ["local_api_env"]


def event(**changes):
    return {
        "event_id": "ev_synthetic_1",
        "tenant_key": "ten_synthetic",
        "app_id": "cli_synthetic",
        "open_id": "ou_synthetic",
        "chat_id": "oc_synthetic",
        "text": "你好 / Hello",
        **changes,
    }


def setup(env, root):
    from openbot.application.feishu_ingress import FeishuIngress

    runtime, state, _ = make_runtime(env, root, model_tool=False)
    apply_config(state, feishu_enabled=True)
    ingress = FeishuIngress(state, env[0]._inbox, runtime)
    ingress.configure("cli_synthetic", "setup")
    return ingress, runtime, state


def test_first_contact_requires_local_confirm_and_paired_replay_never_restarts(
    local_api_env, tmp_path
):
    ingress, runtime, state = setup(local_api_env, tmp_path)
    try:
        pending = ingress.receive(canonicalize(event()))
        assert pending["status"] == "PENDING_LOCAL_CONFIRMATION"
        assert not local_api_env[0]._inbox._writer.read(
            lambda db: db.execute("SELECT task_id FROM tasks").fetchall()
        )
        candidate = ingress.snapshot()["candidates"][0]
        assert candidate["chat_id"] == "oc_synthetic"
        confirmation = ingress.confirm(candidate["candidate_id"], "confirm-1")
        assert confirmation["status"] == "ACTIVE_OWNER"
        assert ingress.confirm(candidate["candidate_id"], "confirm-1") == confirmation
        accepted = ingress.receive(canonicalize(event(event_id="ev_synthetic_2")))
        task = accepted["task_id"]
        wait_for(lambda: any(e["kind"] == "RUN_FINISHED" for e in state.trace(task)["events"]))
        assert ingress.receive(canonicalize(event(event_id="ev_synthetic_2")))["task_id"] == task
        assert sum(e["kind"] == "MODEL_REQUESTED" for e in state.trace(task)["events"]) == 1
        hb = ingress.heartbeat(
            json.dumps({"stage": "CONNECTED", "task_ids": [task, "tsk_nonexistent"]})
        )
        assert hb["finished"][task] == "SUCCEEDED"
        assert "tsk_nonexistent" not in hb["finished"]
        counts = state.writer.read(
            lambda db: (
                db.execute("SELECT count(*) FROM channel_identities").fetchone()[0],
                db.execute(
                    "SELECT count(*) FROM events WHERE event_type='FEISHU_PAIRED'"
                ).fetchone()[0],
                db.execute(
                    "SELECT count(*) FROM outbox WHERE semantic_key LIKE 'client:feishu-pair:%'"
                ).fetchone()[0],
            )
        )
        assert counts == (1, 1, 1)
        assert any(e["data"].get("source") == "FEISHU" for e in state.trace(task)["events"])
    finally:
        runtime.close()


def test_scope_offline_redaction_and_expired_candidate(local_api_env, tmp_path):
    ingress, runtime, state = setup(local_api_env, tmp_path)
    try:
        ingress.receive(canonicalize(event()))
        candidate = ingress.snapshot()["candidates"][0]
        ingress.confirm(candidate["candidate_id"], "confirm")
        with pytest.raises(PermissionError):
            ingress.receive(canonicalize(event(app_id="cli_other")))
        assert (
            ingress.receive(canonicalize(event(chat_id="oc_other")))["status"]
            == "PENDING_LOCAL_CONFIRMATION"
        )
        from openbot.observability.redaction import RedactionPipeline

        state.redactor = RedactionPipeline(registered_secrets=("synthetic-credential-canary",))
        accepted = ingress.receive(
            canonicalize(event(event_id="ev_redact", text="synthetic-credential-canary hello"))
        )
        goal = state.writer.read(
            lambda db: db.execute(
                "SELECT goal FROM tasks WHERE task_id=?", (accepted["task_id"],)
            ).fetchone()[0]
        )
        assert "synthetic-credential-canary" not in goal
        other = ingress.snapshot()["candidates"][0]
        ingress._pending[other["candidate_id"]]["expires_at"] = time.monotonic() - 1
        with pytest.raises(PermissionError):
            ingress.confirm(other["candidate_id"], "expired")
        apply_config(state, mode="OFFLINE", feishu_enabled=False)
        with pytest.raises(PermissionError):
            ingress.receive(canonicalize(event(event_id="ev_offline")))
        assert ingress.config()["connect_allowed"] is False
    finally:
        runtime.close()


def test_unpaired_candidates_are_bounded_and_cannot_inject_owner(local_api_env, tmp_path):
    ingress, runtime, _ = setup(local_api_env, tmp_path)
    try:
        with pytest.raises(ValueError):
            ingress.receive(json.dumps(event(principal_id="attacker")))
        for n in range(20):
            ingress.receive(canonicalize(event(open_id=f"ou_synthetic_{n}")))
        assert len(ingress.snapshot()["candidates"]) <= 16
    finally:
        runtime.close()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX guardian pipe protocol")
@pytest.mark.parametrize("scenario", ["duplicate", "unpaired", "rollback", "unauthorized"])
def test_worker_ack_follows_authenticated_durable_inbox_only(
    local_api_env, tmp_path, monkeypatch, scenario
):
    from openbot.adapters.local_api.client_routes import ClientRoutes
    from openbot.cli import CliApiSession
    from openbot.storage import inbox as inbox_module
    from openbot_feishu import live_gateway as gateway

    from tests.unit.test_feishu_live_gateway import _Reactor, protocol_spawn

    ingress, runtime, state = setup(local_api_env, tmp_path)
    runtime.model_factory = None  # This slice tests admission, not model/tool execution.
    api = local_api_env[0]
    api._client = ClientRoutes(state, runtime, ingress)
    if scenario != "unpaired":
        ingress.receive(canonicalize(event()))
        ingress.confirm(ingress.snapshot()["candidates"][0]["candidate_id"], "confirm-ack")
    if scenario == "rollback":
        emit = inbox_module.emit_state

        def fail_after_effects(*args, **kwargs):
            emit(*args, **kwargs)
            raise ValueError("synthetic failure before commit")

        monkeypatch.setattr(inbox_module, "emit_state", fail_after_effects)

    class Transport:
        def request(self, req):
            if scenario == "unauthorized" and req.path == "/v1/feishu/events":
                req = replace(
                    req, headers={**req.headers, "Authorization": "Bearer synthetic-invalid"}
                )
            return api.handle(req)

    session = CliApiSession("pro_test1", local_api_env[8], Transport())
    monkeypatch.setattr(gateway, "Reactor", lambda *args: _Reactor())
    repeated = event(message_id="om_synthetic")
    spawn, result_path, children = protocol_spawn(tmp_path, [repeated, repeated])
    try:
        if scenario == "duplicate":
            gateway.supervise(
                session,
                tmp_path,
                "cli_synthetic",
                "synthetic-only",
                spawn=spawn,
                lifetime_seconds=4,
            )
        else:
            with pytest.raises(ConnectionError, match="FEISHU_INGRESS_REJECTED"):
                gateway.supervise(
                    session,
                    tmp_path,
                    "cli_synthetic",
                    "synthetic-only",
                    spawn=spawn,
                    lifetime_seconds=4,
                )
        acks = [json.loads(line) for line in json.loads(result_path.read_text())]
        expected = (
            [
                {"type": "ack", "event_id": "ev_synthetic_1", "callback_id": "0" * 31 + "1"},
                {"type": "ack", "event_id": "ev_synthetic_1", "callback_id": "0" * 31 + "2"},
            ]
            if scenario == "duplicate"
            else []
        )
        assert acks == expected
        assert children[0].poll() == 0
        counts = state.writer.read(
            lambda db: (
                db.execute("SELECT count(*) FROM inbox").fetchone()[0],
                db.execute("SELECT count(*) FROM tasks").fetchone()[0],
                db.execute("SELECT count(*) FROM events WHERE event_type='TASK_QUEUED'").fetchone()[
                    0
                ],
                db.execute(
                    "SELECT count(*) FROM outbox WHERE semantic_key LIKE 'task:%'"
                ).fetchone()[0],
            )
        )
        assert counts == ((1, 1, 1, 1) if scenario == "duplicate" else (0, 0, 0, 0))
        assert runtime.tool.calls == 0
    finally:
        runtime.close()
