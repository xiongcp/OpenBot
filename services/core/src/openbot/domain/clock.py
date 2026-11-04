"""UTC is persistent; monotonic time and boot identity constrain process TTLs."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClockSnapshot:
    utc_ms: int
    monotonic_ms: int
    boot_id: str


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
