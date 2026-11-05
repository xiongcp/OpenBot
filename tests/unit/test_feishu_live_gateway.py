import json
import subprocess
import sys

import pytest


def test_normalize_only_bounded_private_text_and_never_accepts_actor_fields():
    from openbot_feishu.live_gateway import normalize_message

    payload = {
        "header": {"event_id": "ev_test", "tenant_key": "ten_test", "app_id": "cli_test"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_test"}, "sender_type": "user"},
            "message": {
                "chat_type": "p2p",
                "chat_id": "oc_test",
                "message_type": "text",
                "message_id": "om_test",
                "content": json.dumps({"text": "hello"}),
            },
            "principal_id": "evil",
        },
    }
    result = normalize_message(payload)
    assert set(result) == {
        "event_id",
        "tenant_key",
        "app_id",
        "open_id",
        "chat_id",
        "text",
        "message_id",
    }
    assert result["text"] == "hello"
    payload["event"]["message"]["chat_type"] = "group"
    assert normalize_message(payload) is None
    payload["event"]["message"].update(chat_type="p2p", content=json.dumps({"text": "x" * 4097}))
    assert normalize_message(payload) is None


@pytest.mark.skipif(sys.platform == "win32", reason="macOS/POSIX consumer lock")
def test_second_known_consumer_is_refused(tmp_path):
    from openbot_feishu.live_gateway import ConsumerLock

    with ConsumerLock(tmp_path):
        script = "from pathlib import Path; from openbot_feishu.live_gateway import ConsumerLock; "
        script += f"ConsumerLock(Path({str(tmp_path)!r})).__enter__()"
        child = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        assert child.returncode != 0
        assert "FEISHU_CONSUMER_ALREADY_RUNNING" in child.stderr
    with ConsumerLock(tmp_path):
        pass


def test_guardian_checks_offline_before_launching_sdk(tmp_path):
    from openbot_feishu.live_gateway import supervise

    class Session:
        def call(self, method, path, **kwargs):
            class Response:
                status_code = 200

                def json(self):
                    return {"app_id": "cli_test", "connect_allowed": False}

            return Response()

    started = []
    with pytest.raises(PermissionError, match="FEISHU_DISABLED_OR_OFFLINE"):
        supervise(
            Session(),
            tmp_path,
            "cli_test",
            "synthetic-secret",
            spawn=lambda *a, **k: started.append(True),
        )
    assert not started


@pytest.mark.skipif(sys.platform == "win32", reason="macOS/POSIX consumer guardian")
def test_disabling_gateway_waits_for_child_exit_before_unlock(tmp_path):
    from openbot_feishu.live_gateway import ConsumerLock, supervise

    children = []

    class Session:
        checks = 0

        def call(self, method, path, **kwargs):
            if method == "GET":
                self.checks += 1
            allowed = self.checks < 3

            class Response:
                status_code = 200

                def json(self):
                    return {"app_id": "cli_test", "connect_allowed": allowed}

            return Response()

    def spawn(*args, **kwargs):
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import sys,time;sys.stdin.readline();print('CONNECTED',flush=True);time.sleep(60)",
            ],
            **kwargs,
        )
        children.append(child)
        return child

    supervise(Session(), tmp_path, "cli_test", "synthetic-only", spawn=spawn)
    assert children[0].poll() is not None
    with ConsumerLock(tmp_path):
        pass


class _Reply:
    def __init__(self, status, doc):
        self.status_code, self._doc = status, doc

    def json(self):
        return self._doc


class _Session:
    def __init__(self, reply):
        self.reply, self.bodies = reply, []

    def call(self, method, path, **kwargs):
        self.bodies.append(kwargs["body"])
        return self.reply


class _Reactor:
    def __init__(self, fail=False):
        self.added, self.removed, self.fail = [], [], fail

    def acknowledge(self, message_id):
        self.added.append(message_id)
        if self.fail:
            raise RuntimeError("synthetic reaction failure with secret-token")
        return "rc_fake_" + message_id

    def remove(self, message_id, reaction_id):
        self.removed.append((message_id, reaction_id))
        if self.fail:
            raise RuntimeError("synthetic removal failure with secret-token")


