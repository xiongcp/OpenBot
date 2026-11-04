import pytest
from openbot_feishu.health import (
    ExternalGatewaySupervisor,
    GatewayStageDeadlines,
    compute_jittered_backoff_ms,
)


def test_feishu_gateway_health_allows_idle_business_traffic_and_prevents_dual_consumers() -> None:
    sup = ExternalGatewaySupervisor(
        deadlines=GatewayStageDeadlines(
            init_ms=3000,
            discovery_ms=3000,
            handshake_ms=5000,
            heartbeat_timeout_ms=15_000,
        )
    )
    inst1 = sup.spawn_consumer(consumer_id="gw_1", pid=4001, now_ms=1000)
    assert inst1.active is True
    assert sup.in_loop_wait_for_claimed_as_hard_kill is False

    # 1. Idle business traffic (no messages for 1 hour) is HEALTHY while heartbeat is fresh
    sup.record_transport_heartbeat(consumer_id="gw_1", now_ms=3_600_000)
    probe_idle = sup.evaluate_health(
        consumer_id="gw_1", now_ms=3_605_000, last_business_msg_ms=1000
    )
    assert probe_idle.healthy is True
    assert probe_idle.reason == "IDLE_BUT_HEARTBEAT_FRESH"

    # 2. Cannot spawn a second consumer while old consumer is not confirmed exited
    with pytest.raises(PermissionError, match="OLD_CONSUMER_NOT_CONFIRMED_EXITED"):
        sup.spawn_consumer(consumer_id="gw_2", pid=4002, now_ms=3_606_000)

    # 3. After heartbeat timeout / TCP half-open, terminate & confirm old exit, then spawn gw_2
    probe_dead = sup.evaluate_health(
        consumer_id="gw_1", now_ms=3_625_000, last_business_msg_ms=1000
    )
    assert probe_dead.healthy is False
    assert probe_dead.reason == "HEARTBEAT_TIMEOUT_OR_HALF_OPEN"

    sup.confirm_consumer_exited(consumer_id="gw_1", now_ms=3_625_100)
    inst2 = sup.spawn_consumer(consumer_id="gw_2", pid=4002, now_ms=3_625_500)
    assert inst2.active is True
    assert sup.active_consumer_count() == 1

    # 4. Bounded jittered backoff is deterministic with seed and bounded by max_backoff_ms
    b1 = compute_jittered_backoff_ms(attempt=3, base_ms=500, max_ms=5000, jitter_ratio=0.2, seed=7)
    assert 1600 <= b1 <= 2400
