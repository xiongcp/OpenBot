import asyncio
from typing import Any

import pytest
from openbot.application.cron_triggers import DurableScheduleSpec, DurableScheduleTriggerService
from openbot.application.memory import VerifiableMemoryService
from openbot.contracts import canonicalize
from openbot.domain.providers import ModelRequest, Text, ToolCall
from openbot.domain.tools import Effect, RetryClass, ToolManifest
from openbot.policy.egress import EgressGuard
from openbot.policy.secrets.broker import SecretBroker
from openbot.providers.anthropic import AnthropicMessagesStreamingAdapter
from openbot.providers.gemini import GeminiStreamingAdapter
from openbot.providers.ollama import (
    LocalModelEndpointAttestation,
    OllamaLocalProviderAdapter,
    OllamaRawResponse,
)
from openbot_feishu.cards import FeishuPlainCardBuilder

from tests.unit.test_secrets_broker import ControlledKeychainBackend


class _DummyBudget:
    def __init__(self) -> None:
        self.reserved: list[str] = []
        self.settled: list[tuple[str, int, int]] = []
        self.unknowns: list[str] = []

    def reserve(self, ref: str, units: int) -> None:
        self.reserved.append(ref)

    def settle(self, ref: str, p: int, c: int) -> None:
        self.settled.append((ref, p, c))

    def unknown(self, ref: str) -> None:
        self.unknowns.append(ref)


def test_v1_021_081_ollama_anthropic_and_gemini_streaming_adapters() -> None:
    manifest = ToolManifest(
        "workspace.read",
        "1.0.0",
        canonicalize(
            {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            }
        ),
        b'{"type":"object"}',
        Effect.READ,
        RetryClass.SAFE_READ,
        ("WORKSPACE",),
        "STOP_AND_WAIT",
        "VERIFY_HASH",
        10_000,
        16_384,
    )
    kc = ControlledKeychainBackend()
    kc.set_secret("keychain:provider:anthropic:main", b"sk-ant-canary-1")
    kc.set_secret("keychain:provider:gemini:main", b"sk-gem-canary-1")
    broker = SecretBroker(kc)
    egress = EgressGuard(
        profile_network_mode="CONNECTED",
        profile_allowed_domains=frozenset(
            {"api.anthropic.com", "generativelanguage.googleapis.com"}
        ),
        workspace_allowed_domains=frozenset(
            {"api.anthropic.com", "generativelanguage.googleapis.com"}
        ),
    )

    # 1. Cross-compartment secret resolution rejected
    with pytest.raises(PermissionError, match="selected_provider"):
        AnthropicMessagesStreamingAdapter(
            endpoint="https://api.anthropic.com/v1/messages",
            model="claude-3-5-sonnet",
            secret_ref="keychain:provider:gemini:main",
            secret_broker=broker,
            egress_guard=egress,
            budget=_DummyBudget(),
            manifests={"workspace.read": manifest},
            transport=None,  # type: ignore[arg-type]
        )

    # 2. Anthropic streaming text + tool_use assembly
    class _AnthTransport:
        async def stream_messages(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
            return [
                {"type": "message_start", "message": {"usage": {"input_tokens": 15}}},
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "tool_use", "id": "tu_1", "name": "workspace.read"},
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "input_json_delta", "partial_json": '{"path":'},
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "input_json_delta", "partial_json": '"demo.txt"}'},
                },
                {"type": "message_delta", "usage": {"output_tokens": 8}},
                {"type": "message_stop"},
            ]

    anth_budget = _DummyBudget()
    anth = AnthropicMessagesStreamingAdapter(
        endpoint="https://api.anthropic.com/v1/messages",
        model="claude-3-5-sonnet",
        secret_ref="keychain:provider:anthropic:main",
        secret_broker=broker,
        egress_guard=egress,
        budget=anth_budget,
        manifests={"workspace.read": manifest},
        transport=_AnthTransport(),
    )
    req_a = ModelRequest(
        "req_anth_1", "claude-3-5-sonnet", (Text("Read demo.txt"),), 999999999999, 50
    )
    resp_a = asyncio.run(anth.generate(req_a))
    assert isinstance(resp_a.blocks[0], ToolCall)
    assert resp_a.blocks[0].tool_name == "workspace.read"
    assert anth_budget.settled == [("req_anth_1:try_1", 15, 8)]

    # 3. Gemini streaming functionCall assembly
    class _GemTransport:
        async def stream_generate_content(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
            return [
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "functionCall": {
                                            "id": "fc_1",
                                            "name": "workspace.read",
                                            "args": {"path": "demo.txt"},
                                        }
                                    }
                                ]
                            },
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 6},
                }
            ]

    gem_budget = _DummyBudget()
    gem = GeminiStreamingAdapter(
        endpoint="https://generativelanguage.googleapis.com/v1beta",
        model="gemini-2.5-pro",
        secret_ref="keychain:provider:gemini:main",
        secret_broker=broker,
        egress_guard=egress,
        budget=gem_budget,
        manifests={"workspace.read": manifest},
        transport=_GemTransport(),
    )
    req_g = ModelRequest("req_gem_1", "gemini-2.5-pro", (Text("Read demo.txt"),), 999999999999, 50)
    resp_g = asyncio.run(gem.generate(req_g))
    assert isinstance(resp_g.blocks[0], ToolCall)
    assert gem_budget.settled == [("req_gem_1:try_1", 11, 6)]

    # 4. Local Ollama ModelRequest + budget + zero cloud fallback
    att = LocalModelEndpointAttestation(
        endpoint_url="http://127.0.0.1:11434/api/chat",
        model_id="qwen2.5-coder:7b",
        local_weights_digest="sha256:" + "f" * 64,
        runner_offline_egress_verified=True,
        cloud_relay_enabled=False,
        web_search_plugin_enabled=False,
        supports_structured_tools=True,
    )

    class _OllamaOk:
        def post_chat(self, payload: dict[str, object]) -> OllamaRawResponse:
            return OllamaRawResponse(
                content="Local summary",
                tool_calls=(),
                prompt_tokens=9,
                eval_tokens=5,
            )

    ol_budget = _DummyBudget()
    ol = OllamaLocalProviderAdapter(attestation=att, transport=_OllamaOk())
    resp_ol = ol.generate_model_response(
        ModelRequest("req_ol_1", "qwen2.5-coder:7b", (Text("Hi"),), 999999999999, 10),
        budget=ol_budget,
        privacy_mode="OFFLINE",
    )
    assert resp_ol.input_tokens == 9 and resp_ol.output_tokens == 5


