"""Two-transaction pre-dispatch gate (claim -> DISPATCHING) and CONSUMED reuse verification."""

import hashlib
import hmac
import secrets
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from openbot.application.operations import (
    PROPOSAL_TTL_MS,
    clock_now,
    load_proposal,
    task_record,
)
from openbot.application.resources import (
    ResourceBusyError,
    ResourceRequest,
    _allocate_fence,
    _check_preconditions,
    _check_quarantine,
    _verify_active_epoch,
    order_resources,
)
from openbot.contracts import SchemaRegistry, canonicalize, strict_json
from openbot.domain.clock import ClockSnapshot, grant_valid
from openbot.storage.inbox import InboundContext, authorize
from openbot.storage.writer import LookupResult, RequestConflict, Writer, WriterCommand

_RECOVERY_SECRET = secrets.token_bytes(32)


@dataclass(frozen=True, slots=True)
class RecoveryTicket:
    operation_id: str
    prior_attempt_id: str
    runtime_epoch: str
    signature: str


def mint_recovery_ticket(
    operation_id: str, prior_attempt_id: str, runtime_epoch: str
) -> RecoveryTicket:
    msg = canonicalize(
        {
            "operation_id": operation_id,
            "prior_attempt_id": prior_attempt_id,
            "runtime_epoch": runtime_epoch,
        }
    )
    sig = hmac.new(_RECOVERY_SECRET, msg, hashlib.sha256).hexdigest()
    return RecoveryTicket(operation_id, prior_attempt_id, runtime_epoch, sig)


def _verify_recovery_ticket(ticket: RecoveryTicket, operation_id: str, runtime_epoch: str) -> None:
    if (
        not isinstance(ticket, RecoveryTicket)
        or ticket.operation_id != operation_id
        or ticket.runtime_epoch != runtime_epoch
    ):
        raise PermissionError("Recovery ticket scope mismatch")
    expected = mint_recovery_ticket(
        ticket.operation_id, ticket.prior_attempt_id, ticket.runtime_epoch
    ).signature
    if not hmac.compare_digest(ticket.signature, expected):
        raise PermissionError("Invalid recovery ticket signature")


def _verify_conditions(
    db: sqlite3.Connection,
    context: InboundContext,
    operation_id: str,
    runtime_epoch: str,
    registry: SchemaRegistry,
) -> tuple[str, int, dict[str, Any], int, int]:
    authorize(db, context)
    _verify_active_epoch(db, runtime_epoch)
    proposal = load_proposal(db, context, operation_id, registry).value()
    task_id = str(proposal["task_id"])
    task_state, task_version, cancel_rev = task_record(db, context, task_id)
    if task_state != "RUNNING" or cancel_rev > 0:
        raise PermissionError("Task is not RUNNING or has a pending cancellation")

    policy_ver = int(
        db.execute("SELECT policy_version FROM profile_config WHERE singleton=1").fetchone()[0]
    )
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
        raise PermissionError("Operation authorization conditions changed")

    apr_row = db.execute(
        "SELECT approval_id,status,version,actor_scope_json,expires_at,consumed_attempt_id "
        "FROM approvals WHERE operation_id=?",
        (operation_id,),
    ).fetchone()
    if not apr_row:
        raise PermissionError("Operation approval record missing")
    scope = strict_json(apr_row[3])
    now = clock_now()
    issued = ClockSnapshot(
        int(scope["issued_utc_ms"]),
        int(scope["issued_monotonic_ms"]),
        str(scope["authority_instance"]),
    )
    if (
        not grant_valid(issued, now, PROPOSAL_TTL_MS)
        or now.utc_ms >= int(proposal["expires_at_ms"])
        or now.utc_ms >= int(apr_row[4])
    ):
        raise PermissionError("Authorization grant expired or time authority unavailable")

    return task_id, task_version, proposal, policy_ver, now.utc_ms


