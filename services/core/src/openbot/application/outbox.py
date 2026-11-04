"""Durable outbox delivery orchestration outside SQLite transactions."""

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from openbot.contracts import canonicalize, strict_json
from openbot.storage.inbox import InboundContext, authorize
from openbot.storage.outbox import (
    OutboxStore,
    append_outbox_event,
    enqueue_outbox_tx,
    event_lookup,
)
from openbot.storage.writer import LookupResult, RequestConflict, Writer, WriterCommand

type DeliveryStatus = Literal["SENT", "RETRYABLE_ERROR", "PERMANENT_ERROR", "UNKNOWN"]
type ReconcileResolution = Literal["CONFIRMED_SENT", "CONFIRMED_NOT_SENT", "MARK_DEAD"]


@dataclass(frozen=True, slots=True)
class OutboxEnvelope:
    outbox_id: str
    task_id: str | None
    target_key: str
    target: dict[str, Any]
    semantic_key: str
    revision: int
    payload: dict[str, Any]
    payload_ref: str | None
    delivery_class: str
    provider_idempotency_key: str | None
    attempt_count: int
    deadline_ms: int | None


@dataclass(frozen=True, slots=True)
class GatewaySendResult:
    status: DeliveryStatus
    provider_message_id: str | None = None
    remote_revision: int | None = None
    retry_after_ms: int | None = None
    error_code: str | None = None
    exact_once_supported: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider_message_id": self.provider_message_id,
            "remote_revision": self.remote_revision,
            "retry_after_ms": self.retry_after_ms,
            "error_code": self.error_code,
            "exact_once_supported": self.exact_once_supported,
        }


class OutboxGatewayPort(Protocol):
    """Outbound channel adapter port. Must disable internal SDK retries (sdk_max_retries == 0)."""

    sdk_max_retries: int

    def capabilities(self) -> frozenset[str]: ...
    def send(self, envelope: OutboxEnvelope) -> GatewaySendResult: ...


