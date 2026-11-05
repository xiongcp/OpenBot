"""Three-state adaptive circuit breaker (CLOSED/OPEN/HALF_OPEN) and step checkpoint resume."""

from dataclasses import dataclass
from typing import Any, Literal

type BreakerState = Literal["CLOSED", "OPEN", "HALF_OPEN"]


@dataclass(frozen=True, slots=True)
class BreakerSnapshot:
    surface_id: str
    state: BreakerState
    consecutive_failures: int
    reopen_not_before_ms: int


class AdaptiveCircuitBreaker:
    """Protect model gateways, Feishu, and executors from retry storms (V1-072)."""

    def __init__(
        self,
        surface_id: str,
        *,
        failure_threshold: int = 3,
        default_cooldown_ms: int = 15_000,
    ) -> None:
        self._surface = surface_id
        self._threshold = max(1, failure_threshold)
        self._cooldown_ms = max(100, default_cooldown_ms)
        self._state: BreakerState = "CLOSED"
        self._failures = 0
        self._not_before_ms = 0

    def allow_request(self, *, now_ms: int) -> BreakerSnapshot:
        if self._state == "OPEN":
            if now_ms >= self._not_before_ms:
                self._state = "HALF_OPEN"
            else:
                raise PermissionError(
                    f"CIRCUIT_BREAKER_OPEN: {self._surface} until {self._not_before_ms}"
                )
        return self.snapshot()

    def record_success(self) -> BreakerSnapshot:
        self._failures = 0
        self._state = "CLOSED"
        self._not_before_ms = 0
        return self.snapshot()

    def record_failure(
        self, *, now_ms: int, retry_after_seconds: int | None = None
    ) -> BreakerSnapshot:
        self._failures += 1
        wait_ms = (
            retry_after_seconds * 1000
            if retry_after_seconds is not None and retry_after_seconds > 0
            else self._cooldown_ms
        )
        if self._state == "HALF_OPEN" or self._failures >= self._threshold:
            self._state = "OPEN"
            self._not_before_ms = now_ms + wait_ms
        return self.snapshot()

    def snapshot(self) -> BreakerSnapshot:
        return BreakerSnapshot(
            surface_id=self._surface,
            state=self._state,
            consecutive_failures=self._failures,
            reopen_not_before_ms=self._not_before_ms,
        )


class StepCheckpointResumer:
    """Resume an interrupted task from step N without re-running completed steps 0..N-1 (V1-072)."""

    def __init__(self) -> None:
        self._completed_by_task: dict[str, list[dict[str, Any]]] = {}

    def record_completed_step(
        self, task_id: str, *, step_index: int, receipt: dict[str, Any]
    ) -> None:
        steps = self._completed_by_task.setdefault(task_id, [])
        if any(s["step_index"] == step_index for s in steps):
            return
        steps.append({"step_index": step_index, "receipt": dict(receipt)})

    def next_resume_step(self, task_id: str) -> int:
        steps = self._completed_by_task.get(task_id, [])
        if not steps:
            return 0
        return max(int(s["step_index"]) for s in steps) + 1
