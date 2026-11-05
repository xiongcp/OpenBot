"""Durable immutable proposals. This module never claims or dispatches work."""

import hashlib
import re
import secrets
import sqlite3
import time
from typing import Any, Protocol

from openbot.contracts import (
    CanonicalDocument,
    ContractError,
    SchemaRegistry,
    canonicalize,
    strict_json,
)
from openbot.domain.clock import ClockSnapshot
from openbot.storage.inbox import InboundContext, authorize, emit_state
from openbot.storage.writer import LookupResult, RequestConflict, Writer, WriterCommand

_AUTHORITY_INSTANCE = secrets.token_hex(32)
PROPOSAL_TTL_MS = 60_000


class ChallengeStore(Protocol):
    """Protected storage supplied by the composition root, never a model or channel body."""

    def put(self, approval_id: str, nonce: bytes) -> None: ...
    def get(self, approval_id: str) -> bytes | None: ...


def clock_now() -> ClockSnapshot:
    # A new control process invalidates sensitive grants without trusted cross-restart time proof.
    return ClockSnapshot(
        time.time_ns() // 1_000_000, time.monotonic_ns() // 1_000_000, _AUTHORITY_INSTANCE
    )


def task_record(
    db: sqlite3.Connection, context: InboundContext, task_id: str
) -> tuple[str, int, int]:
    authorize(db, context)
    row = db.execute(
        "SELECT owner_id,session_id,state,version,cancel_revision FROM tasks WHERE task_id=?",
        (task_id,),
    ).fetchone()
    if not row or row[:2] != (context.principal_id, context.session_id):
        raise PermissionError("Task scope mismatch")
    return str(row[2]), int(row[3]), int(row[4])


def command_lookup(
    db: sqlite3.Connection, context: InboundContext, task_id: str, request_id: str
) -> LookupResult | None:
    task_record(db, context, task_id)
    row = db.execute(
        "SELECT payload_json FROM events WHERE json_extract(payload_json,'$.request_id')=?",
        (request_id,),
    ).fetchone()
    if row is None:
        return None
    value = strict_json(row[0])
    return LookupResult(value["command_hash"], canonicalize(value["receipt"]))


def advance_task(db: sqlite3.Connection, task_id: str, version: int, target: str, now: int) -> None:
    changed = db.execute(
        "UPDATE tasks SET state=?,version=version+1,updated_at=? WHERE task_id=? AND version=?",
        (target, now, task_id, version),
    )
    if changed.rowcount != 1:
        raise RequestConflict("Task version changed")


def load_proposal(
    db: sqlite3.Connection, context: InboundContext, operation_id: str, registry: SchemaRegistry
) -> CanonicalDocument:
    row = db.execute(
        "SELECT proposal_canonical_json,binding_hash,canonical_args_json,resource_snapshot_json,"
        "destination_json,tool_id,tool_version,tool_manifest_digest,workspace_id,workspace_generation,"
        "policy_version,identity_epoch,authorization_expires_at,data_class,retry_class,"
        "provider_idempotency_key,requested_by,task_id FROM operations WHERE operation_id=?",
        (operation_id,),
    ).fetchone()
    if not row:
        raise PermissionError("Operation unavailable")
    task_record(db, context, row[17])
    if row[0] is None:
        raise PermissionError("Legacy operation has no authoritative binding")
    doc = CanonicalDocument(row[0].encode())
    registry.validate("tool-proposal.schema.json", doc.canonical)
    value = doc.value()
    binding = dict(value)
    digest = binding.pop("binding_hash")
    if digest != "sha256:" + hashlib.sha256(canonicalize(binding)).hexdigest():
        raise PermissionError("Authoritative proposal digest mismatch")
    if not re.fullmatch(r"policy-[1-9][0-9]*", value["policy_version"]):
        raise PermissionError("Unsupported policy version")
    expected = (
        digest[7:],
        canonicalize(value["args"]).decode(),
        canonicalize(value["resource_snapshot"]).decode(),
        canonicalize(value["destination"]).decode(),
        value["tool"]["name"],
        value["tool"]["version"],
        value["tool"]["manifest_digest"][7:],
        value["workspace_id"],
        value["resource_snapshot"]["workspace_generation"],
        int(value["policy_version"][7:]),
        value["identity_epoch"],
        value["expires_at_ms"],
        value["data_class"],
        value["retry_class"],
        value["provider_idempotency_key"],
        value["principal_id"],
        value["task_id"],
    )
    if (
        value["operation_id"] != operation_id
        or row[1:] != expected
        or (
            value["profile_id"],
            value["principal_id"],
            value["session_id"],
            value["workspace_id"],
        )
        != (context.profile_id, context.principal_id, context.session_id, context.workspace_id)
    ):
        raise PermissionError("Proposal authority/projection mismatch")
    return doc


