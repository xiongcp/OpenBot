import hashlib
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from openbot.application.operations import OperationService
from openbot.application.state_machine import TaskStateService
from openbot.contracts import SchemaRegistry, canonicalize
from openbot.policy.approvals import ApprovalService
from openbot.storage.writer import RequestConflict

from tests.integration.storage.test_inbox_state import deadline, payload
from tests.integration.storage.test_inbox_state import system as storage_system

system = storage_system


class Challenges:
    def __init__(self):
        self.values = {}

    def put(self, identifier, nonce):
        assert identifier not in self.values
        self.values[identifier] = nonce

    def get(self, identifier):
        return self.values.get(identifier)


@pytest.fixture
def approval_system(system):
    path, context, writer, inbox = system
    context = replace(context, channel="local")
    task = json.loads(inbox.submit(context, "approval-task", payload(), deadline()).result(5))[
        "task_id"
    ]
    writer.submit(
        TaskStateService(writer).command(context, task, 0, "RUNNING", "start-task", deadline())
    ).result(5)
    manifest = {
        "name": "test.marker",
        "version": "1.0.0",
        "effect": "LOCAL_WRITE",
        "retry_class": "IDEMPOTENT_WRITE",
        "input_schema": {
            "type": "object",
            "properties": {"marker": {"type": "string", "maxLength": 100}},
            "required": ["marker"],
            "additionalProperties": False,
        },
    }
    raw = canonicalize(manifest)
    # Reviewed registry fixture only. No tool implementation or executor is installed.
    import sqlite3

    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO tool_registry VALUES('test.marker','1.0.0',?,NULL,"
            "'synthetic-reviewed',?,'ACTIVE',1000)",
            (hashlib.sha256(raw).hexdigest(), raw.decode()),
        )
    challenges = Challenges()
    from tests.integration.storage.test_migrations import ROOT

    registry = SchemaRegistry.from_directory(ROOT / "contracts")
    operations = OperationService(writer, challenges, registry)
    approvals = ApprovalService(writer, challenges, registry)
    return path, context, writer, task, operations, approvals, challenges


def propose(env, request_id="proposal-one", args=None):
    path, context, writer, task, operations, approvals, challenges = env
    return json.loads(
        operations.propose(
            context,
            task,
            "test.marker",
            canonicalize(args or {"marker": "synthetic"}),
            {"workspace_generation": 1, "files": []},
            "WORKSPACE",
            {"kind": "LOCAL", "resource_ref": context.workspace_id},
            request_id,
            deadline(),
        )
    )


def decision(env, proposal, kind="APPROVE", **changes):
    nonce = env[-1].get(proposal["approval_id"]).decode()
    return canonicalize(
        {
            "decision": kind,
            "nonce": nonce,
            "expected_binding_hash": proposal["binding_hash"],
            "expected_version": 1,
        }
        | changes
    )


def test_approval_only_makes_ready_and_preserves_immutable_canonical_bytes(approval_system):
    env = approval_system
    _, context, writer, task, operations, approvals, challenges = env
    original = {"marker": "synthetic"}
    proposal = propose(env, args=original)
    original["marker"] = "changed"
    assert propose(env) == proposal
    doc = operations.load(context, proposal["operation_id"])
    assert doc.value()["args"] == {"marker": "synthetic"}
    before = doc.canonical
    body = decision(env, proposal)
    receipt = approvals.decide(context, proposal["approval_id"], body, "approve-one", deadline())
    assert json.loads(receipt)["operation_state"] == "READY"
    assert (
        approvals.decide(context, proposal["approval_id"], body, "approve-one", deadline())
        == receipt
    )
    assert operations.load(context, proposal["operation_id"]).canonical == before
    assert (
        writer.read(lambda db: db.execute("SELECT count(*) FROM operation_attempts").fetchone()[0])
        == 0
    )
    assert (
        writer.read(lambda db: db.execute("SELECT status FROM approvals").fetchone()[0])
        == "APPROVED"
    )
    logs = writer.read(lambda db: str(db.execute("SELECT payload_json FROM events").fetchall()))
    assert challenges.get(proposal["approval_id"]).decode() not in logs
    assert '"marker"' not in logs


