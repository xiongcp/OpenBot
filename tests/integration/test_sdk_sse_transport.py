import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from openbot.providers.openai import ProviderFailure
from openbot.providers.stream_transport import SdkSSETransport

pytestmark = pytest.mark.sdk


@pytest.fixture
def stream_server():
    pytest.importorskip("openai")
    calls = []
    reply = {"status": 200, "body": b'data: {"choices":[]}\n\ndata: [DONE]\n\n'}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(
                (
                    self.path,
                    self.headers.get("Authorization"),
                    json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
                )
            )
            self.send_response(reply["status"])
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(reply["body"])))
            if reply["status"] == 302:
                self.send_header("Location", "/redirect-target")
            self.end_headers()
            self.wfile.write(reply["body"])

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", calls, reply
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def payload():
    return {
        "model": "test-model",
        "messages": [{"role": "user", "content": "synthetic"}],
        "stream": True,
    }


def test_real_sdk_stream_uses_single_allowed_request_and_closes(stream_server):
    endpoint, calls, reply = stream_server
    transport = SdkSSETransport(endpoint=endpoint, api_key="synthetic-secret")
    chunks = asyncio.run(transport.stream_chat(payload()))
    assert b"".join(chunks) == reply["body"]
    assert len(calls) == 1
    assert calls[0] == ("/v1/chat/completions", "Bearer synthetic-secret", payload())
    assert transport.sdk.is_closed()


@pytest.mark.parametrize("status", [302, 429, 500])
def test_redirects_and_server_errors_never_retry_or_leak(stream_server, status):
    endpoint, calls, reply = stream_server
    reply.update(status=status, body=b"upstream synthetic-secret")
    transport = SdkSSETransport(endpoint=endpoint, api_key="synthetic-secret")
    with pytest.raises(ProviderFailure) as caught:
        asyncio.run(transport.stream_chat(payload()))
    assert "synthetic-secret" not in str(caught.value)
    assert caught.value.__suppress_context__
    assert len(calls) == 1
    assert transport.sdk.is_closed()


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://example.com/v1",
        "https://user:pass@example.com/v1",
        "https://example.com/v1?key=secret",
    ],
)
def test_unsafe_endpoint_rejected_without_connection(endpoint):
    with pytest.raises(PermissionError):
        SdkSSETransport(endpoint=endpoint, api_key="synthetic-secret")
