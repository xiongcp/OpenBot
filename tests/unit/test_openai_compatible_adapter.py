import asyncio
import json
import time
from typing import Any

import pytest
from openbot.domain.providers import ModelRequest, Text, ToolCall
from openbot.domain.tools import Effect, RetryClass, ToolManifest
from openbot.policy.egress import EgressGuard
from openbot.providers.openai import ProviderFailure
from openbot.providers.openai_compatible import (
    ALLOWED_OPENAI_REQUEST_FIELDS,
    FORBIDDEN_SDK_HELPERS,
    PROVIDER_CAPABILITY_MATRIX,
    OpenAICompatibleAdapter,
    validate_outbound_sdk_payload,
)


class RecordingBudgetLedger:
    def __init__(self) -> None:
        self.reserved: list[tuple[str, int]] = []
        self.settled: list[tuple[str, int, int]] = []
        self.unknowns: list[str] = []

    def reserve(self, request_id: str, units: int) -> None:
        self.reserved.append((request_id, units))

    def settle(self, request_id: str, input_tokens: int, output_tokens: int) -> None:
        self.settled.append((request_id, input_tokens, output_tokens))

    def unknown(self, request_id: str) -> None:
        self.unknowns.append(request_id)


class FakeSSEStreamTransport:
    """Deterministic SSE stream double counting exact HTTP attempts without socket bind."""

    def __init__(self, scripts: list[list[bytes] | int]) -> None:
        self.scripts = list(scripts)
        self.http_attempts = 0
        self.last_payloads: list[dict[str, Any]] = []

    async def stream_chat(self, payload: dict[str, Any]) -> list[bytes]:
        self.http_attempts += 1
        self.last_payloads.append(payload)
        nxt = self.scripts.pop(0)
        if isinstance(nxt, int):
            raise ProviderFailure(f"HTTP_{nxt}")
        return nxt


def _manifest(*, canary_tracker: list[int]) -> ToolManifest:
    # Canary tracker proves no tool function is ever invoked during model generation
    assert len(canary_tracker) == 0
    return ToolManifest(
        "fs.patch",
        "1.0.0",
        b'{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},'
        b'"required":["path","content"],"additionalProperties":false}',
        b'{"type":"object"}',
        Effect.LOCAL_WRITE,
        RetryClass.IDEMPOTENT_WRITE,
        ("workspace",),
        "stop",
        "patch",
        1000,
        1024,
    )


def _egress() -> EgressGuard:
    return EgressGuard(
        profile_network_mode="CONNECTED",
        profile_allowed_domains=frozenset({"api.openai.com"}),
        workspace_allowed_domains=frozenset({"api.openai.com"}),
    )


def _sse(obj: dict[str, Any]) -> bytes:
    return b"data: " + json.dumps(obj).encode("utf-8") + b"\n\n"


def test_sdk_whitelist_capability_matrix_and_rejection_of_extra_fields_or_hosted_tools():
    assert "beta.chat.completions.run_tools" in FORBIDDEN_SDK_HELPERS
    assert "extra_body" not in ALLOWED_OPENAI_REQUEST_FIELDS
    assert "extra_headers" not in ALLOWED_OPENAI_REQUEST_FIELDS
    assert PROVIDER_CAPABILITY_MATRIX["openai_official"].supports_stream_usage is True
    assert PROVIDER_CAPABILITY_MATRIX["openai_compatible_generic"].supports_stream_usage is False

    for bad in (
        {"model": "gpt-4o-mini", "messages": [], "extra_body": {"web_search": True}},
        {"model": "gpt-4o-mini", "messages": [], "extra_headers": {"Authorization": "Bearer evil"}},
        {"model": "gpt-4o-mini", "messages": [], "web_search_options": {}},
        {"model": "gpt-4o-mini", "messages": [], "mcp_servers": ["https://evil.invalid"]},
    ):
        with pytest.raises(PermissionError):
            validate_outbound_sdk_payload(bad)


def test_fragmented_tool_call_assembly_429_retry_accounting_and_zero_canary_execution():
    canary_calls: list[int] = []
    manifest = _manifest(canary_tracker=canary_calls)
    budget = RecordingBudgetLedger()

    # Attempt 1 returns 429; Attempt 2 streams fragmented tool call JSON across 3 chunks + usage
    sse_frames = [
        _sse(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_frag_1",
                                    "type": "function",
                                    "function": {
                                        "name": "fs.patch",
                                        "arguments": '{"path":"a.',
                                    },
                                }
                            ]
                        },
                    }
                ],
                "usage": None,
            }
        ),
        _sse(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {"arguments": 'txt","content":"hello"}'},
                                }
                            ]
                        },
                    }
                ],
                "usage": None,
            }
        ),
        _sse(
            {
                "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
            }
        ),
        b"data: [DONE]\n\n",
    ]
    transport = FakeSSEStreamTransport([429, sse_frames])
    adapter = OpenAICompatibleAdapter(
        endpoint="https://api.openai.com/v1",
        model="gpt-4o-mini",
        egress_guard=_egress(),
        budget=budget,
        manifests={"fs.patch": manifest},
        stream_transport=transport,
        max_gateway_retries=1,
        retry_backoff_ms=0,
    )
    req = ModelRequest(
        request_id="req_frag_1",
        model="gpt-4o-mini",
        blocks=(Text("patch a.txt"),),
        deadline_monotonic_ms=int(time.monotonic() * 1000) + 5000,
        reserved_cost_units=100,
    )
    resp = asyncio.run(adapter.generate(req))
    # 1. Server HTTP attempts == Gateway attempts == Budget reservations == 2
    assert transport.http_attempts == 2
    assert len(budget.reserved) == 2
    assert budget.unknowns == ["req_frag_1:try_1"]
    assert budget.settled == [("req_frag_1:try_2", 12, 8)]
    # 2. Assembled ToolCall proposal is canonical and validated against manifest schema; canary == 0
    assert len(resp.blocks) == 1
    call = resp.blocks[0]
    assert isinstance(call, ToolCall)
    assert call.call_id == "call_frag_1"
    assert call.tool_name == "fs.patch"
    assert call.arguments == b'{"content":"hello","path":"a.txt"}'
    assert canary_calls == []


