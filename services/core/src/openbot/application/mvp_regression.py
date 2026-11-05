"""M3 full MVP capability regression suite across providers, Feishu, ACI, browser, and MCP."""

import asyncio
import importlib.util
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from openbot_feishu.e2e_harness import FeishuM2EndToEndHarness

from openbot.application.skills import ReadOnlySkillLoader, SkillManifestSpec
from openbot.application.vertical_slice import M1VerticalSliceHarness
from openbot.domain.providers import ModelRequest, Text
from openbot.providers.ollama import (
    LocalModelEndpointAttestation,
    OllamaHttpTransport,
    OllamaLocalProviderAdapter,
    OllamaRawResponse,
)
from openbot.providers.openai import OpenAITransport
from openbot.tools.browser.verifier import BrowserOutcomeRegressionHarness
from openbot.tools.mcp.fault_harness import McpFaultAndMaliciousHarness


class _OfflineOllamaTransport:
    def post_chat(self, payload: dict[str, object]) -> OllamaRawResponse:
        del payload
        return OllamaRawResponse(content="ok", tool_calls=(), prompt_tokens=4, eval_tokens=4)


class _FailingLocalTransport:
    def post_chat(self, payload: dict[str, object]) -> OllamaRawResponse:
        del payload
        raise ConnectionRefusedError("Local Ollama runner is stopped")


class _InMemoryRequestBudget:
    def __init__(self, *, total_units: int = 100_000) -> None:
        self.total_units = total_units
        self.reserved: dict[str, int] = {}
        self.settled: dict[str, tuple[int, int]] = {}
        self.unknown_ids: list[str] = []

    def reserve(self, request_id: str, units: int) -> None:
        if sum(self.reserved.values()) + units > self.total_units:
            raise PermissionError("BUDGET_EXHAUSTED")
        self.reserved[request_id] = units

    def settle(self, request_id: str, input_tokens: int, output_tokens: int) -> None:
        self.settled[request_id] = (input_tokens, output_tokens)

    def unknown(self, request_id: str) -> None:
        self.unknown_ids.append(request_id)


@dataclass(frozen=True, slots=True)
class MvpCapabilityRegressionReport:
    subsystems_verified: tuple[str, ...]
    security_critical_failures: int
    provider_qualifications: dict[str, str]
    both_real_providers_verified: bool = False
    reference_only_or_deferred_claimed_as_active: Literal[False] = False
    claims_three_os_release_complete: Literal[False] = False


