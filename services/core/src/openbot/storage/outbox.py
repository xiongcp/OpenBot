"""Durable outbox storage primitives with revision coalescing and terminal state guards."""

import hashlib
import secrets
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from openbot.contracts import canonicalize, strict_json
from openbot.storage.inbox import InboundContext, authorize
from openbot.storage.writer import LookupResult, RequestConflict, Writer, WriterCommand

DELIVERY_CLASSES = frozenset({"UPSERT_REVISION", "PROVIDER_IDEMPOTENT", "RECONCILE_ONLY"})
OUTBOX_STATES = frozenset(
    {"PENDING", "IN_FLIGHT", "SENT", "UNKNOWN", "DEAD", "EXPIRED", "SUPERSEDED"}
)
TERMINAL_TASK_STATES = frozenset({"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"})


def is_terminal_payload(payload: dict[str, Any]) -> bool:
    return bool(payload.get("terminal") is True or payload.get("state") in TERMINAL_TASK_STATES)


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    outbox_id: str
    task_id: str | None
    channel_account_id: str | None
    target_key: str
    target: dict[str, Any]
    semantic_key: str
    revision: int
    payload_ref: str | None
    payload: dict[str, Any]
    delivery_class: str
    provider_idempotency_key: str | None
    state: str
    attempt_count: int
    version: int
    not_before: int
    deadline: int | None
    claim_runtime_epoch: str | None
    lease_token: str | None
    lease_until: int | None
    provider_receipt: dict[str, Any] | None
    error_code: str | None
    created_at: int
    updated_at: int


@dataclass(frozen=True, slots=True)
class OutboxClaim:
    outbox_id: str
    task_id: str | None
    channel_account_id: str | None
    target_key: str
    target: dict[str, Any]
    semantic_key: str
    revision: int
    payload_ref: str | None
    payload: dict[str, Any]
    delivery_class: str
    provider_idempotency_key: str | None
    attempt_count: int
    version: int
    deadline: int | None
    claim_runtime_epoch: str
    lease_token: str
    lease_until: int


def _row_to_record(row: tuple[Any, ...]) -> OutboxRecord:
    return OutboxRecord(
        outbox_id=str(row[0]),
        task_id=None if row[1] is None else str(row[1]),
        channel_account_id=None if row[2] is None else str(row[2]),
        target_key=str(row[3]),
        target=strict_json(str(row[4])),
        semantic_key=str(row[5]),
        revision=int(row[6]),
        payload_ref=None if row[7] is None else str(row[7]),
        payload=strict_json(str(row[8])),
        delivery_class=str(row[9]),
        provider_idempotency_key=None if row[10] is None else str(row[10]),
        state=str(row[11]),
        attempt_count=int(row[12]),
        version=int(row[13]),
        not_before=int(row[14]),
        deadline=None if row[15] is None else int(row[15]),
        claim_runtime_epoch=None if row[16] is None else str(row[16]),
        lease_token=None if row[17] is None else str(row[17]),
        lease_until=None if row[18] is None else int(row[18]),
        provider_receipt=None if row[19] is None else strict_json(str(row[19])),
        error_code=None if row[20] is None else str(row[20]),
        created_at=int(row[21]),
        updated_at=int(row[22]),
    )


def event_lookup(
    db: sqlite3.Connection, context: InboundContext, request_id: str
) -> LookupResult | None:
    authorize(db, context)
    row = db.execute(
        "SELECT actor_principal_id,payload_json FROM events "
        "WHERE json_extract(payload_json,'$.request_id')=?",
        (request_id,),
    ).fetchone()
    if row is None:
        return None
    if row[0] != context.principal_id:
        raise PermissionError("Request belongs to another principal")
    val = strict_json(str(row[1]))
    if val.get("source_scope") not in (None, context.source_scope):
        raise PermissionError("Request belongs to another source scope")
    return LookupResult(str(val["command_hash"]), canonicalize(val["receipt"]))


