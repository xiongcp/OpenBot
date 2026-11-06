import json
import os
import select
import subprocess
import sys
import threading
import time
from pathlib import Path

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


@pytest.mark.parametrize("status", [200, 201])
def test_receipt_only_after_durable_admission_and_never_sent_to_daemon(status):
    from openbot_feishu.live_gateway import forward_event

    session = _Session(_Reply(status, {"task_id": "tsk_1", "state": "QUEUED", "version": 0}))
    receipt = forward_event(session, EVENT)
    assert receipt.task_id == "tsk_1"
    assert receipt.event_id == "ev1"
    assert receipt.message_id == "om_1"
    assert "message_id" not in session.bodies[0]
    assert session.bodies[0]["event_id"] == "ev1"


@pytest.mark.parametrize(
    "reply",
    [
        _Reply(201, {"status": "PENDING_LOCAL_CONFIRMATION", "candidate_id": "pcn_1"}),
        _Reply(201, {"status": "PENDING_LIMIT_REACHED"}),
        _Reply(403, {"code": "FEISHU_DISABLED_OR_OFFLINE"}),
        _Reply(503, {"code": "WRITER_UNAVAILABLE"}),
        _Reply(202, {"task_id": "tsk_1", "state": "QUEUED", "version": 0}),
        _Reply(201, {}),
        _Reply(200, {"task_id": "tsk_1"}),
        _Reply(201, {"task_id": "tsk_1", "state": "QUEUED", "version": True}),
    ],
)
def test_no_receipt_for_unpaired_or_rejected_events(reply):
    from openbot_feishu.live_gateway import forward_event

    with pytest.raises(ConnectionError, match="FEISHU_INGRESS_REJECTED"):
        forward_event(_Session(reply), EVENT)


def test_reaction_lifecycle_tracked_and_removed_on_completion():
    from openbot_feishu.live_gateway import _Presentation

    removed = threading.Event()

    class Reactor(_Reactor):
        def remove(self, message_id, reaction_id):
            super().remove(message_id, reaction_id)
            removed.set()

    reactor = Reactor()
    presentation = _Presentation(reactor)
    try:
        presentation.acknowledge("tsk_1", "om_1")
        deadline = time.monotonic() + 2
        while "tsk_1" not in presentation.task_ids() and time.monotonic() < deadline:
            removed.wait(0.01)
        assert presentation.task_ids() == ["tsk_1"]
        presentation.finish({"tsk_1": "SUCCEEDED"})
        assert removed.wait(2)
        assert reactor.removed == [("om_1", "rc_fake_om_1")]
        assert presentation.task_ids() == []
    finally:
        presentation.close()


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


def protocol_spawn(tmp_path, events):
    """A real child pipe peer; close stdin rather than signal any process during cleanup."""
    result_path = tmp_path / "synthetic-acks.json"
    children = []
    frames = [
        {"type": "event", "callback_id": f"{n:032x}", "event": event}
        for n, event in enumerate(events, 1)
    ]
    script = f"""
import json, os, select, sys, time
from pathlib import Path
sys.stdin.buffer.readline()
frames = {frames!r}
wire = b"CONNECTED\\n" + b"".join((json.dumps(f) + "\\n").encode() for f in frames)
os.write(sys.stdout.fileno(), wire)
data = b""
end = time.monotonic() + 2
while data.count(b"\\n") < len(frames):
    remaining = end - time.monotonic()
    if remaining <= 0 or not select.select([sys.stdin], [], [], remaining)[0]:
        break
    chunk = os.read(sys.stdin.fileno(), 4096)
    if not chunk:
        break
    data += chunk
Path({str(result_path)!r}).write_text(json.dumps(data.decode().splitlines()))
"""

    def spawn(*args, **kwargs):
        child = subprocess.Popen([sys.executable, "-c", script], **kwargs)
        child.terminate = child.stdin.close
        children.append(child)
        return child

    return spawn, result_path, children


