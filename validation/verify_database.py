#!/usr/bin/env python3
"""Offline acceptance examples for OpenBot's DESIGN DDL and reference transactions.

Python standard library only. Creates temporary databases; never opens a real profile.
This is NOT an implemented OpenBot runtime, gateway, sandbox, or external executor.
The ReferenceTransactions class deliberately models one workspace and one pending
operation. Authentication, secure resource observation, supervisor proofs, RFC 8785,
provider reconciliation and real network/process effects are outside this script.

Run: python3 validation/verify_database.py [--report validation/database_report.json]
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
DDL_PATH = ROOT / "db" / "001_baseline.sql"
NOW = 1_700_000_000_000  # Deterministic fixture time, not the wall clock.
MANIFEST = hashlib.sha256(b"reviewed-tool-fixture").hexdigest()
OLD_FILE = hashlib.sha256(b"old file snapshot").hexdigest()
OBSERVED = {"workspace_generation": 1, "old_sha256": OLD_FILE}


def uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def j(value: object) -> str:
    # Fixture JSON uses only strings, booleans, null and safe integers. This
    # helper is NOT a general RFC 8785 implementation and must not be copied as one.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def insert(c: sqlite3.Connection, table: str, **values: object) -> None:
    # Identifiers are fixed developer-controlled schema names, never user input.
    names = [table, *values]
    if any(not name.replace("_", "").isalnum() or not name.isascii() for name in names):
        raise ValueError("invalid internal identifier")
    columns = ",".join(values)
    marks = ",".join("?" for _ in values)
    c.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(values.values()))


@contextmanager
def transaction(c: sqlite3.Connection):
    if c.in_transaction:
        raise RuntimeError("reference transactions must not be nested")
    c.execute("BEGIN IMMEDIATE")
    try:
        yield
        c.commit()
    except BaseException:
        c.rollback()
        raise


class GuardError(RuntimeError):
    """Expected application-layer refusal; no external execution has happened."""


def install_baseline(c: sqlite3.Connection) -> str:
    if sqlite3.sqlite_version_info < (3, 38, 0):
        raise RuntimeError("SQLite >= 3.38 is required by this design baseline")
    c.execute("PRAGMA foreign_keys=ON")
    mode = c.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    c.execute("PRAGMA synchronous=FULL")
    c.execute("PRAGMA recursive_triggers=ON")
    c.execute("PRAGMA busy_timeout=250")
    if mode.lower() != "wal" or c.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("required SQLite connection settings were not applied")
    c.execute("SELECT json_valid('{}')").fetchone()
    ddl = DDL_PATH.read_text(encoding="utf-8")
    checksum = hashlib.sha256(DDL_PATH.read_bytes()).hexdigest()
    # executescript owns no parameter binding and commits a pre-existing txn.
    # Start explicitly INSIDE the script, then insert the bound checksum and
    # commit once so schema and its migration record are one atomic unit.
    try:
        c.executescript("BEGIN IMMEDIATE;\n" + ddl)
        insert(c, "schema_migrations", version=1, name=DDL_PATH.name, checksum=checksum, applied_at=NOW)
        c.commit()
    except BaseException:
        c.rollback()
        raise
    return checksum


def seed(c: sqlite3.Connection) -> None:
    """A deliberately small fixture; fake account IDs and secret REFERENCES only."""
    with transaction(c):
        insert(c, "policy_revisions", version=1, digest=digest("policy-one"), rules_json=j({"fixture": True}), effective_at=NOW, created_at=NOW)
        insert(c, "runtime_instances", runtime_epoch="epoch-1", boot_id="boot-1", supervisor_ref="fixture-supervisor", state="ACTIVE", started_at=NOW, heartbeat_at=NOW)
        insert(c, "profile_config", singleton=1, profile_id="profile-1", schema_version=1, policy_version=1, identity_epoch=1, privacy_mode="CONNECTED", active_runtime_epoch="epoch-1", created_at=NOW, updated_at=NOW)
        insert(c, "principals", principal_id="owner", role="OWNER", status="ACTIVE", display_name="Fixture owner", created_at=NOW)
        insert(c, "principals", principal_id="viewer", role="VIEWER", status="ACTIVE", display_name="Fixture viewer", created_at=NOW)
        insert(c, "channel_accounts", account_id="feishu-1", channel="FEISHU", tenant_id="tenant-1", app_id="app-1", secret_ref="vault:fixture-only", status="ACTIVE", created_at=NOW)
        insert(c, "channel_identities", identity_id="identity-1", account_id="feishu-1", external_user_id="external-owner", principal_id="owner", status="ACTIVE", linked_at=NOW)
        insert(c, "workspaces", workspace_id="ws-1", root_ref="managed:fixture-worktree", generation=1, status="ACTIVE", created_at=NOW, updated_at=NOW)
        insert(c, "sessions", session_id="session-1", owner_id="owner", workspace_id="ws-1", channel_identity_id="identity-1", status="OPEN", created_at=NOW, updated_at=NOW)
        new_budget(c, "budget-1")
        insert(c, "tasks", task_id="task-1", session_id="session-1", owner_id="owner", budget_id="budget-1", goal="Apply a reviewed fixture patch", state="WAITING_APPROVAL", created_at=NOW, updated_at=NOW)
        insert(c, "tool_registry", tool_id="file.apply_patch", tool_version="1.0.0", manifest_digest=MANIFEST, package_digest=digest("fixture-package"), installation_ref="builtin:fixture", manifest_json=j({"retry_class": "IDEMPOTENT_WRITE"}), status="ACTIVE", registered_at=NOW)
        add_operation(c)


def new_budget(c: sqlite3.Connection, budget_id: str) -> None:
    insert(c, "budgets", budget_id=budget_id, owner_id="owner", currency="USD", amount_limit_micros=1_000_000, token_limit=10_000, created_at=NOW, updated_at=NOW)


def add_operation(c: sqlite3.Connection, op_id: str = "op-1", ordinal: int = 1,
                  with_approval: bool = True, retry_class: str = "IDEMPOTENT_WRITE",
                  task_id: str = "task-1") -> None:
    args = {"path": "src/example.txt", "old_sha256": OLD_FILE, "new_text": "fixture"}
    binding = digest(j({"operation_id": op_id, "task_id": task_id, "args": args, "actor": "owner", "policy_version": 1, "identity_epoch": 1, "resource": OBSERVED}))
    insert(c, "operations", operation_id=op_id, task_id=task_id, ordinal=ordinal, requested_by="owner", workspace_id="ws-1", workspace_generation=1, tool_id="file.apply_patch", tool_version="1.0.0", tool_manifest_digest=MANIFEST, canonical_args_json=j(args), resource_snapshot_json=j(OBSERVED), data_class="WORKSPACE", authorization_kind="APPROVAL" if with_approval else "POLICY_ALLOW", policy_version=1, identity_epoch=1, authorization_expires_at=NOW + 60_000, binding_hash=binding, retry_class=retry_class, provider_idempotency_key=f"provider-key-{op_id}", state="AWAITING_APPROVAL" if with_approval else "READY", created_at=NOW, updated_at=NOW)
    if with_approval:
        insert(c, "approvals", approval_id=f"approval-{op_id}", operation_id=op_id, allowed_actor_id="owner", actor_scope_json=j({"principal_id": "owner", "account_id": "feishu-1"}), binding_hash=binding, nonce_hash=digest(f"nonce-{op_id}"), requested_at=NOW, expires_at=NOW + 60_000)


class ReferenceTransactions:
    """Executable examples of application invariants, deliberately NOT a product API.

    actor is assumed to come from verified authentication, never a request body.
    observed is assumed to come from a trusted handle-based resource observer.
    These assumptions are explicit and are not established by SQLite.
    """

    def __init__(self, c: sqlite3.Connection):
        self.c = c

    def one(self, sql: str, params: tuple = ()) -> sqlite3.Row:
        row = self.c.execute(sql, params).fetchone()
        if row is None:
            raise GuardError("NOT_FOUND")
        return row

    def event(self, task_id: str, event_type: str, now: int, op_id: str | None = None, payload: dict | None = None) -> None:
        task = self.one("SELECT version FROM tasks WHERE task_id=?", (task_id,))
        insert(self.c, "events", event_id=uid("event"), aggregate_kind="TASK", aggregate_id=task_id, aggregate_version=task["version"], task_id=task_id, operation_id=op_id, actor_principal_id="owner", event_type=event_type, schema_version=1, trace_id=uid("trace"), payload_json=j(payload or {}), created_at=now)

    def notify(self, task_id: str, label: str, now: int, invalid_payload: bool = False) -> None:
        semantic_key = f"task-status:{task_id}"
        revision = self.c.execute("SELECT coalesce(max(revision),0)+1 FROM outbox WHERE target_key='feishu-1:owner' AND semantic_key=?", (semantic_key,)).fetchone()[0]
        insert(self.c, "outbox", outbox_id=uid("outbox"), task_id=task_id, channel_account_id="feishu-1", target_key="feishu-1:owner", target_json=j({"principal_id": "owner"}), semantic_key=semantic_key, revision=revision, payload_json="{" if invalid_payload else j({"status": label}), delivery_class="UPSERT_REVISION", not_before=now, created_at=now, updated_at=now)

    def preflight(self, op_id: str, actor: str, now: int, observed: dict) -> tuple[sqlite3.Row, sqlite3.Row, sqlite3.Row]:
        op = self.one("SELECT * FROM operations WHERE operation_id=?", (op_id,))
        task = self.one("SELECT * FROM tasks WHERE task_id=?", (op["task_id"],))
        profile = self.one("SELECT * FROM profile_config WHERE singleton=1")
        principal = self.one("SELECT * FROM principals WHERE principal_id=?", (actor,))
        if actor != op["requested_by"] or principal["status"] != "ACTIVE" or principal["role"] != "OWNER":
            raise GuardError("ACTOR_DENIED")
        if task["cancel_requested_at"] is not None or task["state"] in {"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"}:
            raise GuardError("TASK_CANCELLED_OR_TERMINAL")
        if task["state"] not in {"QUEUED", "RUNNING", "WAITING_APPROVAL"}:
            raise GuardError("TASK_NOT_RUNNABLE_RECONCILIATION_REQUIRED")
        if profile["policy_version"] != op["policy_version"] or profile["identity_epoch"] != op["identity_epoch"]:
            raise GuardError("AUTHORIZATION_STALE")
        if now >= op["authorization_expires_at"]:
            raise GuardError("APPROVAL_EXPIRED")
        tool = self.one("SELECT status FROM tool_registry WHERE tool_id=? AND tool_version=? AND manifest_digest=?", (op["tool_id"], op["tool_version"], op["tool_manifest_digest"]))
        if tool["status"] != "ACTIVE":
            raise GuardError("TOOL_QUARANTINED")
        workspace = self.one("SELECT * FROM workspaces WHERE workspace_id=?", (op["workspace_id"],))
        if workspace["status"] != "ACTIVE" or workspace["generation"] != op["workspace_generation"] or observed != json.loads(op["resource_snapshot_json"]):
            raise GuardError("RESOURCE_CHANGED")
        return op, task, profile

    def approve(self, op_id: str = "op-1", actor: str = "owner", now: int = NOW + 1,
                nonce: str | None = None, expected_version: int = 0,
                observed: dict | None = None, fail_notification: bool = False) -> str:
        with transaction(self.c):
            op, task, _ = self.preflight(op_id, actor, now, observed if observed is not None else OBSERVED)
            approval = self.one("SELECT * FROM approvals WHERE operation_id=?", (op_id,))
            if approval["allowed_actor_id"] != actor or approval["binding_hash"] != op["binding_hash"]:
                raise GuardError("BINDING_MISMATCH")
            if approval["nonce_hash"] != digest(nonce if nonce is not None else f"nonce-{op_id}"):
                raise GuardError("NONCE_MISMATCH")
            if now >= approval["expires_at"]:
                raise GuardError("APPROVAL_EXPIRED")
            if approval["status"] in {"APPROVED", "CONSUMED"}:
                return approval["status"]  # Query-like idempotent duplicate decision.
            changed = self.c.execute("UPDATE approvals SET status='APPROVED', decided_by=?, decided_at=?, version=version+1 WHERE approval_id=? AND status='PENDING' AND version=? AND expires_at>?", (actor, now, approval["approval_id"], expected_version, now)).rowcount
            if changed != 1 or op["state"] != "AWAITING_APPROVAL":
                raise GuardError("VERSION_CONFLICT")
            self.c.execute("UPDATE operations SET state='READY', version=version+1, updated_at=? WHERE operation_id=? AND version=?", (now, op_id, op["version"]))
            self.c.execute("UPDATE tasks SET state='QUEUED', version=version+1, updated_at=? WHERE task_id=? AND version=?", (now, task["task_id"], task["version"]))
            self.event(task["task_id"], "ApprovalApproved", now, op_id)
            self.notify(task["task_id"], "READY", now, invalid_payload=fail_notification)
            return "APPROVED"

    def claim(self, op_id: str = "op-1", actor: str = "owner", now: int = NOW + 2,
              epoch: str = "epoch-1", observed: dict | None = None,
              expected_version: int | None = None) -> str:
        with transaction(self.c):
            op, task, profile = self.preflight(op_id, actor, now, observed if observed is not None else OBSERVED)
            if op["state"] != "READY" or (expected_version is not None and op["version"] != expected_version):
                raise GuardError("NOT_READY_OR_VERSION_CONFLICT")
            runtime = self.one("SELECT state FROM runtime_instances WHERE runtime_epoch=?", (epoch,))
            if profile["active_runtime_epoch"] != epoch or runtime["state"] != "ACTIVE":
                raise GuardError("STALE_EPOCH")
            prior = self.c.execute("SELECT * FROM operation_attempts WHERE operation_id=? ORDER BY attempt_no DESC LIMIT 1", (op_id,)).fetchone()
            if prior is not None and (prior["status"] != "ABANDONED" or not prior["recovery_evidence_ref"]):
                # UNKNOWN/provider-specific retry needs a separate reconciler.
                raise GuardError("RECONCILIATION_REQUIRED")
            approval = None
            if op["authorization_kind"] == "APPROVAL":
                approval = self.one("SELECT * FROM approvals WHERE operation_id=?", (op_id,))
                if approval["allowed_actor_id"] != actor or approval["binding_hash"] != op["binding_hash"] or now >= approval["expires_at"]:
                    raise GuardError("APPROVAL_INVALID")
                if approval["status"] not in {"APPROVED", "CONSUMED"}:
                    raise GuardError("APPROVAL_NOT_GRANTED")
                if approval["status"] == "CONSUMED" and prior is None:
                    raise GuardError("CONSUMPTION_LEDGER_MISSING")
            resource_key = f"workspace:{op['workspace_id']}"
            lease = self.c.execute("SELECT * FROM resource_leases WHERE resource_key=?", (resource_key,)).fetchone()
            if lease is not None and lease["state"] == "HELD":
                raise GuardError("RESOURCE_BUSY_REQUIRES_FENCING")  # Expiry alone is insufficient.
            fence = profile["last_fencing_token"] + 1
            self.c.execute("UPDATE profile_config SET last_fencing_token=?, version=version+1, updated_at=? WHERE singleton=1 AND version=? AND active_runtime_epoch=?", (fence, now, profile["version"], epoch))
            attempt_id = uid("attempt")
            dispatch_id = uid("dispatch")
            insert(self.c, "operation_attempts", attempt_id=attempt_id, operation_id=op_id, attempt_no=1 if prior is None else prior["attempt_no"] + 1, approval_id=None if approval is None else approval["approval_id"], runtime_epoch=epoch, fencing_token=fence, dispatch_id=dispatch_id, executor_id="fixture-executor", claim_cancel_revision=task["cancel_revision"], claim_policy_version=op["policy_version"], claim_identity_epoch=op["identity_epoch"], lease_set_json=j([{"key": resource_key, "fence": fence}]), status="CLAIMED", created_at=now)
            if approval is not None and approval["status"] == "APPROVED":
                changed = self.c.execute("UPDATE approvals SET status='CONSUMED', consumed_at=?, consumed_attempt_id=?, version=version+1 WHERE approval_id=? AND status='APPROVED' AND version=? AND expires_at>?", (now, attempt_id, approval["approval_id"], approval["version"], now)).rowcount
                if changed != 1:
                    raise GuardError("APPROVAL_CONSUME_CONFLICT")
                self.event(task["task_id"], "ApprovalConsumed", now, op_id)
            if lease is None:
                insert(self.c, "resource_leases", resource_key=resource_key, resource_type="WORKSPACE", holder_attempt_id=attempt_id, runtime_epoch=epoch, fencing_token=fence, state="HELD", acquired_at=now, expires_at=now + 5_000, updated_at=now)
            else:
                changed = self.c.execute("UPDATE resource_leases SET holder_attempt_id=?, runtime_epoch=?, fencing_token=?, state='HELD', acquired_at=?, expires_at=?, updated_at=?, version=version+1 WHERE resource_key=? AND version=? AND state<>'HELD'", (attempt_id, epoch, fence, now, now + 5_000, now, resource_key, lease["version"])).rowcount
                if changed != 1:
                    raise GuardError("RESOURCE_CLAIM_CONFLICT")
            changed = self.c.execute("UPDATE operations SET state='CLAIMED', current_attempt_id=?, version=version+1, updated_at=? WHERE operation_id=? AND state='READY' AND version=?", (attempt_id, now, op_id, op["version"])).rowcount
            if changed != 1:
                raise GuardError("OPERATION_CLAIM_CONFLICT")
            self.c.execute("UPDATE tasks SET state='RUNNING', version=version+1, updated_at=? WHERE task_id=? AND version=?", (now, task["task_id"], task["version"]))
            self.event(task["task_id"], "OperationClaimed", now, op_id, {"attempt_id": attempt_id, "dispatch_id": dispatch_id})
            return attempt_id

    def dispatch(self, attempt_id: str, actor: str = "owner", now: int = NOW + 3,
                 observed: dict | None = None) -> dict:
        """Persist intent, return only AFTER commit; does not contact a worker."""
        with transaction(self.c):
            attempt = self.one("SELECT * FROM operation_attempts WHERE attempt_id=?", (attempt_id,))
            op, task, profile = self.preflight(attempt["operation_id"], actor, now, observed if observed is not None else OBSERVED)
            if attempt["status"] != "CLAIMED" or op["state"] != "CLAIMED" or op["current_attempt_id"] != attempt_id:
                raise GuardError("NOT_CLAIMED")
            if profile["active_runtime_epoch"] != attempt["runtime_epoch"]:
                raise GuardError("STALE_EPOCH")
            if self.one("SELECT state FROM runtime_instances WHERE runtime_epoch=?", (attempt["runtime_epoch"],))["state"] != "ACTIVE":
                raise GuardError("STALE_EPOCH")
            if task["cancel_revision"] != attempt["claim_cancel_revision"]:
                raise GuardError("CANCELLATION_CHANGED")
            if op["authorization_kind"] == "APPROVAL":
                approval = self.one("SELECT * FROM approvals WHERE operation_id=?", (op["operation_id"],))
                if approval["status"] != "CONSUMED" or now >= approval["expires_at"]:
                    raise GuardError("CONSUMED_GRANT_EXPIRED_OR_INVALID")
            lease = self.one("SELECT * FROM resource_leases WHERE resource_key=?", (f"workspace:{op['workspace_id']}",))
            if lease["state"] != "HELD" or lease["holder_attempt_id"] != attempt_id or lease["runtime_epoch"] != attempt["runtime_epoch"] or lease["fencing_token"] != attempt["fencing_token"] or lease["expires_at"] <= now:
                raise GuardError("STALE_RESOURCE_LEASE")
            # This transaction is the linearization boundary for FIRST dispatch.
            # A later cancellation cannot atomically retract a remote side effect.
            changed = self.c.execute("""UPDATE operations SET state='DISPATCHING', version=version+1, updated_at=?
                WHERE operation_id=? AND state='CLAIMED' AND version=?
                  AND EXISTS (SELECT 1 FROM tasks t WHERE t.task_id=operations.task_id
                              AND t.cancel_requested_at IS NULL AND t.cancel_revision=?)
                  AND EXISTS (SELECT 1 FROM profile_config p WHERE p.singleton=1
                              AND p.active_runtime_epoch=? AND p.policy_version=operations.policy_version
                              AND p.identity_epoch=operations.identity_epoch)""",
                (now, op["operation_id"], op["version"], attempt["claim_cancel_revision"], attempt["runtime_epoch"])).rowcount
            if changed != 1:
                raise GuardError("DISPATCH_PRECONDITION_CHANGED")
            self.c.execute("UPDATE operation_attempts SET status='DISPATCHING', dispatch_started_at=?, version=version+1 WHERE attempt_id=? AND status='CLAIMED' AND version=?", (now, attempt_id, attempt["version"]))
            self.event(task["task_id"], "OperationDispatching", now, op["operation_id"])
            self.notify(task["task_id"], "DISPATCHING", now)
            envelope = {"operation_id": op["operation_id"], "attempt_id": attempt_id, "dispatch_id": attempt["dispatch_id"], "provider_idempotency_key": op["provider_idempotency_key"], "runtime_epoch": attempt["runtime_epoch"], "fencing_token": attempt["fencing_token"]}
        return envelope

    def release_lease(self, attempt_id: str, now: int) -> None:
        self.c.execute("UPDATE resource_leases SET state='RELEASED', holder_attempt_id=NULL, runtime_epoch=NULL, acquired_at=NULL, expires_at=NULL, updated_at=?, version=version+1 WHERE holder_attempt_id=? AND state='HELD'", (now, attempt_id))

    def abandon_before_dispatch(self, attempt_id: str, supervisor_evidence: str, now: int = NOW + 3) -> None:
        # The real product must VERIFY this proof using its supervisor. A string
        # supplied by a model, user request body or lease timer is not a proof.
        if not supervisor_evidence:
            raise GuardError("ISOLATION_EVIDENCE_REQUIRED")
        with transaction(self.c):
            attempt = self.one("SELECT * FROM operation_attempts WHERE attempt_id=?", (attempt_id,))
            op = self.one("SELECT * FROM operations WHERE operation_id=?", (attempt["operation_id"],))
            if attempt["status"] != "CLAIMED" or attempt["dispatch_started_at"] is not None or op["state"] != "CLAIMED" or op["current_attempt_id"] != attempt_id:
                raise GuardError("NOT_PROVEN_UNDISPATCHED")
            self.c.execute("UPDATE operation_attempts SET status='ABANDONED', finished_at=?, recovery_evidence_ref=?, version=version+1 WHERE attempt_id=? AND version=?", (now, supervisor_evidence, attempt_id, attempt["version"]))
            self.c.execute("UPDATE operations SET state='READY', version=version+1, updated_at=? WHERE operation_id=? AND version=?", (now, op["operation_id"], op["version"]))
            self.release_lease(attempt_id, now)
            self.event(op["task_id"], "UndispatchedClaimAbandoned", now, op["operation_id"], {"evidence_ref": supervisor_evidence})

    def cancel(self, task_id: str = "task-1", now: int = NOW + 3) -> str:
        with transaction(self.c):
            task = self.one("SELECT * FROM tasks WHERE task_id=?", (task_id,))
            if task["cancel_requested_at"] is not None or task["state"] in {"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"}:
                return task["state"]
            operations = self.c.execute("SELECT * FROM operations WHERE task_id=?", (task_id,)).fetchall()
            unresolved = any(op["state"] in {"DISPATCHING", "UNKNOWN"} for op in operations)
            for op in operations:
                if op["state"] not in {"PROPOSED", "AWAITING_APPROVAL", "READY", "CLAIMED"}:
                    continue
                if op["state"] == "CLAIMED":
                    self.c.execute("UPDATE operation_attempts SET status='CANCELLED', finished_at=?, version=version+1 WHERE attempt_id=? AND status='CLAIMED'", (now, op["current_attempt_id"]))
                    self.release_lease(op["current_attempt_id"], now)
                self.c.execute("UPDATE operations SET state='CANCELLED', completed_at=?, updated_at=?, version=version+1 WHERE operation_id=? AND version=?", (now, now, op["operation_id"], op["version"]))
                self.c.execute("UPDATE approvals SET status='REVOKED', version=version+1 WHERE operation_id=? AND status IN ('PENDING','APPROVED')", (op["operation_id"],))
            state = "RECONCILING" if unresolved else "CANCELLED"
            self.c.execute("UPDATE tasks SET state=?, cancel_requested_at=?, cancel_revision=cancel_revision+1, finished_at=?, updated_at=?, version=version+1 WHERE task_id=? AND version=?", (state, now, None if unresolved else now, now, task_id, task["version"]))
            self.event(task_id, "TaskCancellationRequested", now)
            self.notify(task_id, state, now)
            return state

    def finish_success(self, attempt_id: str, now: int = NOW + 4) -> None:
        """Fixture assumes a verified receipt and a one-operation outcome; no real verifier."""
        with transaction(self.c):
            attempt = self.one("SELECT * FROM operation_attempts WHERE attempt_id=?", (attempt_id,))
            op = self.one("SELECT * FROM operations WHERE operation_id=?", (attempt["operation_id"],))
            profile = self.one("SELECT * FROM profile_config WHERE singleton=1")
            lease = self.one("SELECT * FROM resource_leases WHERE holder_attempt_id=? AND state='HELD'", (attempt_id,))
            if profile["active_runtime_epoch"] != attempt["runtime_epoch"] or lease["fencing_token"] != attempt["fencing_token"] or op["current_attempt_id"] != attempt_id:
                raise GuardError("STALE_RESULT_REQUIRES_RECONCILIATION")
            if attempt["status"] != "DISPATCHING" or op["state"] != "DISPATCHING":
                raise GuardError("RESULT_STATE_CONFLICT")
            receipt = j({"fixture_receipt": True, "dispatch_id": attempt["dispatch_id"]})
            self.c.execute("UPDATE operation_attempts SET status='SUCCEEDED', finished_at=?, receipt_json=?, version=version+1 WHERE attempt_id=? AND version=?", (now, receipt, attempt_id, attempt["version"]))
            self.c.execute("UPDATE operations SET state='SUCCEEDED', completed_at=?, result_json=?, updated_at=?, version=version+1 WHERE operation_id=? AND version=?", (now, receipt, now, op["operation_id"], op["version"]))
            self.release_lease(attempt_id, now)
            remaining = self.c.execute("SELECT count(*) FROM operations WHERE task_id=? AND state<>'SUCCEEDED'", (op["task_id"],)).fetchone()[0]
            if remaining == 0:
                task = self.one("SELECT * FROM tasks WHERE task_id=?", (op["task_id"],))
                final = "CANCELLED" if task["cancel_requested_at"] is not None else "SUCCEEDED"
                self.c.execute("UPDATE tasks SET state=?, finished_at=?, updated_at=?, version=version+1 WHERE task_id=?", (final, now, now, op["task_id"]))
            self.event(op["task_id"], "OperationSucceeded", now, op["operation_id"])
            self.notify(op["task_id"], "RESULT_RECORDED", now)

    def unknown(self, attempt_id: str, now: int = NOW + 4) -> None:
        with transaction(self.c):
            attempt = self.one("SELECT * FROM operation_attempts WHERE attempt_id=?", (attempt_id,))
            op = self.one("SELECT * FROM operations WHERE operation_id=?", (attempt["operation_id"],))
            if attempt["status"] != "DISPATCHING" or op["state"] != "DISPATCHING" or op["current_attempt_id"] != attempt_id:
                raise GuardError("NOT_IN_FLIGHT")
            self.c.execute("UPDATE operation_attempts SET status='UNKNOWN', error_code='RESPONSE_LOST', version=version+1 WHERE attempt_id=?", (attempt_id,))
            self.c.execute("UPDATE operations SET state='UNKNOWN', unknown_reason='response lost after durable dispatch', updated_at=?, version=version+1 WHERE operation_id=?", (now, op["operation_id"]))
            self.c.execute("UPDATE tasks SET state='RECONCILING', updated_at=?, version=version+1 WHERE task_id=?", (now, op["task_id"]))
            self.event(op["task_id"], "OutcomeUnknown", now, op["operation_id"])
            self.notify(op["task_id"], "RECONCILING", now)
            # Deliberately retain the lease until worker isolation/reconciliation.

    def receive(self, scope: str, external_id: str, payload: dict, now: int = NOW) -> str:
        normalized = j(payload)
        with transaction(self.c):
            existing = self.c.execute("SELECT * FROM inbox WHERE source_scope=? AND external_event_id=?", (scope, external_id)).fetchone()
            if existing is not None:
                if existing["payload_hash"] != digest(normalized):
                    raise GuardError("IDEMPOTENCY_PAYLOAD_MISMATCH")
                return existing["task_id"]
            task_id, budget_id = uid("task"), uid("budget")
            new_budget(self.c, budget_id)
            insert(self.c, "tasks", task_id=task_id, session_id="session-1", owner_id="owner", budget_id=budget_id, goal="Fixture incoming message", created_at=now, updated_at=now)
            insert(self.c, "inbox", inbox_id=uid("inbox"), source_scope=scope, external_event_id=external_id, channel_account_id="feishu-1", payload_hash=digest(normalized), normalized_payload_json=normalized, task_id=task_id, status="PROCESSED", received_at=now, processed_at=now)
            self.event(task_id, "TaskQueued", now)
            self.notify(task_id, "QUEUED", now)
            return task_id


class DatabaseDesignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="openbot-ddl-design-")
        self.c = sqlite3.connect(str(Path(self.temp.name) / "test.sqlite3"), isolation_level=None)
        self.c.row_factory = sqlite3.Row
        self.checksum = install_baseline(self.c)
        seed(self.c)
        self.ref = ReferenceTransactions(self.c)

    def tearDown(self):
        try:
            self.assertEqual(self.c.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            self.c.close()
            self.temp.cleanup()

    def row(self, table: str, key: str, value: str) -> dict:
        return dict(self.c.execute(f"SELECT * FROM {table} WHERE {key}=?", (value,)).fetchone())

    def rejected(self, sql: str, params: tuple = ()) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.c):
                self.c.execute(sql, params)

    def approved_claim(self) -> str:
        self.ref.approve()
        return self.ref.claim()

    def test_01_connection_and_schema(self):
        """WAL/FULL/FK settings and migration checksum are actual connection values."""
        self.assertEqual(self.c.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(self.c.execute("PRAGMA synchronous").fetchone()[0], 2)
        self.assertEqual(self.c.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(self.c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(self.c.execute("SELECT checksum FROM schema_migrations").fetchone()[0], self.checksum)
        self.assertEqual(self.c.execute("SELECT count(*) FROM pragma_table_list WHERE schema='main' AND name NOT LIKE 'sqlite_%' AND strict=0").fetchone()[0], 0)

    def test_02_successful_reference_lifecycle(self):
        """Approve -> claim -> durable dispatch -> receipt commits state/event/outbox."""
        attempt_id = self.approved_claim()
        envelope = self.ref.dispatch(attempt_id)
        self.assertFalse(self.c.in_transaction)
        self.assertEqual(envelope["dispatch_id"], self.row("operation_attempts", "attempt_id", attempt_id)["dispatch_id"])
        self.ref.finish_success(attempt_id)
        self.assertEqual(self.row("tasks", "task_id", "task-1")["state"], "SUCCEEDED")
        self.assertEqual(self.row("approvals", "operation_id", "op-1")["status"], "CONSUMED")
        self.assertEqual(self.c.execute("SELECT count(*) FROM events WHERE event_type='ApprovalConsumed'").fetchone()[0], 1)
        self.assertGreaterEqual(self.c.execute("SELECT count(*) FROM outbox").fetchone()[0], 3)

    def test_03_inbox_idempotency_and_payload_conflict(self):
        task = self.ref.receive("feishu-1:messages", "provider-event-1", {"text": "hello"})
        self.assertEqual(task, self.ref.receive("feishu-1:messages", "provider-event-1", {"text": "hello"}))
        with self.assertRaisesRegex(GuardError, "PAYLOAD_MISMATCH"):
            self.ref.receive("feishu-1:messages", "provider-event-1", {"text": "changed"})
        self.assertEqual(self.c.execute("SELECT count(*) FROM inbox").fetchone()[0], 1)
        self.assertEqual(self.c.execute("SELECT count(*) FROM tasks").fetchone()[0], 2)
        raw = dict(self.c.execute("SELECT * FROM inbox").fetchone())
        raw["inbox_id"] = "duplicate-id"
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.c):
                insert(self.c, "inbox", **raw)

    def test_04_external_ids_are_source_scoped(self):
        a = self.ref.receive("account-a:events", "same-external-id", {"text": "hello"})
        b = self.ref.receive("account-b:events", "same-external-id", {"text": "hello"})
        self.assertNotEqual(a, b)

    def test_05_duplicate_approval_and_nonce_are_rejected(self):
        raw = self.row("approvals", "operation_id", "op-1")
        raw["approval_id"] = "duplicate-approval"
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.c):
                insert(self.c, "approvals", **raw)
        with transaction(self.c):
            add_operation(self.c, "op-2", 2, with_approval=False)
        raw.update(operation_id="op-2", binding_hash=self.row("operations", "operation_id", "op-2")["binding_hash"])
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.c):
                insert(self.c, "approvals", **raw)  # Same nonce across a different Operation.
        self.ref.approve()
        before = self.c.execute("SELECT count(*) FROM events").fetchone()[0]
        self.assertEqual(self.ref.approve(), "APPROVED")
        self.assertEqual(self.c.execute("SELECT count(*) FROM events").fetchone()[0], before)

    def test_06_wrong_actor_nonce_and_expiry_are_application_guards(self):
        for kwargs in ({"actor": "viewer"}, {"nonce": "forged"}, {"now": NOW + 60_000}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(GuardError):
                    self.ref.approve(**kwargs)
        self.assertEqual(self.row("approvals", "operation_id", "op-1")["status"], "PENDING")
        self.assertEqual(self.c.execute("SELECT count(*) FROM events").fetchone()[0], 0)

    def test_07_proposal_and_provider_key_are_immutable(self):
        for column, value in (("canonical_args_json", j({"path": "different"})), ("resource_snapshot_json", "{}"), ("binding_hash", digest("changed")), ("provider_idempotency_key", "different-key"), ("authorization_expires_at", NOW + 90_000)):
            with self.subTest(column=column):
                self.rejected(f"UPDATE operations SET {column}=?, version=version+1 WHERE operation_id='op-1'", (value,))
        self.rejected("INSERT OR REPLACE INTO operations SELECT * FROM operations WHERE operation_id='op-1'")

    def test_08_foreign_keys_and_approval_binding(self):
        raw = self.row("operations", "operation_id", "op-1")
        raw.update(operation_id="orphan-op", task_id="missing-task", provider_idempotency_key="orphan-key")
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.c):
                insert(self.c, "operations", **raw)
        with transaction(self.c):
            add_operation(self.c, "op-2", 2, with_approval=False)
        approval = self.row("approvals", "operation_id", "op-1")
        approval.update(approval_id="bad-binding", operation_id="op-2", nonce_hash=digest("nonce-other"))
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.c):
                insert(self.c, "approvals", **approval)

    def test_09_status_json_nonempty_and_strict_types(self):
        for field, value in (("state", "SUCCEDED"), ("canonical_args_json", "{"), ("canonical_args_json", "[]"), ("retry_class", "UNSAFE_AUTO_RETRY"), ("operation_id", " "), ("ordinal", "not-an-integer")):
            with self.subTest(field=field, value=value):
                raw = self.row("operations", "operation_id", "op-1")
                raw.update(operation_id=uid("op"), ordinal=10, provider_idempotency_key=uid("key"))
                raw[field] = value
                with self.assertRaises(sqlite3.IntegrityError):
                    with transaction(self.c):
                        insert(self.c, "operations", **raw)
        self.rejected("UPDATE approvals SET status='ALLOW', version=version+1 WHERE operation_id='op-1'")
        self.rejected("UPDATE tasks SET state='UNKNOWN', version=version+1 WHERE task_id='task-1'")

    def test_10_audit_append_only_including_replace(self):
        with transaction(self.c):
            self.ref.event("task-1", "FixtureEvent", NOW)
        self.rejected("UPDATE events SET payload_json='{}'")
        self.rejected("DELETE FROM events")
        self.rejected("INSERT OR REPLACE INTO events SELECT * FROM events")
        self.rejected("UPDATE schema_migrations SET checksum=?", (digest("other"),))
        self.rejected("DELETE FROM policy_revisions")

    def test_11_no_cascading_authorization_deletion(self):
        self.rejected("DELETE FROM approvals WHERE operation_id='op-1'")
        self.rejected("DELETE FROM operations WHERE operation_id='op-1'")
        self.rejected("DELETE FROM tasks WHERE task_id='task-1'")
        self.assertEqual(self.c.execute("SELECT count(*) FROM approvals").fetchone()[0], 1)

    def test_12_consumed_approval_cannot_revive(self):
        self.approved_claim()
        for status in ("APPROVED", "PENDING", "REVOKED", "EXPIRED"):
            with self.subTest(status=status):
                self.rejected("UPDATE approvals SET status=?, consumed_at=NULL, consumed_attempt_id=NULL, version=version+1 WHERE operation_id='op-1'", (status,))
        self.rejected("UPDATE approvals SET consumed_at=consumed_at+1, version=version+1 WHERE operation_id='op-1'")

    def test_13_safe_retry_keeps_consumption_and_operation_key(self):
        first = self.approved_claim()
        original_grant = self.row("approvals", "operation_id", "op-1")
        first_row = self.row("operation_attempts", "attempt_id", first)
        self.ref.abandon_before_dispatch(first, "fixture:supervisor-isolated-first-worker")
        second = self.ref.claim(now=NOW + 4)
        second_row = self.row("operation_attempts", "attempt_id", second)
        self.assertNotEqual(first_row["dispatch_id"], second_row["dispatch_id"])
        self.assertEqual(second_row["attempt_no"], 2)
        self.assertGreater(second_row["fencing_token"], first_row["fencing_token"])
        self.assertEqual(original_grant, self.row("approvals", "operation_id", "op-1"))
        self.assertEqual(self.row("operations", "operation_id", "op-1")["provider_idempotency_key"], "provider-key-op-1")
        self.assertEqual(self.c.execute("SELECT count(*) FROM events WHERE event_type='ApprovalConsumed'").fetchone()[0], 1)
        self.ref.dispatch(second, now=NOW + 5)

    def test_14_retry_rechecks_consumed_grant_expiry(self):
        first = self.approved_claim()
        self.ref.abandon_before_dispatch(first, "fixture:isolated")
        with self.assertRaisesRegex(GuardError, "EXPIRED"):
            self.ref.claim(now=NOW + 60_001)
        self.assertEqual(self.c.execute("SELECT count(*) FROM operation_attempts").fetchone()[0], 1)
        self.assertEqual(self.row("approvals", "operation_id", "op-1")["status"], "CONSUMED")

    def test_15_cancel_before_claim_prevents_execution(self):
        self.ref.approve()
        self.ref.cancel(now=NOW + 2)
        with self.assertRaisesRegex(GuardError, "CANCELLED"):
            self.ref.claim(now=NOW + 3)
        self.assertEqual(self.c.execute("SELECT count(*) FROM operation_attempts").fetchone()[0], 0)

    def test_16_cancel_between_claim_and_dispatch(self):
        attempt = self.approved_claim()
        self.assertEqual(self.ref.cancel(now=NOW + 3), "CANCELLED")
        with self.assertRaises(GuardError):
            self.ref.dispatch(attempt, now=NOW + 4)
        self.assertEqual(self.row("operation_attempts", "attempt_id", attempt)["status"], "CANCELLED")
        self.assertEqual(self.c.execute("SELECT count(*) FROM events WHERE event_type='OperationDispatching'").fetchone()[0], 0)
        self.assertEqual(self.row("approvals", "operation_id", "op-1")["status"], "CONSUMED")

    def test_17_cancel_after_dispatch_remains_reconciling(self):
        attempt = self.approved_claim()
        self.ref.dispatch(attempt)
        self.assertEqual(self.ref.cancel(now=NOW + 4), "RECONCILING")
        self.assertEqual(self.row("operations", "operation_id", "op-1")["state"], "DISPATCHING")
        self.rejected("UPDATE tasks SET state='CANCELLED', finished_at=?, version=version+1 WHERE task_id='task-1'", (NOW + 5,))

    def test_18_epoch_changes_block_first_dispatch_and_stale_results(self):
        attempt = self.approved_claim()
        with transaction(self.c):
            self.c.execute("UPDATE runtime_instances SET state='LOST', ended_at=? WHERE runtime_epoch='epoch-1'", (NOW + 3,))
            insert(self.c, "runtime_instances", runtime_epoch="epoch-2", boot_id="boot-2", supervisor_ref="fixture:new-supervisor", state="ACTIVE", started_at=NOW + 3, heartbeat_at=NOW + 3)
            self.c.execute("UPDATE profile_config SET active_runtime_epoch='epoch-2', version=version+1 WHERE singleton=1")
        with self.assertRaisesRegex(GuardError, "STALE_EPOCH"):
            self.ref.dispatch(attempt, now=NOW + 4)
        with self.assertRaisesRegex(GuardError, "STALE_RESULT"):
            self.ref.finish_success(attempt, now=NOW + 4)

    def test_19_resource_change_after_claim_blocks_dispatch(self):
        attempt = self.approved_claim()
        with self.assertRaisesRegex(GuardError, "RESOURCE_CHANGED"):
            self.ref.dispatch(attempt, observed={"workspace_generation": 1, "old_sha256": digest("attacker changed file")})
        with transaction(self.c):
            self.c.execute("UPDATE workspaces SET generation=2, version=version+1 WHERE workspace_id='ws-1'")
        with self.assertRaisesRegex(GuardError, "RESOURCE_CHANGED"):
            self.ref.dispatch(attempt)

    def test_20_policy_change_after_claim_blocks_dispatch(self):
        attempt = self.approved_claim()
        with transaction(self.c):
            insert(self.c, "policy_revisions", version=2, digest=digest("policy-two"), rules_json="{}", effective_at=NOW + 3, created_at=NOW + 3)
            self.c.execute("UPDATE profile_config SET policy_version=2, version=version+1 WHERE singleton=1")
        with self.assertRaisesRegex(GuardError, "AUTHORIZATION_STALE"):
            self.ref.dispatch(attempt, now=NOW + 4)

    def test_21_identity_change_and_tool_quarantine_block_claim(self):
        self.ref.approve()
        with transaction(self.c):
            self.c.execute("UPDATE tool_registry SET status='QUARANTINED'")
        with self.assertRaisesRegex(GuardError, "QUARANTINED"):
            self.ref.claim()
        with transaction(self.c):
            self.c.execute("UPDATE tool_registry SET status='ACTIVE'")
            self.c.execute("UPDATE profile_config SET identity_epoch=2, version=version+1 WHERE singleton=1")
        with self.assertRaisesRegex(GuardError, "AUTHORIZATION_STALE"):
            self.ref.claim()

    def test_22_wrong_expected_version_has_no_partial_commit(self):
        with self.assertRaisesRegex(GuardError, "VERSION_CONFLICT"):
            self.ref.approve(expected_version=42)
        self.assertEqual(self.row("approvals", "operation_id", "op-1")["status"], "PENDING")
        self.assertEqual(self.row("operations", "operation_id", "op-1")["state"], "AWAITING_APPROVAL")
        self.rejected("UPDATE operations SET state='READY' WHERE operation_id='op-1'")

    def test_23_failed_outbox_rolls_back_approval_state_and_event(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.ref.approve(fail_notification=True)
        self.assertEqual(self.row("approvals", "operation_id", "op-1")["status"], "PENDING")
        self.assertEqual(self.row("operations", "operation_id", "op-1")["state"], "AWAITING_APPROVAL")
        self.assertEqual(self.c.execute("SELECT count(*) FROM events").fetchone()[0], 0)
        self.assertEqual(self.c.execute("SELECT count(*) FROM outbox").fetchone()[0], 0)

    def test_24_unknown_outcome_blocks_retry_and_success(self):
        attempt = self.approved_claim()
        self.ref.dispatch(attempt)
        self.ref.unknown(attempt)
        self.assertEqual(self.row("tasks", "task_id", "task-1")["state"], "RECONCILING")
        with self.assertRaises(GuardError):
            self.ref.claim(now=NOW + 5)
        with self.assertRaises(GuardError):
            self.ref.abandon_before_dispatch(attempt, "pretend-proof", now=NOW + 5)
        self.rejected("UPDATE tasks SET state='SUCCEEDED', finished_at=?, version=version+1 WHERE task_id='task-1'", (NOW + 5,))
        self.rejected("UPDATE operations SET state='READY', version=version+1 WHERE operation_id='op-1'")

    def test_25_fencing_counters_never_reset(self):
        attempt = self.approved_claim()
        self.ref.abandon_before_dispatch(attempt, "fixture:isolated")
        self.ref.claim(now=NOW + 4)
        self.rejected("UPDATE resource_leases SET fencing_token=fencing_token-1, version=version+1")
        self.rejected("DELETE FROM resource_leases")
        self.rejected("INSERT OR REPLACE INTO resource_leases SELECT * FROM resource_leases")
        self.rejected("UPDATE profile_config SET last_fencing_token=0, version=version+1")

    def test_26_attempt_and_dispatch_identity_are_not_reused(self):
        attempt = self.approved_claim()
        self.rejected("UPDATE operation_attempts SET dispatch_id='changed', version=version+1 WHERE attempt_id=?", (attempt,))
        raw = self.row("operation_attempts", "attempt_id", attempt)
        original_dispatch_id = raw["dispatch_id"]
        raw.update(attempt_id="duplicate-active-attempt", attempt_no=2, dispatch_id="new-dispatch")
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.c):
                insert(self.c, "operation_attempts", **raw)
        envelope = self.ref.dispatch(attempt)
        self.assertEqual(envelope["dispatch_id"], original_dispatch_id)
        self.assertEqual(self.row("operation_attempts", "attempt_id", attempt)["dispatch_id"], original_dispatch_id)
        with self.assertRaisesRegex(GuardError, "NOT_CLAIMED"):
            self.ref.dispatch(attempt, now=NOW + 4)

    def test_27_single_profile_owner_and_active_runtime(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.c):
                insert(self.c, "principals", principal_id="another-owner", role="OWNER", status="ACTIVE", display_name="other", created_at=NOW)
        raw = self.row("profile_config", "singleton", 1)
        raw.update(singleton=2, profile_id="profile-2")
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.c):
                insert(self.c, "profile_config", **raw)
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.c):
                insert(self.c, "runtime_instances", runtime_epoch="concurrent", boot_id="boot", supervisor_ref="fixture", state="ACTIVE", started_at=NOW, heartbeat_at=NOW)

    def test_28_outbox_revisions_do_not_overwrite_payload(self):
        self.ref.approve()
        raw = dict(self.c.execute("SELECT * FROM outbox LIMIT 1").fetchone())
        self.rejected("UPDATE outbox SET payload_json='{}', version=version+1")
        raw["outbox_id"] = "duplicate-revision"
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.c):
                insert(self.c, "outbox", **raw)
        with transaction(self.c):
            self.ref.notify("task-1", "NEWER_STATE", NOW + 2)
            self.c.execute("""UPDATE outbox SET state='SUPERSEDED', version=version+1
                WHERE state='PENDING' AND revision < (SELECT max(newer.revision) FROM outbox newer
                  WHERE newer.target_key=outbox.target_key AND newer.semantic_key=outbox.semantic_key)""")
        states = [row[0] for row in self.c.execute("SELECT state FROM outbox ORDER BY revision")]
        self.assertEqual(states, ["SUPERSEDED", "PENDING"])

    def test_29_budget_admission_is_conditional_and_atomic(self):
        def reserve(amount: int, call: str):
            with transaction(self.c):
                changed = self.c.execute("""UPDATE budgets SET amount_reserved_micros=amount_reserved_micros+?, version=version+1
                    WHERE budget_id='budget-1' AND ? <= amount_limit_micros-amount_spent_micros-amount_reserved_micros""", (amount, amount)).rowcount
                if changed != 1:
                    raise GuardError("BUDGET_EXHAUSTED")
                insert(self.c, "budget_reservations", reservation_id=uid("reservation"), budget_id="budget-1", operation_id="op-1", call_ref=call, kind="MODEL", status="RESERVED", reserved_amount_micros=amount, reserved_tokens=0, created_at=NOW)
        reserve(700_000, "call-1")
        with self.assertRaisesRegex(GuardError, "BUDGET_EXHAUSTED"):
            reserve(400_000, "call-2")
        self.assertEqual(self.row("budgets", "budget_id", "budget-1")["amount_reserved_micros"], 700_000)
        self.assertEqual(self.c.execute("SELECT count(*) FROM budget_reservations").fetchone()[0], 1)

    def test_30_definition_artifact_and_workspace_guards(self):
        self.rejected("UPDATE tool_registry SET package_digest=?", (digest("unreviewed-code"),))
        self.rejected("UPDATE workspaces SET root_ref='managed:other', version=version+1")
        with transaction(self.c):
            insert(self.c, "artifacts", object_id="artifact-1", object_key="objects/fixture", sha256=digest("artifact"), mime="text/plain", bytes=8, classification="WORKSPACE", state="AVAILABLE", created_at=NOW)
        self.rejected("UPDATE artifacts SET sha256=?", (digest("replaced"),))
        self.rejected("INSERT OR REPLACE INTO artifacts SELECT * FROM artifacts")
        self.rejected("INSERT OR REPLACE INTO tool_registry SELECT * FROM tool_registry")

    def test_31_approval_survives_connection_reopen(self):
        """Close/reopen verifies durable state recovery, not physical power-loss safety."""
        self.ref.approve()
        saved_event_count = self.c.execute("SELECT count(*) FROM events").fetchone()[0]
        self.c.close()
        self.c = sqlite3.connect(str(Path(self.temp.name) / "test.sqlite3"), isolation_level=None)
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA foreign_keys=ON")
        self.c.execute("PRAGMA synchronous=FULL")
        self.c.execute("PRAGMA recursive_triggers=ON")
        self.c.execute("PRAGMA busy_timeout=250")
        self.ref = ReferenceTransactions(self.c)
        self.assertEqual(self.row("operations", "operation_id", "op-1")["state"], "READY")
        self.assertEqual(self.c.execute("SELECT count(*) FROM events").fetchone()[0], saved_event_count)
        self.assertEqual(self.c.execute("SELECT checksum FROM schema_migrations").fetchone()[0], self.checksum)
        self.ref.claim(now=NOW + 10)
        self.assertEqual(self.c.execute("SELECT count(*) FROM operation_attempts").fetchone()[0], 1)

    def test_32_expired_lease_is_not_automatic_takeover_permission(self):
        attempt = self.approved_claim()
        with self.assertRaisesRegex(GuardError, "STALE_RESOURCE_LEASE"):
            self.ref.dispatch(attempt, now=NOW + 6_000)
        with self.assertRaises(GuardError):
            self.ref.claim(now=NOW + 6_001)
        self.assertEqual(self.row("operation_attempts", "attempt_id", attempt)["status"], "CLAIMED")
        self.assertEqual(self.c.execute("SELECT count(*) FROM operation_attempts").fetchone()[0], 1)

    def test_33_unknown_quarantine_blocks_new_task_or_operation_ids(self):
        attempt = self.approved_claim()
        self.ref.dispatch(attempt)
        self.ref.unknown(attempt)
        with transaction(self.c):
            new_budget(self.c, "budget-2")
            insert(self.c, "tasks", task_id="task-2", session_id="session-1", owner_id="owner", budget_id="budget-2", goal="New task still uses the quarantined workspace", state="QUEUED", created_at=NOW + 5, updated_at=NOW + 5)
            add_operation(self.c, "op-new-task", 1, with_approval=False, task_id="task-2")
            add_operation(self.c, "op-same-task", 2, with_approval=False)
        with self.assertRaisesRegex(GuardError, "RESOURCE_BUSY"):
            self.ref.claim("op-new-task", now=NOW + 6_000)
        with self.assertRaisesRegex(GuardError, "TASK_NOT_RUNNABLE"):
            self.ref.claim("op-same-task", now=NOW + 6_000)
        self.assertEqual(self.c.execute("SELECT count(*) FROM operation_attempts").fetchone()[0], 1)
        self.assertEqual(self.row("resource_leases", "resource_key", "workspace:ws-1")["state"], "HELD")


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed_ids: list[str] = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed_ids.append(test.id())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Optional JSON report; does not retain temporary databases")
    args = parser.parse_args()
    print("OpenBot design DDL + reference transaction verification; no real product, network or worker execution.", flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DatabaseDesignTests)
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(suite)
    report = {
        "kind": "design_ddl_and_reference_transactions_only",
        "sqlite_version": sqlite3.sqlite_version,
        "schema_sha256": hashlib.sha256(DDL_PATH.read_bytes()).hexdigest(),
        "tests_run": result.testsRun,
        "passed": result.passed_ids,
        "failures": [{"test": test.id(), "traceback": detail} for test, detail in result.failures],
        "errors": [{"test": test.id(), "traceback": detail} for test, detail in result.errors],
        "success": result.wasSuccessful(),
        "not_validated": ["real authentication", "RFC 8785 implementation", "OS/file/network isolation", "supervisor evidence", "actual external effects or provider idempotency", "physical power-loss durability", "multi-process load", "full product state machine", "migration from an existing database"],
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
