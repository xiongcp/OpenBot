import sys
from pathlib import Path

import pytest
from openbot.tools.browser.actions import BrowserActionCoordinator, BrowserActionProposal
from openbot.tools.browser.read import BrowserDomNodeSpec
from openbot.tools.desktop.macos_ax_actions import (
    DesktopActionProposal,
    HumanInputTakeoverMonitor,
    MacOSAxActionExecutor,
)
from openbot.tools.desktop.macos_ax_observer import MacOSAxWindowObserver
from openbot.tools.executors.browser.network_policy import BrowserNetworkBoundaryConfig
from openbot.tools.executors.browser.playwright_session import ManagedPlaywrightSession
from openbot.tools.executors.browser.session import (
    BrowserIsolationAttestation,
    BrowserProfileSessionManager,
    BrowserSessionSpec,
)
from openbot.tools.executors.sandbox import ContainerOwnership
from openbot.tools.mcp.client import McpCompatibilityManifest, McpStdioLifecycleClient
from openbot.tools.mcp.container_executor import ContainerIntentLedger, McpContainerExecutor

ROOT = Path(__file__).resolve().parents[2]


def test_v1_016_017_076_mcp_stdio_deadline_catalog_pin_and_orphan_reaping(
    tmp_path: Path,
) -> None:
    # 1. MCP stdio init_timeout_ms enforced when server hangs before replying
    hang_manifest = McpCompatibilityManifest(
        server_id="srv_hang",
        pinned_package_digest="sha256:" + "a" * 64,
        executable=sys.executable,
        argv=(sys.executable, "-c", "import time; time.sleep(5)"),
        transport="stdio",
        supported_protocol_versions=("2025-03-26",),
        init_timeout_ms=100,
    )
    client = McpStdioLifecycleClient(hang_manifest)
    with pytest.raises(PermissionError, match="MCP_INITIALIZE_TIMEOUT"):
        client.start_and_handshake()

    # 2. McpContainerExecutor loads 3 official tools from components/locks/mcp-catalog.json
    ledger = ContainerIntentLedger(tmp_path / "container_intents.json")
    executor = McpContainerExecutor(
        catalog_path=ROOT / "components/locks/mcp-catalog.json",
        intent_ledger=ledger,
    )
    assert executor.admitted_tools() == (
        "mcp.doc_extractor",
        "mcp.git_inspector",
        "mcp.sqlite_reader",
    )
    ownership = ContainerOwnership("pro_1", "op_1", "att_1", "ep_1")
    res = executor.execute_tool(
        "mcp.git_inspector",
        {"subcommand": "status"},
        ownership,
        runtime_runner=lambda spec, args: {"branch": "main", "clean": True},
    )
    assert res["cleanup_verified"] is True
    assert "--network=none" in res["create_argv"]
    assert "--read-only" in res["create_argv"]

    # 3. Metadata drift triggers QUARANTINED_ON_DRIFT
    with pytest.raises(PermissionError, match="MCP_METADATA_DRIFT_QUARANTINED"):
        executor.execute_tool(
            "mcp.git_inspector",
            {"subcommand": "status"},
            ownership,
            runtime_runner=lambda spec, args: {},
            observed_tool_description="Tampered description with hidden prompt",
        )

    # 4. Pre-create intent log reaps orphan container after SIGKILL
    with pytest.raises(RuntimeError, match="SIMULATED_SIGKILL_AFTER_CONTAINER_CREATE"):
        executor.execute_tool(
            "mcp.sqlite_reader",
            {"db_rel_path": "a.db", "table": "tasks"},
            ownership,
            runtime_runner=lambda spec, args: {},
            simulate_sigkill_before_reclaim=True,
        )
    assert len(ledger.pending_intents()) == 1
    reaped = executor.reap_orphan_containers()
    assert len(reaped) == 1
    assert len(ledger.pending_intents()) == 0


