"""CAS task transitions, OutcomeVerifier completion, cancellation and recovery resume."""

import hashlib
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

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
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_UNRESOLVED_OP_STATES = (
    "PROPOSED",
    "AWAITING_APPROVAL",
    "READY",
    "CLAIMED",
    "DISPATCHING",
    "UNKNOWN",
)


@dataclass(frozen=True, slots=True)
class OutcomeSubmission:
    task_kind: str
    target: str
    summary: str
    artifact_ids: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    original_hashes: dict[str, str] | None = None
    test_command: str | None = None
    snapshot_ref: str | None = None
    exit_code: int | None = None
    log_summary: str | None = None
    completed_actions: tuple[str, ...] = ()
    missing_requirements: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "task_kind": self.task_kind,
            "target": self.target,
            "summary": self.summary,
            "artifact_ids": list(self.artifact_ids),
            "source_refs": list(self.source_refs),
            "original_hashes": dict(self.original_hashes or {}),
            "test_command": self.test_command,
            "snapshot_ref": self.snapshot_ref,
            "exit_code": self.exit_code,
            "log_summary": self.log_summary,
            "completed_actions": list(self.completed_actions),
            "missing_requirements": list(self.missing_requirements),
        }


def verify_outcome(
    db: sqlite3.Connection,
    context: InboundContext,
    task_id: str,
    budget_id: str,
    submission: OutcomeSubmission,
) -> dict[str, Any]:
    if submission.target not in {"SUCCEEDED", "PARTIAL"} or not submission.summary.strip():
        raise PermissionError("Outcome target or summary is invalid")
    if submission.target == "SUCCEEDED" and submission.missing_requirements:
        raise PermissionError("SUCCEEDED outcome cannot have missing requirements")
    if submission.target == "PARTIAL" and (
        not submission.missing_requirements
        or not submission.completed_actions
        or any(not item.strip() for item in submission.missing_requirements)
        or any(not item.strip() for item in submission.completed_actions)
    ):
        raise PermissionError("PARTIAL outcome requires completed_actions and missing_requirements")

    unresolved_op = db.execute(
        "SELECT 1 FROM operations WHERE task_id=? AND state IN "
        "('PROPOSED','AWAITING_APPROVAL','READY','CLAIMED','DISPATCHING','UNKNOWN')",
        (task_id,),
    ).fetchone()
    if unresolved_op is not None:
        raise PermissionError("Unresolved operation blocks task completion")

    unresolved_approval = db.execute(
        "SELECT 1 FROM approvals a JOIN operations o ON o.operation_id=a.operation_id "
        "WHERE o.task_id=? AND a.status IN ('PENDING','APPROVED')",
        (task_id,),
    ).fetchone()
    if unresolved_approval is not None:
        raise PermissionError("Unresolved approval blocks task completion")

    unresolved_budget = db.execute(
        "SELECT 1 FROM budget_reservations WHERE budget_id=? AND status IN ('RESERVED','UNKNOWN')",
        (budget_id,),
    ).fetchone()
    if unresolved_budget is not None:
        raise PermissionError("Unsettled budget reservation blocks task completion")

    for artifact_id in submission.artifact_ids:
        row = db.execute(
            "SELECT a.state FROM artifacts a JOIN artifact_refs r ON r.object_id=a.object_id "
            "WHERE a.object_id=? AND r.owner_id=? AND ("
            "(r.scope_kind='TASK' AND r.task_id=?) OR "
            "(r.scope_kind='OPERATION' AND r.operation_id IN "
            "(SELECT operation_id FROM operations WHERE task_id=?)))",
            (artifact_id, context.principal_id, task_id, task_id),
        ).fetchone()
        if row != ("AVAILABLE",):
            raise PermissionError(f"Deliverable artifact {artifact_id} is not AVAILABLE for task")

    if submission.task_kind == "DIAGNOSIS":
        if not submission.source_refs or any(not ref.strip() for ref in submission.source_refs):
            raise PermissionError("Diagnosis task requires verified source references")
    elif submission.task_kind == "PATCH":
        if (
            not submission.artifact_ids
            or not submission.original_hashes
            or any(
                not path.strip() or not _HEX64.fullmatch(digest)
                for path, digest in submission.original_hashes.items()
            )
        ):
            raise PermissionError("Patch task requires diff artifact and original file hashes")
    elif submission.task_kind == "TEST":
        if (
            not submission.test_command
            or not submission.test_command.strip()
            or not submission.snapshot_ref
            or not submission.snapshot_ref.strip()
            or not submission.log_summary
            or not submission.log_summary.strip()
            or type(submission.exit_code) is not int
        ):
            raise PermissionError("Test task requires command, snapshot, exit_code and log_summary")
        if submission.target == "SUCCEEDED" and submission.exit_code != 0:
            raise PermissionError("Non-zero test exit_code cannot mark task SUCCEEDED")
    else:
        raise PermissionError("Unsupported task verification kind")

    return submission.to_payload()


