"""External gateway health watchdog, single-consumer guard, and jittered backoff (OB-054)."""

import random
from dataclasses import dataclass
from typing import Literal


def compute_jittered_backoff_ms(
    *, attempt: int, base_ms: int, max_ms: int, jitter_ratio: float = 0.2, seed: int | None = None
) -> int:
    raw = min(max_ms, base_ms * (2 ** max(0, attempt - 1)))
    rng = random.Random(seed)
    delta = raw * max(0.0, min(0.5, jitter_ratio))
    jittered = raw + rng.uniform(-delta, delta)
    return max(1, min(max_ms, int(round(jittered))))


@dataclass(frozen=True, slots=True)
class GatewayStageDeadlines:
    init_ms: int = 3000
    discovery_ms: int = 3000
    handshake_ms: int = 5000
    heartbeat_timeout_ms: int = 15_000


@dataclass
class GatewayConsumerInstance:
    consumer_id: str
    pid: int
    started_ms: int
    last_heartbeat_ms: int
    active: bool = True
    exited_ms: int | None = None


@dataclass(frozen=True, slots=True)
class HealthProbeOutcome:
    consumer_id: str
    healthy: bool
    reason: str
    blocks_daemon_writer: Literal[False] = False


class ExternalGatewaySupervisor:
    """Supervise gateway outside the SDK loop; forbid dual consumers and idle false-positives."""

    in_loop_wait_for_claimed_as_hard_kill: Literal[False] = False

    def __init__(self, *, deadlines: GatewayStageDeadlines) -> None:
        self._deadlines = deadlines
        self._instances: dict[str, GatewayConsumerInstance] = {}

    def active_consumer_count(self) -> int:
        return sum(1 for inst in self._instances.values() if inst.active)

    def spawn_consumer(self, *, consumer_id: str, pid: int, now_ms: int) -> GatewayConsumerInstance:
        if self.active_consumer_count() > 0:
            raise PermissionError("OLD_CONSUMER_NOT_CONFIRMED_EXITED")
        inst = GatewayConsumerInstance(
            consumer_id=consumer_id,
            pid=pid,
            started_ms=now_ms,
            last_heartbeat_ms=now_ms,
            active=True,
        )
        self._instances[consumer_id] = inst
        return inst

    def record_transport_heartbeat(self, *, consumer_id: str, now_ms: int) -> None:
        inst = self._instances[consumer_id]
        inst.last_heartbeat_ms = now_ms

    def evaluate_health(
        self, *, consumer_id: str, now_ms: int, last_business_msg_ms: int
    ) -> HealthProbeOutcome:
        del last_business_msg_ms  # Idle business traffic is NEVER treated as disconnect!
        inst = self._instances[consumer_id]
        if not inst.active:
            return HealthProbeOutcome(consumer_id, False, "CONSUMER_EXITED")
        if now_ms - inst.last_heartbeat_ms > self._deadlines.heartbeat_timeout_ms:
            return HealthProbeOutcome(consumer_id, False, "HEARTBEAT_TIMEOUT_OR_HALF_OPEN")
        return HealthProbeOutcome(consumer_id, True, "IDLE_BUT_HEARTBEAT_FRESH")

    def confirm_consumer_exited(self, *, consumer_id: str, now_ms: int) -> None:
        inst = self._instances[consumer_id]
        inst.active = False
        inst.exited_ms = now_ms