class GuardianSession:
    def __init__(self, reply):
        self.reply = reply
        self.events = []

    def call(self, method, path, **kwargs):
        if (method, path) == ("GET", "/v1/feishu/config"):
            return _Reply(200, {"app_id": "cli_x", "connect_allowed": True})
        if (method, path) == ("POST", "/v1/feishu/health"):
            return _Reply(200, {"finished": {}})
        assert (method, path) == ("POST", "/v1/feishu/events")
        self.events.append(kwargs["body"])
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX guardian pipe protocol")
@pytest.mark.parametrize("status", [201, 200])
@pytest.mark.parametrize("presentation", ["ok", "failed", "blocked"])
def test_guardian_flushes_correlated_acks_without_waiting_for_presentation(
    tmp_path, monkeypatch, capsys, status, presentation
):
    from openbot_feishu import live_gateway as gateway

    release, entered = threading.Event(), threading.Event()

    class Reactor(_Reactor):
        def acknowledge(self, message_id):
            entered.set()
            if presentation == "blocked":
                release.wait(5)
            return super().acknowledge(message_id)

    reactor = Reactor(fail=presentation == "failed")
    monkeypatch.setattr(gateway, "Reactor", lambda *args: reactor)
    events = [json.loads(EVENT), {**json.loads(EVENT), "event_id": "ev2", "message_id": "om_2"}]
    spawn, result_path, children = protocol_spawn(tmp_path, events)
    session = GuardianSession(_Reply(status, {"task_id": "tsk_1", "state": "QUEUED", "version": 0}))
    try:
        gateway.supervise(
            session, tmp_path, "cli_x", "synthetic-only", spawn=spawn, lifetime_seconds=4
        )
        acks = [json.loads(line) for line in json.loads(result_path.read_text())]
        assert acks == [
            {"type": "ack", "event_id": "ev1", "callback_id": "0" * 31 + "1"},
            {"type": "ack", "event_id": "ev2", "callback_id": "0" * 31 + "2"},
        ], "durable receipts must be flushed to the actual worker stdin"
        assert session.events == [{k: v for k, v in e.items() if k != "message_id"} for e in events]
        assert entered.is_set()
        assert children[0].poll() == 0
        assert "secret-token" not in capsys.readouterr().out
    finally:
        release.set()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX guardian pipe protocol")
@pytest.mark.parametrize(
    "reply",
    [
        _Reply(201, {"status": "PENDING_LOCAL_CONFIRMATION", "candidate_id": "pcn_1"}),
        _Reply(201, {}),
        _Reply(401, {"code": "UNAUTHORIZED"}),
        _Reply(503, {"code": "WRITER_UNAVAILABLE"}),
        TimeoutError("synthetic commit deadline"),
    ],
)
def test_guardian_never_writes_ack_for_failed_or_uncommitted_receipt(tmp_path, monkeypatch, reply):
    from openbot_feishu import live_gateway as gateway

    reactor = _Reactor()
    monkeypatch.setattr(gateway, "Reactor", lambda *args: reactor)
    spawn, result_path, children = protocol_spawn(tmp_path, [json.loads(EVENT)])
    with pytest.raises((ConnectionError, TimeoutError)):
        gateway.supervise(
            GuardianSession(reply),
            tmp_path,
            "cli_x",
            "synthetic-only",
            spawn=spawn,
            lifetime_seconds=4,
        )
    assert json.loads(result_path.read_text()) == []
    assert reactor.added == []
    assert children[0].poll() == 0


# The fake SDK supplies only callback dispatch. Normalization, worker framing and ACK waiting
# are production code in a real child; no optional SDK, credential, socket or service is used.
FAKE_SDK_WORKER = r"""
import asyncio, json, sys, threading, types
from openbot_feishu.live_gateway import _worker
payloads, concurrent = json.loads(sys.argv[1]), json.loads(sys.argv[2])
class Builder:
    @staticmethod
    def builder(*args): return Builder()
    def register_p2_im_message_receive_v1(self, callback):
        self.callback = callback
        return self
    def build(self): return self.callback
class Client:
    def __init__(self, *args, event_handler, **kwargs): self.callback = event_handler
    async def _connect(self): pass
    async def _disconnect(self): pass
    async def _handle_control_frame(self, frame): pass
    def start(self):
        asyncio.run(self._connect())
        results = []
        def receive(payload):
            try:
                self.callback(payload)
                results.append(True)
            except RuntimeError:
                results.append(False)
        if concurrent:
            threads = [threading.Thread(target=receive, args=(p,)) for p in payloads]
            for t in threads: t.start()
            for t in threads: t.join()
        else:
            for p in payloads: receive(p)
        print(json.dumps(results), file=sys.stderr, flush=True)
lark = types.ModuleType("lark_oapi")
lark.EventDispatcherHandler = Builder
lark.JSON = types.SimpleNamespace(marshal=json.dumps)
lark.ws = types.ModuleType("lark_oapi.ws")
lark.ws.Client = Client
lark.ws.client = types.ModuleType("lark_oapi.ws.client")
for name, module in [("lark_oapi", lark), ("lark_oapi.ws", lark.ws),
                     ("lark_oapi.ws.client", lark.ws.client)]:
    sys.modules[name] = module
requests = types.ModuleType("requests")
requests.Session = lambda: types.SimpleNamespace(close=lambda: None)
sys.modules["requests"] = requests
_worker()
"""


