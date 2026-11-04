"""Durable resource leases, deterministic multi-lock ordering, and session queueing."""

import hashlib
import sqlite3
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from openbot.contracts import canonicalize, strict_json
from openbot.storage.inbox import InboundContext, authorize, emit_state
from openbot.storage.writer import LookupResult, RequestConflict, Writer, WriterCommand

_TYPE_SPECS: dict[str, tuple[int, str]] = {
    "WORKSPACE": (0, "workspace"),
    "BROWSER_PROFILE": (1, "browser_profile"),
    "DESKTOP_SESSION": (2, "desktop_session"),
    "EXTERNAL_ACCOUNT": (3, "external_account"),
}
_WAIT_STATES = frozenset({"WAITING_APPROVAL", "WAITING_INPUT", "WAITING_RESOURCE", "PAUSED"})


class ResourceBusyError(RuntimeError):
    pass


class ResourcePreconditionError(PermissionError):
    pass


class ResourceQuarantinedError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class ResourceRequest:
    resource_type: str
    resource_id: str
    expected_generation: int | None = None
    expected_version: int | None = None

    @property
    def resource_key(self) -> str:
        spec = _TYPE_SPECS.get(self.resource_type)
        if spec is None or not self.resource_id or not self.resource_id.strip():
            raise ValueError("Invalid resource_type or resource_id")
        return f"{spec[1]}:{self.resource_id.strip()}"

    def to_payload(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id.strip(),
            "resource_key": self.resource_key,
            "expected_generation": self.expected_generation,
            "expected_version": self.expected_version,
        }


OrderedResources = tuple[ResourceRequest, ...]


def order_resources(requests: Sequence[ResourceRequest]) -> OrderedResources:
    if not requests:
        raise ValueError("At least one resource request is required")
    seen: set[str] = set()
    validated: list[ResourceRequest] = []
    for req in requests:
        key = req.resource_key
        if key in seen:
            raise ValueError(f"Duplicate resource key in acquisition set: {key}")
        seen.add(key)
        validated.append(req)
    return tuple(
        sorted(validated, key=lambda item: (_TYPE_SPECS[item.resource_type][0], item.resource_key))
    )


def _verify_active_epoch(db: sqlite3.Connection, runtime_epoch: str) -> None:
    cfg = db.execute("SELECT active_runtime_epoch FROM profile_config WHERE singleton=1").fetchone()
    inst = db.execute(
        "SELECT state FROM runtime_instances WHERE runtime_epoch=?", (runtime_epoch,)
    ).fetchone()
    if not cfg or cfg[0] != runtime_epoch or inst != ("ACTIVE",):
        raise PermissionError("Runtime epoch is not the active owner")


def _allocate_fence(db: sqlite3.Connection, now: int) -> int:
    row = db.execute("SELECT last_fencing_token FROM profile_config WHERE singleton=1").fetchone()
    if row is None:
        raise PermissionError("Profile config missing")
    fence = int(row[0]) + 1
    db.execute(
        "UPDATE profile_config SET last_fencing_token=?,version=version+1,updated_at=? "
        "WHERE singleton=1",
        (fence, now),
    )
    return fence


def _check_quarantine(db: sqlite3.Connection, req: ResourceRequest) -> None:
    if req.resource_type == "WORKSPACE":
        row = db.execute(
            "SELECT 1 FROM operations WHERE workspace_id=? AND state IN ('UNKNOWN','DISPATCHING')",
            (req.resource_id,),
        ).fetchone()
        if row is not None:
            raise ResourceQuarantinedError("Workspace is quarantined by unresolved external effect")

    for (lease_json,) in db.execute(
        "SELECT a.lease_set_json FROM operation_attempts a "
        "JOIN operations o ON o.operation_id=a.operation_id "
        "WHERE a.status IN ('DISPATCHING','UNKNOWN') OR o.state IN ('DISPATCHING','UNKNOWN')"
    ):
        keys = strict_json(lease_json)
        if isinstance(keys, list) and req.resource_key in keys:
            raise ResourceQuarantinedError(
                f"Resource {req.resource_key} is quarantined by unresolved external effect"
            )


def _check_preconditions(db: sqlite3.Connection, req: ResourceRequest) -> None:
    if req.resource_type == "WORKSPACE":
        ws = db.execute(
            "SELECT generation,version,status FROM workspaces WHERE workspace_id=?",
            (req.resource_id,),
        ).fetchone()
        if not ws or ws[2] != "ACTIVE":
            raise ResourcePreconditionError("Workspace is not active")
        if req.expected_generation is not None and int(ws[0]) != req.expected_generation:
            raise ResourcePreconditionError("Workspace generation changed while unlocked")
        if req.expected_version is not None and int(ws[1]) != req.expected_version:
            raise ResourcePreconditionError("Workspace version changed while unlocked")