@pytest.mark.parametrize(
    "fault",
    [
        "actor",
        "epoch",
        "nonce",
        "hash",
        "version",
        "policy",
        "resource",
        "cancel",
        "lost_challenge",
        "device",
    ],
)
def test_approval_rechecks_authority_before_ready(approval_system, fault):
    env = approval_system
    path, context, writer, task, operations, approvals, challenges = env
    proposal = propose(env)
    changes = {}
    if fault == "actor":
        context = replace(context, principal_id="pri_wrong1")
    elif fault == "epoch":
        context = replace(context, identity_epoch=2)
    elif fault == "device":
        context = replace(context, app_id="other-device")
    elif fault == "nonce":
        changes["nonce"] = "wrong-nonce-" * 4
    elif fault == "hash":
        changes["expected_binding_hash"] = "sha256:" + "b" * 64
    elif fault == "version":
        changes["expected_version"] = 2
    body = decision(env, proposal, **changes)
    import sqlite3

    with sqlite3.connect(path) as db:
        if fault == "policy":
            db.execute("INSERT INTO policy_revisions VALUES(2,?,'{}',1001,1001)", ("b" * 64,))
            db.execute("UPDATE profile_config SET policy_version=2,version=version+1")
        elif fault == "resource":
            db.execute("UPDATE workspaces SET generation=2,version=version+1")
        elif fault == "cancel":
            db.execute(
                "UPDATE tasks SET cancel_revision=1,cancel_requested_at=2000,version=version+1"
            )
    if fault == "lost_challenge":
        challenges.values.clear()
    with pytest.raises((PermissionError, RequestConflict)):
        approvals.decide(context, proposal["approval_id"], body, "approve-rejected", deadline())
    assert (
        writer.read(lambda db: db.execute("SELECT state FROM operations").fetchone()[0]) != "READY"
    )


def test_conflicting_parallel_decisions_have_one_durable_winner(approval_system):
    env = approval_system
    proposal = propose(env)
    _, context, writer, _, _, approvals, _ = env
    bodies = [decision(env, proposal, kind=kind) for kind in ("APPROVE", "DENY")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                approvals.decide,
                context,
                proposal["approval_id"],
                body,
                "decision-" + str(i),
                deadline(),
            )
            for i, body in enumerate(bodies)
        ]
        successes = []
        for future in futures:
            try:
                successes.append(future.result(5))
            except RequestConflict:
                pass
    assert len(successes) == 1
    assert (
        writer.read(
            lambda db: db.execute(
                "SELECT count(*) FROM events WHERE event_type='APPROVAL_DECIDED'"
            ).fetchone()[0]
        )
        == 1
    )
    assert writer.read(lambda db: db.execute("SELECT version FROM approvals").fetchone()[0]) == 1


def test_stored_proposal_cannot_be_replaced_or_rebound(approval_system):
    env = approval_system
    proposal = propose(env)
    path, _, _, _, _, _, _ = env
    import sqlite3

    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE operations SET proposal_canonical_json='{}',version=version+1")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE operations SET canonical_args_json='{}',version=version+1")
    assert proposal["binding_hash"].startswith("sha256:")


@pytest.mark.parametrize("reason", ["expired", "restart", "clock_backwards"])
def test_old_time_authority_cannot_approve(approval_system, monkeypatch, reason):
    env = approval_system
    proposal = propose(env)
    import openbot.policy.approvals as module
    from openbot.application.operations import clock_now
    from openbot.domain.clock import ClockSnapshot

    now = clock_now()
    if reason == "expired":
        current = ClockSnapshot(now.utc_ms + 61_000, now.monotonic_ms + 61_000, now.boot_id)
    elif reason == "restart":
        current = ClockSnapshot(now.utc_ms, now.monotonic_ms, "new-authority-instance")
    else:
        current = ClockSnapshot(now.utc_ms - 10_000, now.monotonic_ms, now.boot_id)
    monkeypatch.setattr(module, "clock_now", lambda: current)
    _, context, writer, _, _, approvals, _ = env
    with pytest.raises(PermissionError):
        approvals.decide(
            context, proposal["approval_id"], decision(env, proposal), "old-time", deadline()
        )
    assert (
        writer.read(lambda db: db.execute("SELECT state FROM operations").fetchone()[0]) != "READY"
    )


