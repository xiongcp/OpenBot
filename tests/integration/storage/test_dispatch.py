import json
import time
from dataclasses import replace

import pytest
from openbot.application.dispatch import (
    DispatchService,
    mint_recovery_ticket,
)
from openbot.application.operations import OperationService
from openbot.application.resources import ResourceCoordinator, ResourceRequest
from openbot.application.state_machine import TaskStateService
from openbot.contracts import SchemaRegistry, canonicalize
from openbot.policy.approvals import ApprovalService
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.migrate import connect, load_migrations, migrate
from openbot.storage.writer import RequestConflict, Writer

from tests.integration.storage.test_migrations import ROOT


class MemoryChallenges:
    def __init__(self):
        self.items: dict[str, bytes] = {}

    def put(self, approval_id: str, nonce: bytes) -> None:
        self.items[approval_id] = nonce

    def get(self, approval_id: str) -> bytes | None:
        return self.items.get(approval_id)


def _deadline() -> int:
    return int(time.monotonic() * 1000) + 5000


@pytest.fixture
def dispatch_env(tmp_path):
    path = tmp_path / "dispatch.sqlite"
    migrate(path, load_migrations(ROOT / "db/migrations"))
    manifest = {
        "name": "provider.send",
        "version": "1.0.0",
        "effect": "EXTERNAL_WRITE",
        "retry_class": "PROVIDER_IDEMPOTENT",
        "input_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"body": {"type": "string"}},
            "required": ["body"],
            "additionalProperties": False,
        },
    }
    import hashlib

    digest = hashlib.sha256(canonicalize(manifest)).hexdigest()
    db = connect(path)
    try:
        db.execute("INSERT INTO policy_revisions VALUES(1,?,'{}',1000,1000)", ("a" * 64,))
        db.execute(
            "INSERT INTO runtime_instances("
            "runtime_epoch,boot_id,supervisor_ref,state,started_at,heartbeat_at) "
            "VALUES('ep_1','boot_1','sup_1','ACTIVE',1000,1000)"
        )
        db.execute(
            "INSERT INTO profile_config("
            "singleton,profile_id,schema_version,policy_version,identity_epoch,"
            "privacy_mode,active_runtime_epoch,last_fencing_token,created_at,updated_at) "
            "VALUES(1,'pro_test1',1,1,1,'OFFLINE','ep_1',0,1000,1000)"
        )
        db.execute(
            "INSERT INTO principals(principal_id,role,status,display_name,created_at) "
            "VALUES('pri_test1','OWNER','ACTIVE','synthetic owner',1000)"
        )
        db.execute(
            "INSERT INTO workspaces("
            "workspace_id,root_ref,generation,status,version,created_at,updated_at) "
            "VALUES('wsp_test1','synthetic-workspace',1,'ACTIVE',0,1000,1000)"
        )
        db.execute(
            "INSERT INTO sessions(session_id,owner_id,workspace_id,status,created_at,updated_at) "
            "VALUES('ses_test1','pri_test1','wsp_test1','OPEN',1000,1000)"
        )
        db.execute(
            "INSERT INTO tool_registry VALUES("
            "'provider.send','1.0.0',?,NULL,'builtin',?,'ACTIVE',1000)",
            (digest, canonicalize(manifest).decode()),
        )
    finally:
        db.close()

    context = InboundContext(
        "pro_test1", "pri_test1", 1, "local", "tenant1", "app1", "ses_test1", "wsp_test1"
    )
    registry = SchemaRegistry.from_directory(ROOT / "contracts")
    challenges = MemoryChallenges()
    writer = Writer(path)
    inbox = Inbox(writer, registry)
    tasks = TaskStateService(writer)
    ops = OperationService(writer, challenges, registry)
    approvals = ApprovalService(writer, challenges, registry)
    coord = ResourceCoordinator(writer)
    dispatcher = DispatchService(writer, registry)
    try:
        yield path, context, writer, inbox, tasks, ops, approvals, coord, dispatcher, challenges
    finally:
        writer.close()