def test_v1_018_019_077_078_playwright_session_aria_snapshot_and_highlight_preview(
    tmp_path: Path,
) -> None:
    pm = BrowserProfileSessionManager(dedicated_root=tmp_path / "profiles")
    net_cfg = BrowserNetworkBoundaryConfig(
        allowed_hosts=frozenset({"portal.example.com"}),
        service_workers_blocked=True,
        outer_network_namespace_verified=True,
        download_quarantine_dir=tmp_path / "quarantine",
        approved_upload_paths=frozenset(),
    )
    session = ManagedPlaywrightSession(profile_manager=pm, network_config=net_cfg)
    session.start_session(
        task_id="tsk_br_1",
        spec=BrowserSessionSpec(
            profile_name="p1",
            user_data_dir=tmp_path / "profiles/p1",
            launch_args=(),
            cdp_attach_url=None,
            decrypt_system_cookies=False,
            isolation=BrowserIsolationAttestation("Darwin", True, True),
        ),
    )
    try:
        snap = session.intercept_and_navigate(
            page_id="pg_1",
            frame_id="fr_main",
            initial_url="https://portal.example.com/order",
            aria_nodes=(BrowserDomNodeSpec(1, "button", "Confirm Pay $25.00", {"role": "button"}),),
        )
        assert snap.provenance_kind == "TAINTED_EXTERNAL"
        assert snap.grants_policy_or_owner_authority is False

        # Evil redirect to metadata IP is blocked
        with pytest.raises(PermissionError, match="169.254.169.254"):
            session.intercept_and_navigate(
                page_id="pg_1",
                frame_id="fr_main",
                initial_url="https://portal.example.com/order",
                redirect_chain=("http://169.254.169.254/latest/meta-data/",),
                aria_nodes=(),
            )

        # Highlight preview & live driver execution
        coord = BrowserActionCoordinator(session._reader)
        proposal = BrowserActionProposal(
            element_ref=snap.elements[0].ref,
            action_kind="CLICK_SUBMIT",
            input_value=None,
            expected_label="Confirm Pay $25.00",
            expected_amount="$25.00",
        )
        preview = coord.build_target_highlight_preview(proposal, snapshot=snap)
        assert b'stroke="#d92d20"' in preview.svg_bytes
        assert len(preview.sha256) == 64

        res_ok = coord.execute_approved_action(
            proposal,
            live_snapshot=snap,
            current_amount="$25.00",
            live_driver=lambda p: {"verified_effect": True},
        )
        assert res_ok.operation_state == "SUCCEEDED"

        # Timeout after click enters UNKNOWN/RECONCILING with zero second click
        def _timeout_driver(_p: BrowserActionProposal) -> dict[str, object]:
            raise TimeoutError("network lost after click")

        res_unk = coord.execute_approved_action(
            proposal,
            live_snapshot=snap,
            current_amount="$25.00",
            live_driver=_timeout_driver,
        )
        assert res_unk.operation_state == "UNKNOWN"
        assert res_unk.task_state == "RECONCILING"
        assert res_unk.second_click_permitted is False
    finally:
        session.close_session()


def test_v1_079_080_macos_ax_blacklist_focus_drift_and_human_input_takeover() -> None:
    obs = MacOSAxWindowObserver(allowed_bundle_ids=frozenset({"com.apple.TextEdit"}))

    # 1. Keychain, 1Password, SecureEventInput, and AXSecureTextField are hard-blocked
    with pytest.raises(PermissionError, match="SENSITIVE_WINDOW_OR_SECURE_INPUT_BLOCKED"):
        obs.observe_window(
            app_bundle_id="com.apple.keychainaccess",
            pid=101,
            window_id=1,
            window_title="Keychain Access",
            raw_nodes=(),
        )
    with pytest.raises(PermissionError, match="SENSITIVE_WINDOW_OR_SECURE_INPUT_BLOCKED"):
        obs.observe_window(
            app_bundle_id="com.apple.TextEdit",
            pid=102,
            window_id=2,
            window_title="Document",
            raw_nodes=({"ax_path": "window[0]/field[0]", "role": "AXSecureTextField"},),
        )

    win = obs.observe_window(
        app_bundle_id="com.apple.TextEdit",
        pid=200,
        window_id=10,
        window_title="Notes.txt",
        raw_nodes=(
            {
                "ax_path": "window[0]/button[0]",
                "role": "AXButton",
                "title": "Save",
                "enabled": True,
            },
        ),
    )
    assert win.provenance_kind == "TAINTED_EXTERNAL"

    monitor = HumanInputTakeoverMonitor()
    executor = MacOSAxActionExecutor(monitor)
    proposal = DesktopActionProposal(
        app_bundle_id="com.apple.TextEdit",
        pid=200,
        window_id=10,
        ax_path="window[0]/button[0]",
        expected_role="AXButton",
        expected_title="Save",
        snapshot_revision=win.snapshot_revision,
        action_kind="AXPress",
    )

    # 2. Focus drift (PID or window_id changed) raises DESKTOP_FOCUS_DRIFT
    drifted_win = obs.observe_window(
        app_bundle_id="com.apple.TextEdit",
        pid=999,
        window_id=10,
        window_title="Notes.txt",
        raw_nodes=(
            {
                "ax_path": "window[0]/button[0]",
                "role": "AXButton",
                "title": "Save",
                "enabled": True,
            },
        ),
    )
    with pytest.raises(PermissionError, match="DESKTOP_FOCUS_DRIFT"):
        executor.execute_approved_desktop_action(proposal, live_window=drifted_win)

    # 3. Physical human input preempts within < 100ms into PAUSED_BY_USER_TAKEOVER
    monitor.record_physical_input("ESC_KEY")
    res = executor.execute_approved_desktop_action(proposal, live_window=win)
    assert res.status == "PAUSED_BY_USER_TAKEOVER"
    assert res.task_state == "PAUSED_BY_USER_TAKEOVER"
    assert res.takeover_latency_ms is not None and res.takeover_latency_ms <= 100.0
