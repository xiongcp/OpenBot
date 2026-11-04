import asyncio
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread

import pytest

pytest.importorskip("openai", reason="M1 SDK group absent from the M0 environment")

from openbot.domain.providers import ModelRequest, Text  # noqa: E402
from openbot.providers.openai import OpenAITransport, ProviderFailure  # noqa: E402

pytestmark = pytest.mark.sdk


class Budget:
    def __init__(self):
        self.attempts = []
        self.held = set()
        self.settled = {}

    def reserve(self, request_id, units):
        assert request_id not in self.attempts
        assert units > 0
        self.attempts.append(request_id)
        self.held.add(request_id)

    def settle(self, request_id, input_tokens, output_tokens):
        self.settled[request_id] = (input_tokens, output_tokens)
        self.held.remove(request_id)

    def unknown(self, request_id):
        assert request_id in self.held


@pytest.fixture
def server():
    state = {
        "status": 200,
        "requests": [],
        "headers": [],
        "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        "mode": "complete",
        "started": Event(),
        "release": Event(),
        "delta": {"content": "ok"},
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            assert length < 65536
            state["requests"].append(json.loads(self.rfile.read(length)))
            state["headers"].append(dict(self.headers))
            if state["mode"] == "disconnect":
                self.close_connection = True
                return
            self.send_response(state["status"])
            if state["status"] == 307:
                self.send_header("Location", state["url"] + "/redirected")
            self.send_header(
                "Content-Type",
                "text/event-stream" if state["status"] == 200 else "application/json",
            )
            self.end_headers()
            if state["status"] != 200:
                self.wfile.write(b'{"error":{"message":"synthetic fault","type":"test"}}')
                return
            chunk = {
                "id": "chatcmpl-synthetic",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "fake-fixed",
                "choices": [{"index": 0, "delta": state["delta"], "finish_reason": None}],
            }
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            self.wfile.flush()
            state["started"].set()
            if state["mode"] == "wait":
                assert state["release"].wait(5)
                return
            if state["mode"] == "cut":
                return
            chunk["choices"] = [{"index": 0, "delta": {}, "finish_reason": "stop"}]
            chunk["usage"] = state["usage"]
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\ndata: [DONE]\n\n")

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    http.daemon_threads = True
    thread = Thread(target=lambda: http.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    state["url"] = f"http://127.0.0.1:{http.server_port}/v1"
    try:
        yield state
    finally:
        state["release"].set()
        http.shutdown()
        http.server_close()
        thread.join(timeout=5)


def request(identifier="req_test1"):
    return ModelRequest(
        identifier, "fake-fixed", (Text("synthetic input"),), int(time.monotonic() * 1000) + 3000, 1
    )


@pytest.mark.parametrize("status", [429, 503])
def test_sdk_does_not_hide_retries_or_release_unknown_cost(server, status):
    server["status"] = status

    async def scenario():
        budget = Budget()
        transport = OpenAITransport(server["url"], "fake-fixed", "synthetic-key", budget)
        try:
            with pytest.raises(ProviderFailure):
                await transport.generate(request())
            assert len(server["requests"]) == len(budget.attempts) == 1
            assert budget.held == {"req_test1"}
        finally:
            await transport.close()

    asyncio.run(scenario())


def test_success_has_matching_request_and_usage_budget(server, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")

    async def scenario():
        budget = Budget()
        transport = OpenAITransport(server["url"], "fake-fixed", "synthetic-key", budget)
        try:
            response = await transport.generate(request())
            assert response.blocks == (Text("ok"),)
            assert budget.settled == {"req_test1": (2, 1)}
            assert len(server["requests"]) == len(budget.attempts) == 1
            assert not {"extra_body", "extra_headers", "tools"} & set(server["requests"][0])
        finally:
            await transport.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["cut", "wait"])
def test_interrupted_or_cancelled_stream_holds_cost_and_never_starts_another_request(server, mode):
    server["mode"] = mode

    async def scenario():
        budget = Budget()
        transport = OpenAITransport(server["url"], "fake-fixed", "synthetic-key", budget)
        try:
            running = asyncio.create_task(transport.generate(request()))
            assert await asyncio.to_thread(server["started"].wait, 3)
            if mode == "wait":
                await transport.cancel("req_test1")
                with pytest.raises(asyncio.CancelledError):
                    await running
            else:
                with pytest.raises(ProviderFailure):
                    await running
            assert budget.held == {"req_test1"}
            assert len(server["requests"]) == len(budget.attempts) == 1
        finally:
            server["release"].set()
            await transport.close()

    asyncio.run(scenario())


def test_unapproved_model_and_past_deadline_send_nothing(server):
    async def scenario():
        budget = Budget()
        transport = OpenAITransport(server["url"], "fake-fixed", "synthetic-key", budget)
        try:
            bad = ModelRequest("req_bad1", "other", (Text("synthetic"),), 0, 1)
            with pytest.raises(ProviderFailure):
                await transport.generate(bad)
            assert not server["requests"]
            assert not budget.attempts
        finally:
            await transport.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "invalid",
    [
        {"prompt_tokens": -5},
        {"prompt_tokens": "2"},
        {"completion_tokens": True},
        {"completion_tokens": 2**60},
    ],
)
def test_untrusted_usage_cannot_release_budget_reservation(server, invalid):
    server["usage"].update(invalid)

    async def scenario():
        budget = Budget()
        transport = OpenAITransport(server["url"], "fake-fixed", "synthetic-key", budget)
        try:
            with pytest.raises(ProviderFailure):
                await transport.generate(request())
            assert budget.held == {"req_test1"}
            assert not budget.settled
            assert len(server["requests"]) == 1
        finally:
            await transport.close()

    asyncio.run(scenario())


def test_sdk_does_not_inherit_ambient_organization_or_project(server, monkeypatch):
    monkeypatch.setenv("OPENAI_ORG_ID", "synthetic-org-canary")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "synthetic-project-canary")

    async def scenario():
        transport = OpenAITransport(server["url"], "fake-fixed", "synthetic-key", Budget())
        try:
            await transport.generate(request())
            values = list(server["headers"][0].values())
            assert "synthetic-org-canary" not in values
            assert "synthetic-project-canary" not in values
        finally:
            await transport.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("mode,status", [("disconnect", 200), ("complete", 307)])