class OutboxService:
    """Single-owner outbox scheduling, transaction-external send, and IN_FLIGHT recovery."""

    def __init__(self, writer: Writer, store: OutboxStore) -> None:
        self._writer = writer
        self._store = store

    def enqueue(
        self,
        context: InboundContext,
        *,
        task_id: str | None = None,
        channel_account_id: str | None = None,
        target_key: str,
        target: dict[str, Any],
        semantic_key: str,
        payload: dict[str, Any],
        delivery_class: str = "UPSERT_REVISION",
        revision: int | None = None,
        provider_idempotency_key: str | None = None,
        payload_ref: str | None = None,
        not_before_ms: int | None = None,
        deadline_ms: int | None = None,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "outbox_enqueue",
                    "task": task_id,
                    "account": channel_account_id,
                    "target_key": target_key,
                    "target": target,
                    "semantic_key": semantic_key,
                    "payload": payload,
                    "delivery_class": delivery_class,
                    "revision": revision,
                    "idempotency_key": provider_idempotency_key,
                    "payload_ref": payload_ref,
                    "deadline": deadline_ms,
                    "actor": context.principal_id,
                    "profile": context.profile_id,
                    "session": context.session_id,
                    "identity": context.identity_epoch,
                    "surface": context.source_scope,
                }
            )
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return event_lookup(db, context, request_id)

        def apply(db: sqlite3.Connection) -> bytes:
            now = time.time_ns() // 1_000_000
            receipt = enqueue_outbox_tx(
                db,
                context,
                task_id=task_id,
                channel_account_id=channel_account_id,
                target_key=target_key,
                target=target,
                semantic_key=semantic_key,
                payload=payload,
                delivery_class=delivery_class,
                revision=revision,
                provider_idempotency_key=provider_idempotency_key,
                payload_ref=payload_ref,
                not_before_ms=not_before_ms,
                deadline_ms=deadline_ms,
                now_ms=now,
            )
            append_outbox_event(
                db,
                context,
                str(receipt["outbox_id"]),
                0,
                task_id,
                "OUTBOX_ENQUEUED",
                request_id,
                fingerprint,
                receipt,
                now,
            )
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "normal", deadline_monotonic_ms, apply, lookup
        )

    def complete_delivery(
        self,
        context: InboundContext,
        *,
        outbox_id: str,
        lease_token: str,
        expected_version: int,
        result: GatewaySendResult,
        max_attempts: int = 3,
        base_backoff_ms: int = 500,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        if max_attempts < 1 or base_backoff_ms < 0:
            raise ValueError("Invalid retry parameters")
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "outbox_complete",
                    "outbox_id": outbox_id,
                    "lease_token": lease_token,
                    "expected_version": expected_version,
                    "result": result.to_payload(),
                    "max_attempts": max_attempts,
                    "base_backoff_ms": base_backoff_ms,
                    "actor": context.principal_id,
                    "profile": context.profile_id,
                    "session": context.session_id,
                    "identity": context.identity_epoch,
                    "surface": context.source_scope,
                }
            )
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return event_lookup(db, context, request_id)

        def apply(db: sqlite3.Connection) -> bytes:
            authorize(db, context)
            row = db.execute(
                "SELECT task_id,target_key,semantic_key,revision,delivery_class,state,"
                "attempt_count,version,deadline,lease_token "
                "FROM outbox WHERE outbox_id=?",
                (outbox_id,),
            ).fetchone()
            if (
                not row
                or row[5] != "IN_FLIGHT"
                or int(row[7]) != expected_version
                or str(row[9]) != lease_token
            ):
                raise RequestConflict("Outbox record is not IN_FLIGHT with matching lease/version")
            task_id = None if row[0] is None else str(row[0])
            target_key, semantic_key = str(row[1]), str(row[2])
            revision = int(row[3])
            delivery_class = str(row[4])
            attempt_count = int(row[6])
            old_ver = int(row[7])
            deadline = None if row[8] is None else int(row[8])
            now = time.time_ns() // 1_000_000

            max_rev_row = db.execute(
                "SELECT coalesce(max(revision),0) FROM outbox "
                "WHERE target_key=? AND semantic_key=?",
                (target_key, semantic_key),
            ).fetchone()
            max_rev = int(max_rev_row[0]) if max_rev_row else revision
            superseded_by_higher = max_rev > revision and delivery_class == "UPSERT_REVISION"

            # Only PROVIDER_IDEMPOTENT with gateway confirmation can guarantee exact-once
            exact_once = bool(
                delivery_class == "PROVIDER_IDEMPOTENT" and result.exact_once_supported
            )
            receipt_doc: dict[str, Any] = {
                "provider_message_id": result.provider_message_id,
                "remote_revision": result.remote_revision,
                "attempt_count": attempt_count,
                "exact_once_guaranteed": exact_once,
                "superseded_by_higher_revision": superseded_by_higher,
            }

            next_not_before: int | None = None
            error_code = result.error_code
            if result.status == "SENT":
                target_state = "SUPERSEDED" if superseded_by_higher else "SENT"
            elif result.status == "RETRYABLE_ERROR":
                if superseded_by_higher:
                    target_state = "SUPERSEDED"
                else:
                    delay_ms = (
                        result.retry_after_ms
                        if result.retry_after_ms is not None
                        else base_backoff_ms * (2 ** max(0, attempt_count - 1))
                    )
                    if deadline is not None and now + delay_ms >= deadline:
                        target_state = "EXPIRED"
                        error_code = error_code or "DEADLINE_EXCEEDED"
                    elif attempt_count >= max_attempts:
                        target_state = "DEAD"
                        error_code = error_code or "MAX_ATTEMPTS_EXCEEDED"
                    else:
                        target_state = "PENDING"
                        next_not_before = now + delay_ms
                        error_code = error_code or "RETRYABLE_ERROR"
            elif result.status == "PERMANENT_ERROR":
                target_state = "DEAD"
                error_code = error_code or "PERMANENT_ERROR"
            else:
                target_state = "UNKNOWN"
                error_code = error_code or "DELIVERY_OUTCOME_UNKNOWN"

            new_ver = old_ver + 1
            upd = db.execute(
                "UPDATE outbox SET state=?,version=?,not_before=coalesce(?,not_before),"
                "claim_runtime_epoch=NULL,lease_token=NULL,lease_until=NULL,"
                "provider_receipt_json=?,error_code=?,updated_at=? "
                "WHERE outbox_id=? AND version=? AND state='IN_FLIGHT'",
                (
                    target_state,
                    new_ver,
                    next_not_before,
                    canonicalize(receipt_doc).decode(),
                    error_code,
                    now,
                    outbox_id,
                    old_ver,
                ),
            )
            if upd.rowcount != 1:
                raise RequestConflict("Outbox completion CAS conflict")

            receipt: dict[str, Any] = {
                "outbox_id": outbox_id,
                "target_key": target_key,
                "semantic_key": semantic_key,
                "revision": revision,
                "state": target_state,
                "attempt_count": attempt_count,
                "version": new_ver,
                "exact_once_guaranteed": exact_once,
                "superseded_by_higher_revision": superseded_by_higher,
                "error_code": error_code,
            }
            append_outbox_event(
                db,
                context,
                outbox_id,
                new_ver,
                task_id,
                "OUTBOX_DELIVERY_RECORDED",
                request_id,
                fingerprint,
                receipt,
                now,
            )
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "result", deadline_monotonic_ms, apply, lookup
        )

    def dispatch_next(
        self,
        context: InboundContext,
        *,
        runtime_epoch: str,
        gateway: OutboxGatewayPort,
        target_key: str | None = None,
        lease_ttl_ms: int = 10_000,
        max_attempts: int = 3,
        base_backoff_ms: int = 500,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> dict[str, Any] | None:
        if getattr(gateway, "sdk_max_retries", 0) != 0:
            raise PermissionError(
                "Gateway SDK retry must be disabled (sdk_max_retries=0); "
                "OutboxService is sole retry owner"
            )
        claim = self._store.claim_due(
            context,
            runtime_epoch=runtime_epoch,
            lease_ttl_ms=lease_ttl_ms,
            target_key=target_key,
            request_id=request_id + ":claim",
            deadline_monotonic_ms=deadline_monotonic_ms,
        )
        if claim is None:
            return None

        envelope = OutboxEnvelope(
            outbox_id=claim.outbox_id,
            task_id=claim.task_id,
            target_key=claim.target_key,
            target=claim.target,
            semantic_key=claim.semantic_key,
            revision=claim.revision,
            payload=claim.payload,
            payload_ref=claim.payload_ref,
            delivery_class=claim.delivery_class,
            provider_idempotency_key=claim.provider_idempotency_key,
            attempt_count=claim.attempt_count,
            deadline_ms=claim.deadline,
        )
        # Execute remote send strictly OUTSIDE any SQLite transaction.
        # Catch library/transport exceptions so outbox consumers never re-run business operations.
        try:
            send_result = gateway.send(envelope)
        except Exception:
            fallback_status: DeliveryStatus = (
                "RETRYABLE_ERROR"
                if claim.delivery_class in {"UPSERT_REVISION", "PROVIDER_IDEMPOTENT"}
                else "UNKNOWN"
            )
            send_result = GatewaySendResult(
                status=fallback_status,
                error_code="GATEWAY_TRANSPORT_EXCEPTION",
                retry_after_ms=base_backoff_ms,
                exact_once_supported=False,
            )

        raw = self._writer.submit(
            self.complete_delivery(
                context,
                outbox_id=claim.outbox_id,
                lease_token=claim.lease_token,
                expected_version=claim.version,
                result=send_result,
                max_attempts=max_attempts,
                base_backoff_ms=base_backoff_ms,
                request_id=request_id + ":complete",
                deadline_monotonic_ms=deadline_monotonic_ms,
            )
        ).result(
            timeout=max(0.001, (deadline_monotonic_ms - time.monotonic() * 1000) / 1000 + 0.05)
        )
        return dict(strict_json(raw))

    def recover_in_flight(
        self,
        context: InboundContext,
        *,
        runtime_epoch: str,
        max_attempts: int = 3,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "outbox_recover_in_flight",
                    "epoch": runtime_epoch,
                    "max_attempts": max_attempts,
                    "actor": context.principal_id,
                    "profile": context.profile_id,
                    "session": context.session_id,
                    "identity": context.identity_epoch,
                    "surface": context.source_scope,
                }
            )
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return event_lookup(db, context, request_id)

        def apply(db: sqlite3.Connection) -> bytes:
            authorize(db, context)
            prof = db.execute(
                "SELECT active_runtime_epoch FROM profile_config WHERE singleton=1"
            ).fetchone()
            inst = db.execute(
                "SELECT state FROM runtime_instances WHERE runtime_epoch=?", (runtime_epoch,)
            ).fetchone()
            if not prof or prof[0] != runtime_epoch or inst != ("ACTIVE",):
                raise PermissionError("Runtime epoch is not active for outbox recovery")

            now = time.time_ns() // 1_000_000
            rows = db.execute(
                "SELECT outbox_id,target_key,semantic_key,revision,delivery_class,attempt_count,"
                "version,deadline,claim_runtime_epoch FROM outbox WHERE state='IN_FLIGHT' "
                "ORDER BY created_at,outbox_id"
            ).fetchall()

            requeued_ids: list[str] = []
            superseded_ids: list[str] = []
            unknown_ids: list[str] = []
            dead_or_expired_ids: list[str] = []

            for r in rows:
                oid, t_key, s_key, rev, d_class, attempts, ver, deadline, old_epoch = (
                    str(r[0]),
                    str(r[1]),
                    str(r[2]),
                    int(r[3]),
                    str(r[4]),
                    int(r[5]),
                    int(r[6]),
                    None if r[7] is None else int(r[7]),
                    str(r[8]),
                )
                old_inst = db.execute(
                    "SELECT state FROM runtime_instances WHERE runtime_epoch=?", (old_epoch,)
                ).fetchone()
                if old_inst != ("STOPPED",):
                    raise PermissionError(
                        f"Claiming runtime_epoch {old_epoch} is not proven STOPPED"
                    )

                max_rev_row = db.execute(
                    "SELECT coalesce(max(revision),0) FROM outbox "
                    "WHERE target_key=? AND semantic_key=?",
                    (t_key, s_key),
                ).fetchone()
                max_rev = int(max_rev_row[0]) if max_rev_row else rev

                if d_class == "UPSERT_REVISION" and max_rev > rev:
                    next_state = "SUPERSEDED"
                    err = None
                    superseded_ids.append(oid)
                elif d_class in {"UPSERT_REVISION", "PROVIDER_IDEMPOTENT"}:
                    if deadline is not None and now >= deadline:
                        next_state = "EXPIRED"
                        err = "DEADLINE_EXCEEDED"
                        dead_or_expired_ids.append(oid)
                    elif attempts >= max_attempts:
                        next_state = "DEAD"
                        err = "MAX_ATTEMPTS_EXCEEDED"
                        dead_or_expired_ids.append(oid)
                    else:
                        next_state = "PENDING"
                        err = "RECOVERED_IN_FLIGHT"
                        requeued_ids.append(oid)
                else:
                    next_state = "UNKNOWN"
                    err = "IN_FLIGHT_OUTCOME_UNKNOWN"
                    unknown_ids.append(oid)

                db.execute(
                    "UPDATE outbox SET state=?,version=?,claim_runtime_epoch=NULL,"
                    "lease_token=NULL,lease_until=NULL,error_code=?,updated_at=? "
                    "WHERE outbox_id=? AND version=? AND state='IN_FLIGHT'",
                    (next_state, ver + 1, err, now, oid, ver),
                )

            receipt: dict[str, Any] = {
                "runtime_epoch": runtime_epoch,
                "requeued_ids": requeued_ids,
                "superseded_ids": superseded_ids,
                "unknown_ids": unknown_ids,
                "dead_or_expired_ids": dead_or_expired_ids,
            }
            append_outbox_event(
                db,
                context,
                f"out_rec_{runtime_epoch}",
                1,
                None,
                "OUTBOX_RECOVERED",
                request_id,
                fingerprint,
                receipt,
                now,
            )
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "result", deadline_monotonic_ms, apply, lookup
        )

    def reconcile_unknown(
        self,
        context: InboundContext,
        *,
        outbox_id: str,
        expected_version: int,
        resolution: ReconcileResolution,
        provider_receipt: dict[str, Any] | None = None,
        max_attempts: int = 3,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        if resolution == "CONFIRMED_SENT" and not provider_receipt:
            raise ValueError("CONFIRMED_SENT requires verified provider_receipt")
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "outbox_reconcile_unknown",
                    "outbox_id": outbox_id,
                    "expected_version": expected_version,
                    "resolution": resolution,
                    "receipt": provider_receipt,
                    "actor": context.principal_id,
                    "profile": context.profile_id,
                    "session": context.session_id,
                    "identity": context.identity_epoch,
                    "surface": context.source_scope,
                }
            )
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return event_lookup(db, context, request_id)

        def apply(db: sqlite3.Connection) -> bytes:
            authorize(db, context)
            row = db.execute(
                "SELECT task_id,target_key,semantic_key,revision,delivery_class,state,"
                "attempt_count,version,deadline FROM outbox WHERE outbox_id=?",
                (outbox_id,),
            ).fetchone()
            if not row or row[5] != "UNKNOWN" or int(row[7]) != expected_version:
                raise RequestConflict("Outbox record is not in UNKNOWN at expected_version")
            task_id = None if row[0] is None else str(row[0])
            t_key, s_key = str(row[1]), str(row[2])
            rev = int(row[3])
            d_class = str(row[4])
            attempts = int(row[6])
            old_ver = int(row[7])
            deadline = None if row[8] is None else int(row[8])
            now = time.time_ns() // 1_000_000

            max_sent_row = db.execute(
                "SELECT coalesce(max(revision),0) FROM outbox "
                "WHERE target_key=? AND semantic_key=? AND state='SENT'",
                (t_key, s_key),
            ).fetchone()
            max_sent = int(max_sent_row[0]) if max_sent_row else 0
            exact_once = bool(
                d_class == "PROVIDER_IDEMPOTENT"
                and provider_receipt is not None
                and provider_receipt.get("exact_once_guaranteed") is True
            )

            receipt_json: str | None = None
            err: str | None = None
            if resolution == "CONFIRMED_SENT":
                target_state = "SUPERSEDED" if max_sent > rev else "SENT"
                doc = dict(provider_receipt or {}) | {"exact_once_guaranteed": exact_once}
                receipt_json = canonicalize(doc).decode()
            elif resolution == "CONFIRMED_NOT_SENT":
                if deadline is not None and now >= deadline:
                    target_state = "EXPIRED"
                    err = "DEADLINE_EXCEEDED"
                elif attempts >= max_attempts:
                    target_state = "DEAD"
                    err = "MAX_ATTEMPTS_EXCEEDED"
                else:
                    target_state = "PENDING"
            else:
                target_state = "DEAD"
                err = "RECONCILED_DEAD"

            new_ver = old_ver + 1
            upd = db.execute(
                "UPDATE outbox SET state=?,version=?,"
                "provider_receipt_json=coalesce(?,provider_receipt_json),"
                "error_code=?,updated_at=? WHERE outbox_id=? AND version=? AND state='UNKNOWN'",
                (target_state, new_ver, receipt_json, err, now, outbox_id, old_ver),
            )
            if upd.rowcount != 1:
                raise RequestConflict("Outbox reconcile CAS conflict")

            receipt: dict[str, Any] = {
                "outbox_id": outbox_id,
                "state": target_state,
                "version": new_ver,
                "exact_once_guaranteed": exact_once,
            }
            append_outbox_event(
                db,
                context,
                outbox_id,
                new_ver,
                task_id,
                "OUTBOX_RECONCILED",
                request_id,
                fingerprint,
                receipt,
                now,
            )
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "result", deadline_monotonic_ms, apply, lookup
        )