def worker_child(event_ids, *, concurrent=False):
    payloads = [
        {
            "header": {"event_id": event_id, "tenant_key": "t", "app_id": "cli_x"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_1"}},
                "message": {
                    "chat_type": "p2p",
                    "chat_id": "oc_1",
                    "message_type": "text",
                    "message_id": "om_1",
                    "content": json.dumps({"text": "hi"}),
                },
            },
        }
        for event_id in event_ids
    ]
    child = subprocess.Popen(
        [sys.executable, "-c", FAKE_SDK_WORKER, json.dumps(payloads), json.dumps(concurrent)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        cwd=Path(__file__).resolve().parents[2],
    )
    child.stdin.write(b'{"app_id":"cli_x","app_secret":"synthetic-only"}\n')
    assert read_frame(child) == b"CONNECTED"
    return child


def read_frame(child, timeout=3):
    end, line = time.monotonic() + timeout, b""
    while not line.endswith(b"\n"):
        remaining = end - time.monotonic()
        assert remaining > 0 and select.select([child.stdout], [], [], remaining)[0], (
            "frame deadline"
        )
        chunk = os.read(child.stdout.fileno(), 1)
        assert chunk, "worker closed before frame"
        line += chunk
    return line.rstrip(b"\n")


def ack(frame, **changes):
    return (
        json.dumps(
            {
                "type": "ack",
                "event_id": frame["event"]["event_id"],
                "callback_id": frame["callback_id"],
                **changes,
            }
        )
        + "\n"
    ).encode()


def close_worker(child):
    child.stdin.close()
    child.wait(timeout=9)
    child.stdout.close()
    child.stderr.close()


@pytest.mark.parametrize("concurrent,same_id", [(False, False), (False, True), (True, False)])
def test_real_worker_correlates_consecutive_and_concurrent_callbacks(concurrent, same_id):
    child = worker_child(["ev1", "ev1" if same_id else "ev2"], concurrent=concurrent)
    try:
        first = json.loads(read_frame(child))
        assert first.get("type") == "event", "callback must emit a correlated event frame"
        # Neither wrong event nor wrong callback can complete this callback.
        child.stdin.write(ack(first, event_id="ev_wrong") + ack(first, callback_id="f" * 32))
        assert not select.select([child.stdout], [], [], 0.1)[0]
        # Split frames must be assembled, not mistaken for a complete ACK.
        good = ack(first)
        child.stdin.write(good[:12])
        assert not select.select([child.stdout], [], [], 0.1)[0]
        child.stdin.write(good[12:])
        second = json.loads(read_frame(child))
        assert second["callback_id"] != first["callback_id"]
        child.stdin.write(ack(first))  # late/replayed ACK must not confirm the second delivery
        assert not select.select([child.stderr], [], [], 0.1)[0]
        child.stdin.write(ack(second))
        assert child.wait(timeout=3) == 0
        assert json.loads(child.stderr.read()) == [True, True]
    finally:
        close_worker(child)


@pytest.mark.parametrize("bad_ack", [b"ACK\n", b'{"type":"ack"', b"x" * 513])
def test_real_worker_rejects_legacy_truncated_and_oversized_ack(bad_ack):
    child = worker_child(["ev1"])
    try:
        read_frame(child)
        child.stdin.write(bad_ack)
        child.stdin.close()
        assert child.wait(timeout=3) == 0
        assert json.loads(child.stderr.read()) == [False]
    finally:
        close_worker(child)