def test_connection_failure_and_redirect_do_not_create_hidden_attempts(server, mode, status):
    server["mode"], server["status"] = mode, status

    async def scenario():
        budget = Budget()
        transport = OpenAITransport(server["url"], "fake-fixed", "synthetic-key", budget)
        try:
            with pytest.raises(ProviderFailure):
                await transport.generate(request())
            assert len(server["requests"]) == len(budget.attempts) == 1
            assert budget.held == {"req_test1"}
            assert not budget.settled
        finally:
            await transport.close()

    asyncio.run(scenario())


def test_provider_tool_canary_remains_unexecuted(server, tmp_path):
    marker = tmp_path / "provider-tool-must-not-run"
    server["delta"] = {
        "tool_calls": [
            {
                "index": 0,
                "id": "call_canary",
                "type": "function",
                "function": {"name": "write_file", "arguments": json.dumps({"path": str(marker)})},
            }
        ]
    }

    async def scenario():
        budget = Budget()
        transport = OpenAITransport(server["url"], "fake-fixed", "synthetic-key", budget)
        try:
            with pytest.raises(ProviderFailure):
                await transport.generate(request())
            assert not marker.exists()
            assert len(server["requests"]) == len(budget.attempts) == 1
            assert budget.held == {"req_test1"}
        finally:
            await transport.close()

    asyncio.run(scenario())


def test_deadline_expires_in_stream_without_sdk_restart(server):
    server["mode"] = "wait"

    async def scenario():
        budget = Budget()
        transport = OpenAITransport(server["url"], "fake-fixed", "synthetic-key", budget)
        original = request()
        limited = ModelRequest(
            original.request_id,
            original.model,
            original.blocks,
            int(time.monotonic() * 1000) + 300,
            original.reserved_cost_units,
        )
        try:
            with pytest.raises(ProviderFailure):
                await transport.generate(limited)
            assert len(server["requests"]) == len(budget.attempts) == 1
            assert budget.held == {"req_test1"}
        finally:
            server["release"].set()
            await transport.close()

    asyncio.run(scenario())
