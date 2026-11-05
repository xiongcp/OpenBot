"""Durable task cancellation, grant revocation, and worker stop propagation."""

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from openbot.application.state_machine import TRANSITIONS
from openbot.contracts import canonicalize, strict_json
from openbot.storage.inbox import InboundContext, authorize, emit_state
from openbot.storage.writer import LookupResult, RequestConflict, Writer, WriterCommand


@dataclass(frozen=True, slots=True)
class WorkerStopAck:
    """Stopping a worker never rolls back an already-dispatched external side effect."""

    stop_signal_sent: bool
    detail: str
    effect_rolled_back: Literal[False] = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "stop_signal_sent": self.stop_signal_sent,
            "detail": self.detail,
            "effect_rolled_back": False,
        }


class WorkerStopPort(Protocol):
    """Port for propagating stop signals to running workers outside SQLite transactions."""

    def request_stop(
        self,
        *,
        task_id: str,
        operation_id: str,
        attempt_id: str,
        dispatch_id: str,
        executor_id: str,
        cancel_revision: int,
    ) -> WorkerStopAck: ...


def _release_claimed_leases(db: sqlite3.Connection, task_id: str, now: int) -> None:
    claimed_attempts = [
        str(r[0])
        for r in db.execute(
            "SELECT attempt_id FROM operation_attempts "
            "WHERE operation_id IN (SELECT operation_id FROM operations WHERE task_id=?) "
            "AND status='CLAIMED'",
            (task_id,),
        ).fetchall()
    ]
    for att_id in claimed_attempts:
        db.execute(
            "UPDATE resource_leases SET holder_attempt_id=NULL,runtime_epoch=NULL,"
            "state='RELEASED',acquired_at=NULL,expires_at=NULL,version=version+1,updated_at=? "
            "WHERE holder_attempt_id=? AND state='HELD'",
            (now, att_id),
        )