class TaskStateService:
    def __init__(self, writer: Writer):
        self._writer = writer

    @staticmethod
    def _task_row(
        db: sqlite3.Connection, context: InboundContext, task_id: str
    ) -> tuple[str, int, str, int, int | None, int | None, str | None]:
        authorize(db, context)
        row = db.execute(
            "SELECT owner_id,session_id,state,version,budget_id,cancel_revision,"
            "cancel_requested_at,finished_at,outcome_json FROM tasks WHERE task_id=?",
            (task_id,),
        ).fetchone()
        if not row or row[:2] != (context.principal_id, context.session_id):
            raise PermissionError("Task scope mismatch")
        return (
            str(row[2]),
            int(row[3]),
            str(row[4]),
            int(row[5]),
            None if row[6] is None else int(row[6]),
            None if row[7] is None else int(row[7]),
            None if row[8] is None else str(row[8]),
        )

    def _lookup(
        self, db: sqlite3.Connection, context: InboundContext, task_id: str, request_id: str
    ) -> LookupResult | None:
        self._task_row(db, context, task_id)
        row = db.execute(
            "SELECT payload_json FROM events WHERE json_extract(payload_json,'$.request_id')=?",
            (request_id,),
        ).fetchone()
        if not row:
            return None
        payload = strict_json(row[0])
        return LookupResult(payload["command_hash"], canonicalize(payload["receipt"]))

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
                    "kind": "transition",
                    "task": task_id,
                    "expected": expected_version,
                    "target": target,
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
            state, version, *_ = self._task_row(db, context, task_id)
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
            receipt: dict[str, Any] = {
                "task_id": task_id,
                "state": target,
                "version": version + 1,
            }
            event_type = "TASK_FINISHED" if terminal else "TASK_STATE_CHANGED"
            emit_state(db, context, receipt, request_id, fingerprint, event_type, now)
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "normal", deadline_monotonic_ms, apply, lookup
        )

    def complete(
        self,
        context: InboundContext,
        task_id: str,
        expected_version: int,
        submission: OutcomeSubmission,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("Invalid expected_version")
        outcome_payload = submission.to_payload()
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "complete",
                    "task": task_id,
                    "expected": expected_version,
                    "outcome": outcome_payload,
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
            state, version, budget_id, cancel_rev, *_ = self._task_row(db, context, task_id)
            if version != expected_version or submission.target not in TRANSITIONS[state]:
                raise RequestConflict("Task version or completion transition conflict")
            if cancel_rev > 0 and submission.target == "SUCCEEDED":
                raise PermissionError("Cancel requested; task cannot be marked SUCCEEDED")
            verified = verify_outcome(db, context, task_id, budget_id, submission)
            now = time.time_ns() // 1_000_000
            cursor = db.execute(
                "UPDATE tasks SET state=?,version=version+1,outcome_json=?,updated_at=?,"
                "finished_at=? WHERE task_id=? AND version=?",
                (
                    submission.target,
                    canonicalize(verified).decode(),
                    now,
                    now,
                    task_id,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise RequestConflict("Task version changed")
            receipt: dict[str, Any] = {
                "task_id": task_id,
                "state": submission.target,
                "version": version + 1,
            }
            emit_state(db, context, receipt, request_id, fingerprint, "TASK_FINISHED", now)
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "result", deadline_monotonic_ms, apply, lookup
        )

    def cancel(
        self,
        context: InboundContext,
        task_id: str,
        expected_version: int,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("Invalid expected_version")
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "cancel",
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
            state, version, _, cancel_rev, cancel_req_at, *_ = self._task_row(db, context, task_id)
            if version != expected_version or "CANCELLED" not in TRANSITIONS[state]:
                raise RequestConflict("Task version or cancel transition conflict")
            now = time.time_ns() // 1_000_000
            db.execute(
                "UPDATE approvals SET status='REVOKED',version=version+1 "
                "WHERE operation_id IN (SELECT operation_id FROM operations WHERE task_id=?) "
                "AND status IN ('PENDING','APPROVED')",
                (task_id,),
            )
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
            unknown = db.execute(
                "SELECT 1 FROM operations WHERE task_id=? AND state IN ('UNKNOWN','DISPATCHING')",
                (task_id,),
            ).fetchone()
            if unknown is not None:
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
            }
            emit_state(db, context, receipt, request_id, fingerprint, event_type, now)
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "cancel", deadline_monotonic_ms, apply, lookup
        )

    def resume_reconciled(
        self,
        context: InboundContext,
        task_id: str,
        expected_version: int,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("Invalid expected_version")
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "resume_reconciled",
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
            state, version, budget_id, cancel_rev, *_ = self._task_row(db, context, task_id)
            if version != expected_version or state != "RECONCILING":
                raise RequestConflict("Task is not in RECONCILING at expected version")
            if cancel_rev > 0:
                raise PermissionError(
                    "Cancel requested; reconciled task must complete cancellation"
                )
            unresolved = db.execute(
                "SELECT 1 FROM operations WHERE task_id=? AND ("
                "state IN ('PROPOSED','AWAITING_APPROVAL','CLAIMED','DISPATCHING','UNKNOWN') OR "
                "(unknown_reason IS NOT NULL AND resolution_evidence_ref IS NULL))",
                (task_id,),
            ).fetchone()
            if unresolved is not None:
                raise PermissionError("Unresolved or unverified operation outcome blocks resume")
            unknown_budget = db.execute(
                "SELECT 1 FROM budget_reservations WHERE budget_id=? AND status='UNKNOWN'",
                (budget_id,),
            ).fetchone()
            if unknown_budget is not None:
                raise PermissionError("Unreconciled budget reservation blocks resume")
            quarantined = db.execute(
                "SELECT 1 FROM operations WHERE workspace_id=? "
                "AND state IN ('UNKNOWN','DISPATCHING')",
                (context.workspace_id,),
            ).fetchone()
            if quarantined is not None:
                raise PermissionError("Workspace quarantine active for unresolved external effect")
            now = time.time_ns() // 1_000_000
            cursor = db.execute(
                "UPDATE tasks SET state='QUEUED',version=version+1,updated_at=? "
                "WHERE task_id=? AND version=?",
                (now, task_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise RequestConflict("Task version changed")
            receipt: dict[str, Any] = {
                "task_id": task_id,
                "state": "QUEUED",
                "version": version + 1,
            }
            emit_state(db, context, receipt, request_id, fingerprint, "TASK_STATE_CHANGED", now)
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "result", deadline_monotonic_ms, apply, lookup
        )

    def snapshot(self, context: InboundContext, task_id: str) -> dict[str, object]:
        def query(db: sqlite3.Connection) -> dict[str, object]:
            state, version, _, cancel_rev, cancel_req_at, finished_at, outcome_json = (
                self._task_row(db, context, task_id)
            )
            unresolved = [
                str(r[0])
                for r in db.execute(
                    "SELECT operation_id FROM operations WHERE task_id=? AND state IN "
                    "('PROPOSED','AWAITING_APPROVAL','READY','CLAIMED','DISPATCHING','UNKNOWN') "
                    "ORDER BY ordinal",
                    (task_id,),
                )
            ]
            return {
                "task_id": task_id,
                "state": state,
                "version": version,
                "cancel_revision": cancel_rev,
                "cancel_requested_at_ms": cancel_req_at,
                "finished_at_ms": finished_at,
                "outcome": None if outcome_json is None else strict_json(outcome_json),
                "unresolved_operation_ids": unresolved,
            }

        return self._writer.read(query)

    def replay(self, context: InboundContext, task_id: str) -> list[dict[str, object]]:
        def query(db: sqlite3.Connection) -> list[dict[str, object]]:
            self._task_row(db, context, task_id)
            result: list[dict[str, object]] = []
            for row in db.execute(
                "SELECT seq,event_type,aggregate_version FROM events "
                "WHERE task_id=? ORDER BY seq LIMIT 1000",
                (task_id,),
            ):
                result.append({"seq": row[0], "event_type": row[1], "version": row[2]})
            return result

        return self._writer.read(query)