def _create_ready_operation(
    context, writer, inbox, tasks, ops, approvals, challenges, event_id: str
) -> tuple[str, str, str]:
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": f"goal-{event_id}", "network_mode": "OFFLINE"}
    )
    task_id = json.loads(inbox.submit(context, event_id, payload, _deadline()).result(5))["task_id"]
    writer.submit(
        tasks.command(context, task_id, 0, "RUNNING", f"run-{event_id}", _deadline())
    ).result(5)
    proposed = json.loads(
        ops.propose(
            context,
            task_id,
            "provider.send",
            '{"body":"hello"}',
            {"workspace_generation": 1, "files": []},
            "WORKSPACE",
            {"kind": "LOCAL", "resource_ref": context.workspace_id},
            f"prop-{event_id}",
            _deadline(),
        )
    )
    op_id, apr_id = proposed["operation_id"], proposed["approval_id"]
    nonce = challenges.get(apr_id).decode()
    approvals.decide(
        context,
        apr_id,
        json.dumps(
            {
                "expected_version": 1,
                "expected_binding_hash": proposed["binding_hash"],
                "decision": "APPROVE",
                "nonce": nonce,
            }
        ),
        f"apr-{event_id}",
        _deadline(),
    )
    # Move task from QUEUED (after approval) back to RUNNING for execution
    writer.submit(
        tasks.command(context, task_id, 3, "RUNNING", f"run-after-apr-{event_id}", _deadline())
    ).result(5)
    return task_id, op_id, apr_id


def test_first_claim_and_second_transaction_dispatch_plus_concurrent_claim_rejection(dispatch_env):
    path, context, writer, inbox, tasks, ops, approvals, coord, dispatcher, challenges = (
        dispatch_env
    )
    task_id, op_id, apr_id = _create_ready_operation(
        context, writer, inbox, tasks, ops, approvals, challenges, "evt-d1"
    )
    resources = [ResourceRequest("WORKSPACE", "wsp_test1", expected_generation=1)]

    # Concurrent first claims with distinct request_ids: exactly one consumes the approval
    f1 = writer.submit(
        dispatcher.claim(
            context, op_id, "ep_1", "exec_1", resources, 30_000, "claim-d1-a", _deadline()
        )
    )
    f2 = writer.submit(
        dispatcher.claim(
            context, op_id, "ep_1", "exec_2", resources, 30_000, "claim-d1-b", _deadline()
        )
    )
    outcomes = []
    for fut in (f1, f2):
        try:
            outcomes.append(("ok", json.loads(fut.result(5))))
        except Exception as exc:
            outcomes.append(("err", exc))

    ok_outcomes = [val for tag, val in outcomes if tag == "ok"]
    err_outcomes = [val for tag, val in outcomes if tag == "err"]
    assert len(ok_outcomes) == 1
    assert len(err_outcomes) == 1
    claimed = ok_outcomes[0]
    assert claimed["operation_state"] == "CLAIMED"
    assert claimed["approval_status"] == "CONSUMED"
    attempt_id = claimed["attempt_id"]
    dispatch_id = claimed["dispatch_id"]
    provider_key = claimed["provider_idempotency_key"]
    assert dispatch_id.startswith("dsp_")
    assert provider_key.startswith("provider_")

    # Second short transaction: CLAIMED -> DISPATCHING
    dispatched = json.loads(
        writer.submit(
            dispatcher.begin_dispatch(
                context, op_id, attempt_id, "ep_1", "exec_1", "disp-d1-1", _deadline()
            )
        ).result(5)
    )
    assert dispatched["operation_state"] == "DISPATCHING"
    assert dispatched["dispatch_id"] == dispatch_id
    assert dispatched["provider_idempotency_key"] == provider_key

    # Retransmitting begin_dispatch for the same attempt keeps the exact same dispatch_id
    retransmitted = json.loads(
        writer.submit(
            dispatcher.begin_dispatch(
                context, op_id, attempt_id, "ep_1", "exec_1", "disp-d1-retransmit", _deadline()
            )
        ).result(5)
    )
    assert retransmitted["dispatch_id"] == dispatch_id


