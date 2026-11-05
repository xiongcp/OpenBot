"""Actual SDK stream transport, with fixed endpoint, bounded bytes and zero hidden retries."""

import importlib
import logging
from typing import Any
from urllib.parse import urlsplit

from openbot.providers.openai import ProviderFailure
from openbot.providers.openai_compatible import validate_outbound_sdk_payload


class SdkSSETransport:
    def __init__(self, *, endpoint: str, api_key: str):
        parsed = urlsplit(endpoint)
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise PermissionError("MODEL_ENDPOINT_INVALID")
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1"}
        ):
            raise PermissionError("MODEL_TLS_REQUIRED")
        sdk, httpx = importlib.import_module("openai"), importlib.import_module("httpx")
        for name in ("openai", "httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.CRITICAL)
        client = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(retries=0, trust_env=False),
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=1),
        )
        self.sdk = sdk.AsyncOpenAI(
            api_key=api_key,
            base_url=endpoint,
            max_retries=0,
            http_client=client,
            organization="",
            project="",
            timeout=30.0,
        )

    async def stream_chat(self, payload: dict[str, Any]) -> list[bytes]:
        validate_outbound_sdk_payload(payload)
        total, chunks = 0, []
        try:
            async with self.sdk.chat.completions.with_streaming_response.create(
                **payload
            ) as response:
                async for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > 1_048_576:
                        raise ProviderFailure("MODEL_OUTPUT_LIMIT")
                    chunks.append(chunk)
            return chunks
        except Exception:
            raise ProviderFailure("MODEL_STREAM_FAILED_USAGE_UNKNOWN") from None
        finally:
            await self.sdk.close()
