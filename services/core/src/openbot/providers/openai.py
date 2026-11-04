"""OB-092 basic text transport qualification. Tool/model product gates remain OB-025."""

import asyncio
import importlib
import logging
import time
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlsplit

from openbot.contracts import strict_json
from openbot.domain.providers import ModelRequest, ModelResponse, RequestBudget, Text


class ProviderFailure(RuntimeError):
    """Request failed; usage may be unknown. This never authorizes a tool retry."""


async def _sse_data(response: Any) -> AsyncIterator[dict[str, Any] | None]:
    """Read bounded raw JSON before the SDK can coerce authority-bearing usage."""
    buffer = b""
    total = 0
    async for part in response.iter_bytes():
        total += len(part)
        if total > 1_048_576:
            raise ProviderFailure("Response stream byte limit exceeded")
        buffer = (buffer + part).replace(b"\r\n", b"\n")
        while b"\n\n" in buffer:
            frame, buffer = buffer.split(b"\n\n", 1)
            data = b"\n".join(
                line[5:].removeprefix(b" ")
                for line in frame.split(b"\n")
                if line.startswith(b"data:")
            )
            if not data:
                continue
            if data == b"[DONE]":
                yield None
                return
            value = strict_json(data)
            if type(value) is not dict:
                raise ProviderFailure("Malformed stream JSON envelope")
            yield value


class OpenAITransport:
    def __init__(self, endpoint: str, model: str, api_key: str, budget: RequestBudget):
        route = urlsplit(endpoint)
        if (
            route.username
            or route.password
            or route.query
            or route.fragment
            or not route.hostname
            or route.scheme not in {"http", "https"}
            or (route.scheme == "http" and route.hostname not in {"127.0.0.1", "::1"})
        ):
            raise ProviderFailure("Invalid prequalified endpoint")
        if not api_key or not model:
            raise ProviderFailure("Model and secret handle injection required")
        try:
            sdk = importlib.import_module("openai")
            httpx = importlib.import_module("httpx")
        except ImportError as exc:
            raise ProviderFailure("CAPABILITY_UNAVAILABLE: optional SDK missing") from exc
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        transport = httpx.AsyncHTTPTransport(retries=0, trust_env=False)
        http = httpx.AsyncClient(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(3.0),
            limits=httpx.Limits(max_connections=1),
        )
        self._sdk = sdk.AsyncOpenAI(
            api_key=api_key,
            base_url=endpoint,
            max_retries=0,
            http_client=http,
            timeout=3.0,
            organization="",
            project="",
        )
        self._model = model
        self._budget = budget
        self._closed = False
        self._inflight: dict[str, asyncio.Task[Any]] = {}

    def capabilities(self) -> frozenset[str]:
        return frozenset({"text_stream"})

    async def generate(self, request: ModelRequest) -> ModelResponse:
        remaining = (request.deadline_monotonic_ms - time.monotonic() * 1000) / 1000
        if (
            self._closed
            or request.model != self._model
            or remaining <= 0
            or request.request_id in self._inflight
            or not request.blocks
            or not all(isinstance(b, Text) for b in request.blocks)
        ):
            raise ProviderFailure("Request is not eligible for this transport")
        content = "\n".join(b.text for b in request.blocks if isinstance(b, Text))
        if len(content.encode()) > 1_048_576:
            raise ProviderFailure("Input size limit exceeded")
        self._budget.reserve(request.request_id, request.reserved_cost_units)
        task = asyncio.current_task()
        assert task is not None
        self._inflight[request.request_id] = task
        settled = False
        try:
            async with asyncio.timeout(remaining):
                async with self._sdk.chat.completions.with_streaming_response.create(
                    model=self._model,
                    messages=[{"role": "user", "content": content}],
                    stream=True,
                    stream_options={"include_usage": True},
                    max_completion_tokens=256,
                ) as response:
                    text: list[str] = []
                    finished = done = False
                    usage = None
                    async for chunk in _sse_data(response):
                        if chunk is None:
                            done = True
                            break
                        if chunk.get("usage") is not None:
                            usage = chunk["usage"]
                        choices = chunk.get("choices")
                        if type(choices) is not list or len(choices) > 1:
                            raise ProviderFailure("Malformed stream choices")
                        for choice in choices:
                            delta = choice["delta"]
                            if (
                                type(choice["index"]) is not int
                                or choice["index"] != 0
                                or type(delta) is not dict
                                or delta.get("tool_calls")
                                or delta.get("function_call")
                            ):
                                raise ProviderFailure("Unsupported output capability")
                            content_delta = delta.get("content")
                            if content_delta is not None:
                                if type(content_delta) is not str or finished:
                                    raise ProviderFailure("Malformed stream ordering")
                                text.append(content_delta)
                            reason = choice.get("finish_reason")
                            if reason is not None:
                                if reason != "stop" or finished:
                                    raise ProviderFailure("Incomplete or duplicate final output")
                                finished = True
                    if not finished or not done:
                        raise ProviderFailure("Stream ended without a verified final output")
                if usage is None:
                    self._budget.unknown(request.request_id)
                else:
                    if type(usage) is not dict:
                        raise ProviderFailure("Untrusted usage envelope")
                    if any(
                        type(value) is not int or not 0 <= value <= 2**53 - 1
                        for value in (
                            usage.get("prompt_tokens"),
                            usage.get("completion_tokens"),
                            usage.get("total_tokens"),
                        )
                    ):
                        raise ProviderFailure(
                            "Untrusted usage is outside the supported integer range"
                        )
                    if usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]:
                        raise ProviderFailure("Untrusted usage totals are inconsistent")
                    self._budget.settle(
                        request.request_id, usage["prompt_tokens"], usage["completion_tokens"]
                    )
                    settled = True
                return ModelResponse(
                    (Text("".join(text)),),
                    None if usage is None else usage["prompt_tokens"],
                    None if usage is None else usage["completion_tokens"],
                    usage is None,
                )
        except asyncio.CancelledError:
            if not settled:
                self._budget.unknown(request.request_id)
            raise
        except Exception as exc:
            if not settled:
                self._budget.unknown(request.request_id)
            raise ProviderFailure("Model request failed; usage requires reconciliation") from exc
        finally:
            self._inflight.pop(request.request_id, None)

    async def cancel(self, request_id: str) -> None:
        task = self._inflight.get(request_id)
        if task is not None:
            task.cancel()

    async def close(self) -> None:
        self._closed = True
        tasks = list(self._inflight.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._sdk.close()
