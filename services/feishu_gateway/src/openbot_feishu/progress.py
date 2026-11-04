"""Monotonic card revision, progress coalescing, retry_after, and terminal guard (OB-052)."""

from dataclasses import dataclass

_TERMINAL_STATES = frozenset({"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"})


@dataclass(frozen=True, slots=True)
class CoalescedProgressUpdate:
    task_id: str
    card_revision: int
    state: str
    summary: str
    coalesced_count: int


@dataclass
class _TaskProgressSlot:
    card_revision: int = 0
    state: str = "QUEUED"
    summary: str = ""
    coalesced_count: int = 0
    dirty: bool = False
    next_allowed_ms: int = 0
    terminal_locked: bool = False


class FeishuProgressCardCoordinator:
    """Coalesce intermediate progress updates, protect terminal state, and honor retry_after."""

    def __init__(self, *, min_interval_ms: int = 500) -> None:
        self._min_interval_ms = max(0, min_interval_ms)
        self._slots: dict[str, _TaskProgressSlot] = {}

    def record_update(self, *, task_id: str, state: str, summary: str, now_ms: int) -> None:
        slot = self._slots.setdefault(task_id, _TaskProgressSlot())
        # Late non-terminal updates NEVER overwrite an already-recorded terminal state
        if slot.terminal_locked and state not in _TERMINAL_STATES:
            return
        if slot.dirty:
            slot.coalesced_count += 1
        slot.card_revision += 1
        slot.state = state
        slot.summary = summary
        slot.dirty = True
        if state in _TERMINAL_STATES:
            slot.terminal_locked = True
            slot.next_allowed_ms = min(slot.next_allowed_ms, now_ms)

    def on_rate_limited(self, *, task_id: str, retry_after_ms: int, now_ms: int) -> None:
        slot = self._slots.setdefault(task_id, _TaskProgressSlot())
        slot.next_allowed_ms = max(slot.next_allowed_ms, now_ms + max(0, retry_after_ms))

    def drain_due(self, *, now_ms: int) -> tuple[CoalescedProgressUpdate, ...]:
        out: list[CoalescedProgressUpdate] = []
        for task_id, slot in sorted(self._slots.items()):
            if not slot.dirty:
                continue
            if not slot.terminal_locked and now_ms < slot.next_allowed_ms:
                continue
            out.append(
                CoalescedProgressUpdate(
                    task_id=task_id,
                    card_revision=slot.card_revision,
                    state=slot.state,
                    summary=slot.summary,
                    coalesced_count=slot.coalesced_count,
                )
            )
            slot.dirty = False
            slot.coalesced_count = 0
            slot.next_allowed_ms = now_ms + self._min_interval_ms
        return tuple(out)
