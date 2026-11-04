"""Controlled message.send use case bound to immutable draft hash, account, and recipient."""

import hashlib
import secrets
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from openbot.application.dispatch import DispatchService
from openbot.application.operations import OperationService, load_proposal
from openbot.application.resources import ResourceRequest
from openbot.artifacts.store import ArtifactStore
from openbot.contracts import canonicalize, strict_json
from openbot.policy.egress import EgressGuard, EgressRequest
from openbot.storage.inbox import InboundContext, authorize
from openbot.storage.writer import LookupResult, Writer, WriterCommand
from openbot.tools.messages.draft import MessageDraftService


@dataclass(frozen=True, slots=True)
class MessageSendEnvelope:
    operation_id: str
    attempt_id: str
    dispatch_id: str
    account_id: str
    recipient_id: str
    draft_artifact_id: str
    draft_sha256: str
    body_text: str


@dataclass(frozen=True, slots=True)
class MessageSendResult:
    status: Literal["SENT", "FAILED", "UNKNOWN"]
    provider_message_id: str | None = None
    error_code: str | None = None


class MessageSendTransportPort(Protocol):
    qualified: bool

    def send_message(self, envelope: MessageSendEnvelope) -> MessageSendResult: ...


class MessageSendService:
    """Broker-gated message.send with draft/recipient binding and RECONCILE_ONLY semantics."""

    def __init__(
        self,
        writer: Writer,
        operations: OperationService,
        dispatcher: DispatchService,
        drafts: MessageDraftService,
        artifacts: ArtifactStore,
        egress: EgressGuard,
    ) -> None:
        self._writer = writer
        self._operations = operations
        self._dispatcher = dispatcher
        self._drafts = drafts
        self._artifacts = artifacts
        self._egress = egress

    def propose_send(
        self,
        context: InboundContext,
        *,
        task_id: str,
        draft_artifact_id: str,
        draft_sha256: str,
        account_id: str,
        recipient_id: str,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> dict[str, Any]:
        if not self._drafts.verify_latest_draft_binding(context, draft_artifact_id, draft_sha256):
            raise PermissionError("Stale or unverified message draft hash cannot be proposed")
        args_json = canonicalize(
            {
                "draft_artifact_id": draft_artifact_id,
                "draft_sha256": draft_sha256,
                "account_id": account_id,
                "recipient_id": recipient_id,
            }
        ).decode()
        raw = self._operations.propose(
            context,
            task_id,
            "message.send",
            args_json,
            {"workspace_generation": 1, "files": []},
            "WORKSPACE",
            {
                "kind": "MESSAGE_RECIPIENT",
                "resource_ref": recipient_id,
                "account_ref": account_id,
            },
            request_id,
            deadline_monotonic_ms,
        )
        return dict(strict_json(raw))

    def execute_approved_send(
        self,
        context: InboundContext,
        *,
        operation_id: str,
        runtime_epoch: str,
        executor_id: str,
        transport: MessageSendTransportPort,
        caller_recipient_id: str,
        is_owner_progress_only_grant: bool = False,
        destination_url: str = "https://open.feishu.cn/open-apis/im/v1/messages",
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> dict[str, Any]:
        if is_owner_progress_only_grant:
            raise PermissionError(
                "Ordinary owner_progress grant cannot authorize third-party message.send"
            )
        if not getattr(transport, "qualified", False):
            raise PermissionError(
                "CAPABILITY_UNAVAILABLE: message send adapter is not qualified for this environment"
            )

        # Verify bound proposal arguments and latest draft hash BEFORE claiming or dispatching
        def inspect_bound(db: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
            doc = load_proposal(db, context, operation_id, self._operations._registry).value()
            return str(doc["task_id"]), dict(doc["args"])

        task_id, bound_args = self._writer.read(inspect_bound)
        if caller_recipient_id != bound_args["recipient_id"]:
            raise PermissionError("Caller recipient_id does not match approved proposal binding")
        if not self._drafts.verify_latest_draft_binding(
            context, str(bound_args["draft_artifact_id"]), str(bound_args["draft_sha256"])
        ):
            raise PermissionError("Approved draft hash is stale or modified; refusing to send")

        eg_dec = self._egress.evaluate(
            EgressRequest(
                surface="MESSAGE_TOOL",
                task_network_mode="CONNECTED",
                data_class="WORKSPACE",
                destination_url=destination_url,
            )
        )
        if eg_dec.decision == "DENY":
            raise PermissionError(f"Egress denied for message.send: {eg_dec.reason_code}")

        draft_dl = self._artifacts.download(context, str(bound_args["draft_artifact_id"]))
        draft_doc = dict(strict_json(draft_dl.data))

        # Short transaction 1: claim
        claimed = dict(
            strict_json(
                self._writer.submit(
                    self._dispatcher.claim(
                        context,
                        operation_id,
                        runtime_epoch,
                        executor_id,
                        [ResourceRequest("WORKSPACE", context.workspace_id, expected_generation=1)],
                        30_000,
                        request_id + ":claim",
                        deadline_monotonic_ms,
                    )
                ).result(timeout=5)
            )
        )
        att_id = str(claimed["attempt_id"])
        disp_id = str(claimed["dispatch_id"])

        # Short transaction 2: begin_dispatch
        self._writer.submit(
            self._dispatcher.begin_dispatch(
                context,
                operation_id,
                att_id,
                runtime_epoch,
                executor_id,
                request_id + ":dispatch",
                deadline_monotonic_ms,
            )
        ).result(timeout=5)

        envelope = MessageSendEnvelope(
            operation_id=operation_id,
            attempt_id=att_id,
            dispatch_id=disp_id,
            account_id=str(bound_args["account_id"]),
            recipient_id=str(bound_args["recipient_id"]),
            draft_artifact_id=str(bound_args["draft_artifact_id"]),
            draft_sha256=str(bound_args["draft_sha256"]),
            body_text=str(draft_doc["body_text"]),
        )
        try:
            send_res = transport.send_message(envelope)
        except Exception:
            send_res = MessageSendResult(status="UNKNOWN", error_code="CONNECTION_LOST_AFTER_SEND")

        return self._record_send_outcome(
            context,
            task_id=task_id,
            operation_id=operation_id,
            attempt_id=att_id,
            result=send_res,
            request_id=request_id + ":outcome",
            deadline_monotonic_ms=deadline_monotonic_ms,
        )

    def _record_send_outcome(
        self,
        context: InboundContext,
        *,
        task_id: str,
        operation_id: str,
        attempt_id: str,
        result: MessageSendResult,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> dict[str, Any]:
        fp = hashlib.sha256(
            canonicalize({"req": request_id, "op": operation_id, "status": result.status})
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return None

        def apply(db: sqlite3.Connection) -> bytes:
            authorize(db, context)
            now = time.time_ns() // 1_000_000
            op_ver = int(
                db.execute(
                    "SELECT version FROM operations WHERE operation_id=?", (operation_id,)
                ).fetchone()[0]
            )
            t_row = db.execute(
                "SELECT state,version FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            assert t_row is not None
            t_state, t_ver = str(t_row[0]), int(t_row[1])

            if result.status == "SENT":
                rec_json = canonicalize(
                    {"provider_message_id": result.provider_message_id}
                ).decode()
                db.execute(
                    "UPDATE resource_leases SET holder_attempt_id=NULL,runtime_epoch=NULL,"
                    "state='RELEASED',acquired_at=NULL,expires_at=NULL,version=version+1,"
                    "updated_at=? WHERE holder_attempt_id=? AND state='HELD'",
                    (now, attempt_id),
                )
                db.execute(
                    "UPDATE operation_attempts SET status='SUCCEEDED',receipt_json=?,"
                    "finished_at=?,version=version+1 WHERE attempt_id=?",
                    (rec_json, now, attempt_id),
                )
                db.execute(
                    "UPDATE operations SET state='SUCCEEDED',completed_at=?,updated_at=?,"
                    "version=? WHERE operation_id=?",
                    (now, now, op_ver + 1, operation_id),
                )
                out_op_state = "SUCCEEDED"
                out_t_state = t_state
            else:
                # Keep lease held as quarantine and transition Operation -> UNKNOWN
                db.execute(
                    "UPDATE operation_attempts SET status='UNKNOWN',error_code=?,version=version+1 "
                    "WHERE attempt_id=?",
                    (result.error_code or "SEND_OUTCOME_UNKNOWN", attempt_id),
                )
                db.execute(
                    "UPDATE operations SET state='UNKNOWN',unknown_reason='send_outcome_unknown',"
                    "updated_at=?,version=? WHERE operation_id=?",
                    (now, op_ver + 1, operation_id),
                )
                if t_state == "RUNNING":
                    db.execute(
                        "UPDATE tasks SET state='RECONCILING',version=version+1,updated_at=? "
                        "WHERE task_id=? AND version=?",
                        (now, task_id, t_ver),
                    )
                    out_t_state = "RECONCILING"
                else:
                    out_t_state = t_state
                out_op_state = "UNKNOWN"

            receipt: dict[str, Any] = {
                "task_id": task_id,
                "operation_id": operation_id,
                "attempt_id": attempt_id,
                "operation_state": out_op_state,
                "task_state": out_t_state,
            }
            db.execute(
                "INSERT INTO events(event_id,aggregate_kind,aggregate_id,aggregate_version,task_id,"
                "operation_id,actor_principal_id,event_type,schema_version,trace_id,payload_json,"
                "created_at) VALUES(?,'Operation',?,?,?,?,?,'MESSAGE_SEND_RECORDED',1,?,?,?)",
                (
                    "evt_" + secrets.token_hex(16),
                    operation_id,
                    op_ver + 1,
                    task_id,
                    operation_id,
                    context.principal_id,
                    "trc_" + secrets.token_hex(16),
                    canonicalize(receipt).decode(),
                    now,
                ),
            )
            return canonicalize(receipt)

        raw = self._writer.submit(
            WriterCommand(request_id, fp, "result", deadline_monotonic_ms, apply, lookup)
        ).result(timeout=5)
        return dict(strict_json(raw))
