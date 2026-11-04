"""M1 minimal local Alpha prototype runner and honest capability boundary reporter (OB-046)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openbot.application.vertical_slice import M1VerticalSliceHarness
from openbot.cli import run_cli_command
from openbot.tools.workspace.read import WorkspaceReadTools


@dataclass(frozen=True, slots=True)
class LocalAlphaCapabilityReport:
    version: str
    pilot_os: str
    read_file_verified: bool
    patch_proposed_and_approved: bool
    isolated_test_executed: bool
    restart_requery_verified: bool
    enabled_m1_components: tuple[str, ...]
    unsupported_or_unverified_capabilities: tuple[str, ...]
    claims_full_mvp_complete: Literal[False] = False


class LocalAlphaPrototypeRunner:
    """Run the M1 local Alpha prototype from an empty directory and emit a versioned report."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def run_from_empty_config(self) -> LocalAlphaCapabilityReport:
        harness = M1VerticalSliceHarness.create(self._base)
        try:
            reader = WorkspaceReadTools(harness.workspace_dir)
            read_res = reader.read("hello.py")
            read_ok = read_res.lines == ((1, "value = 1"),)

            slice_res = harness.run_local_restricted_effect_slice()
            crash_res = harness.run_fault_crash_scenario("after_effect_before_receipt")
            code_h, _ = run_cli_command(["version"])
            return LocalAlphaCapabilityReport(
                version="0.1.0-alpha.m1",
                pilot_os="Darwin-arm64",
                read_file_verified=read_ok and code_h == 0,
                patch_proposed_and_approved=bool(slice_res["workspace_file_patched"]),
                isolated_test_executed=bool(slice_res["worker_reaped"]),
                restart_requery_verified=(crash_res["resolved_operation_state"] == "SUCCEEDED"),
                enabled_m1_components=(
                    "sqlite3",
                    "rfc8785",
                    "pydantic-jsonschema",
                    "openai-python-sdk (offline fault-verified)",
                    "httpx",
                    "cli-toolchain",
                ),
                unsupported_or_unverified_capabilities=(
                    "Windows-native",
                    "Linux-native",
                    "real_feishu_tenant",
                    "real_production_cloud_model_credentials",
                    "playwright_browser_automation",
                    "desktop_gui_automation",
                ),
                claims_full_mvp_complete=False,
            )
        finally:
            harness.close()
