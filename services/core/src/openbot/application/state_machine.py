"""CAS task transitions and projections; replay has no execution callback."""

import hashlib
import sqlite3
import time

from openbot.contracts import canonicalize, strict_json
from openbot.storage.inbox import InboundContext, authorize, emit_state
from openbot.storage.writer import LookupResult, RequestConflict, Writer, WriterCommand

_WAITING = frozenset({"QUEUED", "PAUSED", "FAILED", "CANCELLED"})
TRANSITIONS = {
    "QUEUED": frozenset({"RUNNING", "PAUSED", "CANCELLED"}),
    "RUNNING": frozenset(
        {
            "WAITING_APPROVAL",
            "WAITING_INPUT",
            "WAITING_RESOURCE",
            "RECONCILING",
            "PAUSED",
            "SUCCEEDED",
            "PARTIAL",
            "FAILED",
            "CANCELLED",
        }
    ),
    "WAITING_APPROVAL": _WAITING,
    "WAITING_INPUT": _WAITING,
    "WAITING_RESOURCE": _WAITING,
    "RECONCILING": frozenset({"QUEUED", "PARTIAL", "FAILED", "CANCELLED"}),
    "PAUSED": frozenset({"QUEUED", "CANCELLED"}),
    "SUCCEEDED": frozenset(),
    "PARTIAL": frozenset(),
    "FAILED": frozenset(),
    "CANCELLED": frozenset(),
}


class TaskStateService:
    def __init__(self, writer: Writer):
        self._writer = writer

    @staticmethod
    def _task(db: sqlite3.Connection, context: InboundContext, task_id: str) -> tuple[str, int]:
        authorize(db, context)
        row = db.execute(
            "SELECT owner_id,session_id,state,version FROM tasks WHERE task_id=?", (task_id,)
        ).fetchone()
        if not row or row[:2] != (context.principal_id, context.session_id):
            raise PermissionError("Task scope mismatch")
        return str(row[2]), int(row[3])

    def command(
        self,
        context: InboundContext,
        task_id: str,
        expected_version: int,
        target: str,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        if target not in TRANSITIONS or type(expected_version) is not int or expected_version < 0:
            raise ValueError("Unknown task state/version")
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "task": task_id,
                    "expected": expected_version,
                    "target": target,
                    "actor": context.principal_id,
                    "profile": context.profile_id,
                    "session": context.session_id,
                    "identity": context.identity_epoch,
                }
            )
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            self._task(db, context, task_id)
            row = db.execute(
                "SELECT payload_json FROM events WHERE json_extract(payload_json,'$.request_id')=?",
                (request_id,),
            ).fetchone()
            if not row:
                return None
            payload = strict_json(row[0])
            return LookupResult(payload["command_hash"], canonicalize(payload["receipt"]))

        def apply(db: sqlite3.Connection) -> bytes:
            state, version = self._task(db, context, task_id)
            if version != expected_version or target not in TRANSITIONS[state]:
                raise RequestConflict("Task version or transition conflict")
            if target in {"SUCCEEDED", "PARTIAL", "CANCELLED"}:
                raise PermissionError(
                    "Dedicated verified completion/cancellation use case required"
                )
            unknown = db.execute(
                "SELECT 1 FROM operations WHERE task_id=? AND state IN ('UNKNOWN','DISPATCHING')",
                (task_id,),
            ).fetchone()
            if unknown and (target in {"SUCCEEDED", "CANCELLED"} or state == "RECONCILING"):
                raise PermissionError("Unresolved external effect blocks this transition")
            if state == "RECONCILING" and target == "QUEUED":
                raise PermissionError(
                    "Only the verified recovery use case may resume reconciliation"
                )
            now = time.time_ns() // 1_000_000
            terminal = target in {"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"}
            cursor = db.execute(
                "UPDATE tasks SET state=?,version=version+1,updated_at=?,finished_at=? "
                "WHERE task_id=? AND version=?",
                (target, now, now if terminal else None, task_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise RequestConflict("Task version changed")
            receipt: dict[str, str | int] = {
                "task_id": task_id,
                "state": target,
                "version": version + 1,
            }
            emit_state(db, context, receipt, request_id, fingerprint, "TASK_STATE_CHANGED", now)
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "normal", deadline_monotonic_ms, apply, lookup
        )

    def snapshot(self, context: InboundContext, task_id: str) -> dict[str, object]:
        def query(db: sqlite3.Connection) -> dict[str, object]:
            state, version = self._task(db, context, task_id)
            return {"task_id": task_id, "state": state, "version": version}

        return self._writer.read(query)

    def replay(self, context: InboundContext, task_id: str) -> list[dict[str, object]]:
        def query(db: sqlite3.Connection) -> list[dict[str, object]]:
            self._task(db, context, task_id)
            result: list[dict[str, object]] = []
            for row in db.execute(
                "SELECT seq,event_type,aggregate_version FROM events "
                "WHERE task_id=? ORDER BY seq LIMIT 1000",
                (task_id,),
            ):
                result.append({"seq": row[0], "event_type": row[1], "version": row[2]})
            return result

        return self._writer.read(query)