EVENT = (
    b'{"event_id":"ev1","tenant_key":"t","app_id":"cli_x","open_id":"ou_1",'
    b'"chat_id":"oc_1","text":"hi","message_id":"om_1"}'
)


def test_normalize_keeps_message_id_for_receipt_only():
    from openbot_feishu.live_gateway import normalize_message

    payload = {
        "header": {"event_id": "e", "tenant_key": "t", "app_id": "cli_x"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou"}, "sender_type": "user"},
            "message": {
                "chat_type": "p2p",
                "chat_id": "oc",
                "message_type": "text",
                "message_id": "om_9",
                "content": json.dumps({"text": "hi"}),
            },
        },
    }
    assert normalize_message(payload)["message_id"] == "om_9"
    payload["event"]["message"]["message_id"] = "bad id\r\n"
    assert normalize_message(payload) is None


def test_receipt_only_after_durable_admission_and_never_sent_to_daemon():
    from openbot_feishu.live_gateway import forward_event

    reactor, session = _Reactor(), _Session(_Reply(201, {"task_id": "tsk_1"}))
    assert forward_event(session, EVENT, reactor) == "TASK_PERSISTED"
    assert reactor.added == ["om_1"]
    assert "message_id" not in session.bodies[0]


@pytest.mark.parametrize(
    "reply",
    [
        _Reply(201, {"status": "PENDING_LOCAL_CONFIRMATION", "candidate_id": "pcn_1"}),
        _Reply(403, {"code": "FEISHU_DISABLED_OR_OFFLINE"}),
    ],
)
def test_no_receipt_for_unpaired_or_rejected_events(reply):
    from openbot_feishu.live_gateway import forward_event

    reactor = _Reactor()
    try:
        forward_event(_Session(reply), EVENT, reactor)
    except ConnectionError:
        pass
    assert reactor.added == []


def test_reaction_failure_is_best_effort_and_not_leaked():
    from openbot_feishu.live_gateway import forward_event

    result = forward_event(_Session(_Reply(201, {"task_id": "tsk_1"})), EVENT, _Reactor(fail=True))
    assert result == "TASK_PERSISTED"


def test_reaction_lifecycle_tracked_in_pending_and_removed_on_completion():
    from openbot_feishu.live_gateway import forward_event

    reactor, session = _Reactor(), _Session(_Reply(201, {"task_id": "tsk_1"}))
    pending = {}
    assert forward_event(session, EVENT, reactor, pending) == "TASK_PERSISTED"
    assert pending == {"tsk_1": ("om_1", "rc_fake_om_1")}

    # Simulate heartbeat detecting terminal state and removing reaction
    mid, rid = pending.pop("tsk_1")
    reactor.remove(mid, rid)
    assert reactor.removed == [("om_1", "rc_fake_om_1")]
    assert pending == {}


def test_reactor_real_delete_request_structure():
    from openbot_feishu.live_gateway import Reactor

    calls = []

    def fake_post(path, body, token, method="POST"):
        calls.append((path, body, token, method))
        if "auth" in path:
            return {"code": 0, "tenant_access_token": "tok_123", "expire": 7200}
        if method == "DELETE":
            return {"code": 0}
        return {"code": 0, "data": {"reaction_id": "rc_real_9"}}

    reactor = Reactor("cli_x", "sec_x", post=fake_post)
    rid = reactor.acknowledge("om_test")
    assert rid == "rc_real_9"
    assert calls[1] == (
        "/open-apis/im/v1/messages/om_test/reactions",
        {"reaction_type": {"emoji_type": "Get"}},
        "tok_123",
        "POST",
    )

    reactor.remove("om_test", rid)
    assert calls[2] == (
        "/open-apis/im/v1/messages/om_test/reactions/rc_real_9",
        {},
        "tok_123",
        "DELETE",
    )
