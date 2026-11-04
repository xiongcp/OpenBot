import json
import sqlite3
import time

import pytest
from openbot.application.cancellation import (
    CancellationService,
    WorkerStopAck,
)
from openbot.application.dispatch import DispatchService
from openbot.application.operations import OperationService
from openbot.application.recovery import RecoveryService
from openbot.application.resources import ResourceRequest
from openbot.application.state_machine import TaskStateService
from openbot.contracts import SchemaRegistry
from openbot.policy.approvals import ApprovalService
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.migrate import connect, load_migrations, migrate
from openbot.storage.writer import RequestConflict, Writer

from tests.integration.storage.test_migrations import ROOT
from tests.integration.storage.test_recovery import MemoryChallenges, _register_tools


def _deadline() -> int:
    return int(time.monotonic() * 1000) + 5000


class RecordingWorkerStop:
    def __init__(self) -> None:
        self.signals: list[dict[str, object]] = []

    def request_stop(
        self,
        *,
        task_id: str,
        operation_id: str,
        attempt_id: str,
        dispatch_id: str,
        executor_id: str,
        cancel_revision: int,
    ) -> WorkerStopAck:
        self.signals.append(
            {
                "task_id": task_id,
                "operation_id": operation_id,
                "attempt_id": attempt_id,
                "dispatch_id": dispatch_id,
                "executor_id": executor_id,
                "cancel_revision": cancel_revision,
            }
        )
        return WorkerStopAck(stop_signal_sent=True, detail="SIGTERM sent to isolated worker")


@pytest.fixture
def cancel_env(tmp_path):
    path = tmp_path / "cancel.sqlite"
    migrate(path, load_migrations(ROOT / "db/migrations"))
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
        _register_tools(db)
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
    dispatcher = DispatchService(writer, registry)
    recovery = RecoveryService(writer, registry)
    cancellation = CancellationService(writer)
    try:
        yield (
            path,
            context,
            writer,
            inbox,
            tasks,
            ops,
            approvals,
            dispatcher,
            recovery,
            cancellation,
            challenges,
        )
    finally:
        writer.close()


