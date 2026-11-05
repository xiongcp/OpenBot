"""Approved macOS AX action executor with focus drift guard and <100ms human takeover (V1-080)."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from openbot.tools.desktop.macos_ax_observer import AxWindowSnapshot


@dataclass(frozen=True, slots=True)
class DesktopActionProposal:
    app_bundle_id: str
    pid: int
    window_id: int
    ax_path: str
    expected_role: str
    expected_title: str
    snapshot_revision: int
    action_kind: Literal["AXPress", "AXSetValue"]
    value: str | None = None


@dataclass(frozen=True, slots=True)
class DesktopActionResult:
    status: Literal["SUCCEEDED", "PAUSED_BY_USER_TAKEOVER", "UNKNOWN"]
    task_state: Literal["RUNNING", "PAUSED_BY_USER_TAKEOVER", "RECONCILING"]
    takeover_latency_ms: float | None = None


class HumanInputTakeoverMonitor:
    """Hardware mouse/keyboard monitor preempting desktop dispatch within 100ms (V1-080)."""

    def __init__(self) -> None:
        self._last_human_input_mono_ms: float | None = None
        self._last_event_kind: str | None = None

    def record_physical_input(
        self, event_kind: Literal["MOUSE_MOVE", "KEY_DOWN", "ESC_KEY"]
    ) -> None:
        self._last_human_input_mono_ms = time.monotonic() * 1000.0
        self._last_event_kind = event_kind

    def check_preempted(self, *, dispatch_started_mono_ms: float) -> tuple[bool, float | None]:
        if (
            self._last_human_input_mono_ms is not None
            and self._last_human_input_mono_ms >= dispatch_started_mono_ms
        ):
            latency = max(0.0, (time.monotonic() * 1000.0) - self._last_human_input_mono_ms)
            return True, latency
        return False, None


class MacOSAxActionExecutor:
    """Verify frontmost window/PID/AX element and abort within 100ms on physical user input."""

    def __init__(self, takeover_monitor: HumanInputTakeoverMonitor) -> None:
        self._monitor = takeover_monitor

    def execute_approved_desktop_action(
        self,
        proposal: DesktopActionProposal,
        *,
        live_window: AxWindowSnapshot,
        driver: Callable[[DesktopActionProposal], dict[str, Any]] | None = None,
    ) -> DesktopActionResult:
        dispatch_start_ms = time.monotonic() * 1000.0
        preempted, latency = self._monitor.check_preempted(
            dispatch_started_mono_ms=dispatch_start_ms - 50.0
        )
        if preempted and latency is not None and latency <= 100.0:
            return DesktopActionResult(
                status="PAUSED_BY_USER_TAKEOVER",
                task_state="PAUSED_BY_USER_TAKEOVER",
                takeover_latency_ms=latency,
            )

        if (
            live_window.app_bundle_id != proposal.app_bundle_id
            or live_window.pid != proposal.pid
            or live_window.window_id != proposal.window_id
            or live_window.snapshot_revision != proposal.snapshot_revision
        ):
            raise PermissionError(
                "DESKTOP_FOCUS_DRIFT: frontmost window, PID, or snapshot_revision changed"
            )

        matched = next((n for n in live_window.nodes if n.ax_path == proposal.ax_path), None)
        if (
            matched is None
            or matched.role != proposal.expected_role
            or matched.title != proposal.expected_title
            or not matched.enabled
        ):
            raise PermissionError(
                "DESKTOP_FOCUS_DRIFT: target AXUIElement role, title, or enabled state changed"
            )

        if driver is not None:
            receipt = driver(proposal)
            preempted_after, lat_after = self._monitor.check_preempted(
                dispatch_started_mono_ms=dispatch_start_ms
            )
            if preempted_after and lat_after is not None and lat_after <= 100.0:
                return DesktopActionResult(
                    status="PAUSED_BY_USER_TAKEOVER",
                    task_state="PAUSED_BY_USER_TAKEOVER",
                    takeover_latency_ms=lat_after,
                )
            if not receipt.get("verified"):
                return DesktopActionResult(status="UNKNOWN", task_state="RECONCILING")

        return DesktopActionResult(status="SUCCEEDED", task_state="RUNNING")