class OperationService:
    def __init__(self, writer: Writer, challenges: ChallengeStore, registry: SchemaRegistry):
        self._writer, self._challenges, self._registry = writer, challenges, registry

    def load(self, context: InboundContext, operation_id: str) -> CanonicalDocument:
        return self._writer.read(
            lambda db: load_proposal(db, context, operation_id, self._registry)
        )

    def propose(
        self,
        context: InboundContext,
        task_id: str,
        tool_id: str,
        raw_args: str | bytes,
        resource_snapshot: dict[str, Any],
        data_class: str,
        destination: dict[str, Any],
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> bytes:
        if context.channel != "local":
            raise PermissionError("Only the local internal proposal boundary is available")
        args = CanonicalDocument.create(strict_json(raw_args))
        snapshot = CanonicalDocument.create(resource_snapshot)
        target = CanonicalDocument.create(destination)
        if data_class not in {"PUBLIC", "WORKSPACE"}:
            raise PermissionError("Data preview/egress gate is unavailable for this classification")
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "propose",
                    "task": task_id,
                    "tool": tool_id,
                    "args": args.value(),
                    "snapshot": snapshot.value(),
                    "data_class": data_class,
                    "destination": target.value(),
                    "actor": context.principal_id,
                    "profile": context.profile_id,
                    "session": context.session_id,
                    "identity": context.identity_epoch,
                    "surface": context.source_scope,
                }
            )
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return command_lookup(db, context, task_id, request_id)

        previous = self._writer.read(lookup)
        if previous is not None:
            if previous.payload_hash != fingerprint:
                raise RequestConflict("Proposal request changed")
            return previous.result

        def inputs(db: sqlite3.Connection) -> tuple[Any, ...]:
            task_record(db, context, task_id)
            tool = db.execute(
                "SELECT tool_version,manifest_digest,manifest_json FROM tool_registry "
                "WHERE tool_id=? AND status='ACTIVE'",
                (tool_id,),
            ).fetchone()
            if tool is None:
                raise PermissionError("Tool is not locally reviewed and active")
            policy = db.execute(
                "SELECT policy_version FROM profile_config WHERE singleton=1"
            ).fetchone()[0]
            generation = db.execute(
                "SELECT generation FROM workspaces WHERE workspace_id=?",
                (context.workspace_id,),
            ).fetchone()[0]
            return (*tool, int(policy), int(generation))

        reviewed = self._writer.read(inputs)
        manifest = strict_json(reviewed[2])
        if hashlib.sha256(canonicalize(manifest)).hexdigest() != reviewed[1] or (
            manifest.get("name"),
            manifest.get("version"),
        ) != (tool_id, reviewed[0]):
            raise PermissionError("Reviewed manifest bytes changed")
        if manifest.get("effect") not in {
            "READ",
            "LOCAL_WRITE",
            "EXTERNAL_WRITE",
            "CODE_EXECUTION",
        } or manifest.get("retry_class") not in {
            "SAFE_READ",
            "IDEMPOTENT_WRITE",
            "PROVIDER_IDEMPOTENT",
            "RECONCILE_ONLY",
            "NON_RETRYABLE",
        }:
            raise ContractError("Invalid reviewed manifest capability")
        SchemaRegistry({"args.schema.json": manifest["input_schema"]}).validate(
            "args.schema.json", args.canonical
        )
        issued = clock_now()
        operation_id, approval_id = "op_" + secrets.token_hex(16), "apr_" + secrets.token_hex(16)
        nonce = secrets.token_urlsafe(32).encode()
        nonce_hash = hashlib.sha256(nonce).hexdigest()
        body = {
            "schema_version": "1.1",
            "operation_id": operation_id,
            "profile_id": context.profile_id,
            "principal_id": context.principal_id,
            "session_id": context.session_id,
            "task_id": task_id,
            "workspace_id": context.workspace_id,
            "tool": {
                "name": tool_id,
                "version": reviewed[0],
                "manifest_digest": "sha256:" + reviewed[1],
            },
            "args": args.value(),
            "resource_snapshot": snapshot.value(),
            "effect": manifest["effect"],
            "retry_class": manifest["retry_class"],
            "data_class": data_class,
            "destination": target.value(),
            "policy_version": "policy-" + str(reviewed[3]),
            "identity_epoch": context.identity_epoch,
            "expires_at_ms": issued.utc_ms + PROPOSAL_TTL_MS,
            "approval_nonce_hash": "sha256:" + nonce_hash,
            "provider_idempotency_key": "provider_" + secrets.token_hex(16)
            if manifest["retry_class"] == "PROVIDER_IDEMPOTENT"
            else None,
        }
        body["binding_hash"] = "sha256:" + hashlib.sha256(canonicalize(body)).hexdigest()
        doc = self._registry.validate("tool-proposal.schema.json", canonicalize(body))
        scope = canonicalize(
            {
                "profile_id": context.profile_id,
                "session_id": context.session_id,
                "channel": context.channel,
                "tenant_id": context.tenant_id,
                "app_id": context.app_id,
                "issued_utc_ms": issued.utc_ms,
                "issued_monotonic_ms": issued.monotonic_ms,
                "authority_instance": issued.boot_id,
            }
        ).decode()
        # Protected store I/O happens before the DB transaction; crash orphans grant no authority.
        self._challenges.put(approval_id, nonce)

        def apply(db: sqlite3.Connection) -> bytes:
            state, version, cancelled = task_record(db, context, task_id)
            if state != "RUNNING" or cancelled:
                raise RequestConflict("Task cannot accept a proposal")
            if (
                inputs(db) != reviewed
                or snapshot.value().get("workspace_generation") != reviewed[4]
            ):
                raise PermissionError("Proposal resource or policy changed")
            now = clock_now().utc_ms
            if now >= body["expires_at_ms"]:
                raise PermissionError("Proposal expired before commit")
            ordinal = db.execute(
                "SELECT coalesce(max(ordinal),0)+1 FROM operations WHERE task_id=?", (task_id,)
            ).fetchone()[0]
            db.execute(
                "INSERT INTO operations(operation_id,task_id,ordinal,requested_by,workspace_id,"
                "workspace_generation,tool_id,tool_version,tool_manifest_digest,canonical_args_json,"
                "resource_snapshot_json,destination_json,data_class,authorization_kind,policy_version,"
                "identity_epoch,authorization_expires_at,binding_hash,retry_class,provider_idempotency_key,"
                "state,created_at,updated_at,proposal_canonical_json) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'APPROVAL',?,?,?,?,?,?,'AWAITING_APPROVAL',?,?,?)",
                (
                    operation_id,
                    task_id,
                    ordinal,
                    context.principal_id,
                    context.workspace_id,
                    reviewed[4],
                    tool_id,
                    reviewed[0],
                    reviewed[1],
                    args.canonical.decode(),
                    snapshot.canonical.decode(),
                    target.canonical.decode(),
                    data_class,
                    reviewed[3],
                    context.identity_epoch,
                    body["expires_at_ms"],
                    body["binding_hash"][7:],
                    manifest["retry_class"],
                    body["provider_idempotency_key"],
                    issued.utc_ms,
                    now,
                    doc.canonical.decode(),
                ),
            )
            db.execute(
                "INSERT INTO approvals(approval_id,operation_id,allowed_actor_id,actor_scope_json,"
                "binding_hash,nonce_hash,requested_at,expires_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    approval_id,
                    operation_id,
                    context.principal_id,
                    scope,
                    body["binding_hash"][7:],
                    nonce_hash,
                    issued.utc_ms,
                    body["expires_at_ms"],
                ),
            )
            advance_task(db, task_id, version, "WAITING_APPROVAL", now)
            receipt = {
                "task_id": task_id,
                "state": "WAITING_APPROVAL",
                "version": version + 1,
                "operation_id": operation_id,
                "approval_id": approval_id,
                "binding_hash": body["binding_hash"],
                "approval_version": 1,
            }
            emit_state(
                db,
                context,
                receipt,
                request_id,
                fingerprint,
                "OPERATION_PROPOSED",
                now,
                operation_id,
            )
            return canonicalize(receipt)

        command = WriterCommand(
            request_id, fingerprint, "normal", deadline_monotonic_ms, apply, lookup
        )
        return self._writer.submit(command).result(
            timeout=min(
                300.0, max(0.001, (deadline_monotonic_ms - time.monotonic() * 1000) / 1000 + 0.05)
            )
        )
