"""Trusted launch-only model configuration; credentials never enter persisted settings."""

import getpass
import sys
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from openbot.application.agent_runtime import DEMO_MANIFEST
from openbot.domain.providers import ModelTransport, RequestBudget
from openbot.policy.egress import EgressGuard
from openbot.providers.openai_compatible import OpenAICompatibleAdapter
from openbot.providers.stream_transport import SdkSSETransport


def read_model_credentials() -> tuple[str, str]:
    values = []
    for prompt in ("Model endpoint / 模型地址: ", "API key (memory only) / 密钥（仅内存）: "):
        if sys.stdin.isatty():
            value = getpass.getpass(prompt)
        else:
            value = sys.stdin.readline(8193).rstrip("\r\n")
        if not value or len(value) > 8192 or any(ord(c) < 32 for c in value):
            raise PermissionError("CREDENTIAL_INPUT_INVALID")
        values.append(value)
    endpoint, key = values
    parsed = urlsplit(endpoint)
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or (
            parsed.scheme != "https"
            and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1"})
        )
    ):
        raise PermissionError("MODEL_ENDPOINT_INVALID")
    return endpoint, key


def model_factory(
    credentials: tuple[str, str] | None,
    active_mode: Callable[[], str],
) -> Callable[[dict[str, Any], RequestBudget], ModelTransport] | None:
    if credentials is None:
        return None
    endpoint, key = credentials
    host = urlsplit(endpoint).hostname
    assert host is not None

    def build(config: dict[str, Any], budget: RequestBudget) -> ModelTransport:
        return OpenAICompatibleAdapter(
            endpoint=endpoint,
            model=config["model"],
            budget=budget,
            egress_guard=EgressGuard(
                profile_network_mode=active_mode(),
                profile_allowed_domains=frozenset({host}),
                workspace_allowed_domains=frozenset({host}),
            ),
            manifests={DEMO_MANIFEST.name: DEMO_MANIFEST} if config["mcp_enabled"] else {},
            stream_transport=SdkSSETransport(endpoint=endpoint, api_key=key),
            capability_profile="openai_official",
            task_network_mode=config["mode"],
            data_class="WORKSPACE",
            max_gateway_retries=0,
        )

    return build
