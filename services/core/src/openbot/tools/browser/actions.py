"""Browser write action proposal, pre-dispatch re-verification, and UNKNOWN guard (OB-060)."""

import hashlib
import html
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from openbot.tools.browser.read import BoundElementRef, BrowserPageSnapshot, BrowserReadTool

type DriverOutcome = Literal["OK", "TIMEOUT_AFTER_CLICK"]
type BrowserPrimitiveKind = Literal["CLICK_SUBMIT", "FILL_INPUT", "SELECT_OPTION", "PRESS_KEY"]


@dataclass(frozen=True, slots=True)
class BrowserActionProposal:
    element_ref: BoundElementRef
    action_kind: BrowserPrimitiveKind
    input_value: str | None
    expected_label: str
    expected_amount: str | None = None


@dataclass(frozen=True, slots=True)
class BrowserHighlightPreview:
    element_index: int
    target_label: str
    expected_amount: str | None
    final_origin: str
    svg_bytes: bytes
    sha256: str


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

    def build_target_highlight_preview(
        self, proposal: BrowserActionProposal, *, snapshot: BrowserPageSnapshot
    ) -> BrowserHighlightPreview:
        el = self._read.resolve_element_ref(proposal.element_ref, current_snapshot=snapshot)
        safe_label = html.escape(el.text)
        safe_origin = html.escape(snapshot.final_origin)
        safe_amt = html.escape(proposal.expected_amount or "N/A")
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="480" height="160">'
            '<rect width="480" height="160" fill="#f7f8f5"/>'
            f'<text x="16" y="32" font-size="13" fill="#142d25">Origin: {safe_origin}</text>'
            '<rect x="16" y="52" width="448" height="76" fill="none" '
            'stroke="#d92d20" stroke-width="3" rx="6"/>'
            f'<text x="28" y="86" font-size="15" font-weight="bold" fill="#142d25">'
            f"Target [{el.tag}#{el.ref.element_index}]: {safe_label}</text>"
            f'<text x="28" y="112" font-size="13" fill="#b42318">Amount: {safe_amt}</text>'
            "</svg>"
        ).encode()
        return BrowserHighlightPreview(
            element_index=el.ref.element_index,
            target_label=el.text,
            expected_amount=proposal.expected_amount,
            final_origin=snapshot.final_origin,
            svg_bytes=svg,
            sha256=hashlib.sha256(svg).hexdigest(),
        )

    def execute_approved_action(
        self,
        proposal: BrowserActionProposal,
        *,
        live_snapshot: BrowserPageSnapshot,
        current_amount: str | None,
        driver_outcome: DriverOutcome = "OK",
        live_driver: Callable[[BrowserActionProposal], dict[str, Any]] | None = None,
    ) -> BrowserActionExecutionResult:
        try:
            el = self._read.resolve_element_ref(
                proposal.element_ref, current_snapshot=live_snapshot
            )
        except PermissionError as exc:
            raise PermissionError("BROWSER_PRECONDITION_DRIFT: snapshot or origin changed") from exc

        if el.text != proposal.expected_label or current_amount != proposal.expected_amount:
            raise PermissionError("BROWSER_PRECONDITION_DRIFT: button label or amount changed")

        if live_driver is not None:
            try:
                receipt = live_driver(proposal)
                if not receipt.get("verified_effect"):
                    return BrowserActionExecutionResult(
                        operation_state="UNKNOWN",
                        task_state="RECONCILING",
                        second_click_permitted=False,
                        page_text_can_clear_unknown=False,
                    )
            except (TimeoutError, ConnectionError, OSError):
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
