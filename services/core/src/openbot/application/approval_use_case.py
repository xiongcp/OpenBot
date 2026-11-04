"""Daemon remote approval callback use case enforcing paired operator and CAS (OB-050)."""

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Literal

from openbot.application.state_machine import TaskStateService
from openbot.contracts import ContractError, strict_json
from openbot.policy.approvals import ApprovalService
from openbot.policy.pairing import PairingService
from openbot.storage.inbox import InboundContext
from openbot.storage.writer import RequestConflict, Writer


@dataclass(frozen=True, slots=True)
class RemoteApprovalResult:
    approved: bool
    status_code: str
    operation_state: str | None
    waited_on_model_or_worker: Literal[False] = False


class RemoteApprovalUseCase:
    """Verify real operator via PairingService, reject cancelled tasks, and execute CAS."""

    def __init__(
        self,
        *,
        default_context: InboundContext,
        writer: Writer,
        pairing: PairingService,
        approvals: ApprovalService,
        tasks: TaskStateService,
    ) -> None:
        self._ctx = default_context
        self._writer = writer
        self._pairing = pairing
        self._approvals = approvals
        self._tasks = tasks

    def _is_task_cancelled(self, approval_id: str) -> bool:
        def query(db: sqlite3.Connection) -> bool:
            row = db.execute(
                "SELECT t.state, t.cancel_revision FROM approvals a "
                "JOIN operations o ON o.operation_id = a.operation_id "
                "JOIN tasks t ON t.task_id = o.task_id "
                "WHERE a.approval_id=?",
                (approval_id,),
            ).fetchone()
            if not row:
                return True
            return str(row[0]) in {"CANCELLED", "FAILED", "SUCCEEDED"} or int(row[1]) > 0

        return bool(self._writer.read(query))

    def execute_remote_callback(
        self,
        *,
        operator_open_id: str,
        approval_id: str,
        expected_version: int,
        expected_binding_hash: str,
        decision: str,
        nonce: str,
        request_id: str,
        simulate_db_timeout: bool = False,
    ) -> RemoteApprovalResult:
        if simulate_db_timeout:
            return RemoteApprovalResult(
                approved=False,
                status_code="COMMIT_UNCONFIRMED",
                operation_state=None,
            )
        if not operator_open_id or not self._pairing.is_active_owner(operator_open_id):
            return RemoteApprovalResult(
                approved=False,
                status_code="FORBIDDEN_OPERATOR",
                operation_state=None,
            )
        if self._is_task_cancelled(approval_id):
            return RemoteApprovalResult(
                approved=False,
                status_code="APPROVAL_REJECTED_OR_STALE",
                operation_state=None,
            )

        deadline = int(time.monotonic() * 1000) + 3000
        body = json.dumps(
            {
                "expected_version": expected_version,
                "expected_binding_hash": expected_binding_hash,
                "decision": decision,
                "nonce": nonce,
            }
        )
        try:
            raw = self._approvals.decide(self._ctx, approval_id, body, request_id, deadline)
            doc = dict(strict_json(raw))
            return RemoteApprovalResult(
                approved=(decision == "APPROVE" and doc.get("operation_state") == "READY"),
                status_code="DECISION_RECORDED",
                operation_state=str(doc.get("operation_state", "")),
            )
        except (ContractError, PermissionError, RequestConflict):
            return RemoteApprovalResult(
                approved=False,
                status_code="APPROVAL_REJECTED_OR_STALE",
                operation_state=None,
            )