def test_v1_082_083_084_feishu_card_v2_verifiable_memory_and_durable_cron() -> None:
    # 1. Feishu 2.0 collapsible diff card & stale interception card
    builder = FeishuPlainCardBuilder()
    card_v2 = builder.build_approval_card_v2(
        approval_id="apr_v2_1",
        task_id="tsk_1",
        tool_name="workspace.apply_patch",
        data_class="WORKSPACE",
        impact_summary="Patch config.py",
        diff_lines=("-MAX_WORKERS = 2", "+MAX_WORKERS = 8"),
        old_sha256="1111222233334444",
        new_sha256="9999888877776666",
        budget_used_pct=45,
        expires_at_iso="2026-11-05T14:00:00Z",
        expected_version=1,
        binding_hash="sha256:" + "a" * 64,
        nonce="n1",
    )
    assert card_v2.mode == "REMOTE_INTERACTIVE"
    assert any(el.get("tag") == "collapsible_panel" for el in card_v2.card_json["elements"])

    stale_card = builder.build_stale_or_expired_card_v2(
        approval_id="apr_v2_1",
        task_id="tsk_1",
        tool_name="workspace.apply_patch",
        reason="TARGET_DRIFTED",
    )
    assert stale_card.mode == "RESOLVED" and stale_card.remote_approve_enabled is False

    # 2. Verifiable Memory (OB-086): source_ref required, SECRET rejected, hard_forget clears cache
    mem = VerifiableMemoryService()
    with pytest.raises(PermissionError, match="MEMORY_CLASSIFICATION_FORBIDDEN"):
        mem.remember(
            owner_id="pri_1",
            workspace_id="wsp_1",
            key="api_key",
            content="sk-secret",
            source_ref="user_explicit:cmd_1",
            data_class="SECRET",
            now_ms=1000,
        )
    with pytest.raises(PermissionError, match="MEMORY_UNVERIFIED_SOURCE_REF"):
        mem.remember(
            owner_id="pri_1",
            workspace_id="wsp_1",
            key="pref",
            content="use ruff",
            source_ref="unverified_model_hallucination",
            data_class="WORKSPACE",
            now_ms=1000,
        )
    rec = mem.remember(
        owner_id="pri_1",
        workspace_id="wsp_1",
        key="indent",
        content="4 spaces",
        source_ref="user_explicit:cmd_101",
        data_class="WORKSPACE",
        now_ms=1000,
    )
    assert rec.authoritative_grants is False
    assert "4 spaces" in mem.cached_summary(owner_id="pri_1", workspace_id="wsp_1")
    # Cross-workspace isolation
    assert mem.recall_active(owner_id="pri_1", workspace_id="wsp_other", now_ms=1000) == ()
    # Hard forget purges record AND summary cache (0% recall)
    mem.hard_forget(rec.memory_id, owner_id="pri_1", workspace_id="wsp_1", now_ms=1001)
    assert mem.recall_active(owner_id="pri_1", workspace_id="wsp_1", now_ms=1001) == ()
    assert mem.cached_summary(owner_id="pri_1", workspace_id="wsp_1") == ""

    # 3. Durable Schedule Trigger (OB-087): sleep misfire coalesced to 1 QUEUED task
    cron = DurableScheduleTriggerService()
    cron.register_schedule(
        DurableScheduleSpec(
            schedule_id="sch_daily",
            owner_id="pri_1",
            workspace_id="wsp_1",
            goal_template="Summarize daily logs",
            timezone_name="America/Los_Angeles",
            interval_minutes=10,
            misfire_policy="COALESCE_SINGLE",
            next_fire_utc_ms=1_000_000,
        )
    )
    # Laptop slept for 5 hours (30 missed 10-min intervals): fires exactly ONCE as QUEUED task
    fired = cron.evaluate_due("sch_daily", now_utc_ms=1_000_000 + 30 * 600_000 + 500)
    assert fired is not None
    assert fired.task_state == "QUEUED"
    assert fired.fired_count == 1
    assert fired.coalesced_missed_runs == 30
    assert fired.bypasses_approval_broker is False
    assert cron.evaluate_due("sch_daily", now_utc_ms=1_000_000 + 30 * 600_000 + 600) is None
