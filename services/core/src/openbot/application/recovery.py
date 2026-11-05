"""Side-effect aware crash recovery and evidence-backed UNKNOWN reconciliation."""

import hashlib
import secrets
import sqlite3
import time
from typing import Any

from openbot.application.dispatch import RecoveryTicket, mint_recovery_ticket
from openbot.application.operations import (
    PROPOSAL_TTL_MS,
    clock_now,
    load_proposal,
    task_record,
)
from openbot.contracts import SchemaRegistry, canonicalize, strict_json
from openbot.domain.clock import ClockSnapshot, grant_valid
from openbot.storage.inbox import InboundContext, authorize
from openbot.storage.writer import LookupResult, RequestConflict, Writer, WriterCommand

_ALLOWED_PROVENANCE = frozenset({"PROVIDER_VERIFIED", "USER_ATTESTED"})


def _release_attempt_leases(db: sqlite3.Connection, attempt_id: str, now: int) -> list[str]:
    rows = db.execute(
        "SELECT resource_key,version FROM resource_leases "
        "WHERE state='HELD' AND holder_attempt_id=? ORDER BY resource_key",
        (attempt_id,),
    ).fetchall()
    released: list[str] = []
    for key, ver in rows:
        db.execute(
            "UPDATE resource_leases SET holder_attempt_id=NULL,runtime_epoch=NULL,"
            "state='RELEASED',acquired_at=NULL,expires_at=NULL,version=version+1,"
            "updated_at=? WHERE resource_key=? AND version=?",
            (now, key, ver),
        )
        released.append(str(key))
    return released


def _verify_recovery_preconditions(
    db: sqlite3.Connection,
    context: InboundContext,
    operation_id: str,
    active_epoch: str,
    registry: SchemaRegistry,
) -> tuple[str, dict[str, Any], int]:
    authorize(db, context)
    cfg = db.execute(
        "SELECT active_runtime_epoch,policy_version FROM profile_config WHERE singleton=1"
    ).fetchone()
    inst = db.execute(
        "SELECT state FROM runtime_instances WHERE runtime_epoch=?", (active_epoch,)
    ).fetchone()
    if not cfg or cfg[0] != active_epoch or inst != ("ACTIVE",):
        raise PermissionError("Active runtime epoch is not established for recovery")
    policy_ver = int(cfg[1])

    proposal = load_proposal(db, context, operation_id, registry).value()
    task_id = str(proposal["task_id"])
    task_state, _, cancel_rev = task_record(db, context, task_id)
    if task_state not in {"RUNNING", "RECONCILING"} or cancel_rev > 0:
        raise PermissionError("Task is cancelled or not eligible for operation recovery")

    ws_row = db.execute(
        "SELECT generation,status FROM workspaces WHERE workspace_id=?",
        (context.workspace_id,),
    ).fetchone()
    tool_row = db.execute(
        "SELECT tool_version,manifest_digest FROM tool_registry "
        "WHERE tool_id=? AND status='ACTIVE'",
        (proposal["tool"]["name"],),
    ).fetchone()
    if (
        proposal["identity_epoch"] != context.identity_epoch
        or proposal["policy_version"] != f"policy-{policy_ver}"
        or not ws_row
        or ws_row[1] != "ACTIVE"
        or int(ws_row[0]) != int(proposal["resource_snapshot"]["workspace_generation"])
        or tool_row
        != (
            proposal["tool"]["version"],
            proposal["tool"]["manifest_digest"][7:],
        )
    ):
        raise PermissionError("Original authorization preconditions changed")

    apr_row = db.execute(
        "SELECT status,actor_scope_json,expires_at FROM approvals WHERE operation_id=?",
        (operation_id,),
    ).fetchone()
    if not apr_row or apr_row[0] not in {"APPROVED", "CONSUMED"}:
        raise PermissionError("Approval is not valid for recovery")
    scope = strict_json(apr_row[1])
    now = clock_now()
    issued = ClockSnapshot(
        int(scope["issued_utc_ms"]),
        int(scope["issued_monotonic_ms"]),
        str(scope["authority_instance"]),
    )
    if (
        not grant_valid(issued, now, PROPOSAL_TTL_MS)
        or now.utc_ms >= int(proposal["expires_at_ms"])
        or now.utc_ms >= int(apr_row[2])
    ):
        raise PermissionError("Original authorization expired or clock authority lost")

    return task_id, proposal, now.utc_ms