class ResourceCoordinator:
    def __init__(self, writer: Writer):
        self._writer = writer

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

    def claim_next_task(
        self,
        context: InboundContext,
        runtime_epoch: str,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "claim_next_task",
                    "epoch": runtime_epoch,
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
            _verify_active_epoch(db, runtime_epoch)
            running = db.execute("SELECT task_id FROM tasks WHERE state='RUNNING'").fetchone()
            if running is not None:
                raise ResourceBusyError("Single active task slot is already occupied")
            queued = db.execute(
                "SELECT task_id,version FROM tasks "
                "WHERE owner_id=? AND session_id=? AND state='QUEUED' "
                "ORDER BY created_at,rowid,task_id LIMIT 1",
                (context.principal_id, context.session_id),
            ).fetchone()
            if queued is None:
                raise ResourceBusyError("No queued task available in session")
            task_id, version = str(queued[0]), int(queued[1])
            now = time.time_ns() // 1_000_000
            cursor = db.execute(
                "UPDATE tasks SET state='RUNNING',version=version+1,updated_at=? "
                "WHERE task_id=? AND version=?",
                (now, task_id, version),
            )
            if cursor.rowcount != 1:
                raise RequestConflict("Task version changed during schedule claim")
            receipt: dict[str, Any] = {
                "task_id": task_id,
                "state": "RUNNING",
                "version": version + 1,
                "runtime_epoch": runtime_epoch,
            }
            emit_state(db, context, receipt, request_id, fingerprint, "TASK_STATE_CHANGED", now)
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "normal", deadline_monotonic_ms, apply, lookup
        )

    def acquire_leases(
        self,
        context: InboundContext,
        task_id: str,
        attempt_id: str,
        runtime_epoch: str,
        requests: Sequence[ResourceRequest],
        lease_ttl_ms: int,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        if type(lease_ttl_ms) is not int or lease_ttl_ms <= 0:
            raise ValueError("lease_ttl_ms must be a positive integer")
        ordered = order_resources(requests)
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "acquire_leases",
                    "task": task_id,
                    "attempt": attempt_id,
                    "epoch": runtime_epoch,
                    "ttl_ms": lease_ttl_ms,
                    "resources": [r.to_payload() for r in ordered],
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
            _verify_active_epoch(db, runtime_epoch)
            task_row = db.execute(
                "SELECT owner_id,session_id,state,version FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if not task_row or task_row[:2] != (context.principal_id, context.session_id):
                raise PermissionError("Task scope mismatch")
            if task_row[2] != "RUNNING":
                raise ResourceBusyError("Task must hold active RUNNING slot before leasing")
            task_version = int(task_row[3])

            att_row = db.execute(
                "SELECT a.operation_id,a.runtime_epoch,a.status,a.dispatch_started_at,"
                "a.lease_set_json,o.task_id "
                "FROM operation_attempts a JOIN operations o ON o.operation_id=a.operation_id "
                "WHERE a.attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if (
                not att_row
                or att_row[5] != task_id
                or att_row[1] != runtime_epoch
                or att_row[2] != "CLAIMED"
                or att_row[3] is not None
            ):
                raise PermissionError("Attempt is not eligible to acquire resource leases")
            operation_id = str(att_row[0])
            declared_keys = strict_json(att_row[4])
            expected_keys = [item.resource_key for item in ordered]
            if declared_keys and declared_keys != expected_keys:
                raise PermissionError("Attempt lease_set_json does not match ordered resource keys")

            now = time.time_ns() // 1_000_000
            acquired: list[dict[str, Any]] = []
            for req in ordered:
                _check_quarantine(db, req)
                _check_preconditions(db, req)
                existing = db.execute(
                    "SELECT holder_attempt_id,runtime_epoch,fencing_token,state,version "
                    "FROM resource_leases WHERE resource_key=?",
                    (req.resource_key,),
                ).fetchone()
                if existing is not None and existing[3] == "HELD":
                    held_attempt, held_epoch = str(existing[0]), str(existing[1])
                    if (held_attempt, held_epoch) != (attempt_id, runtime_epoch):
                        old_inst = db.execute(
                            "SELECT state FROM runtime_instances WHERE runtime_epoch=?",
                            (held_epoch,),
                        ).fetchone()
                        old_att = db.execute(
                            "SELECT status,dispatch_started_at FROM operation_attempts "
                            "WHERE attempt_id=?",
                            (held_attempt,),
                        ).fetchone()
                        if (
                            old_inst != ("STOPPED",)
                            or not old_att
                            or old_att[0] not in {"CLAIMED", "ABANDONED", "CANCELLED"}
                            or old_att[1] is not None
                        ):
                            raise ResourceBusyError(
                                f"Resource {req.resource_key} is held; "
                                "expiry alone cannot steal lease"
                            )
                fence = _allocate_fence(db, now)
                expires_at = now + lease_ttl_ms
                if existing is None:
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
                    old_ver = int(existing[4])
                    updated = db.execute(
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
                            old_ver,
                        ),
                    )
                    if updated.rowcount != 1:
                        raise RequestConflict("Resource lease version changed")
                acquired.append(
                    {
                        "resource_key": req.resource_key,
                        "resource_type": req.resource_type,
                        "fencing_token": fence,
                        "expires_at_ms": expires_at,
                    }
                )

            receipt: dict[str, Any] = {
                "task_id": task_id,
                "attempt_id": attempt_id,
                "version": task_version,
                "leases": acquired,
            }
            payload = canonicalize(
                {"request_id": request_id, "command_hash": fingerprint, "receipt": receipt}
            ).decode()
            db.execute(
                "INSERT INTO events(event_id,aggregate_kind,aggregate_id,aggregate_version,task_id,"
                "operation_id,actor_principal_id,event_type,schema_version,trace_id,payload_json,"
                "created_at) VALUES(?,'ResourceLease',?,?,?,?,?,'OPERATION_CLAIMED',1,?,?,?)",
                (
                    "evt_" + hashlib.sha256(f"{request_id}:{attempt_id}".encode()).hexdigest()[:32],
                    attempt_id,
                    acquired[-1]["fencing_token"],
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

    def park_for_wait(
        self,
        context: InboundContext,
        task_id: str,
        expected_version: int,
        target_wait_state: str,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        if (
            target_wait_state not in _WAIT_STATES
            or type(expected_version) is not int
            or expected_version < 0
        ):
            raise ValueError("Invalid wait state or expected_version")
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "park_for_wait",
                    "task": task_id,
                    "expected": expected_version,
                    "target": target_wait_state,
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
            row = db.execute(
                "SELECT owner_id,session_id,state,version FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if not row or row[:2] != (context.principal_id, context.session_id):
                raise PermissionError("Task scope mismatch")
            state, version = str(row[2]), int(row[3])
            if version != expected_version or state != "RUNNING":
                raise RequestConflict("Task must be RUNNING at expected_version to park for wait")

            in_flight = db.execute(
                "SELECT 1 FROM operation_attempts a "
                "JOIN operations o ON o.operation_id=a.operation_id "
                "WHERE o.task_id=? AND (a.status IN ('DISPATCHING','UNKNOWN') "
                "OR o.state IN ('DISPATCHING','UNKNOWN'))",
                (task_id,),
            ).fetchone()
            if in_flight is not None:
                raise PermissionError("Cannot release leases for wait while dispatch is in flight")

            now = time.time_ns() // 1_000_000
            held_rows = db.execute(
                "SELECT resource_key,version FROM resource_leases "
                "WHERE state='HELD' AND holder_attempt_id IN ("
                "SELECT a.attempt_id FROM operation_attempts a "
                "JOIN operations o ON o.operation_id=a.operation_id WHERE o.task_id=?) "
                "ORDER BY resource_key",
                (task_id,),
            ).fetchall()
            released_keys: list[str] = []
            for r_key, r_ver in held_rows:
                db.execute(
                    "UPDATE resource_leases SET holder_attempt_id=NULL,runtime_epoch=NULL,"
                    "state='RELEASED',acquired_at=NULL,expires_at=NULL,version=version+1,"
                    "updated_at=? WHERE resource_key=? AND version=?",
                    (now, r_key, r_ver),
                )
                released_keys.append(str(r_key))

            cursor = db.execute(
                "UPDATE tasks SET state=?,version=version+1,updated_at=? "
                "WHERE task_id=? AND version=?",
                (target_wait_state, now, task_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise RequestConflict("Task version changed")
            receipt: dict[str, Any] = {
                "task_id": task_id,
                "state": target_wait_state,
                "version": version + 1,
                "released_keys": released_keys,
            }
            emit_state(db, context, receipt, request_id, fingerprint, "TASK_STATE_CHANGED", now)
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "normal", deadline_monotonic_ms, apply, lookup
        )