class CancellationService:
    """Persist cancellation first, revoke undispatched grants, and propagate stop signals."""

    def __init__(self, writer: Writer) -> None:
        self._writer = writer

    def _task_row(
        self, db: sqlite3.Connection, context: InboundContext, task_id: str
    ) -> tuple[str, int, int, int | None]:
        authorize(db, context)
        row = db.execute(
            "SELECT owner_id,session_id,state,version,cancel_revision,cancel_requested_at "
            "FROM tasks WHERE task_id=?",
            (task_id,),
        ).fetchone()
        if not row or row[:2] != (context.principal_id, context.session_id):
            raise PermissionError("Task does not belong to this owner or session")
        return (
            str(row[2]),
            int(row[3]),
            int(row[4]),
            None if row[5] is None else int(row[5]),
        )

    def _lookup(
        self, db: sqlite3.Connection, context: InboundContext, task_id: str, request_id: str
    ) -> LookupResult | None:
        self._task_row(db, context, task_id)
        row = db.execute(
            "SELECT payload_json FROM events WHERE task_id=? "
            "AND json_extract(payload_json,'$.request_id')=?",
            (task_id, request_id),
        ).fetchone()
        if row is None:
            return None
        value = strict_json(str(row[0]))
        return LookupResult(str(value["command_hash"]), canonicalize(value["receipt"]))

    def request_cancel(
        self,
        context: InboundContext,
        task_id: str,
        expected_version: int,
        *,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("Invalid expected_version")
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "request_cancel",
                    "task": task_id,
                    "expected": expected_version,
                    "actor": context.principal_id,
                    "profile": context.profile_id,
                    "session": context.session_id,
                    "identity": context.identity_epoch,
                    "surface": context.source_scope,
                }
            )
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return self._lookup(db, context, task_id, request_id)

        def apply(db: sqlite3.Connection) -> bytes:
            state, version, cancel_rev, cancel_req_at = self._task_row(db, context, task_id)
            if version != expected_version or "CANCELLED" not in TRANSITIONS[state]:
                raise RequestConflict("Task version or cancel transition conflict")
            now = time.time_ns() // 1_000_000

            # 1. Release leases held by undispatched CLAIMED attempts before cancelling them
            _release_claimed_leases(db, task_id, now)

            # 2. Revoke unconsumed approvals (CONSUMED approvals are never modified or revived)
            db.execute(
                "UPDATE approvals SET status='REVOKED',version=version+1 "
                "WHERE operation_id IN (SELECT operation_id FROM operations WHERE task_id=?) "
                "AND status IN ('PENDING','APPROVED')",
                (task_id,),
            )
            # 3. Cancel undispatched CLAIMED attempts and undispatched operations
            db.execute(
                "UPDATE operation_attempts SET status='CANCELLED',version=version+1,finished_at=? "
                "WHERE operation_id IN (SELECT operation_id FROM operations WHERE task_id=?) "
                "AND status='CLAIMED'",
                (now, task_id),
            )
            db.execute(
                "UPDATE operations SET state='CANCELLED',version=version+1,updated_at=?,"
                "completed_at=? WHERE task_id=? "
                "AND state IN ('PROPOSED','AWAITING_APPROVAL','READY','CLAIMED')",
                (now, now, task_id),
            )

            # 4. Inspect in-flight DISPATCHING/UNKNOWN and already SUCCEEDED operations
            in_flight_rows = db.execute(
                "SELECT o.operation_id,a.attempt_id,a.dispatch_id,a.executor_id "
                "FROM operations o JOIN operation_attempts a ON a.attempt_id=o.current_attempt_id "
                "WHERE o.task_id=? AND o.state='DISPATCHING' AND a.status='DISPATCHING' "
                "ORDER BY o.ordinal",
                (task_id,),
            ).fetchall()
            in_flight = [
                {
                    "operation_id": str(r[0]),
                    "attempt_id": str(r[1]),
                    "dispatch_id": str(r[2]),
                    "executor_id": str(r[3]),
                }
                for r in in_flight_rows
            ]
            preserved_succeeded = [
                str(r[0])
                for r in db.execute(
                    "SELECT operation_id FROM operations WHERE task_id=? AND state='SUCCEEDED' "
                    "ORDER BY ordinal",
                    (task_id,),
                ).fetchall()
            ]
            unresolved = db.execute(
                "SELECT 1 FROM operations WHERE task_id=? AND state IN ('UNKNOWN','DISPATCHING')",
                (task_id,),
            ).fetchone()
            if unresolved is not None:
                if state != "RECONCILING" and "RECONCILING" not in TRANSITIONS[state]:
                    raise PermissionError("Unresolved external effect blocks cancellation")
                target = "RECONCILING"
                finished_at: int | None = None
                event_type = "TASK_STATE_CHANGED"
            else:
                target = "CANCELLED"
                finished_at = now
                event_type = "TASK_FINISHED"

            new_cancel_rev = cancel_rev + 1
            req_at = cancel_req_at if cancel_req_at is not None else now
            cursor = db.execute(
                "UPDATE tasks SET state=?,version=version+1,cancel_revision=?,"
                "cancel_requested_at=?,updated_at=?,finished_at=? WHERE task_id=? AND version=?",
                (target, new_cancel_rev, req_at, now, finished_at, task_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise RequestConflict("Task version changed")

            receipt: dict[str, Any] = {
                "task_id": task_id,
                "state": target,
                "version": version + 1,
                "cancel_revision": new_cancel_rev,
                "cancel_requested_at_ms": req_at,
                "effects_rolled_back": False,
                "preserved_succeeded_operations": preserved_succeeded,
                "in_flight_attempts": in_flight,
            }
            emit_state(db, context, receipt, request_id, fingerprint, event_type, now)
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "cancel", deadline_monotonic_ms, apply, lookup
        )

    def propagate_cancel(
        self,
        context: InboundContext,
        task_id: str,
        *,
        expected_version: int,
        worker_port: WorkerStopPort | None = None,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> dict[str, Any]:
        # 1. Persist cancellation first in short transaction; never report success before commit
        raw = self._writer.submit(
            self.request_cancel(
                context,
                task_id,
                expected_version,
                request_id=request_id,
                deadline_monotonic_ms=deadline_monotonic_ms,
            )
        ).result(
            timeout=min(
                300.0, max(0.001, (deadline_monotonic_ms - time.monotonic() * 1000) / 1000 + 0.05)
            )
        )
        committed = dict(strict_json(raw))

        # 2. Propagate stop signals to running workers outside SQLite transaction
        stop_acks: list[dict[str, Any]] = []
        if worker_port is not None:
            for item in committed.get("in_flight_attempts", []):
                ack = worker_port.request_stop(
                    task_id=task_id,
                    operation_id=str(item["operation_id"]),
                    attempt_id=str(item["attempt_id"]),
                    dispatch_id=str(item["dispatch_id"]),
                    executor_id=str(item["executor_id"]),
                    cancel_revision=int(committed["cancel_revision"]),
                )
                stop_acks.append(ack.to_payload())
        committed["worker_stop_signals"] = stop_acks
        return committed

    def finalize_cancelled(
        self,
        context: InboundContext,
        task_id: str,
        *,
        expected_version: int,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("Invalid expected_version")
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "finalize_cancelled",
                    "task": task_id,
                    "expected": expected_version,
                    "actor": context.principal_id,
                    "profile": context.profile_id,
                    "session": context.session_id,
                    "identity": context.identity_epoch,
                    "surface": context.source_scope,
                }
            )
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return self._lookup(db, context, task_id, request_id)

        def apply(db: sqlite3.Connection) -> bytes:
            state, version, cancel_rev, cancel_req_at = self._task_row(db, context, task_id)
            if version != expected_version or state != "RECONCILING":
                raise RequestConflict("Task is not in RECONCILING at expected_version")
            if cancel_rev < 1 or cancel_req_at is None:
                raise PermissionError("Task has no persisted cancellation request")
            unresolved = db.execute(
                "SELECT 1 FROM operations WHERE task_id=? AND ("
                "state IN ('PROPOSED','AWAITING_APPROVAL','READY','CLAIMED',"
                "'DISPATCHING','UNKNOWN') "
                "OR (unknown_reason IS NOT NULL AND resolution_evidence_ref IS NULL))",
                (task_id,),
            ).fetchone()
            if unresolved is not None:
                raise PermissionError(
                    "Cannot finalize CANCELLED while DISPATCHING or UNKNOWN operations remain"
                )
            preserved_succeeded = [
                str(r[0])
                for r in db.execute(
                    "SELECT operation_id FROM operations WHERE task_id=? AND state='SUCCEEDED' "
                    "ORDER BY ordinal",
                    (task_id,),
                ).fetchall()
            ]
            now = time.time_ns() // 1_000_000
            cursor = db.execute(
                "UPDATE tasks SET state='CANCELLED',version=version+1,updated_at=?,finished_at=? "
                "WHERE task_id=? AND version=? AND state='RECONCILING'",
                (now, now, task_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise RequestConflict("Task version changed")
            receipt: dict[str, Any] = {
                "task_id": task_id,
                "state": "CANCELLED",
                "version": version + 1,
                "cancel_revision": cancel_rev,
                "cancel_requested_at_ms": cancel_req_at,
                "effects_rolled_back": False,
                "preserved_succeeded_operations": preserved_succeeded,
            }
            emit_state(db, context, receipt, request_id, fingerprint, "TASK_FINISHED", now)
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "cancel", deadline_monotonic_ms, apply, lookup
        )

    def inspect_cancel_status(self, context: InboundContext, task_id: str) -> dict[str, object]:
        def query(db: sqlite3.Connection) -> dict[str, object]:
            state, version, cancel_rev, cancel_req_at = self._task_row(db, context, task_id)
            unresolved = [
                str(r[0])
                for r in db.execute(
                    "SELECT operation_id FROM operations WHERE task_id=? "
                    "AND state IN ('DISPATCHING','UNKNOWN') ORDER BY ordinal",
                    (task_id,),
                ).fetchall()
            ]
            preserved = [
                str(r[0])
                for r in db.execute(
                    "SELECT operation_id FROM operations WHERE task_id=? "
                    "AND state='SUCCEEDED' ORDER BY ordinal",
                    (task_id,),
                ).fetchall()
            ]
            return {
                "task_id": task_id,
                "state": state,
                "version": version,
                "cancel_revision": cancel_rev,
                "cancel_requested_at_ms": cancel_req_at,
                "unresolved_operation_ids": unresolved,
                "preserved_succeeded_operations": preserved,
                "effects_rolled_back": False,
            }

        return self._writer.read(query)