class DispatchService:
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

    def claim(
        self,
        context: InboundContext,
        operation_id: str,
        runtime_epoch: str,
        executor_id: str,
        resources: Sequence[ResourceRequest],
        lease_ttl_ms: int,
        request_id: str,
        deadline_monotonic_ms: int,
        *,
        recovery_ticket: RecoveryTicket | None = None,
    ) -> WriterCommand:
        if (
            not executor_id
            or not executor_id.strip()
            or type(lease_ttl_ms) is not int
            or lease_ttl_ms <= 0
        ):
            raise ValueError("Invalid executor_id or lease_ttl_ms")
        ordered = order_resources(resources)
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "claim_operation",
                    "operation": operation_id,
                    "epoch": runtime_epoch,
                    "executor": executor_id.strip(),
                    "ttl_ms": lease_ttl_ms,
                    "resources": [r.to_payload() for r in ordered],
                    "recovery": None
                    if recovery_ticket is None
                    else {
                        "prior_attempt_id": recovery_ticket.prior_attempt_id,
                        "signature": recovery_ticket.signature,
                    },
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
            task_id, _, proposal, policy_ver, now = _verify_conditions(
                db, context, operation_id, runtime_epoch, self._registry
            )
            op_row = db.execute(
                "SELECT state,version,provider_idempotency_key FROM operations "
                "WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if not op_row or op_row[0] != "READY":
                raise RequestConflict("Operation is not READY for claim")
            op_version = int(op_row[1])
            provider_key = None if op_row[2] is None else str(op_row[2])

            apr_row = db.execute(
                "SELECT approval_id,status,version,consumed_attempt_id FROM approvals "
                "WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            assert apr_row is not None
            approval_id, apr_status, apr_version, consumed_att = (
                str(apr_row[0]),
                str(apr_row[1]),
                int(apr_row[2]),
                None if apr_row[3] is None else str(apr_row[3]),
            )

            if recovery_ticket is None:
                if apr_status != "APPROVED":
                    raise PermissionError(
                        "First claim requires APPROVED grant; CONSUMED cannot be reused by client"
                    )
            else:
                _verify_recovery_ticket(recovery_ticket, operation_id, runtime_epoch)
                if apr_status != "CONSUMED" or consumed_att != recovery_ticket.prior_attempt_id:
                    raise PermissionError("CONSUMED grant does not match recovery ticket")

            for req in ordered:
                _check_quarantine(db, req)
                _check_preconditions(db, req)
                existing = db.execute(
                    "SELECT holder_attempt_id,runtime_epoch,state FROM resource_leases "
                    "WHERE resource_key=?",
                    (req.resource_key,),
                ).fetchone()
                if existing is not None and existing[2] == "HELD":
                    old_inst = db.execute(
                        "SELECT state FROM runtime_instances WHERE runtime_epoch=?",
                        (existing[1],),
                    ).fetchone()
                    old_att = db.execute(
                        "SELECT status,dispatch_started_at FROM operation_attempts "
                        "WHERE attempt_id=?",
                        (existing[0],),
                    ).fetchone()
                    if (
                        old_inst != ("STOPPED",)
                        or not old_att
                        or old_att[0] not in {"CLAIMED", "ABANDONED", "CANCELLED"}
                        or old_att[1] is not None
                    ):
                        raise ResourceBusyError(f"Resource {req.resource_key} is held")

            attempt_no = int(
                db.execute(
                    "SELECT coalesce(max(attempt_no),0)+1 FROM operation_attempts "
                    "WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()[0]
            )
            attempt_id = "att_" + secrets.token_hex(16)
            dispatch_id = "dsp_" + secrets.token_hex(16)
            fences: list[tuple[ResourceRequest, int]] = [
                (req, _allocate_fence(db, now)) for req in ordered
            ]
            max_fence = fences[-1][1]
            lease_keys = [req.resource_key for req, _ in fences]

            db.execute(
                "INSERT INTO operation_attempts("
                "attempt_id,operation_id,attempt_no,approval_id,runtime_epoch,fencing_token,"
                "dispatch_id,executor_id,claim_cancel_revision,claim_policy_version,"
                "claim_identity_epoch,lease_set_json,status,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,0,?,?,?,'CLAIMED',?)",
                (
                    attempt_id,
                    operation_id,
                    attempt_no,
                    approval_id,
                    runtime_epoch,
                    max_fence,
                    dispatch_id,
                    executor_id.strip(),
                    policy_ver,
                    context.identity_epoch,
                    canonicalize(lease_keys).decode(),
                    now,
                ),
            )

            expires_at = now + lease_ttl_ms
            for req, fence in fences:
                existing_lease = db.execute(
                    "SELECT version FROM resource_leases WHERE resource_key=?",
                    (req.resource_key,),
                ).fetchone()
                if existing_lease is None:
                    db.execute(
                        "INSERT INTO resource_leases("
                        "resource_key,resource_type,holder_attempt_id,runtime_epoch,fencing_token,"
                        "state,acquired_at,expires_at,version,updated_at) "
                        "VALUES(?,?,?,?,?,'HELD',?,?,0,?)",
                        (
                            req.resource_key,
                            req.resource_type,
                            attempt_id,
                            runtime_epoch,
                            fence,
                            now,
                            expires_at,
                            now,
                        ),
                    )
                else:
                    updated_lease = db.execute(
                        "UPDATE resource_leases SET holder_attempt_id=?,runtime_epoch=?,"
                        "fencing_token=?,state='HELD',acquired_at=?,expires_at=?,"
                        "version=version+1,updated_at=? WHERE resource_key=? AND version=?",
                        (
                            attempt_id,
                            runtime_epoch,
                            fence,
                            now,
                            expires_at,
                            now,
                            req.resource_key,
                            int(existing_lease[0]),
                        ),
                    )
                    if updated_lease.rowcount != 1:
                        raise RequestConflict("Resource lease CAS lost")

            if recovery_ticket is None:
                consumed = db.execute(
                    "UPDATE approvals SET status='CONSUMED',version=version+1,consumed_at=?,"
                    "consumed_attempt_id=? WHERE approval_id=? AND version=? AND status='APPROVED'",
                    (now, attempt_id, approval_id, apr_version),
                )
                if consumed.rowcount != 1:
                    raise RequestConflict("Approval consumption CAS lost")

            updated_op = db.execute(
                "UPDATE operations SET state='CLAIMED',current_attempt_id=?,version=version+1,"
                "updated_at=? WHERE operation_id=? AND state='READY' AND version=?",
                (attempt_id, now, operation_id, op_version),
            )
            if updated_op.rowcount != 1:
                raise RequestConflict("Operation claim CAS lost")

            receipt: dict[str, Any] = {
                "task_id": task_id,
                "operation_id": operation_id,
                "operation_state": "CLAIMED",
                "attempt_id": attempt_id,
                "attempt_no": attempt_no,
                "dispatch_id": dispatch_id,
                "provider_idempotency_key": provider_key,
                "approval_id": approval_id,
                "approval_status": "CONSUMED",
                "fencing_token": max_fence,
                "lease_keys": lease_keys,
            }
            payload = canonicalize(
                {"request_id": request_id, "command_hash": fingerprint, "receipt": receipt}
            ).decode()
            db.execute(
                "INSERT INTO events(event_id,aggregate_kind,aggregate_id,aggregate_version,task_id,"
                "operation_id,actor_principal_id,event_type,schema_version,trace_id,payload_json,"
                "created_at) VALUES(?,'Operation',?,?,?,?,?,'OPERATION_CLAIMED',1,?,?,?)",
                (
                    "evt_" + secrets.token_hex(16),
                    operation_id,
                    op_version + 1,
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
            request_id, fingerprint, "normal", deadline_monotonic_ms, apply, lookup
        )

    def begin_dispatch(
        self,
        context: InboundContext,
        operation_id: str,
        attempt_id: str,
        runtime_epoch: str,
        executor_id: str,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "begin_dispatch",
                    "operation": operation_id,
                    "attempt": attempt_id,
                    "epoch": runtime_epoch,
                    "executor": executor_id.strip(),
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
            task_id, _, proposal, policy_ver, now = _verify_conditions(
                db, context, operation_id, runtime_epoch, self._registry
            )
            op_row = db.execute(
                "SELECT state,version,current_attempt_id,provider_idempotency_key "
                "FROM operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            att_row = db.execute(
                "SELECT status,version,runtime_epoch,fencing_token,dispatch_id,executor_id,"
                "claim_cancel_revision,claim_policy_version,claim_identity_epoch,lease_set_json "
                "FROM operation_attempts WHERE attempt_id=? AND operation_id=?",
                (attempt_id, operation_id),
            ).fetchone()
            if not op_row or not att_row or str(op_row[2]) != attempt_id:
                raise PermissionError("Attempt is not the current claimed attempt for operation")
            if (
                str(att_row[2]) != runtime_epoch
                or str(att_row[5]) != executor_id.strip()
                or int(att_row[6]) != 0
                or int(att_row[7]) != policy_ver
                or int(att_row[8]) != context.identity_epoch
            ):
                raise PermissionError("Attempt epoch, executor, policy, or identity changed")

            lease_keys = strict_json(att_row[9])
            for key in lease_keys:
                lease = db.execute(
                    "SELECT holder_attempt_id,runtime_epoch,state,expires_at "
                    "FROM resource_leases WHERE resource_key=?",
                    (key,),
                ).fetchone()
                if (
                    not lease
                    or lease[:3] != (attempt_id, runtime_epoch, "HELD")
                    or now >= int(lease[3])
                ):
                    raise PermissionError(f"Resource lease {key} is no longer valid for dispatch")

            dispatch_id = str(att_row[4])
            provider_key = None if op_row[3] is None else str(op_row[3])
            fencing_token = int(att_row[3])

            if op_row[0] == "DISPATCHING" and att_row[0] == "DISPATCHING":
                # Same-attempt message retransmission preserves the exact dispatch_id
                receipt: dict[str, Any] = {
                    "task_id": task_id,
                    "operation_id": operation_id,
                    "operation_state": "DISPATCHING",
                    "attempt_id": attempt_id,
                    "dispatch_id": dispatch_id,
                    "provider_idempotency_key": provider_key,
                    "fencing_token": fencing_token,
                }
                return canonicalize(receipt)

            if op_row[0] != "CLAIMED" or att_row[0] != "CLAIMED":
                raise RequestConflict("Operation or attempt is not in CLAIMED state")

            op_ver, att_ver = int(op_row[1]), int(att_row[1])
            upd_att = db.execute(
                "UPDATE operation_attempts SET status='DISPATCHING',dispatch_started_at=?,"
                "version=version+1 WHERE attempt_id=? AND version=? AND status='CLAIMED'",
                (now, attempt_id, att_ver),
            )
            upd_op = db.execute(
                "UPDATE operations SET state='DISPATCHING',version=version+1,updated_at=? "
                "WHERE operation_id=? AND version=? AND state='CLAIMED'",
                (now, operation_id, op_ver),
            )
            if upd_att.rowcount != 1 or upd_op.rowcount != 1:
                raise RequestConflict("DISPATCHING transition CAS lost")

            receipt = {
                "task_id": task_id,
                "operation_id": operation_id,
                "operation_state": "DISPATCHING",
                "attempt_id": attempt_id,
                "dispatch_id": dispatch_id,
                "provider_idempotency_key": provider_key,
                "fencing_token": fencing_token,
            }
            payload = canonicalize(
                {"request_id": request_id, "command_hash": fingerprint, "receipt": receipt}
            ).decode()
            db.execute(
                "INSERT INTO events(event_id,aggregate_kind,aggregate_id,aggregate_version,task_id,"
                "operation_id,actor_principal_id,event_type,schema_version,trace_id,payload_json,"
                "created_at) VALUES(?,'Operation',?,?,?,?,?,'OPERATION_DISPATCHING',1,?,?,?)",
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
            request_id, fingerprint, "normal", deadline_monotonic_ms, apply, lookup
        )
