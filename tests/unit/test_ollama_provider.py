import pytest
from openbot.providers.ollama import (
    LocalModelEndpointAttestation,
    OllamaLocalProviderAdapter,
    OllamaRawResponse,
)


class _FakeOllamaTransport:
    def __init__(self, response: OllamaRawResponse | Exception) -> None:
        self._resp = response
        self.calls: int = 0

    def post_chat(self, payload: dict[str, object]) -> OllamaRawResponse:
        self.calls += 1
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp


def test_ollama_provider_verifies_runner_egress_and_never_falls_back() -> None:
    valid_attestation = LocalModelEndpointAttestation(
        endpoint_url="http://127.0.0.1:11434/api/chat",
        model_id="qwen2.5-coder:7b",
        local_weights_digest="sha256:" + "c" * 64,
        runner_offline_egress_verified=True,
        cloud_relay_enabled=False,
        web_search_plugin_enabled=False,
        supports_structured_tools=True,
        allow_runtime_model_pull=False,
    )

    # 1. Localhost endpoint that relays to cloud or enables web search is rejected on 127.0.0.1!
    for bad_att in (
        LocalModelEndpointAttestation(
            endpoint_url="http://127.0.0.1:11434/api/chat",
            model_id="qwen2.5:cloud-proxy",
            local_weights_digest="sha256:" + "c" * 64,
            runner_offline_egress_verified=True,
            cloud_relay_enabled=True,
            web_search_plugin_enabled=False,
            supports_structured_tools=True,
        ),
        LocalModelEndpointAttestation(
            endpoint_url="http://127.0.0.1:11434/api/chat",
            model_id="qwen2.5-coder:7b",
            local_weights_digest="sha256:" + "c" * 64,
            runner_offline_egress_verified=False,
            cloud_relay_enabled=False,
            web_search_plugin_enabled=False,
            supports_structured_tools=True,
        ),
    ):
        with pytest.raises(PermissionError, match="CAPABILITY_UNAVAILABLE"):
            OllamaLocalProviderAdapter(
                attestation=bad_att,
                transport=_FakeOllamaTransport(
                    OllamaRawResponse(content="ok", tool_calls=(), prompt_tokens=5, eval_tokens=5)
                ),
            )

    # 2. Model without tool support returns CAPABILITY_UNAVAILABLE when tools are required
    no_tool_att = LocalModelEndpointAttestation(
        endpoint_url="http://127.0.0.1:11434/api/chat",
        model_id="llama-text-only:7b",
        local_weights_digest="sha256:" + "d" * 64,
        runner_offline_egress_verified=True,
        cloud_relay_enabled=False,
        web_search_plugin_enabled=False,
        supports_structured_tools=False,
    )
    no_tool_adapter = OllamaLocalProviderAdapter(
        attestation=no_tool_att,
        transport=_FakeOllamaTransport(
            OllamaRawResponse(content="ok", tool_calls=(), prompt_tokens=5, eval_tokens=5)
        ),
    )
    with pytest.raises(PermissionError, match="CAPABILITY_UNAVAILABLE_NO_TOOL_SUPPORT"):
        no_tool_adapter.generate(prompt="edit file", require_tools=True, privacy_mode="LOCAL_MODEL")

    # 3. Local failure in LOCAL_MODEL or OFFLINE never triggers cloud fallback
    failing_adapter = OllamaLocalProviderAdapter(
        attestation=valid_attestation,
        transport=_FakeOllamaTransport(ConnectionError("local runner down")),
    )
    res_fail = failing_adapter.generate(
        prompt="edit file", require_tools=True, privacy_mode="OFFLINE"
    )
    assert res_fail.status == "LOCAL_PROVIDER_FAILED"
    assert res_fail.cloud_fallback_attempted is False

    # 4. Valid local response returns untrusted candidate tool calls (authority_granted=False)
    ok_adapter = OllamaLocalProviderAdapter(
        attestation=valid_attestation,
        transport=_FakeOllamaTransport(
            OllamaRawResponse(
                content="proposing read",
                tool_calls=({"name": "workspace.read", "arguments": {"path": "hello.py"}},),
                prompt_tokens=12,
                eval_tokens=8,
            )
        ),
    )
    res_ok = ok_adapter.generate(prompt="read hello.py", require_tools=True, privacy_mode="OFFLINE")
    assert res_ok.status == "OK"
    assert res_ok.cloud_fallback_attempted is False
    assert res_ok.authority_granted is False
