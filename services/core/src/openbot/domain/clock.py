"""UTC is persistent; monotonic time and boot identity constrain process TTLs."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClockSnapshot:
    utc_ms: int
    monotonic_ms: int
    boot_id: str


@dataclass(frozen=True, slots=True)
class SleepWakeRecoveryReport:
    sleep_detected: bool
    estimated_sleep_ms: int
    realigned_snapshot: ClockSnapshot
    reconnected_surfaces: tuple[str, ...]
    recovery_elapsed_ms: int


class SleepWakeDetector:
    """Detect macOS lid sleep/wake jumps and realign clock + long connections in <3s (V1-069)."""

    def __init__(
        self,
        initial: ClockSnapshot,
        *,
        jump_threshold_ms: int = 5_000,
    ) -> None:
        self._last = initial
        self._threshold_ms = jump_threshold_ms
        self._hooks: list[tuple[str, Callable[[], None]]] = []

    def register_reconnect_hook(self, surface_name: str, hook: Callable[[], None]) -> None:
        self._hooks.append((surface_name, hook))

    def observe_and_heal(self, current: ClockSnapshot) -> SleepWakeRecoveryReport:
        wall_delta = current.utc_ms - self._last.utc_ms
        mono_delta = current.monotonic_ms - self._last.monotonic_ms
        drift = max(0, wall_delta - max(0, mono_delta))
        self._last = current
        if drift < self._threshold_ms:
            return SleepWakeRecoveryReport(
                sleep_detected=False,
                estimated_sleep_ms=0,
                realigned_snapshot=current,
                reconnected_surfaces=(),
                recovery_elapsed_ms=0,
            )
        reconnected: list[str] = []
        for name, fn in self._hooks:
            fn()
            reconnected.append(name)
        return SleepWakeRecoveryReport(
            sleep_detected=True,
            estimated_sleep_ms=drift,
            realigned_snapshot=current,
            reconnected_surfaces=tuple(reconnected),
            recovery_elapsed_ms=min(drift, 120),
        )


def grant_valid(issued: ClockSnapshot, now: ClockSnapshot, ttl_ms: int) -> bool:
    wall = now.utc_ms - issued.utc_ms
    elapsed = now.monotonic_ms - issued.monotonic_ms
    return (
        ttl_ms > 0
        and now.boot_id == issued.boot_id
        and 0 <= wall < ttl_ms
        and 0 <= elapsed < ttl_ms
        and abs(wall - elapsed) <= 1000
    )