def test_completed_request_id_cannot_bypass_authenticated_device_scope(approval_system):
    env = approval_system
    proposal = propose(env)
    _, context, _, _, _, approvals, _ = env
    body = decision(env, proposal)
    approvals.decide(context, proposal["approval_id"], body, "one-device-request", deadline())
    with pytest.raises((PermissionError, RequestConflict)):
        approvals.decide(
            replace(context, app_id="another-device"),
            proposal["approval_id"],
            body,
            "one-device-request",
            deadline(),
        )


def test_authoritative_operation_id_must_match_ledger_primary_key(approval_system):
    env = approval_system
    proposal = propose(env)
    path, context, _, _, operations, _, _ = env
    import sqlite3

    doc = operations.load(context, proposal["operation_id"]).value()
    doc["operation_id"] = "op_other_binding1"
    doc.pop("binding_hash")
    doc["binding_hash"] = "sha256:" + hashlib.sha256(canonicalize(doc)).hexdigest()
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        cursor = db.execute(
            "SELECT * FROM operations WHERE operation_id=?", (proposal["operation_id"],)
        )
        record = dict(zip([c[0] for c in cursor.description], cursor.fetchone(), strict=True))
        record.update(
            operation_id="op_drifted_ledger1",
            ordinal=2,
            binding_hash=doc["binding_hash"][7:],
            proposal_canonical_json=canonicalize(doc).decode(),
        )
        db.execute(
            "INSERT INTO operations("
            + ",".join(record)
            + ") VALUES("
            + ",".join("?" for _ in record)
            + ")",
            tuple(record.values()),
        )
    with pytest.raises(PermissionError):
        operations.load(context, "op_drifted_ledger1")


def test_schema_failure_traceback_does_not_reveal_raw_approval_nonce(approval_system):
    env = approval_system
    proposal = propose(env)
    _, context, _, _, _, approvals, challenges = env
    with pytest.raises(ValueError) as failure:
        approvals.decide(
            context,
            proposal["approval_id"],
            decision(env, proposal, actor="forged"),
            "bad-schema-secret",
            deadline(),
        )
    rendered = "".join(traceback.format_exception(failure.value))
    assert challenges.get(proposal["approval_id"]).decode() not in rendered


def test_decision_schema_rejects_body_identity_and_conflicting_decisions(approval_system):
    env = approval_system
    proposal = propose(env)
    _, context, _, _, _, approvals, _ = env
    with pytest.raises(ValueError):
        approvals.decide(
            context,
            proposal["approval_id"],
            decision(env, proposal, actor="owner"),
            "body-owner",
            deadline(),
        )
    approvals.decide(
        context, proposal["approval_id"], decision(env, proposal, kind="DENY"), "deny", deadline()
    )
    with pytest.raises(RequestConflict):
        approvals.decide(
            context,
            proposal["approval_id"],
            decision(env, proposal),
            "approve-after-deny",
            deadline(),
        )


def test_unreviewed_tool_and_invalid_tool_args_never_create_operation(approval_system):
    env = approval_system
    with pytest.raises(ValueError):
        propose(env, args={"marker": "safe", "owner": True})
    _, context, writer, task, operations, _, _ = env
    with pytest.raises(PermissionError):
        operations.propose(
            context, task, "unknown.tool", b"{}", {}, "PUBLIC", {}, "unknown-tool", deadline()
        )
    assert writer.read(lambda db: db.execute("SELECT count(*) FROM operations").fetchone()[0]) == 0