def test_cancel_after_claim_before_begin_dispatch_blocks_packet_and_revokes_grants(cancel_env):
    (
        path,
        context,
        writer,
        inbox,
        tasks,
        ops,
        approvals,
        dispatcher,
        _,
        cancellation,
        challenges,
    ) = cancel_env
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": "cancel-claimed", "network_mode": "OFFLINE"}
    )
    task_id = json.loads(inbox.submit(context, "evt-can-1", payload, _deadline()).result(5))[
        "task_id"
    ]
    writer.submit(tasks.command(context, task_id, 0, "RUNNING", "run-can-1", _deadline())).result(5)

    # Operation 1: CLAIMED (approval CONSUMED, not yet DISPATCHING)
    prop1 = json.loads(
        ops.propose(
            context,
            task_id,
            "fs.patch",
            '{"arg":"v1"}',
            {"workspace_generation": 1, "files": []},
            "WORKSPACE",
            {"kind": "LOCAL", "resource_ref": context.workspace_id},
            "prop-can-1",
            _deadline(),
        )
    )
    op1, apr1 = prop1["operation_id"], prop1["approval_id"]
    approvals.decide(
        context,
        apr1,
        json.dumps(
            {
                "expected_version": 1,
                "expected_binding_hash": prop1["binding_hash"],
                "decision": "APPROVE",
                "nonce": challenges.get(apr1).decode(),
            }
        ),
        "apr-can-1",
        _deadline(),
    )
    writer.submit(tasks.command(context, task_id, 3, "RUNNING", "run2-can-1", _deadline())).result(
        5
    )
    claimed1 = json.loads(
        writer.submit(
            dispatcher.claim(
                context,
                op1,
                "ep_1",
                "exec_1",
                [ResourceRequest("WORKSPACE", "wsp_test1", expected_generation=1)],
                30_000,
                "claim-can-1",
                _deadline(),
            )
        ).result(5)
    )
    att1 = claimed1["attempt_id"]

    # Operation 2: AWAITING_APPROVAL (approval PENDING)
    prop2 = json.loads(
        ops.propose(
            context,
            task_id,
            "gui.click",
            '{"arg":"v2"}',
            {"workspace_generation": 1, "files": []},
            "WORKSPACE",
            {"kind": "LOCAL", "resource_ref": context.workspace_id},
            "prop-can-2",
            _deadline(),
        )
    )
    op2, apr2 = prop2["operation_id"], prop2["approval_id"]

    # Cancel arrives after op1 is CLAIMED but before begin_dispatch
    snap_before = tasks.snapshot(context, task_id)
    res = cancellation.propagate_cancel(
        context,
        task_id,
        expected_version=int(snap_before["version"]),
        request_id="req-can-claimed",
        deadline_monotonic_ms=_deadline(),
    )
    assert res["state"] == "CANCELLED"
    assert res["cancel_revision"] == 1
    assert res["effects_rolled_back"] is False

    # Second short transaction (CLAIMED -> DISPATCHING) MUST be rejected; zero packets sent
    with pytest.raises((PermissionError, RequestConflict)):
        writer.submit(
            dispatcher.begin_dispatch(
                context, op1, att1, "ep_1", "exec_1", "disp-after-cancel", _deadline()
            )
        ).result(5)

    # Old PENDING approval apr2 was revoked and cannot be approved after cancel
    with pytest.raises((PermissionError, RequestConflict)):
        approvals.decide(
            context,
            apr2,
            json.dumps(
                {
                    "expected_version": 1,
                    "expected_binding_hash": prop2["binding_hash"],
                    "decision": "APPROVE",
                    "nonce": challenges.get(apr2).decode(),
                }
            ),
            "apr-after-cancel",
            _deadline(),
        )

    db = connect(path, readonly=True)
    try:
        assert (
            db.execute("SELECT state FROM operations WHERE operation_id=?", (op1,)).fetchone()[0]
            == "CANCELLED"
        )
        assert (
            db.execute("SELECT state FROM operations WHERE operation_id=?", (op2,)).fetchone()[0]
            == "CANCELLED"
        )
        assert (
            db.execute("SELECT status FROM approvals WHERE approval_id=?", (apr1,)).fetchone()[0]
            == "CONSUMED"
        )
        assert (
            db.execute("SELECT status FROM approvals WHERE approval_id=?", (apr2,)).fetchone()[0]
            == "REVOKED"
        )
        assert (
            db.execute(
                "SELECT dispatch_started_at FROM operation_attempts WHERE attempt_id=?", (att1,)
            ).fetchone()[0]
            is None
        )
        assert (
            db.execute(
                "SELECT state FROM resource_leases WHERE resource_key='workspace:wsp_test1'"
            ).fetchone()[0]
            == "RELEASED"
        )
    finally:
        db.close()


