"""Google Gemini streaming adapter with zero auto-retries and strict functionCall assembly."""

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
)
from openbot.domain.tools import ToolManifest
from openbot.policy.egress import EgressGuard, EgressRequest
from openbot.policy.secrets.broker import SecretBroker
from openbot.providers.openai import ProviderFailure

FORBIDDEN_GEMINI_HELPERS = frozenset(
    {"automatic_function_calling", "enable_automatic_function_calling"}
)


class GeminiStreamTransportPort(Protocol):
    async def stream_generate_content(self, payload: dict[str, Any]) -> list[dict[str, Any]]: ...


class GeminiStreamingAdapter:
    """Google Gemini streaming adapter enforcing egress, compartment secrets, and budget."""

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
        transport: GeminiStreamTransportPort,
        task_network_mode: str = "CONNECTED",
        data_class: str = "WORKSPACE",
    ) -> None:
        secret_broker.resolve_for_model_provider(secret_ref, "gemini")
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

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if request.model != self._model or request.request_id in self._cancelled:
            raise ProviderFailure("Gemini request cancelled or model mismatch")
        rem_s = (request.deadline_monotonic_ms - time.monotonic() * 1000.0) / 1000.0
        if rem_s <= 0:
            raise ProviderFailure("Gemini request deadline expired")
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
        self._broker.resolve_for_model_provider(self._secret_ref, "gemini")
        contents = [
            {"role": "user", "parts": [{"text": b.text}]}
            for b in request.blocks
            if isinstance(b, Text)
        ]
        payload: dict[str, Any] = {"model": self._model, "contents": contents}
        if self._manifests:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {"name": m.name, "parameters": strict_json(m.input_schema)}
                        for m in self._manifests.values()
                    ]
                }
            ]
        attempt_ref = f"{request.request_id}:try_1"
        self._budget.reserve(attempt_ref, request.reserved_cost_units)
        settled = False
        try:
            async with asyncio.timeout(rem_s):
                chunks = await self._transport.stream_generate_content(payload)
                text_parts: list[str] = []
                fn_calls: list[tuple[str, str, dict[str, Any]]] = []
                finish_reason: str | None = None
                p_tok: int | None = None
                c_tok: int | None = None
                for idx, chunk in enumerate(chunks):
                    if request.request_id in self._cancelled:
                        raise ProviderFailure("Cancelled during Gemini stream")
                    for cand in chunk.get("candidates", []):
                        for part in cand.get("content", {}).get("parts", []):
                            if "text" in part:
                                text_parts.append(str(part["text"]))
                            if "functionCall" in part:
                                fc = dict(part["functionCall"])
                                fn_calls.append(
                                    (
                                        str(fc.get("id", f"gem_call_{idx}")),
                                        str(fc["name"]),
                                        dict(fc.get("args", {})),
                                    )
                                )
                        if cand.get("finishReason"):
                            finish_reason = str(cand["finishReason"])
                    if "usageMetadata" in chunk:
                        um = dict(chunk["usageMetadata"])
                        p_tok = int(um.get("promptTokenCount", 0))
                        c_tok = int(um.get("candidatesTokenCount", 0))
                if finish_reason != "STOP":
                    raise ProviderFailure("Gemini stream ended without finishReason=STOP")
                blocks: list[Block] = []
                if text_parts:
                    blocks.append(Text("".join(text_parts)))
                for call_id, t_name, t_args in fn_calls:
                    if t_name not in self._manifests:
                        raise ProviderFailure(f"Unregistered Gemini tool: {t_name}")
                    env = canonicalize({"tool_name": t_name, "args": t_args})
                    blocks.append(accept_model_call(env, self._manifests[t_name], call_id))
                if p_tok is not None and c_tok is not None:
                    self._budget.settle(attempt_ref, p_tok, c_tok)
                    settled = True
                else:
                    self._budget.unknown(attempt_ref)
                return ModelResponse(tuple(blocks), p_tok, c_tok, not settled)
        except Exception as exc:
            if not settled:
                self._budget.unknown(attempt_ref)
            if isinstance(exc, ProviderFailure):
                raise
            raise ProviderFailure("Gemini generation failed; usage UNKNOWN") from exc

    async def cancel(self, request_id: str) -> None:
        self._cancelled.add(request_id)

    async def close(self) -> None:
        pass
