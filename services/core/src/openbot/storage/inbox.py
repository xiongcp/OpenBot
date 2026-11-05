"""Scoped durable ingress. Identity is supplied by a trusted authenticated boundary."""

import hashlib
import secrets
import sqlite3
import time
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass

from openbot.contracts import SchemaRegistry, canonicalize, strict_json
from openbot.storage.writer import LookupResult, RequestConflict, Writer, WriterCommand


@dataclass(frozen=True, slots=True)
class InboundContext:
    profile_id: str
    principal_id: str
    identity_epoch: int
    channel: str
    tenant_id: str
    app_id: str
    session_id: str
    workspace_id: str

    @property
    def source_scope(self) -> str:
        return canonicalize(
            {
                "channel": self.channel,
                "tenant": self.tenant_id,
                "app": self.app_id,
                "profile": self.profile_id,
            }
        ).decode()


def authorize(db: sqlite3.Connection, context: InboundContext) -> str:
    profile = db.execute(
        "SELECT profile_id,identity_epoch,privacy_mode FROM profile_config WHERE singleton=1"
    ).fetchone()
    actor = db.execute(
        "SELECT role,status FROM principals WHERE principal_id=?", (context.principal_id,)
    ).fetchone()
    session = db.execute(
        "SELECT owner_id,workspace_id,status FROM sessions WHERE session_id=?",
        (context.session_id,),
    ).fetchone()
    workspace = db.execute(
        "SELECT status FROM workspaces WHERE workspace_id=?", (context.workspace_id,)
    ).fetchone()
    if (
        not profile
        or profile[:2] != (context.profile_id, context.identity_epoch)
        or actor != ("OWNER", "ACTIVE")
        or session != (context.principal_id, context.workspace_id, "OPEN")
        or workspace != ("ACTIVE",)
    ):
        raise PermissionError("Trusted profile/owner/session context is no longer valid")
    return str(profile[2])


def emit_state(
    db: sqlite3.Connection,
    context: InboundContext,
    receipt: dict[str, str | int],
    request_id: str,
    command_hash: str,
    event_type: str,
    now: int,
    operation_id: str | None = None,
) -> int:
    task_id = receipt["task_id"]
    payload = canonicalize(
        {"request_id": request_id, "command_hash": command_hash, "receipt": receipt}
    ).decode()
    cursor = db.execute(
        "INSERT INTO events(event_id,aggregate_kind,aggregate_id,aggregate_version,task_id,"
        "actor_principal_id,event_type,schema_version,trace_id,payload_json,created_at,"
        "operation_id) "
        "VALUES(?,'Task',?,?,?,?,?,1,?,?,?,?)",
        (
            "evt_" + secrets.token_hex(16),
            task_id,
            receipt["version"],
            task_id,
            context.principal_id,
            event_type,
            "trc_" + hashlib.sha256(request_id.encode()).hexdigest()[:32],
            payload,
            now,
            operation_id,
        ),
    )
    db.execute(
        "INSERT INTO outbox(outbox_id,task_id,target_key,target_json,semantic_key,revision,"
        "payload_json,delivery_class,not_before,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,'UPSERT_REVISION',?,?,?)",
        (
            "out_" + secrets.token_hex(16),
            task_id,
            "local:" + context.principal_id,
            canonicalize({"principal_id": context.principal_id}).decode(),
            "task:" + str(task_id),
            int(receipt["version"]) + 1,
            canonicalize(receipt).decode(),
            now,
            now,
            now,
        ),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


class Inbox:
    def __init__(self, writer: Writer, registry: SchemaRegistry):
        self._writer = writer
        self._registry = registry

    def submit(
        self,
        context: InboundContext,
        event_id: str,
        raw: str | bytes,
        deadline_monotonic_ms: int,
        *,
        admission: Callable[[sqlite3.Connection], None] | None = None,
    ) -> Future[bytes]:
        doc = self._registry.validate("create-task.schema.json", raw)
        value = doc.value()
        if (
            not event_id
            or len(event_id) > 200
            or not value["goal"].strip()
            or value["workspace_id"] != context.workspace_id
            or value.get("session_id", context.session_id) != context.session_id
        ):
            raise ValueError("Inbound scope or task fields mismatch")
        if value.get("artifact_ids"):
            raise ValueError("CAPABILITY_UNAVAILABLE: artifact ingress gate OB-036 is incomplete")
        payload_hash = hashlib.sha256(doc.canonical).hexdigest()
        scope = context.source_scope
        request_id = "inbox:" + hashlib.sha256(canonicalize([scope, event_id])).hexdigest()
        fingerprint = hashlib.sha256(canonicalize([payload_hash, context.principal_id])).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            authorize(db, context)
            if admission is not None:
                admission(db)
            old = db.execute(
                "SELECT i.payload_hash,t.task_id,t.owner_id,t.state,t.version FROM inbox i "
                "JOIN tasks t ON t.task_id=i.task_id "
                "WHERE i.source_scope=? AND i.external_event_id=?",
                (scope, event_id),
            ).fetchone()
            if not old:
                return None
            if old[0] != payload_hash:
                raise RequestConflict("Same inbound event with changed payload")
            if old[2] != context.principal_id:
                raise PermissionError("Inbound task belongs to another owner")
            return LookupResult(
                fingerprint, canonicalize({"task_id": old[1], "state": old[3], "version": old[4]})
            )

        def apply(db: sqlite3.Connection) -> bytes:
            mode = authorize(db, context)
            if admission is not None:
                admission(db)
            task_input = strict_json(doc.canonical)
            if mode == "OFFLINE" and task_input["network_mode"] != "OFFLINE":
                raise PermissionError("Task cannot expand profile network mode")
            if mode == "LOCAL_MODEL" and task_input["network_mode"] == "CONNECTED":
                raise PermissionError("Task cannot expand model egress")
            now = time.time_ns() // 1_000_000
            task_id, budget_id = "tsk_" + secrets.token_hex(16), "bdg_" + secrets.token_hex(16)
            db.execute(
                "INSERT INTO budgets(budget_id,owner_id,currency,amount_limit_micros,"
                "token_limit,created_at,updated_at) "
                "VALUES(?,?,'USD',0,16384,?,?)",
                (budget_id, context.principal_id, now, now),
            )
            db.execute(
                "INSERT INTO tasks(task_id,session_id,owner_id,budget_id,goal,"
                "checkpoint_json,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    task_id,
                    context.session_id,
                    context.principal_id,
                    budget_id,
                    task_input["goal"],
                    canonicalize(
                        {
                            "network_mode": task_input["network_mode"],
                            "workspace_id": context.workspace_id,
                        }
                    ).decode(),
                    now,
                    now,
                ),
            )
            db.execute(
                "INSERT INTO inbox(inbox_id,source_scope,external_event_id,payload_hash,"
                "normalized_payload_json,task_id,status,received_at,processed_at) "
                "VALUES(?,?,?,?,?,?,'PROCESSED',?,?)",
                (
                    "inb_" + secrets.token_hex(16),
                    scope,
                    event_id,
                    payload_hash,
                    doc.canonical.decode(),
                    task_id,
                    now,
                    now,
                ),
            )
            receipt: dict[str, str | int] = {"task_id": task_id, "state": "QUEUED", "version": 0}
            emit_state(db, context, receipt, request_id, fingerprint, "TASK_QUEUED", now)
            return canonicalize(receipt)

        return self._writer.submit(
            WriterCommand(request_id, fingerprint, "inbound", deadline_monotonic_ms, apply, lookup)
        )
