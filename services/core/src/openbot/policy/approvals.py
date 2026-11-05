"""One-way approval decisions. Approval does not execute an operation."""

import hashlib
import hmac
import sqlite3
import time

from openbot.application.operations import (
    PROPOSAL_TTL_MS,
    ChallengeStore,
    advance_task,
    clock_now,
    command_lookup,
    load_proposal,
    task_record,
)
from openbot.contracts import SchemaRegistry, canonicalize, strict_json
from openbot.domain.clock import ClockSnapshot, grant_valid
from openbot.storage.inbox import InboundContext, emit_state
from openbot.storage.writer import LookupResult, RequestConflict, Writer, WriterCommand


class ApprovalService:
    def __init__(self, writer: Writer, challenges: ChallengeStore, registry: SchemaRegistry):
        self._writer, self._challenges, self._registry = writer, challenges, registry

    def decide(
        self,
        context: InboundContext,
        approval_id: str,
        raw: str | bytes,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> bytes:
        if context.channel != "local":
            raise PermissionError("Remote approval preview and identity gates are unavailable")
        decision = self._registry.validate("approval-decision.schema.json", raw).value()
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "approval-decision",
                    "approval": approval_id,
                    "actor": context.principal_id,
                    "profile": context.profile_id,
                    "session": context.session_id,
                    "identity": context.identity_epoch,
                    "surface": context.source_scope,
                    "decision": decision,
                }
            )
        ).hexdigest()
        # Never perform protected-store I/O while the writer owns a transaction.
        nonce = self._challenges.get(approval_id)

        def details(db: sqlite3.Connection) -> tuple[str, str]:
            row = db.execute(
                "SELECT a.operation_id,o.task_id FROM approvals a JOIN operations o "
                "ON o.operation_id=a.operation_id WHERE a.approval_id=?",
                (approval_id,),
            ).fetchone()
            if not row:
                raise PermissionError("Approval unavailable")
            task_record(db, context, row[1])
            return str(row[0]), str(row[1])

        operation_id, task_id = self._writer.read(details)

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return command_lookup(db, context, task_id, request_id)

        def apply(db: sqlite3.Connection) -> bytes:
            state, task_version, cancelled = task_record(db, context, task_id)
            proposal = load_proposal(db, context, operation_id, self._registry).value()
            row = db.execute(
                "SELECT status,version,nonce_hash,actor_scope_json FROM approvals "
                "WHERE approval_id=?",
                (approval_id,),
            ).fetchone()
            assert row is not None
            if row[0] != "PENDING" or row[1] + 1 != decision["expected_version"]:
                raise RequestConflict("Approval is no longer the expected pending version")
            if decision["expected_binding_hash"] != proposal["binding_hash"]:
                raise PermissionError("Approval binding changed")
            scope = strict_json(row[3])
            expected_scope = (
                context.profile_id,
                context.session_id,
                context.channel,
                context.tenant_id,
                context.app_id,
            )
            if (
                tuple(
                    scope.get(k)
                    for k in ("profile_id", "session_id", "channel", "tenant_id", "app_id")
                )
                != expected_scope
            ):
                raise PermissionError("Approval authenticated surface mismatch")
            if cancelled or state != "WAITING_APPROVAL":
                raise PermissionError("Task is cancelled or not awaiting this approval")
            policy = db.execute(
                "SELECT policy_version FROM profile_config WHERE singleton=1"
            ).fetchone()[0]
            generation = db.execute(
                "SELECT generation FROM workspaces WHERE workspace_id=?", (context.workspace_id,)
            ).fetchone()[0]
            tool = db.execute(
                "SELECT manifest_digest FROM tool_registry WHERE tool_id=? AND status='ACTIVE'",
                (proposal["tool"]["name"],),
            ).fetchone()
            if (
                proposal["identity_epoch"] != context.identity_epoch
                or proposal["policy_version"] != "policy-" + str(policy)
                or generation != proposal["resource_snapshot"]["workspace_generation"]
                or tool != (proposal["tool"]["manifest_digest"][7:],)
            ):
                raise PermissionError("Approval policy/identity/resource/tool changed")
            now = clock_now()
            issued = ClockSnapshot(
                scope["issued_utc_ms"], scope["issued_monotonic_ms"], scope["authority_instance"]
            )
            if (
                not grant_valid(issued, now, PROPOSAL_TTL_MS)
                or now.utc_ms >= proposal["expires_at_ms"]
            ):
                raise PermissionError("Approval expired or time authority is unavailable")
            if nonce is not None and (
                type(nonce) is not bytes
                or not hmac.compare_digest(hashlib.sha256(nonce).hexdigest(), row[2])
                or not hmac.compare_digest(nonce, decision["nonce"].encode())
                or "sha256:" + row[2] != proposal["approval_nonce_hash"]
            ):
                raise PermissionError("Approval nonce mismatch")
            approved = nonce is not None and decision["decision"] == "APPROVE"
            status = "REVOKED" if nonce is None else "APPROVED" if approved else "DENIED"
            op_state = "READY" if approved else "REVOKED" if nonce is None else "REJECTED"
            changed = db.execute(
                "UPDATE approvals SET status=?,version=version+1,decided_by=?,decided_at=? "
                "WHERE approval_id=? AND version=? AND status='PENDING'",
                (
                    status,
                    None if nonce is None else context.principal_id,
                    None if nonce is None else now.utc_ms,
                    approval_id,
                    row[1],
                ),
            )
            if changed.rowcount != 1:
                raise RequestConflict("Approval CAS lost")
            changed = db.execute(
                "UPDATE operations SET state=?,version=version+1,updated_at=?,completed_at=? "
                "WHERE operation_id=? AND state='AWAITING_APPROVAL'",
                (op_state, now.utc_ms, None if approved else now.utc_ms, operation_id),
            )
            if changed.rowcount != 1:
                raise RequestConflict("Operation is no longer awaiting approval")
            advance_task(db, task_id, task_version, "QUEUED", now.utc_ms)
            receipt = {
                "task_id": task_id,
                "state": "QUEUED",
                "version": task_version + 1,
                "operation_id": operation_id,
                "operation_state": op_state,
                "approval_id": approval_id,
                "approval_status": status,
                "approval_version": row[1] + 2,
            }
            emit_state(
                db,
                context,
                receipt,
                request_id,
                fingerprint,
                "APPROVAL_DECIDED",
                now.utc_ms,
                operation_id,
            )
            return canonicalize(receipt)

        result = self._writer.submit(
            WriterCommand(request_id, fingerprint, "approval", deadline_monotonic_ms, apply, lookup)
        ).result(
            timeout=min(
                300.0, max(0.001, (deadline_monotonic_ms - time.monotonic() * 1000) / 1000 + 0.05)
            )
        )
        if strict_json(result)["approval_status"] == "REVOKED":
            raise PermissionError(
                "CHALLENGE_UNAVAILABLE: old approval revoked; create a new operation"
            )
        return result