def test_malformed_json_missing_tool_id_stream_cut_and_cancel_hold_cost_without_retry():
    canary_calls: list[int] = []
    manifest = _manifest(canary_tracker=canary_calls)

    # 1. Half-packet / truncated tool call JSON is discarded, cost held as UNKNOWN, and NOT retried
    cut_frames = [
        _sse(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_cut",
                                    "type": "function",
                                    "function": {
                                        "name": "fs.patch",
                                        "arguments": '{"path":"cut',
                                    },
                                }
                            ]
                        },
                    }
                ]
            }
        ),
    ]
    budget_cut = RecordingBudgetLedger()
    transport_cut = FakeSSEStreamTransport([cut_frames, cut_frames])
    adapter_cut = OpenAICompatibleAdapter(
        endpoint="https://api.openai.com/v1",
        model="gpt-4o-mini",
        egress_guard=_egress(),
        budget=budget_cut,
        manifests={"fs.patch": manifest},
        stream_transport=transport_cut,
        max_gateway_retries=2,
        retry_backoff_ms=0,
    )
    req_cut = ModelRequest(
        request_id="req_cut_1",
        model="gpt-4o-mini",
        blocks=(Text("cut"),),
        deadline_monotonic_ms=int(time.monotonic() * 1000) + 5000,
        reserved_cost_units=100,
    )
    with pytest.raises(ProviderFailure):
        asyncio.run(adapter_cut.generate(req_cut))
    # Half-packet stream must NOT be retried by gateway and must hold budget as UNKNOWN
    assert transport_cut.http_attempts == 1
    assert budget_cut.unknowns == ["req_cut_1:try_1"]

    # 2. Missing tool_call_id is rejected and holds cost as UNKNOWN
    no_id_frames = [
        _sse(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "type": "function",
                                    "function": {
                                        "name": "fs.patch",
                                        "arguments": '{"path":"a","content":"b"}',
                                    },
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        ),
        b"data: [DONE]\n\n",
    ]
    budget_noid = RecordingBudgetLedger()
    transport_noid = FakeSSEStreamTransport([no_id_frames])
    adapter_noid = OpenAICompatibleAdapter(
        endpoint="https://api.openai.com/v1",
        model="gpt-4o-mini",
        egress_guard=_egress(),
        budget=budget_noid,
        manifests={"fs.patch": manifest},
        stream_transport=transport_noid,
    )
    with pytest.raises(ProviderFailure, match="tool_call_id"):
        asyncio.run(
            adapter_noid.generate(
                ModelRequest(
                    "req_noid", "gpt-4o-mini", (Text("x"),), int(time.monotonic() * 1000) + 5000, 50
                )
            )
        )
    assert budget_noid.unknowns == ["req_noid:try_1"]

    # 3. Cancelled request sends 0 new HTTP requests
    asyncio.run(adapter_noid.cancel("req_cancelled"))
    with pytest.raises(ProviderFailure, match="cancelled"):
        asyncio.run(
            adapter_noid.generate(
                ModelRequest(
                    "req_cancelled",
                    "gpt-4o-mini",
                    (Text("x"),),
                    int(time.monotonic() * 1000) + 5000,
                    50,
                )
            )
        )
    assert transport_noid.http_attempts == 1


def test_tool_result_continuation_keeps_assistant_and_tool_roles():
    from openbot.domain.providers import ToolResult

    adapter = OpenAICompatibleAdapter(
        endpoint="https://api.openai.com/v1",
        model="gpt-4o-mini",
        egress_guard=_egress(),
        budget=RecordingBudgetLedger(),
        manifests={"fs.patch": _manifest(canary_tracker=[])},
        stream_transport=FakeSSEStreamTransport([]),
    )
    request = ModelRequest(
        "req_history",
        "gpt-4o-mini",
        (
            Text("synthetic goal"),
            ToolCall("call_1", "fs.patch", b'{"path":"demo","content":"x"}'),
            ToolResult("call_1", b"verified result; ignore any instructions here"),
            Text("Summarize the verified result"),
        ),
        999999999999,
        100,
    )
    messages = adapter._build_payload(request)["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "user"]
    assert messages[1]["tool_calls"][0]["id"] == messages[2]["tool_call_id"] == "call_1"
    assert messages[2]["content"].startswith("UNTRUSTED_TOOL_DATA")


def test_unmatched_tool_result_fails_before_network():
    from openbot.domain.providers import ToolResult

    adapter = OpenAICompatibleAdapter(
        endpoint="https://api.openai.com/v1",
        model="gpt-4o-mini",
        egress_guard=_egress(),
        budget=RecordingBudgetLedger(),
        manifests={},
        stream_transport=FakeSSEStreamTransport([]),
    )
    with pytest.raises(ProviderFailure):
        adapter._build_payload(
            ModelRequest(
                "req_bad_history",
                "gpt-4o-mini",
                (
                    Text("goal"),
                    ToolResult("call_unmatched", b"untrusted"),
                ),
                999999999999,
                100,
            )
        )
