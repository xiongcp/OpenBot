"""Dead-letter inspection and notification redelivery without UNKNOWN replay (OB-055)."""

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from openbot.contracts import canonicalize, strict_json
from openbot.storage.inbox import InboundContext, authorize
from openbot.storage.writer import LookupResult, RequestConflict, Writer, WriterCommand


@dataclass(frozen=True, slots=True)
class DeadLetterRecord:
    outbox_id: str
    task_id: str | None
    delivery_class: str
    state: str
    attempt_count: int
    error_code: str | None


class DeadLetterInspectorService:
    """Inspect, discard, or redeliver DEAD notifications; never replay UNKNOWN side effects."""

    def __init__(self, writer: Writer) -> None:
        self._writer = writer

    def list_dead_letters(self, context: InboundContext) -> tuple[DeadLetterRecord, ...]:
        def query(db: sqlite3.Connection) -> tuple[DeadLetterRecord, ...]:
            authorize(db, context)
            rows = db.execute(
                "SELECT outbox_id,task_id,delivery_class,state,attempt_count,error_code "
                "FROM outbox WHERE state IN ('DEAD','EXPIRED') ORDER BY updated_at,outbox_id"
            ).fetchall()
            return tuple(
                DeadLetterRecord(
                    outbox_id=str(r[0]),
                    task_id=None if r[1] is None else str(r[1]),
                    delivery_class=str(r[2]),
                    state=str(r[3]),
                    attempt_count=int(r[4]),
                    error_code=None if r[5] is None else str(r[5]),
                )
                for r in rows
            )

        return self._writer.read(query)

    def redeliver_notification(
        self,
        context: InboundContext,
        *,
        outbox_id: str,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> dict[str, Any]:
        fp = hashlib.sha256(
            canonicalize({"kind": "dlq_redeliver", "id": outbox_id, "req": request_id})
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return None

        def apply(db: sqlite3.Connection) -> bytes:
            authorize(db, context)
            row = db.execute(
                "SELECT state,delivery_class,version FROM outbox WHERE outbox_id=?",
                (outbox_id,),
            ).fetchone()
            if not row:
                raise RequestConflict("Dead letter record not found")
            state, d_class, ver = str(row[0]), str(row[1]), int(row[2])
            if state == "UNKNOWN" or d_class == "RECONCILE_ONLY":
                raise PermissionError("UNKNOWN_REQUIRES_RECONCILE")
            if state not in {"DEAD", "EXPIRED"}:
                raise RequestConflict("Record is not in DEAD or EXPIRED state")
            now = time.time_ns() // 1_000_000
            db.execute(
                "UPDATE outbox SET state='PENDING',attempt_count=0,not_before=?,"
                "error_code=NULL,version=version+1,updated_at=? "
                "WHERE outbox_id=? AND version=?",
                (now, now, outbox_id, ver),
            )
            return canonicalize(
                {
                    "outbox_id": outbox_id,
                    "state": "PENDING",
                    "business_operation_reexecuted": False,
                }
            )

        raw = self._writer.submit(
            WriterCommand(request_id, fp, "normal", deadline_monotonic_ms, apply, lookup)
        ).result(timeout=5)
        return dict(strict_json(raw))

    def discard_dead_letter(
        self,
        context: InboundContext,
        *,
        outbox_id: str,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> dict[str, Any]:
        fp = hashlib.sha256(
            canonicalize({"kind": "dlq_discard", "id": outbox_id, "req": request_id})
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return None

        def apply(db: sqlite3.Connection) -> bytes:
            authorize(db, context)
            row = db.execute(
                "SELECT state,version FROM outbox WHERE outbox_id=?", (outbox_id,)
            ).fetchone()
            if not row:
                raise RequestConflict("Dead letter record not found")
            state, ver = str(row[0]), int(row[1])
            if state == "UNKNOWN":
                raise PermissionError("UNKNOWN_REQUIRES_RECONCILE")
            now = time.time_ns() // 1_000_000
            db.execute(
                "UPDATE outbox SET state='SUPERSEDED',error_code='DISCARDED_BY_OWNER',"
                "version=version+1,updated_at=? WHERE outbox_id=? AND version=?",
                (now, outbox_id, ver),
            )
            return canonicalize({"outbox_id": outbox_id, "state": "SUPERSEDED"})

        raw = self._writer.submit(
            WriterCommand(request_id, fp, "normal", deadline_monotonic_ms, apply, lookup)
        ).result(timeout=5)
        return dict(strict_json(raw))
