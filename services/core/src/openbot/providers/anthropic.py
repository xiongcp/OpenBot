"""Anthropic Claude Messages streaming adapter with zero auto-retries and strict tool assembly."""

import asyncio
import time
from typing import Any, Protocol

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
from openbot.policy.secrets.broker import SecretBroker
from openbot.providers.openai import ProviderFailure

FORBIDDEN_ANTHROPIC_HELPERS = frozenset({"beta.messages.tool_runner", "messages.run_tools"})
ALLOWED_ANTHROPIC_FIELDS = frozenset({"model", "messages", "max_tokens", "stream", "tools"})


class AnthropicStreamTransportPort(Protocol):
    async def stream_messages(self, payload: dict[str, Any]) -> list[dict[str, Any]]: ...


class AnthropicMessagesStreamingAdapter:
    """Anthropic Messages streaming adapter enforcing egress, compartment secrets, and budget."""

    sdk_max_retries: int = 0
    trust_env: bool = False
    follow_redirects: bool = False

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        secret_ref: str,
        secret_broker: SecretBroker,
        egress_guard: EgressGuard,
        budget: RequestBudget,
        manifests: dict[str, ToolManifest],
        transport: AnthropicStreamTransportPort,
        task_network_mode: str = "CONNECTED",
        data_class: str = "WORKSPACE",
    ) -> None:
        # Enforce compartment isolation: must be keychain:provider:anthropic:*
        secret_broker.resolve_for_model_provider(secret_ref, "anthropic")
        self._endpoint = endpoint
        self._model = model
        self._secret_ref = secret_ref
        self._broker = secret_broker
        self._egress = egress_guard
        self._budget = budget
        self._manifests = dict(manifests)
        self._transport = transport
        self._task_mode = task_network_mode
        self._data_class = data_class
        self._cancelled: set[str] = set()

    def _build_payload(self, request: ModelRequest) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        for block in request.blocks:
            if isinstance(block, Text):
                messages.append({"role": "user", "content": block.text})
            elif isinstance(block, ToolCall):
                messages.append(
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": block.call_id,
                                "name": block.tool_name,
                                "input": strict_json(block.arguments),
                            }
                        ],
                    }
                )
            elif isinstance(block, ToolResult):
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": block.call_id,
                                "content": "UNTRUSTED_TOOL_DATA\n" + block.result.decode("utf-8"),
                            }
                        ],
                    }
                )
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": 1024,
            "stream": True,
        }
        if self._manifests:
            payload["tools"] = [
                {
                    "name": m.name,
                    "input_schema": strict_json(m.input_schema),
                }
                for m in self._manifests.values()
            ]
        if set(payload) - ALLOWED_ANTHROPIC_FIELDS:
            raise PermissionError("FORBIDDEN_ANTHROPIC_REQUEST_FIELDS")
        return payload

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if request.model != self._model or request.request_id in self._cancelled:
            raise ProviderFailure("Anthropic request cancelled or model mismatch")
        rem_s = (request.deadline_monotonic_ms - time.monotonic() * 1000.0) / 1000.0
        if rem_s <= 0:
            raise ProviderFailure("Anthropic request deadline expired")
        eg = self._egress.evaluate(
            EgressRequest(
                surface="MODEL_GATEWAY",
                task_network_mode=self._task_mode,
                data_class=self._data_class,
                destination_url=self._endpoint,
            )
        )
        if eg.decision != "ALLOW":
            raise ProviderFailure(f"Egress denied: {eg.reason_code}")
        self._broker.resolve_for_model_provider(self._secret_ref, "anthropic")
        payload = self._build_payload(request)
        attempt_ref = f"{request.request_id}:try_1"
        self._budget.reserve(attempt_ref, request.reserved_cost_units)
        settled = False
        try:
            async with asyncio.timeout(rem_s):
                events = await self._transport.stream_messages(payload)
                text_parts: list[str] = []
                tool_slots: dict[int, dict[str, str]] = {}
                input_tokens: int | None = None
                output_tokens: int | None = None
                stopped = False
                for ev in events:
                    if request.request_id in self._cancelled:
                        raise ProviderFailure("Cancelled during Anthropic stream")
                    ev_type = ev.get("type")
                    if ev_type == "message_start":
                        usage = dict(ev.get("message", {}).get("usage", {}))
                        if "input_tokens" in usage:
                            input_tokens = int(usage["input_tokens"])
                    elif ev_type == "content_block_start":
                        idx = int(ev.get("index", 0))
                        cb = dict(ev.get("content_block", {}))
                        if cb.get("type") == "tool_use":
                            tool_slots[idx] = {
                                "id": str(cb.get("id", "")),
                                "name": str(cb.get("name", "")),
                                "json": "",
                            }
                    elif ev_type == "content_block_delta":
                        idx = int(ev.get("index", 0))
                        delta = dict(ev.get("delta", {}))
                        if delta.get("type") == "text_delta":
                            text_parts.append(str(delta.get("text", "")))
                        elif delta.get("type") == "input_json_delta":
                            tool_slots[idx]["json"] += str(delta.get("partial_json", ""))
                    elif ev_type == "message_delta":
                        usage = dict(ev.get("usage", {}))
                        if "output_tokens" in usage:
                            output_tokens = int(usage["output_tokens"])
                    elif ev_type == "message_stop":
                        stopped = True
                if not stopped:
                    raise ProviderFailure("Anthropic stream ended without message_stop")
                blocks: list[Block] = []
                if text_parts:
                    blocks.append(Text("".join(text_parts)))
                for idx in sorted(tool_slots):
                    slot = tool_slots[idx]
                    t_name = slot["name"]
                    if t_name not in self._manifests:
                        raise ProviderFailure(f"Unregistered tool proposed: {t_name}")
                    parsed = strict_json(slot["json"])
                    if type(parsed) is not dict:
                        raise ProviderFailure("Tool input must be JSON object")
                    env = canonicalize({"tool_name": t_name, "args": parsed})
                    blocks.append(accept_model_call(env, self._manifests[t_name], slot["id"]))
                if input_tokens is not None and output_tokens is not None:
                    self._budget.settle(attempt_ref, input_tokens, output_tokens)
                    settled = True
                else:
                    self._budget.unknown(attempt_ref)
                return ModelResponse(
                    tuple(blocks),
                    input_tokens,
                    output_tokens,
                    not settled,
                )
        except Exception as exc:
            if not settled:
                self._budget.unknown(attempt_ref)
            if isinstance(exc, ProviderFailure):
                raise
            raise ProviderFailure("Anthropic generation failed; usage UNKNOWN") from exc

    async def cancel(self, request_id: str) -> None:
        self._cancelled.add(request_id)

    async def close(self) -> None:
        pass
