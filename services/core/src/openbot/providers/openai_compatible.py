"""OB-025 cloud model adapter with egress/budget gating and full-JSON tool proposal assembly."""

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

from openbot.application.budgets import OfflineVocabularyEstimator
from openbot.boundaries import accept_model_call
from openbot.contracts import canonicalize, strict_json
from openbot.domain.providers import (
    Block,
    ModelRequest,
    ModelResponse,
    RequestBudget,
    Text,
    ToolCall,
    ToolResult,
)
from openbot.domain.tools import ToolManifest
from openbot.policy.egress import EgressGuard, EgressRequest
from openbot.providers.openai import ProviderFailure, _sse_data

ALLOWED_OPENAI_SDK_METHODS = frozenset({"chat.completions.with_streaming_response.create"})
FORBIDDEN_SDK_HELPERS = frozenset(
    {
        "beta.chat.completions.run_tools",
        "responses.create",
        "agents.run",
        "tool_runner",
    }
)
ALLOWED_OPENAI_REQUEST_FIELDS = frozenset(
    {
        "model",
        "messages",
        "tools",
        "tool_choice",
        "stream",
        "stream_options",
        "max_completion_tokens",
        "temperature",
    }
)


@dataclass(frozen=True, slots=True)
class ProviderCapabilityProfile:
    profile_name: str
    supports_stream_usage: bool
    supports_strict_tool_schema: bool
    supports_parallel_tool_calls: bool = False


PROVIDER_CAPABILITY_MATRIX: dict[str, ProviderCapabilityProfile] = {
    "openai_official": ProviderCapabilityProfile(
        profile_name="openai_official",
        supports_stream_usage=True,
        supports_strict_tool_schema=True,
        supports_parallel_tool_calls=False,
    ),
    "openai_compatible_generic": ProviderCapabilityProfile(
        profile_name="openai_compatible_generic",
        supports_stream_usage=False,
        supports_strict_tool_schema=False,
        supports_parallel_tool_calls=False,
    ),
}


def validate_outbound_sdk_payload(payload: dict[str, Any]) -> None:
    """Reject extra_body, extra_headers, provider-hosted web_search/remote_mcp, or unknown keys."""
    unexpected = set(payload) - ALLOWED_OPENAI_REQUEST_FIELDS
    if unexpected:
        raise PermissionError(f"Forbidden or unapproved SDK request fields: {sorted(unexpected)}")


class SSEStreamTransportPort(Protocol):
    async def stream_chat(self, payload: dict[str, Any]) -> list[bytes]: ...


class _ByteListResponse:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def iter_bytes(self):  # type: ignore[no-untyped-def]
        for chunk in self._chunks:
            await asyncio.sleep(0)
            yield chunk


