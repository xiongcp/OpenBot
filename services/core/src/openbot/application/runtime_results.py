"""Trusted runtime result commits preserve consumed approvals and unknown resource locks."""

import hashlib
import sqlite3
import time
from typing import Any

from openbot.application.operations import command_lookup, task_record
from openbot.contracts import canonicalize, strict_json
from openbot.storage.inbox import InboundContext, emit_state
from openbot.storage.writer import Writer, WriterCommand


def record_result(
    writer: Writer,
    context: InboundContext,
    *,
    task_id: str,
    operation_id: str,
    attempt_id: str,
    runtime_epoch: str,
    artifact_id: str | None,
    unknown: bool,
) -> dict[str, Any]:
    request_id = "agent-result:" + attempt_id
    payload = {
        "operation_id": operation_id,
        "attempt_id": attempt_id,
        "artifact_id": artifact_id,
        "unknown": unknown,
        "runtime_epoch": runtime_epoch,
    }
    fingerprint = hashlib.sha256(canonicalize(payload)).hexdigest()

    def apply(db: sqlite3.Connection) -> bytes:
        state, version, _ = task_record(db, context, task_id)
        row = db.execute(
            "SELECT o.state,o.current_attempt_id,a.status,a.runtime_epoch "
            "FROM operations o JOIN operation_attempts a ON a.operation_id=o.operation_id "
            "WHERE o.operation_id=? AND o.task_id=? AND a.attempt_id=?",
            (operation_id, task_id, attempt_id),
        ).fetchone()
        active = db.execute("SELECT active_runtime_epoch FROM profile_config").fetchone()
        if row != ("DISPATCHING", attempt_id, "DISPATCHING", runtime_epoch) or active != (
            runtime_epoch,
        ):
            raise PermissionError("RUNTIME_RESULT_ATTEMPT_MISMATCH")
        now = time.time_ns() // 1_000_000
        outcome = "UNKNOWN" if unknown else "SUCCEEDED"
        if not unknown:
            evidence = db.execute(
                "SELECT a.state FROM artifacts a JOIN artifact_refs r ON r.object_id=a.object_id "
                "WHERE a.object_id=? AND r.operation_id=? AND r.owner_id=?",
                (artifact_id, operation_id, context.principal_id),
            ).fetchone()
            if evidence != ("AVAILABLE",):
                raise PermissionError("RUNTIME_RESULT_ARTIFACT_REQUIRED")
            db.execute(
                "UPDATE resource_leases SET holder_attempt_id=NULL,runtime_epoch=NULL,"
                "state='RELEASED',acquired_at=NULL,expires_at=NULL,version=version+1,"
                "updated_at=? WHERE holder_attempt_id=? AND state='HELD'",
                (now, attempt_id),
            )
        db.execute(
            "UPDATE operation_attempts SET status=?,receipt_json=?,finished_at=?,"
            "version=version+1 WHERE attempt_id=?",
            (outcome, canonicalize(payload).decode(), None if unknown else now, attempt_id),
        )
        db.execute(
            "UPDATE operations SET state=?,result_artifact_id=?,result_json=?,completed_at=?,"
            "unknown_reason=?,"
            "updated_at=?,version=version+1 WHERE operation_id=?",
            (
                outcome,
                artifact_id,
                canonicalize(payload).decode(),
                None if unknown else now,
                "TOOL_RECEIPT_UNAVAILABLE" if unknown else None,
                now,
                operation_id,
            ),
        )
        target = (
            "RECONCILING"
            if unknown and state not in {"SUCCEEDED", "FAILED", "PARTIAL", "CANCELLED"}
            else state
        )
        db.execute(
            "UPDATE tasks SET state=?,version=version+1,updated_at=? WHERE task_id=?",
            (target, now, task_id),
        )
        receipt: dict[str, str | int] = {
            "task_id": task_id,
            "state": target,
            "version": version + 1,
            "operation_id": operation_id,
            "operation_state": outcome,
        }
        emit_state(
            db,
            context,
            receipt,
            request_id,
            fingerprint,
            "OUTCOME_UNKNOWN" if unknown else "OPERATION_FINISHED",
            now,
            operation_id,
        )
        return canonicalize(receipt)

    command = WriterCommand(
        request_id,
        fingerprint,
        "result",
        int(time.monotonic() * 1000) + 5000,
        apply,
        lambda db: command_lookup(db, context, task_id, request_id),
    )
    return dict(strict_json(writer.submit(command).result(timeout=5)))