def append_outbox_event(
    db: sqlite3.Connection,
    context: InboundContext,
    outbox_id: str,
    outbox_version: int,
    task_id: str | None,
    event_type: str,
    request_id: str,
    fingerprint: str,
    receipt: dict[str, Any],
    now: int,
) -> None:
    payload = canonicalize(
        {
            "request_id": request_id,
            "command_hash": fingerprint,
            "source_scope": context.source_scope,
            "receipt": receipt,
        }
    ).decode()
    db.execute(
        "INSERT INTO events(event_id,aggregate_kind,aggregate_id,aggregate_version,task_id,"
        "actor_principal_id,event_type,schema_version,trace_id,payload_json,created_at) "
        "VALUES(?,'Outbox',?,?,?,?,?,1,?,?,?)",
        (
            "evt_" + secrets.token_hex(16),
            outbox_id,
            outbox_version,
            task_id,
            context.principal_id,
            event_type,
            "trc_" + hashlib.sha256(request_id.encode()).hexdigest()[:32],
            payload,
            now,
        ),
    )


def enqueue_outbox_tx(
    db: sqlite3.Connection,
    context: InboundContext,
    *,
    task_id: str | None,
    channel_account_id: str | None,
    target_key: str,
    target: dict[str, Any],
    semantic_key: str,
    payload: dict[str, Any],
    delivery_class: str,
    revision: int | None = None,
    provider_idempotency_key: str | None = None,
    payload_ref: str | None = None,
    not_before_ms: int | None = None,
    deadline_ms: int | None = None,
    now_ms: int,
) -> dict[str, Any]:
    authorize(db, context)
    if task_id is not None:
        t_row = db.execute("SELECT owner_id FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not t_row or t_row[0] != context.principal_id:
            raise PermissionError("Task scope mismatch for outbox enqueue")
    if not target_key.strip() or not semantic_key.strip():
        raise ValueError("target_key and semantic_key must be non-empty")
    if delivery_class not in DELIVERY_CLASSES:
        raise ValueError(f"Unsupported delivery_class: {delivery_class}")
    if delivery_class == "PROVIDER_IDEMPOTENT" and (
        provider_idempotency_key is None or not provider_idempotency_key.strip()
    ):
        raise ValueError("PROVIDER_IDEMPOTENT requires provider_idempotency_key")

    existing = db.execute(
        "SELECT revision,payload_json,state FROM outbox "
        "WHERE target_key=? AND semantic_key=? ORDER BY revision",
        (target_key, semantic_key),
    ).fetchall()
    max_rev = max((int(r[0]) for r in existing), default=0)
    has_terminal = any(
        is_terminal_payload(strict_json(str(r[1])))
        for r in existing
        if str(r[2]) in {"PENDING", "IN_FLIGHT", "SENT", "UNKNOWN"}
    )
    incoming_terminal = is_terminal_payload(payload)
    if has_terminal and not incoming_terminal:
        raise RequestConflict("Non-terminal progress cannot overwrite terminal outbox state")

    assigned_rev = max_rev + 1 if revision is None else int(revision)
    if assigned_rev <= 0:
        raise ValueError("Outbox revision must be positive")
    if any(int(r[0]) == assigned_rev for r in existing):
        raise RequestConflict("Duplicate outbox revision for target_key and semantic_key")

    initial_state = (
        "SUPERSEDED"
        if (assigned_rev < max_rev and delivery_class == "UPSERT_REVISION")
        else "PENDING"
    )
    if initial_state == "PENDING" and delivery_class == "UPSERT_REVISION":
        db.execute(
            "UPDATE outbox SET state='SUPERSEDED',version=version+1,updated_at=? "
            "WHERE target_key=? AND semantic_key=? AND state='PENDING' AND revision<?",
            (now_ms, target_key, semantic_key, assigned_rev),
        )

    outbox_id = "out_" + secrets.token_hex(16)
    nb = now_ms if not_before_ms is None else int(not_before_ms)
    db.execute(
        "INSERT INTO outbox("
        "outbox_id,task_id,channel_account_id,target_key,target_json,semantic_key,revision,"
        "payload_ref,payload_json,delivery_class,provider_idempotency_key,state,attempt_count,"
        "version,not_before,deadline,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,0,?,?,?,?)",
        (
            outbox_id,
            task_id,
            channel_account_id,
            target_key,
            canonicalize(target).decode(),
            semantic_key,
            assigned_rev,
            payload_ref,
            canonicalize(payload).decode(),
            delivery_class,
            provider_idempotency_key,
            initial_state,
            nb,
            deadline_ms,
            now_ms,
            now_ms,
        ),
    )
    return {
        "outbox_id": outbox_id,
        "target_key": target_key,
        "semantic_key": semantic_key,
        "revision": assigned_rev,
        "state": initial_state,
        "version": 0,
    }


class OutboxStore:
    """Authoritative SQLite persistence for outbox state transitions."""

    def __init__(self, writer: Writer) -> None:
        self._writer = writer

    def claim_due(
        self,
        context: InboundContext,
        *,
        runtime_epoch: str,
        lease_ttl_ms: int,
        target_key: str | None = None,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> OutboxClaim | None:
        if lease_ttl_ms <= 0:
            raise ValueError("lease_ttl_ms must be positive")
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "outbox_claim_due",
                    "epoch": runtime_epoch,
                    "target_key": target_key,
                    "ttl": lease_ttl_ms,
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
                raise PermissionError("Runtime epoch is not active for outbox claim")
            now = time.time_ns() // 1_000_000

            # 1. Expire past-deadline PENDING rows
            db.execute(
                "UPDATE outbox SET state='EXPIRED',error_code='DEADLINE_EXCEEDED',"
                "version=version+1,updated_at=? "
                "WHERE state='PENDING' AND deadline IS NOT NULL AND deadline<=?",
                (now, now),
            )
            # 2. Coalesce superseded UPSERT_REVISION PENDING rows
            db.execute(
                "UPDATE outbox SET state='SUPERSEDED',version=version+1,updated_at=? "
                "WHERE state='PENDING' AND delivery_class='UPSERT_REVISION' AND revision < ("
                "SELECT max(newer.revision) FROM outbox newer "
                "WHERE newer.target_key=outbox.target_key "
                "AND newer.semantic_key=outbox.semantic_key)",
                (now,),
            )

            # 3. Select oldest due PENDING row not blocked by IN_FLIGHT/UNKNOWN on same key
            sql = (
                "SELECT outbox_id,task_id,channel_account_id,target_key,target_json,semantic_key,"
                "revision,payload_ref,payload_json,delivery_class,provider_idempotency_key,"
                "attempt_count,version,deadline FROM outbox o "
                "WHERE o.state='PENDING' AND o.not_before<=? "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM outbox b WHERE b.target_key=o.target_key "
                "  AND b.semantic_key=o.semantic_key AND b.state IN ('IN_FLIGHT','UNKNOWN')"
                ") "
            )
            params: list[Any] = [now]
            if target_key is not None:
                sql += "AND o.target_key=? "
                params.append(target_key)
            sql += "ORDER BY o.not_before,o.created_at,o.revision LIMIT 1"
            row = db.execute(sql, tuple(params)).fetchone()
            if row is None:
                return canonicalize({"claimed": None})

            outbox_id = str(row[0])
            old_ver = int(row[12])
            new_attempts = int(row[11]) + 1
            new_ver = old_ver + 1
            lease_token = "ols_" + secrets.token_hex(16)
            lease_until = now + lease_ttl_ms
            upd = db.execute(
                "UPDATE outbox SET state='IN_FLIGHT',attempt_count=?,version=?,"
                "claim_runtime_epoch=?,lease_token=?,lease_until=?,updated_at=? "
                "WHERE outbox_id=? AND version=? AND state='PENDING'",
                (
                    new_attempts,
                    new_ver,
                    runtime_epoch,
                    lease_token,
                    lease_until,
                    now,
                    outbox_id,
                    old_ver,
                ),
            )
            if upd.rowcount != 1:
                raise RequestConflict("Outbox claim CAS conflict")

            claim_dict: dict[str, Any] = {
                "outbox_id": outbox_id,
                "task_id": row[1],
                "channel_account_id": row[2],
                "target_key": str(row[3]),
                "target": strict_json(str(row[4])),
                "semantic_key": str(row[5]),
                "revision": int(row[6]),
                "payload_ref": row[7],
                "payload": strict_json(str(row[8])),
                "delivery_class": str(row[9]),
                "provider_idempotency_key": row[10],
                "attempt_count": new_attempts,
                "version": new_ver,
                "deadline": None if row[13] is None else int(row[13]),
                "claim_runtime_epoch": runtime_epoch,
                "lease_token": lease_token,
                "lease_until": lease_until,
            }
            receipt = {"claimed": claim_dict}
            append_outbox_event(
                db,
                context,
                outbox_id,
                new_ver,
                None if row[1] is None else str(row[1]),
                "OUTBOX_CLAIMED",
                request_id,
                fingerprint,
                receipt,
                now,
            )
            return canonicalize(receipt)

        raw = self._writer.submit(
            WriterCommand(request_id, fingerprint, "normal", deadline_monotonic_ms, apply, lookup)
        ).result(
            timeout=max(0.001, (deadline_monotonic_ms - time.monotonic() * 1000) / 1000 + 0.05)
        )
        parsed = strict_json(raw)
        claimed = parsed["claimed"]
        if claimed is None:
            return None
        return OutboxClaim(
            outbox_id=str(claimed["outbox_id"]),
            task_id=None if claimed["task_id"] is None else str(claimed["task_id"]),
            channel_account_id=(
                None
                if claimed["channel_account_id"] is None
                else str(claimed["channel_account_id"])
            ),
            target_key=str(claimed["target_key"]),
            target=dict(claimed["target"]),
            semantic_key=str(claimed["semantic_key"]),
            revision=int(claimed["revision"]),
            payload_ref=None if claimed["payload_ref"] is None else str(claimed["payload_ref"]),
            payload=dict(claimed["payload"]),
            delivery_class=str(claimed["delivery_class"]),
            provider_idempotency_key=(
                None
                if claimed["provider_idempotency_key"] is None
                else str(claimed["provider_idempotency_key"])
            ),
            attempt_count=int(claimed["attempt_count"]),
            version=int(claimed["version"]),
            deadline=None if claimed["deadline"] is None else int(claimed["deadline"]),
            claim_runtime_epoch=str(claimed["claim_runtime_epoch"]),
            lease_token=str(claimed["lease_token"]),
            lease_until=int(claimed["lease_until"]),
        )

    def get(self, context: InboundContext, outbox_id: str) -> OutboxRecord:
        def query(db: sqlite3.Connection) -> OutboxRecord:
            authorize(db, context)
            row = db.execute(
                "SELECT outbox_id,task_id,channel_account_id,target_key,target_json,semantic_key,"
                "revision,payload_ref,payload_json,delivery_class,provider_idempotency_key,state,"
                "attempt_count,version,not_before,deadline,claim_runtime_epoch,lease_token,"
                "lease_until,provider_receipt_json,error_code,created_at,updated_at "
                "FROM outbox WHERE outbox_id=?",
                (outbox_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Outbox record not found: {outbox_id}")
            return _row_to_record(row)

        return self._writer.read(query)

    def list_by_semantic_key(
        self, context: InboundContext, target_key: str, semantic_key: str
    ) -> list[OutboxRecord]:
        def query(db: sqlite3.Connection) -> list[OutboxRecord]:
            authorize(db, context)
            rows = db.execute(
                "SELECT outbox_id,task_id,channel_account_id,target_key,target_json,semantic_key,"
                "revision,payload_ref,payload_json,delivery_class,provider_idempotency_key,state,"
                "attempt_count,version,not_before,deadline,claim_runtime_epoch,lease_token,"
                "lease_until,provider_receipt_json,error_code,created_at,updated_at "
                "FROM outbox WHERE target_key=? AND semantic_key=? ORDER BY revision",
                (target_key, semantic_key),
            ).fetchall()
            return [_row_to_record(r) for r in rows]

        return self._writer.read(query)

    def highest_delivered_revision(
        self, context: InboundContext, target_key: str, semantic_key: str
    ) -> int:
        def query(db: sqlite3.Connection) -> int:
            authorize(db, context)
            row = db.execute(
                "SELECT coalesce(max(revision),0) FROM outbox "
                "WHERE target_key=? AND semantic_key=? AND state='SENT'",
                (target_key, semantic_key),
            ).fetchone()
            return int(row[0]) if row else 0

        return self._writer.read(query)