@pytest.mark.parametrize(
    "mutation", ["cancel_task", "epoch_changed", "workspace_changed", "policy_changed"]
)
def test_mutation_between_claim_and_dispatching_prevents_dispatch(dispatch_env, mutation):
    path, context, writer, inbox, tasks, ops, approvals, coord, dispatcher, challenges = (
        dispatch_env
    )
    task_id, op_id, _ = _create_ready_operation(
        context, writer, inbox, tasks, ops, approvals, challenges, f"evt-mut-{mutation}"
    )
    resources = [ResourceRequest("WORKSPACE", "wsp_test1", expected_generation=1)]
    claimed = json.loads(
        writer.submit(
            dispatcher.claim(
                context,
                op_id,
                "ep_1",
                "exec_1",
                resources,
                30_000,
                f"claim-mut-{mutation}",
                _deadline(),
            )
        ).result(5)
    )
    attempt_id = claimed["attempt_id"]

    # Inject mutation between Tx1 (CLAIMED) and Tx2 (DISPATCHING)
    if mutation == "cancel_task":
        writer.submit(tasks.cancel(context, task_id, 4, f"cancel-{mutation}", _deadline())).result(
            5
        )
    elif mutation == "epoch_changed":
        db = connect(path)
        db.execute(
            "UPDATE runtime_instances SET state='STOPPED',ended_at=2000 WHERE runtime_epoch='ep_1'"
        )
        db.execute(
            "INSERT INTO runtime_instances("
            "runtime_epoch,boot_id,supervisor_ref,state,started_at,heartbeat_at) "
            "VALUES('ep_2','boot_2','sup_2','ACTIVE',2000,2000)"
        )
        db.execute(
            "UPDATE profile_config SET active_runtime_epoch='ep_2',version=version+1,"
            "updated_at=2000 WHERE singleton=1"
        )
        db.close()
    elif mutation == "workspace_changed":
        db = connect(path)
        db.execute(
            "UPDATE workspaces SET root_ref='ws-v2',generation=2,version=version+1,updated_at=2000 "
            "WHERE workspace_id='wsp_test1'"
        )
        db.close()
    elif mutation == "policy_changed":
        db = connect(path)
        db.execute("INSERT INTO policy_revisions VALUES(2,?,'{\"v\":2}',2000,2000)", ("b" * 64,))
        db.execute(
            "UPDATE profile_config SET policy_version=2,version=version+1,updated_at=2000 "
            "WHERE singleton=1"
        )
        db.close()

    with pytest.raises((PermissionError, RequestConflict)):
        writer.submit(
            dispatcher.begin_dispatch(
                context, op_id, attempt_id, "ep_1", "exec_1", f"disp-mut-{mutation}", _deadline()
            )
        ).result(5)

    # Verify the attempt never entered DISPATCHING (dispatch_started_at is still NULL)
    db = connect(path, readonly=True)
    try:
        row = db.execute(
            "SELECT status,dispatch_started_at FROM operation_attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        assert row[0] != "DISPATCHING" and row[1] is None
    finally:
        db.close()


def test_consumed_grant_never_revives_and_only_recovery_ticket_creates_new_attempt(dispatch_env):
    path, context, writer, inbox, tasks, ops, approvals, coord, dispatcher, challenges = (
        dispatch_env
    )
    task_id, op_id, apr_id = _create_ready_operation(
        context, writer, inbox, tasks, ops, approvals, challenges, "evt-rec-1"
    )
    resources = [ResourceRequest("WORKSPACE", "wsp_test1", expected_generation=1)]

    claimed1 = json.loads(
        writer.submit(
            dispatcher.claim(
                context, op_id, "ep_1", "exec_1", resources, 30_000, "claim-rec-1", _deadline()
            )
        ).result(5)
    )
    att1 = claimed1["attempt_id"]
    dsp1 = claimed1["dispatch_id"]
    prov_key = claimed1["provider_idempotency_key"]

    # Simulate old worker isolated before dispatch: attempt 1 ABANDONED, operation back to READY
    db = connect(path)
    db.execute(
        "UPDATE resource_leases SET holder_attempt_id=NULL,runtime_epoch=NULL,state='RELEASED',"
        "acquired_at=NULL,expires_at=NULL,version=version+1,updated_at=2000"
    )
    db.execute(
        "UPDATE operation_attempts SET status='ABANDONED',recovery_evidence_ref='ev_isolated',"
        "finished_at=2000,version=version+1 WHERE attempt_id=?",
        (att1,),
    )
    db.execute(
        "UPDATE operations SET state='READY',version=version+1,updated_at=2000 "
        "WHERE operation_id=?",
        (op_id,),
    )
    db.close()

    # 1. Ordinary claim without recovery ticket is rejected because approval is already CONSUMED
    with pytest.raises(PermissionError):
        writer.submit(
            dispatcher.claim(
                context,
                op_id,
                "ep_1",
                "exec_2",
                resources,
                30_000,
                "claim-ordinary-reuse",
                _deadline(),
            )
        ).result(5)

    # 2. Recovery ticket for a DIFFERENT operation is rejected
    bad_ticket = mint_recovery_ticket("op_other", att1, "ep_1")
    with pytest.raises(PermissionError):
        writer.submit(
            dispatcher.claim(
                context,
                op_id,
                "ep_1",
                "exec_2",
                resources,
                30_000,
                "claim-wrong-op-ticket",
                _deadline(),
                recovery_ticket=bad_ticket,
            )
        ).result(5)

    # 3. Valid recovery ticket for same operation re-verifies conditions, keeps CONSUMED unchanged,
    # creates attempt 2 with a NEW dispatch_id, and preserves Operation provider_idempotency_key
    valid_ticket = mint_recovery_ticket(op_id, att1, "ep_1")
    claimed2 = json.loads(
        writer.submit(
            dispatcher.claim(
                context,
                op_id,
                "ep_1",
                "exec_2",
                resources,
                30_000,
                "claim-valid-recovery",
                _deadline(),
                recovery_ticket=valid_ticket,
            )
        ).result(5)
    )
    assert claimed2["attempt_id"] != att1
    assert claimed2["attempt_no"] == 2
    assert claimed2["dispatch_id"] != dsp1
    assert claimed2["provider_idempotency_key"] == prov_key
    assert claimed2["approval_status"] == "CONSUMED"

    db = connect(path, readonly=True)
    try:
        apr_row = db.execute(
            "SELECT status,consumed_attempt_id FROM approvals WHERE approval_id=?", (apr_id,)
        ).fetchone()
        # Original CONSUMED record never reverted to APPROVED and still points to first attempt
        assert apr_row == ("CONSUMED", att1)
    finally:
        db.close()

    # 4. If original authorization has expired, even a valid recovery ticket is rejected
    db = connect(path)
    db.execute(
        "UPDATE resource_leases SET holder_attempt_id=NULL,runtime_epoch=NULL,state='RELEASED',"
        "acquired_at=NULL,expires_at=NULL,version=version+1,updated_at=2500"
    )
    db.execute(
        "UPDATE operation_attempts SET status='ABANDONED',recovery_evidence_ref='ev_isolated2',"
        "finished_at=2500,version=version+1 WHERE attempt_id=?",
        (claimed2["attempt_id"],),
    )
    db.execute(
        "UPDATE operations SET state='READY',version=version+1,updated_at=2500 "
        "WHERE operation_id=?",
        (op_id,),
    )
    db.close()

    expired_ticket = mint_recovery_ticket(op_id, att1, "ep_1")
    with pytest.raises(PermissionError):
        writer.submit(
            dispatcher.claim(
                replace(context, identity_epoch=2),
                op_id,
                "ep_1",
                "exec_3",
                resources,
                30_000,
                "claim-stale-identity-recovery",
                _deadline(),
                recovery_ticket=expired_ticket,
            )
        ).result(5)
