import pytest
from openbot.tools.browser.actions import (
    BrowserActionCoordinator,
    BrowserActionProposal,
)
from openbot.tools.browser.read import BrowserDomNodeSpec, BrowserReadTool


def test_browser_action_revalidates_preconditions_and_turns_timeout_into_unknown() -> None:
    read_tool = BrowserReadTool()
    snap1 = read_tool.extract_snapshot(
        page_id="pg_1",
        frame_id="fr_1",
        final_url="https://shop.example.com/checkout",
        nodes=(
            BrowserDomNodeSpec(element_index=1, tag="button", text="Pay $19.99", attributes={}),
        ),
    )
    coord = BrowserActionCoordinator(read_tool)
    proposal = BrowserActionProposal(
        element_ref=snap1.elements[0].ref,
        action_kind="CLICK_SUBMIT",
        input_value=None,
        expected_label="Pay $19.99",
        expected_amount="$19.99",
    )

    # 1. If button label / amount / origin drifts before execution, old approval is REJECTED
    snap_tampered = read_tool.extract_snapshot(
        page_id="pg_1",
        frame_id="fr_1",
        final_url="https://shop.example.com/checkout",
        nodes=(
            BrowserDomNodeSpec(element_index=1, tag="button", text="Pay $999.99", attributes={}),
        ),
    )
    with pytest.raises(PermissionError, match="BROWSER_PRECONDITION_DRIFT"):
        coord.execute_approved_action(
            proposal,
            live_snapshot=snap_tampered,
            current_amount="$999.99",
            driver_outcome="OK",
        )

    # 2. Timeout after submit enters UNKNOWN / RECONCILING and forbids automatic second click
    res_timeout = coord.execute_approved_action(
        proposal,
        live_snapshot=snap1,
        current_amount="$19.99",
        driver_outcome="TIMEOUT_AFTER_CLICK",
    )
    assert res_timeout.operation_state == "UNKNOWN"
    assert res_timeout.task_state == "RECONCILING"
    assert res_timeout.second_click_permitted is False
    assert res_timeout.page_text_can_clear_unknown is False
