"""Durable schedule triggers producing ordinary QUEUED tasks with misfire coalescing (V1-084)."""

import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

type MisfirePolicy = Literal["COALESCE_SINGLE", "SKIP_MISSED"]


@dataclass(frozen=True, slots=True)
class DurableScheduleSpec:
    schedule_id: str
    owner_id: str
    workspace_id: str
    goal_template: str
    timezone_name: str
    interval_minutes: int
    misfire_policy: MisfirePolicy = "COALESCE_SINGLE"
    next_fire_utc_ms: int = 0
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class TriggeredQueuedTaskReceipt:
    schedule_id: str
    task_id: str
    task_state: Literal["QUEUED"]
    fired_count: int
    coalesced_missed_runs: int
    bypasses_approval_broker: Literal[False] = False


class DurableScheduleTriggerService:
    """Evaluate persistent schedules across DST and sleep windows without burst catch-up."""

    def __init__(self) -> None:
        self._schedules: dict[str, DurableScheduleSpec] = {}

    def register_schedule(self, spec: DurableScheduleSpec) -> DurableScheduleSpec:
        if spec.interval_minutes < 1:
            raise ValueError("interval_minutes must be >= 1")
        # Validate IANA timezone via stdlib zoneinfo
        ZoneInfo(spec.timezone_name)
        self._schedules[spec.schedule_id] = spec
        return spec

    def evaluate_due(
        self, schedule_id: str, *, now_utc_ms: int
    ) -> TriggeredQueuedTaskReceipt | None:
        spec = self._schedules.get(schedule_id)
        if spec is None or not spec.enabled or now_utc_ms < spec.next_fire_utc_ms:
            return None
        step_ms = spec.interval_minutes * 60_000
        missed_intervals = max(0, (now_utc_ms - spec.next_fire_utc_ms) // step_ms)
        next_due = spec.next_fire_utc_ms + (missed_intervals + 1) * step_ms
        self._schedules[schedule_id] = replace(spec, next_fire_utc_ms=next_due)
        if missed_intervals > 0 and spec.misfire_policy == "SKIP_MISSED":
            return None
        return TriggeredQueuedTaskReceipt(
            schedule_id=schedule_id,
            task_id="tsk_cron_" + secrets.token_hex(10),
            task_state="QUEUED",
            fired_count=1,
            coalesced_missed_runs=int(missed_intervals),
            bypasses_approval_broker=False,
        )

    @staticmethod
    def compute_next_local_wall_time_utc_ms(
        *, base_utc_ms: int, timezone_name: str, add_days: int, target_hour: int, target_minute: int
    ) -> int:
        tz = ZoneInfo(timezone_name)
        base_dt = datetime.fromtimestamp(base_utc_ms / 1000.0, tz=tz)
        target_date = (base_dt + timedelta(days=add_days)).date()
        local_dt = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            target_hour,
            target_minute,
            tzinfo=tz,
        )
        return int(local_dt.timestamp() * 1000)
