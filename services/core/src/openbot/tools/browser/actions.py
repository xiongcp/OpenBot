"""Browser write action proposal, pre-dispatch re-verification, and UNKNOWN guard (OB-060)."""

from dataclasses import dataclass
from typing import Literal

from openbot.tools.browser.read import BoundElementRef, BrowserPageSnapshot, BrowserReadTool

type DriverOutcome = Literal["OK", "TIMEOUT_AFTER_CLICK"]


@dataclass(frozen=True, slots=True)
class BrowserActionProposal:
    element_ref: BoundElementRef
    action_kind: Literal["CLICK_SUBMIT", "FILL_INPUT"]
    input_value: str | None
    expected_label: str
    expected_amount: str | None = None


@dataclass(frozen=True, slots=True)
class BrowserActionExecutionResult:
    operation_state: Literal["SUCCEEDED", "UNKNOWN"]
    task_state: Literal["RUNNING", "RECONCILING"]
    second_click_permitted: Literal[False] = False
    page_text_can_clear_unknown: Literal[False] = False


class BrowserActionCoordinator:
    """Re-verify snapshot revision, origin, button label, and amount before browser.act."""

    def __init__(self, read_tool: BrowserReadTool) -> None:
        self._read = read_tool

    def execute_approved_action(
        self,
        proposal: BrowserActionProposal,
        *,
        live_snapshot: BrowserPageSnapshot,
        current_amount: str | None,
        driver_outcome: DriverOutcome,
    ) -> BrowserActionExecutionResult:
        try:
            el = self._read.resolve_element_ref(
                proposal.element_ref, current_snapshot=live_snapshot
            )
        except PermissionError as exc:
            raise PermissionError("BROWSER_PRECONDITION_DRIFT: snapshot or origin changed") from exc

        if el.text != proposal.expected_label or current_amount != proposal.expected_amount:
            raise PermissionError("BROWSER_PRECONDITION_DRIFT: button label or amount changed")

        if driver_outcome == "TIMEOUT_AFTER_CLICK":
            return BrowserActionExecutionResult(
                operation_state="UNKNOWN",
                task_state="RECONCILING",
                second_click_permitted=False,
                page_text_can_clear_unknown=False,
            )
        return BrowserActionExecutionResult(
            operation_state="SUCCEEDED",
            task_state="RUNNING",
            second_click_permitted=False,
            page_text_can_clear_unknown=False,
        )