class OpenAICompatibleAdapter:
    """Cloud model adapter enforcing egress, per-attempt budget, and full-JSON tool assembly."""

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        egress_guard: EgressGuard,
        budget: RequestBudget,
        manifests: dict[str, ToolManifest],
        stream_transport: SSEStreamTransportPort,
        capability_profile: str = "openai_official",
        task_network_mode: str = "CONNECTED",
        data_class: str = "WORKSPACE",
        max_gateway_retries: int = 0,
        retry_backoff_ms: int = 100,
    ) -> None:
        if capability_profile not in PROVIDER_CAPABILITY_MATRIX:
            raise ValueError(f"Unknown capability_profile: {capability_profile}")
        if max_gateway_retries < 0 or retry_backoff_ms < 0:
            raise ValueError("Invalid gateway retry configuration")
        self._endpoint = endpoint
        self._model = model
        self._egress = egress_guard
        self._budget = budget
        self._manifests = dict(manifests)
        self._transport = stream_transport
        self._profile = PROVIDER_CAPABILITY_MATRIX[capability_profile]
        self._task_mode = task_network_mode
        self._data_class = data_class
        self._max_retries = max_gateway_retries
        self._backoff_ms = retry_backoff_ms
        self._cancelled: set[str] = set()
        self._inflight: dict[str, asyncio.Task[Any]] = {}
        self._closed = False

    def capabilities(self) -> frozenset[str]:
        return frozenset({"text_stream", "function_proposals"})

    def _build_payload(self, request: ModelRequest) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        pending: str | None = None
        seen: set[str] = set()
        if len(request.blocks) > 64:
            raise ProviderFailure("Model history exceeds block limit")
        for block in request.blocks:
            if isinstance(block, Text) and pending is None:
                messages.append({"role": "user", "content": block.text})
            elif isinstance(block, ToolCall) and pending is None:
                if (
                    not block.call_id
                    or len(block.call_id) > 128
                    or block.call_id in seen
                    or block.tool_name not in self._manifests
                ):
                    raise ProviderFailure("Invalid history tool call")
                accept_model_call(
                    canonicalize(
                        {"tool_name": block.tool_name, "args": strict_json(block.arguments)}
                    ),
                    self._manifests[block.tool_name],
                    block.call_id,
                )
                messages.append(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": block.call_id,
                                "type": "function",
                                "function": {
                                    "name": block.tool_name,
                                    "arguments": block.arguments.decode("utf-8"),
                                },
                            }
                        ],
                    }
                )
                pending = block.call_id
                seen.add(block.call_id)
            elif isinstance(block, ToolResult) and block.call_id == pending:
                if len(block.result) > 16384:
                    raise ProviderFailure("Tool history result exceeds limit")
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": pending,
                        "content": "UNTRUSTED_TOOL_DATA\n" + block.result.decode("utf-8"),
                    }
                )
                pending = None
            else:
                raise ProviderFailure("Unsupported or unmatched history block")
        if pending is not None or not messages or len(canonicalize(messages)) > 65536:
            raise ProviderFailure("Incomplete or oversized model history")
        tools_list = [
            {
                "type": "function",
                "function": {
                    "name": m.name,
                    "parameters": strict_json(m.input_schema),
                },
            }
            for m in self._manifests.values()
        ]
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "max_completion_tokens": 256,
        }
        if self._profile.supports_stream_usage:
            payload["stream_options"] = {"include_usage": True}
        if tools_list:
            payload["tools"] = tools_list
            payload["tool_choice"] = "auto"
        validate_outbound_sdk_payload(payload)
        return payload

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if self._closed or request.model != self._model:
            raise ProviderFailure("Adapter closed or model mismatch")
        if request.request_id in self._cancelled:
            raise ProviderFailure("Request was cancelled before dispatch")
        payload = self._build_payload(request)
        # Match SDK/httpx JSON serialization, including all history and complete tool schemas.
        # This offline byte bound plus framing/output margins is not exact billed usage.
        estimate = OfflineVocabularyEstimator().estimate(
            request.model,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
            tool_count=len(payload.get("tools", [])),
            completion_reserve_tokens=payload["max_completion_tokens"],
        )
        reserved_units = max(request.reserved_cost_units, estimate.conservative_reserved_tokens)

        total_allowed_attempts = 1 + self._max_retries
        for attempt_idx in range(1, total_allowed_attempts + 1):
            if request.request_id in self._cancelled:
                raise ProviderFailure("Request cancelled during retry backoff")
            remaining_s = (request.deadline_monotonic_ms - time.monotonic() * 1000) / 1000
            if remaining_s <= 0:
                raise ProviderFailure("Request deadline expired before attempt")

            # 1. Egress check before EVERY HTTP attempt
            eg_dec = self._egress.evaluate(
                EgressRequest(
                    surface="MODEL_GATEWAY",
                    task_network_mode=self._task_mode,
                    data_class=self._data_class,
                    destination_url=self._endpoint,
                )
            )
            if eg_dec.decision != "ALLOW":
                raise ProviderFailure(f"Egress denied: {eg_dec.reason_code}")

            # 2. Reserve budget for this exact HTTP attempt
            attempt_ref = f"{request.request_id}:try_{attempt_idx}"
            self._budget.reserve(attempt_ref, reserved_units)
            cur_task = asyncio.current_task()
            if cur_task is not None:
                self._inflight[request.request_id] = cur_task
            received_any_chunk = False
            settled = False
            try:
                async with asyncio.timeout(remaining_s):
                    raw_chunks = await self._transport.stream_chat(payload)
                    stream_source = (
                        raw_chunks
                        if hasattr(raw_chunks, "iter_bytes")
                        else _ByteListResponse(raw_chunks)
                    )
                    text_parts: list[str] = []
                    tool_accum: dict[int, dict[str, str]] = {}
                    finish_reason: str | None = None
                    done = False
                    usage: dict[str, Any] | None = None

                    async for chunk in _sse_data(stream_source):
                        received_any_chunk = True
                        if request.request_id in self._cancelled:
                            raise ProviderFailure("Request cancelled after first stream chunk")
                        if chunk is None:
                            done = True
                            break
                        if chunk.get("usage") is not None:
                            if type(chunk["usage"]) is not dict:
                                raise ProviderFailure("Malformed usage object")
                            usage = chunk["usage"]
                        choices = chunk.get("choices")
                        if type(choices) is not list or len(choices) > 1:
                            raise ProviderFailure("Malformed choices in stream")
                        for choice in choices:
                            delta = choice.get("delta", {})
                            if type(delta) is not dict:
                                raise ProviderFailure("Malformed delta object")
                            c_delta = delta.get("content")
                            if c_delta is not None:
                                if type(c_delta) is not str or finish_reason is not None:
                                    raise ProviderFailure("Invalid content delta")
                                text_parts.append(c_delta)
                            t_calls = delta.get("tool_calls")
                            if t_calls is not None:
                                if type(t_calls) is not list or finish_reason is not None:
                                    raise ProviderFailure("Invalid tool_calls delta")
                                for tc in t_calls:
                                    idx = tc.get("index", 0)
                                    if type(idx) is not int or idx < 0:
                                        raise ProviderFailure("Invalid tool_call index")
                                    slot = tool_accum.setdefault(
                                        idx, {"id": "", "name": "", "arguments": ""}
                                    )
                                    if tc.get("id"):
                                        slot["id"] += str(tc["id"])
                                    fn = tc.get("function")
                                    if isinstance(fn, dict):
                                        if fn.get("name"):
                                            slot["name"] += str(fn["name"])
                                        if fn.get("arguments"):
                                            slot["arguments"] += str(fn["arguments"])
                            r_reason = choice.get("finish_reason")
                            if r_reason is not None:
                                if (
                                    r_reason not in {"stop", "tool_calls"}
                                    or finish_reason is not None
                                ):
                                    raise ProviderFailure("Unsupported or duplicate finish_reason")
                                finish_reason = str(r_reason)

                if not done or finish_reason is None:
                    raise ProviderFailure("Stream ended before complete output and [DONE]")

                # 3. Validate complete JSON and schema BEFORE producing any ToolCall proposal
                blocks: list[Block] = []
                if text_parts:
                    blocks.append(Text("".join(text_parts)))
                for idx in sorted(tool_accum):
                    slot = tool_accum[idx]
                    call_id = slot["id"].strip()
                    tool_name = slot["name"].strip()
                    raw_args = slot["arguments"]
                    if not call_id or not tool_name or not raw_args:
                        raise ProviderFailure("Incomplete tool_call_id, name, or arguments")
                    if tool_name not in self._manifests:
                        raise ProviderFailure(f"Unregistered tool proposed: {tool_name}")
                    parsed_args = strict_json(raw_args)
                    if type(parsed_args) is not dict:
                        raise ProviderFailure("Tool arguments must be a JSON object")
                    envelope = canonicalize({"tool_name": tool_name, "args": parsed_args})
                    validated_call = accept_model_call(
                        envelope, self._manifests[tool_name], call_id
                    )
                    blocks.append(validated_call)

                if usage is None:
                    self._budget.unknown(attempt_ref)
                else:
                    p_tok = usage.get("prompt_tokens")
                    c_tok = usage.get("completion_tokens")
                    t_tok = usage.get("total_tokens")
                    if (
                        type(p_tok) is not int
                        or type(c_tok) is not int
                        or type(t_tok) is not int
                        or p_tok < 0
                        or c_tok < 0
                        or t_tok != p_tok + c_tok
                    ):
                        raise ProviderFailure("Invalid usage token counts")
                    self._budget.settle(attempt_ref, p_tok, c_tok)
                    settled = True

                return ModelResponse(
                    tuple(blocks),
                    None if usage is None else int(usage["prompt_tokens"]),
                    None if usage is None else int(usage["completion_tokens"]),
                    usage is None,
                )
            except asyncio.CancelledError as exc:
                if not settled:
                    self._budget.unknown(attempt_ref)
                raise ProviderFailure("Request cancelled while in-flight; usage UNKNOWN") from exc
            except Exception as exc:
                if not settled:
                    self._budget.unknown(attempt_ref)
                is_retryable_pre_stream = (
                    not received_any_chunk
                    and attempt_idx < total_allowed_attempts
                    and request.request_id not in self._cancelled
                    and str(exc) in {"HTTP_429", "HTTP_503"}
                )
                if is_retryable_pre_stream:
                    if self._backoff_ms > 0:
                        await asyncio.sleep(self._backoff_ms / 1000)
                    continue
                if isinstance(exc, ProviderFailure):
                    raise
                raise ProviderFailure("Model generation failed; usage held as UNKNOWN") from exc
            finally:
                self._inflight.pop(request.request_id, None)

        raise ProviderFailure("Exhausted gateway retry budget")

    async def cancel(self, request_id: str) -> None:
        self._cancelled.add(request_id)
        inflight = self._inflight.get(request_id)
        if inflight is not None:
            inflight.cancel()

    async def close(self) -> None:
        self._closed = True
        tasks = list(self._inflight.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
