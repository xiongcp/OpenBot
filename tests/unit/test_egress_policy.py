import pytest
from openbot.policy.egress import (
    EgressGuard,
    EgressRequest,
    LocalModelRunnerAttestation,
    build_controlled_http_config,
)


def test_offline_blocks_all_surfaces_and_local_model_requires_runner_attestation():
    guard = EgressGuard(
        profile_network_mode="OFFLINE",
        profile_allowed_domains=frozenset({"api.openai.com", "open.feishu.cn", "example.com"}),
        workspace_allowed_domains=frozenset({"api.openai.com", "open.feishu.cn", "example.com"}),
    )
    # 1. OFFLINE blocks remote egress across ALL surfaces (not just LLM)
    for surface in (
        "MODEL_GATEWAY",
        "FEISHU_NOTIFICATION",
        "BROWSER",
        "MCP",
        "FILE_UPLOAD",
        "MESSAGE_TOOL",
    ):
        dec = guard.evaluate(
            EgressRequest(
                surface=surface,
                task_network_mode="OFFLINE",
                data_class="PUBLIC",
                destination_url="https://example.com/resource",
            )
        )
        assert dec.decision == "DENY"
        assert dec.reason_code == "OFFLINE_REMOTE_EGRESS_DENIED"

    # 2. Loopback localhost alone does NOT prove local model safety without runner attestation
    local_guard = EgressGuard(
        profile_network_mode="LOCAL_MODEL",
        profile_allowed_domains=frozenset(),
        workspace_allowed_domains=frozenset(),
    )
    unverified_local = local_guard.evaluate(
        EgressRequest(
            surface="LOCAL_MODEL_RUNNER",
            task_network_mode="LOCAL_MODEL",
            data_class="WORKSPACE",
            destination_url="http://127.0.0.1:11434/api/chat",
            runner_attestation=LocalModelRunnerAttestation(
                model_id="deepseek-v3:cloud",
                model_source_verified=True,
                cloud_routing_disabled=False,
                web_search_disabled=True,
                egress_isolated_verified=True,
            ),
        )
    )
    assert unverified_local.decision == "DENY"
    assert unverified_local.reason_code == "LOCAL_MODEL_CLOUD_ROUTING_OR_UNVERIFIED"

    verified_local = local_guard.evaluate(
        EgressRequest(
            surface="LOCAL_MODEL_RUNNER",
            task_network_mode="LOCAL_MODEL",
            data_class="WORKSPACE",
            destination_url="http://127.0.0.1:11434/api/chat",
            runner_attestation=LocalModelRunnerAttestation(
                model_id="qwen2.5-coder:7b-local",
                model_source_verified=True,
                cloud_routing_disabled=True,
                web_search_disabled=True,
                egress_isolated_verified=True,
            ),
        )
    )
    assert verified_local.decision == "ALLOW"


def test_sensitive_summary_artifact_card_and_allowed_domain_restrictions():
    guard = EgressGuard(
        profile_network_mode="CONNECTED",
        profile_allowed_domains=frozenset({"api.openai.com", "open.feishu.cn"}),
        workspace_allowed_domains=frozenset({"api.openai.com", "open.feishu.cn"}),
    )
    # 1. SECRET is always denied even to an allowed domain or after redaction flag
    sec_dec = guard.evaluate(
        EgressRequest(
            surface="MODEL_GATEWAY",
            task_network_mode="CONNECTED",
            data_class="SECRET",
            destination_url="https://api.openai.com/v1/chat/completions",
            redacted=True,
        )
    )
    assert sec_dec.decision == "DENY"
    assert sec_dec.reason_code == "SECRET_EGRESS_FORBIDDEN"

    # 2. SENSITIVE data placed in a Feishu card preview or context summary is NEVER auto-sent
    card_sens = guard.evaluate(
        EgressRequest(
            surface="FEISHU_NOTIFICATION",
            task_network_mode="CONNECTED",
            data_class="SENSITIVE",
            destination_url="https://open.feishu.cn/open-apis/im/v1/messages",
            from_summary=True,
        )
    )
    assert card_sens.decision == "REQUIRE_LOCAL"
    assert card_sens.reason_code == "SENSITIVE_PREVIEW_REQUIRES_LOCAL"

    # 3. SENSITIVE artifact sent to an allowed model domain requires explicit ASK
    model_sens = guard.evaluate(
        EgressRequest(
            surface="MODEL_GATEWAY",
            task_network_mode="CONNECTED",
            data_class="SENSITIVE",
            destination_url="https://api.openai.com/v1/chat/completions",
            from_artifact=True,
            redacted=True,
        )
    )
    assert model_sens.decision == "ASK"
    assert model_sens.reason_code == "SENSITIVE_REMOTE_REQUIRES_APPROVAL"

    # 4. Provider-hosted web search / remote MCP / online secret verify / downloads denied
    for feature in (
        "web_search",
        "remote_mcp",
        "price_map_download",
        "tokenizer_download",
        "online_secret_verify",
    ):
        feat_dec = guard.evaluate(
            EgressRequest(
                surface="MODEL_GATEWAY",
                task_network_mode="CONNECTED",
                data_class="PUBLIC",
                destination_url="https://api.openai.com/v1/responses",
                implicit_features=(feature,),
            )
        )
        assert feat_dec.decision == "DENY"
        assert feat_dec.reason_code == "IMPLICIT_OR_HOSTED_EGRESS_FORBIDDEN"


def test_controlled_http_config_strips_ambient_proxies_and_validates_approved_proxy():
    ambient = {
        "HTTP_PROXY": "http://evil-proxy.invalid:8080",
        "HTTPS_PROXY": "http://evil-proxy.invalid:8080",
        "ALL_PROXY": "socks5://evil-proxy.invalid:1080",
        "PATH": "/usr/bin",
    }
    cfg = build_controlled_http_config(
        effective_network_mode="CONNECTED",
        allowed_domains=frozenset({"proxy.corp.example", "api.openai.com"}),
        approved_proxy_url=None,
        ambient_env=ambient,
    )
    assert cfg.trust_env is False
    assert cfg.follow_redirects is False
    assert cfg.max_retries == 0
    assert cfg.proxy_url is None
    assert "HTTP_PROXY" not in cfg.sanitized_env
    assert "HTTPS_PROXY" not in cfg.sanitized_env
    assert "ALL_PROXY" not in cfg.sanitized_env
    assert "native" in cfg.unproven_by_python_probe.lower()

    # Unapproved proxy host is rejected
    with pytest.raises(PermissionError, match="proxy"):
        build_controlled_http_config(
            effective_network_mode="CONNECTED",
            allowed_domains=frozenset({"api.openai.com"}),
            approved_proxy_url="https://unapproved-proxy.example:8443",
            ambient_env=ambient,
        )