class RecoveryService:
    def __init__(self, writer: Writer, registry: SchemaRegistry):
        self._writer = writer
        self._registry = registry

    @staticmethod
    def _lookup(
        db: sqlite3.Connection, context: InboundContext, request_id: str
    ) -> LookupResult | None:
        authorize(db, context)
        row = db.execute(
            "SELECT payload_json FROM events WHERE json_extract(payload_json,'$.request_id')=?",
            (request_id,),
        ).fetchone()
        if not row:
            return None
        payload = strict_json(row[0])
        return LookupResult(payload["command_hash"], canonicalize(payload["receipt"]))

    def recover_epoch(
        self,
        context: InboundContext,
        new_runtime_epoch: str,
        boot_id: str,
        supervisor_ref: str,
        *,
        old_epoch_isolated: bool,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "recover_epoch",
                    "new_epoch": new_runtime_epoch,
                    "boot_id": boot_id,
                    "supervisor_ref": supervisor_ref,
                    "isolated": old_epoch_isolated,
                    "actor": context.principal_id,
                    "profile": context.profile_id,
                    "session": context.session_id,
                    "identity": context.identity_epoch,
                    "surface": context.source_scope,
                }
            )
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return self._lookup(db, context, request_id)

        def apply(db: sqlite3.Connection) -> bytes:
            authorize(db, context)
            now = time.time_ns() // 1_000_000
            unknown_ops: list[str] = []

            for op_id, op_ver, task_id, att_id in db.execute(
                "SELECT operation_id,version,task_id,current_attempt_id FROM operations "
                "WHERE state='DISPATCHING' ORDER BY created_at,operation_id"
            ).fetchall():
                if att_id is not None:
                    db.execute(
                        "UPDATE operation_attempts SET status='UNKNOWN',version=version+1 "
                        "WHERE attempt_id=? AND status='DISPATCHING'",
                        (att_id,),
                    )
                db.execute(
                    "UPDATE operations SET state='UNKNOWN',unknown_reason='crash_during_dispatch',"
                    "version=version+1,updated_at=? WHERE operation_id=? AND version=?",
                    (now, op_id, op_ver),
                )
                t_row = db.execute(
                    "SELECT state,version FROM tasks WHERE task_id=?", (task_id,)
                ).fetchone()
                if t_row and t_row[0] == "RUNNING":
                    db.execute(
                        "UPDATE tasks SET state='RECONCILING',version=version+1,updated_at=? "
                        "WHERE task_id=? AND version=?",
                        (now, task_id, int(t_row[1])),
                    )
                unknown_ops.append(str(op_id))

            target_inst_state = "STOPPED" if old_epoch_isolated else "LOST"
            db.execute(
                "UPDATE runtime_instances SET state=?,ended_at=? "
                "WHERE state IN ('STARTING','ACTIVE','DRAINING')",
                (target_inst_state, now),
            )

            if old_epoch_isolated:
                db.execute(
                    "INSERT INTO runtime_instances("
                    "runtime_epoch,boot_id,supervisor_ref,state,started_at,heartbeat_at) "
                    "VALUES(?,?,?,'ACTIVE',?,?)",
                    (new_runtime_epoch, boot_id, supervisor_ref, now, now),
                )
                db.execute(
                    "UPDATE profile_config SET active_runtime_epoch=?,version=version+1,"
                    "updated_at=? WHERE singleton=1",
                    (new_runtime_epoch, now),
                )

            receipt: dict[str, Any] = {
                "takeover_allowed": old_epoch_isolated,
                "active_runtime_epoch": new_runtime_epoch if old_epoch_isolated else None,
                "unknown_operations": unknown_ops,
            }
            payload = canonicalize(
                {"request_id": request_id, "command_hash": fingerprint, "receipt": receipt}
            ).decode()
            db.execute(
                "INSERT INTO events(event_id,aggregate_kind,aggregate_id,aggregate_version,"
                "actor_principal_id,event_type,schema_version,trace_id,payload_json,created_at) "
                "VALUES(?,'Runtime',?,1,?,'OUTCOME_UNKNOWN',1,?,?,?)",
                (
                    "evt_" + secrets.token_hex(16),
                    new_runtime_epoch,
                    context.principal_id,
                    "trc_" + hashlib.sha256(request_id.encode()).hexdigest()[:32],
                    payload,
                    now,
                ),
            )
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "result", deadline_monotonic_ms, apply, lookup
        )

    def recover_operation(
        self,
        context: InboundContext,
        operation_id: str,
        runtime_epoch: str,
        *,
        dispatch_was_sent: bool,
        probe_status: str,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> tuple[dict[str, Any], RecoveryTicket | None]:
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "recover_operation",
                    "operation": operation_id,
                    "epoch": runtime_epoch,
                    "sent": dispatch_was_sent,
                    "probe": probe_status,
                    "actor": context.principal_id,
                    "profile": context.profile_id,
                    "session": context.session_id,
                    "identity": context.identity_epoch,
                    "surface": context.source_scope,
                }
            )
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return self._lookup(db, context, request_id)

        def apply(db: sqlite3.Connection) -> bytes:
            task_id, _, now = _verify_recovery_preconditions(
                db, context, operation_id, runtime_epoch, self._registry
            )
            op_row = db.execute(
                "SELECT state,version,current_attempt_id,retry_class,provider_retry_deadline_at "
                "FROM operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if not op_row or op_row[2] is None:
                raise PermissionError("Operation has no recoverable attempt")
            op_state, op_ver, att_id, retry_class, retry_deadline = (
                str(op_row[0]),
                int(op_row[1]),
                str(op_row[2]),
                str(op_row[3]),
                None if op_row[4] is None else int(op_row[4]),
            )
            att_row = db.execute(
                "SELECT status,version,runtime_epoch,dispatch_started_at "
                "FROM operation_attempts WHERE attempt_id=?",
                (att_id,),
            ).fetchone()
            if not att_row:
                raise PermissionError("Attempt record missing")
            att_status, att_ver, old_epoch, disp_started = (
                str(att_row[0]),
                int(att_row[1]),
                str(att_row[2]),
                att_row[3],
            )
            old_inst = db.execute(
                "SELECT state FROM runtime_instances WHERE runtime_epoch=?", (old_epoch,)
            ).fetchone()
            if old_inst != ("STOPPED",):
                raise PermissionError("Previous runtime epoch is not proven STOPPED")

            # Case 1: CLAIMED and never dispatched -> safe to abandon attempt and return to READY
            if (
                op_state == "CLAIMED"
                and att_status == "CLAIMED"
                and disp_started is None
                and not dispatch_was_sent
            ):
                _release_attempt_leases(db, att_id, now)
                db.execute(
                    "UPDATE operation_attempts SET status='ABANDONED',"
                    "recovery_evidence_ref='ev_claimed_undispatched_isolated',"
                    "finished_at=?,version=version+1 WHERE attempt_id=? AND version=?",
                    (now, att_id, att_ver),
                )
                db.execute(
                    "UPDATE operations SET state='READY',version=version+1,updated_at=? "
                    "WHERE operation_id=? AND version=?",
                    (now, operation_id, op_ver),
                )
                receipt: dict[str, Any] = {
                    "task_id": task_id,
                    "operation_id": operation_id,
                    "operation_state": "READY",
                    "prior_attempt_id": att_id,
                    "retry_allowed": True,
                }
            else:
                # Case 2: DISPATCHING or UNKNOWN -> evaluate by retry_class
                if op_state == "DISPATCHING":
                    db.execute(
                        "UPDATE operation_attempts SET status='UNKNOWN',version=version+1 "
                        "WHERE attempt_id=? AND version=?",
                        (att_id, att_ver),
                    )
                    db.execute(
                        "UPDATE operations SET state='UNKNOWN',"
                        "unknown_reason='crash_during_dispatch',version=version+1,updated_at=? "
                        "WHERE operation_id=? AND version=?",
                        (now, operation_id, op_ver),
                    )
                    op_state = "UNKNOWN"
                    op_ver += 1
                    att_ver += 1

                if op_state != "UNKNOWN":
                    raise RequestConflict("Operation is not in a recoverable state")

                can_retry = False
                evidence_ref = ""
                if retry_class == "SAFE_READ":
                    can_retry = True
                    evidence_ref = "ev_safe_read_retry"
                elif retry_class == "IDEMPOTENT_WRITE" and probe_status == "NOT_APPLIED":
                    can_retry = True
                    evidence_ref = "ev_idempotent_not_applied"
                elif (
                    retry_class == "PROVIDER_IDEMPOTENT"
                    and probe_status == "CONFIRMED_NOT_EXECUTED"
                    and (retry_deadline is None or now < retry_deadline)
                ):
                    can_retry = True
                    evidence_ref = "ev_provider_not_executed"

                if can_retry:
                    _release_attempt_leases(db, att_id, now)
                    db.execute(
                        "UPDATE operation_attempts SET status='FAILED',"
                        "error_code='RECOVERED_RETRY',recovery_evidence_ref=?,finished_at=?,"
                        "version=version+1 WHERE attempt_id=?",
                        (evidence_ref, now, att_id),
                    )
                    db.execute(
                        "UPDATE operations SET state='READY',resolution_evidence_ref=?,"
                        "version=version+1,updated_at=? WHERE operation_id=? AND version=?",
                        (evidence_ref, now, operation_id, op_ver),
                    )
                    t_row = db.execute(
                        "SELECT state,version FROM tasks WHERE task_id=?", (task_id,)
                    ).fetchone()
                    other_unknown = db.execute(
                        "SELECT 1 FROM operations WHERE task_id=? "
                        "AND state IN ('UNKNOWN','DISPATCHING')",
                        (task_id,),
                    ).fetchone()
                    if t_row and t_row[0] == "RECONCILING" and other_unknown is None:
                        db.execute(
                            "UPDATE tasks SET state='RUNNING',version=version+1,updated_at=? "
                            "WHERE task_id=? AND version=?",
                            (now, task_id, int(t_row[1])),
                        )
                    receipt = {
                        "task_id": task_id,
                        "operation_id": operation_id,
                        "operation_state": "READY",
                        "prior_attempt_id": att_id,
                        "retry_allowed": True,
                    }
                else:
                    t_row = db.execute(
                        "SELECT state,version FROM tasks WHERE task_id=?", (task_id,)
                    ).fetchone()
                    if t_row and t_row[0] == "RUNNING":
                        db.execute(
                            "UPDATE tasks SET state='RECONCILING',version=version+1,updated_at=? "
                            "WHERE task_id=? AND version=?",
                            (now, task_id, int(t_row[1])),
                        )
                    receipt = {
                        "task_id": task_id,
                        "operation_id": operation_id,
                        "operation_state": "UNKNOWN",
                        "prior_attempt_id": att_id,
                        "retry_allowed": False,
                    }

            payload = canonicalize(
                {"request_id": request_id, "command_hash": fingerprint, "receipt": receipt}
            ).decode()
            db.execute(
                "INSERT INTO events(event_id,aggregate_kind,aggregate_id,aggregate_version,task_id,"
                "operation_id,actor_principal_id,event_type,schema_version,trace_id,payload_json,"
                "created_at) VALUES(?,'Operation',?,?,?,?,?,'OUTCOME_UNKNOWN',1,?,?,?)",
                (
                    "evt_" + secrets.token_hex(16),
                    operation_id,
                    op_ver + 1,
                    task_id,
                    operation_id,
                    context.principal_id,
                    "trc_" + hashlib.sha256(request_id.encode()).hexdigest()[:32],
                    payload,
                    now,
                ),
            )
            return canonicalize(receipt)

        raw = self._writer.submit(
            WriterCommand(request_id, fingerprint, "result", deadline_monotonic_ms, apply, lookup)
        ).result(
            timeout=min(
                300.0, max(0.001, (deadline_monotonic_ms - time.monotonic() * 1000) / 1000 + 0.05)
            )
        )
        parsed = strict_json(raw)
        ticket = (
            mint_recovery_ticket(operation_id, str(parsed["prior_attempt_id"]), runtime_epoch)
            if parsed["retry_allowed"]
            else None
        )
        return parsed, ticket

    def reconcile_unknown(
        self,
        context: InboundContext,
        operation_id: str,
        raw: str | bytes,
        *,
        provenance_kind: str,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        doc = self._registry.validate("reconciliation.schema.json", raw)
        body = doc.value()
        if provenance_kind not in _ALLOWED_PROVENANCE:
            raise PermissionError(
                "Reconciliation provenance must be PROVIDER_VERIFIED or USER_ATTESTED"
            )
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "reconcile_unknown",
                    "operation": operation_id,
                    "provenance": provenance_kind,
                    "body": body,
                    "actor": context.principal_id,
                    "profile": context.profile_id,
                    "session": context.session_id,
                    "identity": context.identity_epoch,
                    "surface": context.source_scope,
                }
            )
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return self._lookup(db, context, request_id)

        def apply(db: sqlite3.Connection) -> bytes:
            authorize(db, context)
            proposal = load_proposal(db, context, operation_id, self._registry).value()
            task_id = str(proposal["task_id"])
            op_row = db.execute(
                "SELECT state,version,current_attempt_id FROM operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if (
                not op_row
                or op_row[0] != "UNKNOWN"
                or int(op_row[1]) != int(body["expected_version"])
            ):
                raise RequestConflict("Operation is not in UNKNOWN at expected_version")
            op_ver = int(op_row[1])
            att_id = None if op_row[2] is None else str(op_row[2])
            now = time.time_ns() // 1_000_000

            if body["outcome"] == "KEEP_UNKNOWN":
                db.execute(
                    "UPDATE operations SET version=version+1,updated_at=? "
                    "WHERE operation_id=? AND version=?",
                    (now, operation_id, op_ver),
                )
                receipt: dict[str, Any] = {
                    "task_id": task_id,
                    "operation_id": operation_id,
                    "operation_state": "UNKNOWN",
                    "version": op_ver + 1,
                    "provenance": provenance_kind,
                }
            else:
                artifact_ids = list(body["evidence_artifact_ids"])
                for art_id in artifact_ids:
                    row = db.execute(
                        "SELECT a.state FROM artifacts a "
                        "JOIN artifact_refs r ON r.object_id=a.object_id "
                        "WHERE a.object_id=? AND r.owner_id=? AND ("
                        "(r.scope_kind='TASK' AND r.task_id=?) OR "
                        "(r.scope_kind='OPERATION' AND r.operation_id=?))",
                        (art_id, context.principal_id, task_id, operation_id),
                    ).fetchone()
                    if row != ("AVAILABLE",):
                        raise PermissionError(
                            f"Reconciliation evidence artifact {art_id} is not AVAILABLE"
                        )

                evidence_ref = canonicalize(
                    {"provenance": provenance_kind, "artifact_ids": artifact_ids}
                ).decode()
                target_state = "SUCCEEDED" if body["outcome"] == "CONFIRMED_SUCCEEDED" else "FAILED"
                if att_id is not None:
                    _release_attempt_leases(db, att_id, now)
                    db.execute(
                        "UPDATE operation_attempts SET status=?,recovery_evidence_ref=?,"
                        "finished_at=?,version=version+1 WHERE attempt_id=? AND status='UNKNOWN'",
                        (target_state, evidence_ref, now, att_id),
                    )
                upd = db.execute(
                    "UPDATE operations SET state=?,resolution_evidence_ref=?,completed_at=?,"
                    "updated_at=?,version=version+1 WHERE operation_id=? AND version=? "
                    "AND state='UNKNOWN'",
                    (target_state, evidence_ref, now, now, operation_id, op_ver),
                )
                if upd.rowcount != 1:
                    raise RequestConflict("Reconciliation CAS lost")
                receipt = {
                    "task_id": task_id,
                    "operation_id": operation_id,
                    "operation_state": target_state,
                    "version": op_ver + 1,
                    "provenance": provenance_kind,
                }

            payload = canonicalize(
                {"request_id": request_id, "command_hash": fingerprint, "receipt": receipt}
            ).decode()
            db.execute(
                "INSERT INTO events(event_id,aggregate_kind,aggregate_id,aggregate_version,task_id,"
                "operation_id,actor_principal_id,event_type,schema_version,trace_id,payload_json,"
                "created_at) VALUES(?,'Operation',?,?,?,?,?,'OPERATION_FINISHED',1,?,?,?)",
                (
                    "evt_" + secrets.token_hex(16),
                    operation_id,
                    op_ver + 1,
                    task_id,
                    operation_id,
                    context.principal_id,
                    "trc_" + hashlib.sha256(request_id.encode()).hexdigest()[:32],
                    payload,
                    now,
                ),
            )
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "result", deadline_monotonic_ms, apply, lookup
        )
