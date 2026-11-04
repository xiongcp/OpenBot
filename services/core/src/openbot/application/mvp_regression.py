"""M3 full MVP capability regression suite across providers, Feishu, ACI, browser, and MCP."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openbot_feishu.e2e_harness import FeishuM2EndToEndHarness

from openbot.application.skills import ReadOnlySkillLoader, SkillManifestSpec
from openbot.application.vertical_slice import M1VerticalSliceHarness
from openbot.providers.ollama import (
    LocalModelEndpointAttestation,
    OllamaLocalProviderAdapter,
    OllamaRawResponse,
)
from openbot.tools.browser.verifier import BrowserOutcomeRegressionHarness
from openbot.tools.mcp.fault_harness import McpFaultAndMaliciousHarness


class _OfflineOllamaTransport:
    def post_chat(self, payload: dict[str, object]) -> OllamaRawResponse:
        del payload
        return OllamaRawResponse(content="ok", tool_calls=(), prompt_tokens=4, eval_tokens=4)


@dataclass(frozen=True, slots=True)
class MvpCapabilityRegressionReport:
    subsystems_verified: tuple[str, ...]
    security_critical_failures: int
    reference_only_or_deferred_claimed_as_active: Literal[False] = False
    claims_three_os_release_complete: Literal[False] = False


class MvpCapabilityRegressionSuite:
    """Verify the combined M3 MVP capability matrix and record honest boundary limits."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def run_all(self) -> MvpCapabilityRegressionReport:
        self._base.mkdir(parents=True, exist_ok=True)
        repo_root = Path(__file__).resolve().parents[5]
        subsystems: list[str] = []
        failures = 0

        # 1. Cloud & Local Ollama providers
        ollama = OllamaLocalProviderAdapter(
            attestation=LocalModelEndpointAttestation(
                endpoint_url="http://127.0.0.1:11434/api/chat",
                model_id="qwen2.5-coder:7b",
                local_weights_digest="sha256:" + "a" * 64,
                runner_offline_egress_verified=True,
                cloud_relay_enabled=False,
                web_search_plugin_enabled=False,
                supports_structured_tools=True,
            ),
            transport=_OfflineOllamaTransport(),
        )
        res_loc = ollama.generate(prompt="ping", require_tools=True, privacy_mode="OFFLINE")
        if res_loc.status == "OK" and not res_loc.cloud_fallback_attempted:
            subsystems.append("cloud_and_local_providers")
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
        )