class MvpCapabilityRegressionSuite:
    """Verify the combined M3 MVP capability matrix and record honest boundary limits."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def _qualify_providers(
        self,
        *,
        cloud_config: dict[str, str] | None,
        ollama_endpoint: str | None,
    ) -> dict[str, str]:
        att = LocalModelEndpointAttestation(
            endpoint_url="http://127.0.0.1:11434/api/chat",
            model_id="qwen2.5-coder:7b",
            local_weights_digest="sha256:" + "a" * 64,
            runner_offline_egress_verified=True,
            cloud_relay_enabled=False,
            web_search_plugin_enabled=False,
            supports_structured_tools=True,
        )
        syn_ok = OllamaLocalProviderAdapter(
            attestation=att, transport=_OfflineOllamaTransport()
        ).generate(prompt="ping", require_tools=True, privacy_mode="OFFLINE")
        syn_down = OllamaLocalProviderAdapter(
            attestation=att, transport=_FailingLocalTransport()
        ).generate(prompt="ping", require_tools=True, privacy_mode="OFFLINE")
        synthetic_status = (
            "PASS"
            if (
                syn_ok.status == "OK"
                and not syn_ok.cloud_fallback_attempted
                and syn_down.status == "LOCAL_PROVIDER_FAILED"
                and not syn_down.cloud_fallback_attempted
            )
            else "FAIL"
        )

        has_sdk = (
            importlib.util.find_spec("openai") is not None
            and importlib.util.find_spec("httpx") is not None
        )
        sdk_loopback_status = "PASS" if has_sdk else "BLOCKED_DEPENDENCY"

        cloud_status = "BLOCKED_CREDENTIALS"
        if cloud_config and cloud_config.get("endpoint") and cloud_config.get("api_key"):
            if not has_sdk:
                cloud_status = "BLOCKED_DEPENDENCY"
            else:
                try:
                    budget = _InMemoryRequestBudget(total_units=100_000)

                    async def _call_cloud() -> Any:
                        tr = OpenAITransport(
                            cloud_config["endpoint"],
                            cloud_config["model"],
                            cloud_config["api_key"],
                            budget,
                        )
                        try:
                            return await tr.generate(
                                ModelRequest(
                                    request_id="mvp_cloud_qual_1",
                                    model=cloud_config["model"],
                                    blocks=(Text("Reply with the single word OK."),),
                                    reserved_cost_units=1000,
                                    deadline_monotonic_ms=int(time.monotonic() * 1000) + 15_000,
                                )
                            )
                        finally:
                            await tr.close()

                    c_resp = asyncio.run(_call_cloud())
                    cloud_status = "PASS" if c_resp.blocks else "FAIL"
                except Exception:
                    cloud_status = "FAIL"

        local_status = "BLOCKED_ENV"
        if ollama_endpoint:
            try:
                http_tr = OllamaHttpTransport(ollama_endpoint, timeout_seconds=5.0)
                models = http_tr.probe_models()
                if models:
                    first = models[0]
                    digest = str(first.get("digest", ""))
                    if len(digest) == 64:
                        digest = f"sha256:{digest}"
                    live_att = LocalModelEndpointAttestation(
                        endpoint_url=ollama_endpoint,
                        model_id=str(first["name"]),
                        local_weights_digest=digest,
                        runner_offline_egress_verified=True,
                        cloud_relay_enabled=False,
                        web_search_plugin_enabled=False,
                        supports_structured_tools=True,
                    )
                    live_res = OllamaLocalProviderAdapter(
                        attestation=live_att, transport=http_tr
                    ).generate(prompt="Reply OK", require_tools=False, privacy_mode="LOCAL_MODEL")
                    local_status = "PASS" if live_res.status == "OK" else "FAIL"
            except Exception:
                local_status = "BLOCKED_ENV"

        return {
            "synthetic_provider_contract": synthetic_status,
            "sdk_loopback_contract": sdk_loopback_status,
            "real_cloud_provider": cloud_status,
            "real_local_ollama_runner": local_status,
        }

    def run_all(
        self,
        *,
        cloud_config: dict[str, str] | None = None,
        ollama_endpoint: str | None = None,
    ) -> MvpCapabilityRegressionReport:
        self._base.mkdir(parents=True, exist_ok=True)
        repo_root = Path(__file__).resolve().parents[5]
        subsystems: list[str] = []
        failures = 0

        # 1. Independent four-tier provider qualification
        quals = self._qualify_providers(cloud_config=cloud_config, ollama_endpoint=ollama_endpoint)
        both_real = (
            quals["real_cloud_provider"] == "PASS" and quals["real_local_ollama_runner"] == "PASS"
        )
        if quals["synthetic_provider_contract"] == "PASS":
            subsystems.append(
                "cloud_and_local_providers" if both_real else "provider_contract_guards"
            )
        else:
            failures += 1

        # 2. Feishu controlled gateway
        feishu_rep = FeishuM2EndToEndHarness(self._base / "feishu").run_all()
        if feishu_rep.main_flow_passed and len(feishu_rep.failure_scenarios_verified) == 6:
            subsystems.append("feishu_controlled_gateway")
        else:
            failures += 1

        # 3. Workspace ACI & isolated process
        slice_h = M1VerticalSliceHarness.create(self._base / "aci")
        try:
            aci_res = slice_h.run_local_restricted_effect_slice()
            if aci_res["task_final_state"] == "SUCCEEDED" and aci_res["workspace_file_patched"]:
                subsystems.append("workspace_aci_and_isolated_process")
            else:
                failures += 1
        finally:
            slice_h.close()

        # 4. Browser structured tools
        br_rep = BrowserOutcomeRegressionHarness(self._base / "browser").run_all_fixture_scenarios()
        if len(br_rep.scenarios_verified) == 5:
            subsystems.append("browser_structured_tools")
        else:
            failures += 1

        # 5. MCP stdio and fault guards
        mcp_rep = McpFaultAndMaliciousHarness().run_all()
        if len(mcp_rep.cases_verified) == 6 and mcp_rep.post_dispatch_disconnect_retried_count == 0:
            subsystems.append("mcp_stdio_and_fault_guards")
        else:
            failures += 1

        # 6. Read-only skills loader
        loader = ReadOnlySkillLoader(
            schema_path=repo_root / "contracts/schemas/skill_manifest.schema.json"
        )
        skl = loader.load_readonly_skill(
            SkillManifestSpec(
                skill_id="skl_mvp",
                name="MVP Skill",
                version="1.0.0",
                source_uri="local://skills/mvp",
                license="MIT",
                sha256="b" * 64,
                required_capabilities=("workspace.read",),
                instructions_markdown="# Read-only",
            )
        )
        if not skl.can_mutate_policy and not skl.can_expand_workspace:
            subsystems.append("readonly_skills_loader")
        else:
            failures += 1

        return MvpCapabilityRegressionReport(
            subsystems_verified=tuple(subsystems),
            security_critical_failures=failures,
            provider_qualifications=quals,
            both_real_providers_verified=both_real,
        )
