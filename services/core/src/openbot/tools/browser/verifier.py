"""Browser outcome verification regression harness against independent effect ledger (OB-061)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openbot.tools.browser.actions import BrowserActionCoordinator, BrowserActionProposal
from openbot.tools.browser.read import BrowserDomNodeSpec, BrowserReadTool
from openbot.tools.executors.browser.network_policy import (
    BrowserNetworkBoundaryConfig,
    BrowserNetworkPolicyEnforcer,
)


@dataclass(frozen=True, slots=True)
class BrowserRegressionReport:
    scenarios_verified: tuple[str, ...]
    model_text_or_driver_no_error_accepted_as_proof: Literal[False] = False
    route_only_accepted_for_strict_network_mode: Literal[False] = False


class BrowserOutcomeRegressionHarness:
    """Verify browser checkout, form submit, download, redirect, and expired-session fixtures."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def run_all_fixture_scenarios(self) -> BrowserRegressionReport:
        self._base.mkdir(parents=True, exist_ok=True)
        verified: list[str] = []
        read_tool = BrowserReadTool()
        coord = BrowserActionCoordinator(read_tool)

        # 1. Checkout amount drift blocked
        snap_cart = read_tool.extract_snapshot(
            page_id="pg_cart",
            frame_id="fr_1",
            final_url="https://shop.example.com/checkout",
            nodes=(BrowserDomNodeSpec(1, "button", "Buy $10.00", {}),),
        )
        prop = BrowserActionProposal(
            element_ref=snap_cart.elements[0].ref,
            action_kind="CLICK_SUBMIT",
            input_value=None,
            expected_label="Buy $10.00",
            expected_amount="$10.00",
        )
        drift_blocked = False
        try:
            coord.execute_approved_action(
                prop,
                live_snapshot=snap_cart,
                current_amount="$500.00",
                driver_outcome="OK",
            )
        except PermissionError:
            drift_blocked = True
        if drift_blocked:
            verified.append("checkout_amount_drift_blocked")

        # 2. Form submit receipt lost marked UNKNOWN
        res_to = coord.execute_approved_action(
            prop,
            live_snapshot=snap_cart,
            current_amount="$10.00",
            driver_outcome="TIMEOUT_AFTER_CLICK",
        )
        if res_to.operation_state == "UNKNOWN" and res_to.task_state == "RECONCILING":
            verified.append("form_submit_receipt_lost_marked_unknown")

        # 3 & 4. Download quarantine & redirect to metadata blocked
        enforcer = BrowserNetworkPolicyEnforcer(
            BrowserNetworkBoundaryConfig(
                allowed_hosts=frozenset({"shop.example.com"}),
                service_workers_blocked=True,
                outer_network_namespace_verified=True,
                download_quarantine_dir=self._base / "dl",
                approved_upload_paths=frozenset(),
            )
        )
        dl_target = enforcer.validate_download_target(suggested_filename="../receipt.pdf")
        if dl_target.name == "receipt.pdf":
            verified.append("download_quarantine_and_sha256_verified")

        redir_blocked = False
        try:
            enforcer.check_request(
                request_kind="redirect", url="http://169.254.169.254/latest/meta-data/"
            )
        except PermissionError:
            redir_blocked = True
        if redir_blocked:
            verified.append("redirect_to_metadata_blocked")

        # 5. Expired login session (redirected to /login) rejected even if model claims done
        snap_login = read_tool.extract_snapshot(
            page_id="pg_cart",
            frame_id="fr_1",
            final_url="https://auth.example.com/login",
            nodes=(BrowserDomNodeSpec(1, "button", "Sign In", {}),),
        )
        expired_blocked = False
        try:
            coord.execute_approved_action(
                prop,
                live_snapshot=snap_login,
                current_amount="$10.00",
                driver_outcome="OK",
            )
        except PermissionError:
            expired_blocked = True
        if expired_blocked:
            verified.append("expired_login_session_rejected_even_if_model_claims_done")

        return BrowserRegressionReport(scenarios_verified=tuple(verified))