def test_cancel_during_dispatching_propagates_stop_retains_reconciling_and_preserves_past_effects(
    cancel_env,
):
    (
        path,
        context,
        writer,
        inbox,
        tasks,
        ops,
        approvals,
        dispatcher,
        recovery,
        cancellation,
        challenges,
    ) = cancel_env
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": "cancel-dispatching", "network_mode": "OFFLINE"}
    )
    task_id = json.loads(inbox.submit(context, "evt-can-2", payload, _deadline()).result(5))[
        "task_id"
    ]
    writer.submit(tasks.command(context, task_id, 0, "RUNNING", "run-can-2", _deadline())).result(5)

    # Record an already SUCCEEDED operation on this task (past effects are not rolled back)
    db = connect(path)
    try:
        raw_manifest = db.execute(
            "SELECT manifest_digest FROM tool_registry WHERE tool_id='fs.read'"
        ).fetchone()[0]
        db.execute(
            "INSERT INTO operations("
            "operation_id,task_id,ordinal,requested_by,workspace_id,workspace_generation,"
            "tool_id,tool_version,tool_manifest_digest,canonical_args_json,resource_snapshot_json,"
            "data_class,authorization_kind,policy_version,identity_epoch,authorization_expires_at,"
            "binding_hash,retry_class,state,created_at,updated_at,completed_at,"
            "proposal_canonical_json) "
            "VALUES('op_done_1',?,1,'pri_test1','wsp_test1',1,'fs.read','1.0.0',?,'{\"arg\":\"ok\"}',"
            "'{\"workspace_generation\":1}','WORKSPACE','POLICY_ALLOW',1,1,9999999999999,?,"
            "'SAFE_READ','SUCCEEDED',1000,1000,1000,'{\"synthetic\":true}')",
            (task_id, raw_manifest, "b" * 64),
        )
    finally:
        db.close()

    # Propose, approve, claim, and begin_dispatch a high-risk external write operation
    prop = json.loads(
        ops.propose(
            context,
            task_id,
            "gui.click",
            '{"arg":"submit"}',
            {"workspace_generation": 1, "files": []},
            "WORKSPACE",
            {"kind": "LOCAL", "resource_ref": context.workspace_id},
            "prop-can-disp",
            _deadline(),
        )
    )
    op_id, apr_id = prop["operation_id"], prop["approval_id"]
    approvals.decide(
        context,
        apr_id,
        json.dumps(
            {
                "expected_version": 1,
                "expected_binding_hash": prop["binding_hash"],
                "decision": "APPROVE",
                "nonce": challenges.get(apr_id).decode(),
            }
        ),
        "apr-can-disp",
        _deadline(),
    )
    writer.submit(tasks.command(context, task_id, 3, "RUNNING", "run2-can-2", _deadline())).result(
        5
    )
    claimed = json.loads(
        writer.submit(
            dispatcher.claim(
                context,
                op_id,
                "ep_1",
                "exec_1",
                [ResourceRequest("WORKSPACE", "wsp_test1", expected_generation=1)],
                30_000,
                "claim-can-disp",
                _deadline(),
            )
        ).result(5)
    )
    att_id = claimed["attempt_id"]
    writer.submit(
        dispatcher.begin_dispatch(
            context, op_id, att_id, "ep_1", "exec_1", "disp-can-disp", _deadline()
        )
    ).result(5)

    worker_stop = RecordingWorkerStop()
    snap = tasks.snapshot(context, task_id)
    res = cancellation.propagate_cancel(
        context,
        task_id,
        expected_version=int(snap["version"]),
        worker_port=worker_stop,
        request_id="req-can-in-flight",
        deadline_monotonic_ms=_deadline(),
    )
    # Must enter RECONCILING (NOT CANCELLED), send stop signal to worker, and preserve past effects
    assert res["state"] == "RECONCILING"
    assert res["cancel_revision"] == 1
    assert res["effects_rolled_back"] is False
    assert "op_done_1" in res["preserved_succeeded_operations"]
    assert len(worker_stop.signals) == 1
    assert worker_stop.signals[0]["operation_id"] == op_id
    assert worker_stop.signals[0]["attempt_id"] == att_id

    # Cannot finalize to CANCELLED while op_id is still DISPATCHING or UNKNOWN
    with pytest.raises(PermissionError):
        writer.submit(
            cancellation.finalize_cancelled(
                context,
                task_id,
                expected_version=int(res["version"]),
                request_id="fin-too-early",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)

    # Transition DISPATCHING -> UNKNOWN via epoch recovery, then reconcile with evidence artifact
    writer.submit(
        recovery.recover_epoch(
            context,
            "ep_2",
            "boot_2",
            "sup_2",
            old_epoch_isolated=True,
            request_id="rec-ep2-can",
            deadline_monotonic_ms=_deadline(),
        )
    ).result(5)
    db = connect(path)
    try:
        db.execute(
            "INSERT INTO artifacts("
            "object_id,object_key,sha256,mime,bytes,classification,state,created_at) "
            "VALUES('art_can_1','key_can_1',?,'text/plain',16,'WORKSPACE','AVAILABLE',2000)",
            ("c" * 64,),
        )
        db.execute(
            "INSERT INTO artifact_refs("
            "ref_id,object_id,owner_id,scope_kind,operation_id,purpose,created_at) "
            "VALUES('ref_can_1','art_can_1','pri_test1','OPERATION',?,'reconciliation',2000)",
            (op_id,),
        )
        op_ver = db.execute(
            "SELECT version FROM operations WHERE operation_id=?", (op_id,)
        ).fetchone()[0]
    finally:
        db.close()

    writer.submit(
        recovery.reconcile_unknown(
            context,
            op_id,
            json.dumps(
                {
                    "expected_version": op_ver,
                    "outcome": "CONFIRMED_SUCCEEDED",
                    "evidence_artifact_ids": ["art_can_1"],
                }
            ),
            provenance_kind="USER_ATTESTED",
            request_id="rec-can-resolve",
            deadline_monotonic_ms=_deadline(),
        )
    ).result(5)

    # Now finalize_cancelled transitions RECONCILING -> CANCELLED while preserving past ops
    cur_ver = int(tasks.snapshot(context, task_id)["version"])
    final_res = json.loads(
        writer.submit(
            cancellation.finalize_cancelled(
                context,
                task_id,
                expected_version=cur_ver,
                request_id="fin-after-reconcile",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    assert final_res["state"] == "CANCELLED"
    assert final_res["effects_rolled_back"] is False
    assert set(final_res["preserved_succeeded_operations"]) == {"op_done_1", op_id}


def test_caller_disconnect_and_uncommitted_cancel_never_lie_or_rollback_committed_cancel(
    cancel_env,
):
    (
        path,
        context,
        writer,
        inbox,
        tasks,
        _,
        _,
        _,
        _,
        cancellation,
        _,
    ) = cancel_env
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": "cancel-disconnect", "network_mode": "OFFLINE"}
    )
    task_id = json.loads(inbox.submit(context, "evt-can-3", payload, _deadline()).result(5))[
        "task_id"
    ]

    # 1. If DB commit fails, propagate_cancel raises and does NOT report cancel success
    db = connect(path)
    db.execute(
        "CREATE TRIGGER fail_cancel_outbox BEFORE INSERT ON outbox "
        "BEGIN SELECT RAISE(ABORT,'synthetic outbox failure'); END;"
    )
    db.close()
    with pytest.raises(sqlite3.IntegrityError):
        cancellation.propagate_cancel(
            context,
            task_id,
            expected_version=0,
            request_id="req-can-fail",
            deadline_monotonic_ms=_deadline(),
        )
    status_after_fail = cancellation.inspect_cancel_status(context, task_id)
    assert status_after_fail["cancel_revision"] == 0
    assert status_after_fail["cancel_requested_at_ms"] is None

    db = connect(path)
    db.execute("DROP TRIGGER fail_cancel_outbox")
    db.close()

    # 2. Commit cancellation; simulate client disconnect after commit and re-query status
    committed = cancellation.propagate_cancel(
        context,
        task_id,
        expected_version=0,
        request_id="req-can-ok",
        deadline_monotonic_ms=_deadline(),
    )
    assert committed["state"] == "CANCELLED"
    assert committed["cancel_revision"] == 1

    # Re-sending the same request_id returns identical idempotent receipt
    dup = cancellation.propagate_cancel(
        context,
        task_id,
        expected_version=0,
        request_id="req-can-ok",
        deadline_monotonic_ms=_deadline(),
    )
    assert dup["cancel_revision"] == 1
    assert dup["state"] == "CANCELLED"

    inspected = cancellation.inspect_cancel_status(context, task_id)
    assert inspected["cancel_revision"] == 1
    assert inspected["cancel_requested_at_ms"] is not None
    assert inspected["state"] == "CANCELLED"
