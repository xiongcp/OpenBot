import json
import sqlite3
import subprocess
import sys
import time
from dataclasses import replace

import pytest
from openbot.application.state_machine import (
    TRANSITIONS,
    OutcomeSubmission,
    TaskStateService,
)
from openbot.contracts import SchemaRegistry
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.migrate import connect, load_migrations, migrate
from openbot.storage.writer import RequestConflict, Writer

from tests.integration.storage.test_migrations import ROOT


@pytest.fixture
def system(tmp_path):
    path = tmp_path / "state.sqlite"
    migrate(path, load_migrations(ROOT / "db/migrations"))
    db = connect(path)
    try:
        db.execute("INSERT INTO policy_revisions VALUES(1,?,'{}',1000,1000)", ("a" * 64,))
        db.execute(
            "INSERT INTO profile_config(singleton,profile_id,schema_version,policy_version,"
            "identity_epoch,privacy_mode,created_at,updated_at) "
            "VALUES(1,'pro_test1',1,1,1,'OFFLINE',1000,1000)"
        )
        db.execute(
            "INSERT INTO principals(principal_id,role,status,display_name,created_at) "
            "VALUES('pri_test1','OWNER','ACTIVE','synthetic owner',1000)"
        )
        db.execute(
            "INSERT INTO workspaces(workspace_id,root_ref,generation,status,created_at,updated_at) "
            "VALUES('wsp_test1','synthetic-workspace',1,'ACTIVE',1000,1000)"
        )
        db.execute(
            "INSERT INTO sessions(session_id,owner_id,workspace_id,status,created_at,updated_at) "
            "VALUES('ses_test1','pri_test1','wsp_test1','OPEN',1000,1000)"
        )
    finally:
        db.close()
    context = InboundContext(
        "pro_test1", "pri_test1", 1, "fake", "tenant1", "app1", "ses_test1", "wsp_test1"
    )
    writer = Writer(path)
    inbox = Inbox(writer, SchemaRegistry.from_directory(ROOT / "contracts"))
    try:
        yield path, context, writer, inbox
    finally:
        writer.close()


def payload(goal="synthetic task"):
    return json.dumps({"workspace_id": "wsp_test1", "goal": goal, "network_mode": "OFFLINE"})


def deadline():
    return int(time.monotonic() * 1000) + 5000


def test_inbox_dedupe_is_scoped_and_task_event_outbox_are_atomic(system):
    path, context, writer, inbox = system
    receipts = [
        json.loads(inbox.submit(context, "event-same", payload(), deadline()).result(timeout=5))
        for _ in range(100)
    ]
    assert len({r["task_id"] for r in receipts}) == 1
    other = json.loads(
        inbox.submit(replace(context, app_id="app2"), "event-same", payload(), deadline()).result(
            timeout=5
        )
    )
    assert other["task_id"] != receipts[0]["task_id"]
    db = connect(path, readonly=True)
    try:
        assert db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM inbox").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM outbox").fetchone()[0] == 2
    finally:
        db.close()
    with pytest.raises(RequestConflict):
        inbox.submit(context, "event-same", payload("changed"), deadline()).result(timeout=5)


def test_outbox_failure_does_not_ack_or_leave_partial_task(system):
    path, context, writer, inbox = system
    db = connect(path)
    db.execute(
        "CREATE TRIGGER fail_outbox BEFORE INSERT ON outbox "
        "BEGIN SELECT RAISE(ABORT,'synthetic full'); END;"
    )
    db.close()
    with pytest.raises(sqlite3.IntegrityError):
        inbox.submit(context, "event-failure", payload(), deadline()).result(timeout=5)
    db = connect(path, readonly=True)
    try:
        for table in ["tasks", "inbox", "events", "outbox", "budgets"]:
            assert db.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0
    finally:
        db.close()


def test_revoked_owner_stale_epoch_and_body_authority_do_not_create_tasks(system):
    path, context, writer, inbox = system
    for index, bad_context in enumerate(
        [replace(context, principal_id="pri_other1"), replace(context, identity_epoch=2)]
    ):
        with pytest.raises(PermissionError):
            inbox.submit(bad_context, f"event-bad-{index}", payload(), deadline()).result(timeout=5)
    with pytest.raises(ValueError):
        inbox.submit(
            context,
            "event-body",
            json.dumps(json.loads(payload()) | {"is_owner": True}),
            deadline(),
        )
    db = connect(path)
    db.execute(
        "UPDATE principals SET status='REVOKED',revoked_at=2000 WHERE principal_id='pri_test1'"
    )
    db.close()
    with pytest.raises(PermissionError):
        inbox.submit(context, "event-revoked", payload(), deadline()).result(timeout=5)


def test_task_cas_event_outbox_and_replay_have_one_authoritative_result(system):
    path, context, writer, inbox = system
    task = json.loads(
        inbox.submit(context, "event-state", payload(), deadline()).result(timeout=5)
    )["task_id"]
    service = TaskStateService(writer)
    command = service.command(context, task, 0, "RUNNING", "request-state-1", deadline())
    first_raw = writer.submit(command).result(timeout=5)
    first = json.loads(first_raw)
    assert first["state"] == "RUNNING" and first["version"] == 1
    assert writer.submit(command).result(timeout=5) == first_raw
    with pytest.raises(ValueError):
        writer.submit(
            service.command(context, task, 0, "PAUSED", "request-state-stale", deadline())
        ).result(timeout=5)
    with pytest.raises(PermissionError):
        writer.submit(
            service.command(context, task, 1, "SUCCEEDED", "model-final", deadline())
        ).result(timeout=5)
    events = service.replay(context, task)
    assert [event["event_type"] for event in events] == ["TASK_QUEUED", "TASK_STATE_CHANGED"]
    assert service.snapshot(context, task)["version"] == 1


def test_generic_state_port_cannot_bypass_cancel_use_case(system):
    path, context, writer, inbox = system
    task = json.loads(
        inbox.submit(context, "event-cancel", payload(), deadline()).result(timeout=5)
    )["task_id"]
    service = TaskStateService(writer)
    with pytest.raises(PermissionError):
        writer.submit(
            service.command(context, task, 0, "CANCELLED", "request-cancel", deadline())
        ).result(timeout=5)
    assert service.snapshot(context, task)["state"] == "QUEUED"


def test_request_id_scope_is_identical_after_writer_restart(system):
    path, context, writer, inbox = system
    first = json.loads(
        inbox.submit(context, "event-first", payload(), deadline()).result(timeout=5)
    )["task_id"]
    second = json.loads(
        inbox.submit(context, "event-second", payload(), deadline()).result(timeout=5)
    )["task_id"]
    service = TaskStateService(writer)
    writer.submit(
        service.command(context, first, 0, "RUNNING", "one-global-request", deadline())
    ).result(timeout=5)
    with pytest.raises(RequestConflict):
        writer.submit(
            service.command(context, second, 0, "RUNNING", "one-global-request", deadline())
        ).result(timeout=5)
    writer.close()
    with Writer(path) as restarted:
        service = TaskStateService(restarted)
        with pytest.raises(RequestConflict):
            restarted.submit(
                service.command(context, second, 0, "RUNNING", "one-global-request", deadline())
            ).result(timeout=5)
        assert service.snapshot(context, second)["state"] == "QUEUED"


@pytest.mark.parametrize("point", ["before_commit", "after_commit_before_ack"])
def test_process_exit_at_inbound_commit_boundary_never_duplicates_task(system, point):
    path, context, writer, inbox = system
    writer.close()
    code = r"""
import os, sys, time
from pathlib import Path
from openbot.contracts import SchemaRegistry
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.writer import Writer
import openbot.storage.inbox as module
context = InboundContext(
    "pro_test1", "pri_test1", 1, "fake", "tenant1", "app1", "ses_test1", "wsp_test1")
if sys.argv[2] == "before_commit":
    original = module.emit_state
    def crash(*args, **kwargs):
        original(*args, **kwargs)
        os._exit(77)
    module.emit_state = crash
writer = Writer(Path(sys.argv[1]))
inbox = Inbox(writer, SchemaRegistry.from_directory(Path("contracts")))
raw = (b'{"workspace_id":"wsp_test1","goal":"synthetic task",'
       b'"network_mode":"OFFLINE"}')
inbox.submit(context, "event-process-crash", raw,
    int(time.monotonic()*1000)+5000).result(timeout=5)
os._exit(77)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(path), point],
        cwd=ROOT,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 77, result.stderr.decode()
    with Writer(path) as recovered:
        before = recovered.read(lambda db: db.execute("SELECT count(*) FROM tasks").fetchone()[0])
        assert before == (point == "after_commit_before_ack")
        retried = Inbox(recovered, SchemaRegistry.from_directory(ROOT / "contracts"))
        first = retried.submit(context, "event-process-crash", payload(), deadline()).result(
            timeout=5
        )
        second = retried.submit(context, "event-process-crash", payload(), deadline()).result(
            timeout=5
        )
        assert first == second
        for table in ["tasks", "inbox", "events", "outbox", "budgets"]:
            count = recovered.read(
                lambda db, name=table: db.execute("SELECT count(*) FROM " + name).fetchone()[0]
            )
            assert count == 1


def _seed_artifact(
    path,
    object_id: str,
    task_id: str,
    owner_id: str = "pri_test1",
    state: str = "AVAILABLE",
    sha256: str = "b" * 64,
) -> None:
    db = connect(path)
    try:
        db.execute(
            "INSERT INTO artifacts("
            "object_id,object_key,sha256,mime,bytes,classification,state,created_at) "
            "VALUES(?,?,?,'text/plain',32,'WORKSPACE',?,1000)",
            (object_id, f"key-{object_id}", sha256, state),
        )
        db.execute(
            "INSERT INTO artifact_refs("
            "ref_id,object_id,owner_id,scope_kind,task_id,purpose,created_at) "
            "VALUES(?,?,?,'TASK',?,'deliverable',1000)",
            (f"ref_{object_id}", object_id, owner_id, task_id),
        )
    finally:
        db.close()


def _seed_operation(
    path,
    operation_id: str,
    task_id: str,
    ordinal: int,
    state: str,
    unknown_reason: str | None = None,
    resolution_evidence_ref: str | None = None,
) -> None:
    db = connect(path)
    try:
        if not db.execute("SELECT 1 FROM tool_registry WHERE tool_id='fs.read'").fetchone():
            db.execute(
                "INSERT INTO tool_registry VALUES("
                "'fs.read','1.0.0',?,NULL,'builtin','{\"name\":\"fs.read\"}','ACTIVE',1000)",
                ("c" * 64,),
            )
        completed_at = (
            1500
            if state in {"SUCCEEDED", "FAILED", "REJECTED", "EXPIRED", "REVOKED", "CANCELLED"}
            else None
        )
        db.execute(
            "INSERT INTO operations(operation_id,task_id,ordinal,requested_by,workspace_id,"
            "workspace_generation,tool_id,tool_version,tool_manifest_digest,canonical_args_json,"
            "resource_snapshot_json,destination_json,data_class,authorization_kind,policy_version,"
            "identity_epoch,authorization_expires_at,binding_hash,retry_class,state,unknown_reason,"
            "resolution_evidence_ref,created_at,updated_at,completed_at,proposal_canonical_json) "
            "VALUES(?,?,?,'pri_test1','wsp_test1',1,'fs.read','1.0.0',?,'{}','{}','{}',"
            "'WORKSPACE','POLICY_ALLOW',1,1,9000,?,'SAFE_READ',?,?,?,1000,1500,?,'{}')",
            (
                operation_id,
                task_id,
                ordinal,
                "c" * 64,
                f"{ordinal:064x}",
                state,
                unknown_reason,
                resolution_evidence_ref,
                completed_at,
            ),
        )
    finally:
        db.close()


def test_all_task_transition_matrix_edges_and_cross_surface_dedupe(system):
    path, context, writer, inbox = system
    service = TaskStateService(writer)
    states = list(TRANSITIONS)
    assert len(states) == 11

    for src in states:
        for dst in states:
            task = json.loads(
                inbox.submit(context, f"evt-{src}-{dst}", payload(), deadline()).result(timeout=5)
            )["task_id"]
            db = connect(path)
            try:
                finished = 1200 if src in {"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"} else None
                db.execute(
                    "UPDATE tasks SET state=?,version=version+1,updated_at=1200,finished_at=? "
                    "WHERE task_id=?",
                    (src, finished, task),
                )
            finally:
                db.close()

            if dst not in TRANSITIONS[src]:
                with pytest.raises(RequestConflict):
                    writer.submit(
                        service.command(
                            context, task, 1, dst, f"req-illegal-{src}-{dst}", deadline()
                        )
                    ).result(timeout=5)
                assert service.snapshot(context, task)["state"] == src
            elif dst in {"SUCCEEDED", "PARTIAL", "CANCELLED"} or (
                src == "RECONCILING" and dst == "QUEUED"
            ):
                with pytest.raises(PermissionError):
                    writer.submit(
                        service.command(
                            context, task, 1, dst, f"req-guarded-{src}-{dst}", deadline()
                        )
                    ).result(timeout=5)
                assert service.snapshot(context, task)["state"] == src
            else:
                res = json.loads(
                    writer.submit(
                        service.command(context, task, 1, dst, f"req-ok-{src}-{dst}", deadline())
                    ).result(timeout=5)
                )
                assert res["state"] == dst and res["version"] == 2

    # Same request_id from another client surface must conflict rather than replay
    t_surface = json.loads(
        inbox.submit(context, "evt-surface-scope", payload(), deadline()).result(timeout=5)
    )["task_id"]
    writer.submit(
        service.command(context, t_surface, 0, "RUNNING", "req-surface-shared", deadline())
    ).result(timeout=5)
    with pytest.raises(RequestConflict):
        writer.submit(
            service.command(
                replace(context, app_id="app2"),
                t_surface,
                0,
                "RUNNING",
                "req-surface-shared",
                deadline(),
            )
        ).result(timeout=5)


def test_outcome_verifier_enforces_artifacts_kind_checks_and_unresolved_guards(system):
    path, context, writer, inbox = system
    service = TaskStateService(writer)

    # 1. Diagnosis task: model final text without source_refs or with staging artifact is rejected
    t_diag = json.loads(
        inbox.submit(context, "evt-diag", payload("diagnose issue"), deadline()).result(timeout=5)
    )["task_id"]
    writer.submit(service.command(context, t_diag, 0, "RUNNING", "run-diag", deadline())).result(
        timeout=5
    )
    with pytest.raises(PermissionError):
        writer.submit(
            service.complete(
                context,
                t_diag,
                1,
                OutcomeSubmission(
                    task_kind="DIAGNOSIS",
                    target="SUCCEEDED",
                    summary="model says done",
                    source_refs=(),
                ),
                "complete-diag-empty",
                deadline(),
            )
        ).result(timeout=5)

    _seed_artifact(path, "art_staging1", t_diag, state="STAGING")
    with pytest.raises(PermissionError):
        writer.submit(
            service.complete(
                context,
                t_diag,
                1,
                OutcomeSubmission(
                    task_kind="DIAGNOSIS",
                    target="SUCCEEDED",
                    summary="with staging artifact",
                    source_refs=("docs/03_runtime_recovery.md#L80",),
                    artifact_ids=("art_staging1",),
                ),
                "complete-diag-staging",
                deadline(),
            )
        ).result(timeout=5)

    _seed_artifact(path, "art_avail1", t_diag, state="AVAILABLE")
    done_diag = json.loads(
        writer.submit(
            service.complete(
                context,
                t_diag,
                1,
                OutcomeSubmission(
                    task_kind="DIAGNOSIS",
                    target="SUCCEEDED",
                    summary="verified diagnosis",
                    source_refs=("docs/03_runtime_recovery.md#L80",),
                    artifact_ids=("art_avail1",),
                ),
                "complete-diag-ok",
                deadline(),
            )
        ).result(timeout=5)
    )
    assert done_diag["state"] == "SUCCEEDED" and done_diag["version"] == 2
    assert service.replay(context, t_diag)[-1]["event_type"] == "TASK_FINISHED"

    # 2. Patch & Test task checks + unresolved operation/budget guards + PARTIAL outcome
    t_patch = json.loads(
        inbox.submit(context, "evt-patch", payload("patch and test"), deadline()).result(timeout=5)
    )["task_id"]
    writer.submit(service.command(context, t_patch, 0, "RUNNING", "run-patch", deadline())).result(
        timeout=5
    )
    _seed_artifact(path, "art_diff1", t_patch, state="AVAILABLE")

    # Non-zero exit code cannot mark TEST task SUCCEEDED
    with pytest.raises(PermissionError):
        writer.submit(
            service.complete(
                context,
                t_patch,
                1,
                OutcomeSubmission(
                    task_kind="TEST",
                    target="SUCCEEDED",
                    summary="test failed",
                    artifact_ids=("art_diff1",),
                    test_command="pytest -q",
                    snapshot_ref="snap_1",
                    exit_code=1,
                    log_summary="1 failed",
                ),
                "complete-test-nonzero",
                deadline(),
            )
        ).result(timeout=5)

    # Unresolved budget reservation blocks SUCCEEDED and PARTIAL
    db = connect(path)
    budget_id = db.execute("SELECT budget_id FROM tasks WHERE task_id=?", (t_patch,)).fetchone()[0]
    db.execute(
        "INSERT INTO budget_reservations(reservation_id,budget_id,call_ref,kind,status,"
        "reserved_amount_micros,reserved_tokens,created_at) "
        "VALUES('res_1',?,'call_1','MODEL','RESERVED',100,50,1000)",
        (budget_id,),
    )
    db.close()
    with pytest.raises(PermissionError):
        writer.submit(
            service.complete(
                context,
                t_patch,
                1,
                OutcomeSubmission(
                    task_kind="PATCH",
                    target="SUCCEEDED",
                    summary="patch ready",
                    artifact_ids=("art_diff1",),
                    original_hashes={"services/core/src/openbot/cli.py": "d" * 64},
                ),
                "complete-patch-reserved-budget",
                deadline(),
            )
        ).result(timeout=5)

    # Release budget reservation, then test PARTIAL completion with explicit missing_requirements
    db = connect(path)
    db.execute("UPDATE budget_reservations SET status='RELEASED' WHERE reservation_id='res_1'")
    db.close()
    partial = json.loads(
        writer.submit(
            service.complete(
                context,
                t_patch,
                1,
                OutcomeSubmission(
                    task_kind="PATCH",
                    target="PARTIAL",
                    summary="patch generated, integration pending",
                    artifact_ids=("art_diff1",),
                    original_hashes={"services/core/src/openbot/cli.py": "d" * 64},
                    completed_actions=("diff_generated",),
                    missing_requirements=("windows_smoke_test",),
                ),
                "complete-patch-partial",
                deadline(),
            )
        ).result(timeout=5)
    )
    assert partial["state"] == "PARTIAL" and partial["version"] == 2
    snap = service.snapshot(context, t_patch)
    assert snap["outcome"]["missing_requirements"] == ["windows_smoke_test"]


def test_cancel_holds_in_reconciling_while_unknown_exists_and_recovery_resumes_queued(system):
    path, context, writer, inbox = system
    service = TaskStateService(writer)

    # Task 1: RUNNING with an UNKNOWN operation -> cancel must hold in RECONCILING, not CANCELLED
    t_rec = json.loads(
        inbox.submit(context, "evt-cancel-unknown", payload(), deadline()).result(timeout=5)
    )["task_id"]
    writer.submit(service.command(context, t_rec, 0, "RUNNING", "run-rec", deadline())).result(
        timeout=5
    )
    _seed_operation(path, "op_unknown_1", t_rec, 1, "UNKNOWN", unknown_reason="timeout_after_send")
    _seed_operation(path, "op_ready_2", t_rec, 2, "READY")

    held = json.loads(
        writer.submit(service.cancel(context, t_rec, 1, "cancel-with-unknown", deadline())).result(
            timeout=5
        )
    )
    assert held["state"] == "RECONCILING"
    assert held["cancel_revision"] == 1
    db = connect(path, readonly=True)
    try:
        # Non-dispatched READY operation was cancelled immediately, UNKNOWN stays UNKNOWN
        assert (
            db.execute("SELECT state FROM operations WHERE operation_id='op_ready_2'").fetchone()[0]
            == "CANCELLED"
        )
        assert (
            db.execute("SELECT state FROM operations WHERE operation_id='op_unknown_1'").fetchone()[
                0
            ]
            == "UNKNOWN"
        )
    finally:
        db.close()

    # While cancel_revision > 0 or UNKNOWN remains, resume_reconciled to QUEUED is forbidden
    with pytest.raises(PermissionError):
        writer.submit(
            service.resume_reconciled(context, t_rec, held["version"], "resume-blocked", deadline())
        ).result(timeout=5)

    # Resolve UNKNOWN operation with evidence, then cancel completes RECONCILING -> CANCELLED
    db = connect(path)
    db.execute(
        "UPDATE operations SET state='FAILED',version=version+1,resolution_evidence_ref='ev_1',"
        "completed_at=2000,updated_at=2000 WHERE operation_id='op_unknown_1'"
    )
    db.close()
    cancelled = json.loads(
        writer.submit(
            service.cancel(context, t_rec, held["version"], "cancel-after-reconcile", deadline())
        ).result(timeout=5)
    )
    assert cancelled["state"] == "CANCELLED"

    # Task 2: RECONCILING without cancel -> resume_reconciled transitions to QUEUED after resolution
    t_res = json.loads(
        inbox.submit(context, "evt-resume-reconciled", payload(), deadline()).result(timeout=5)
    )["task_id"]
    writer.submit(service.command(context, t_res, 0, "RUNNING", "run-res", deadline())).result(
        timeout=5
    )
    _seed_operation(path, "op_unknown_2", t_res, 1, "UNKNOWN", unknown_reason="stream_dropped")
    writer.submit(
        service.command(context, t_res, 1, "RECONCILING", "enter-reconciling", deadline())
    ).result(timeout=5)
    with pytest.raises(PermissionError):
        writer.submit(
            service.resume_reconciled(context, t_res, 2, "resume-premature", deadline())
        ).result(timeout=5)

    db = connect(path)
    db.execute(
        "UPDATE operations SET state='SUCCEEDED',version=version+1,resolution_evidence_ref='ev_2',"
        "completed_at=2100,updated_at=2100 WHERE operation_id='op_unknown_2'"
    )
    db.close()
    resumed = json.loads(
        writer.submit(
            service.resume_reconciled(context, t_res, 2, "resume-verified", deadline())
        ).result(timeout=5)
    )
    assert resumed["state"] == "QUEUED" and resumed["version"] == 3


@pytest.mark.parametrize("point", ["before_commit", "after_commit_before_ack"])
def test_state_completion_crash_boundary_is_atomic_and_idempotent(system, point):
    path, context, writer, inbox = system
    task_id = json.loads(
        inbox.submit(context, f"evt-state-crash-{point}", payload(), deadline()).result(timeout=5)
    )["task_id"]
    service = TaskStateService(writer)
    writer.submit(
        service.command(context, task_id, 0, "RUNNING", f"run-{point}", deadline())
    ).result(timeout=5)
    _seed_artifact(path, f"art_{point}", task_id, state="AVAILABLE")
    writer.close()

    code = r"""
import os, sys, time
from pathlib import Path
from openbot.application.state_machine import OutcomeSubmission, TaskStateService
from openbot.storage.inbox import InboundContext
from openbot.storage.writer import Writer
import openbot.application.state_machine as module
context = InboundContext(
    "pro_test1", "pri_test1", 1, "fake", "tenant1", "app1", "ses_test1", "wsp_test1")
if sys.argv[3] == "before_commit":
    original = module.emit_state
    def crash(*args, **kwargs):
        original(*args, **kwargs)
        os._exit(78)
    module.emit_state = crash
writer = Writer(Path(sys.argv[1]))
service = TaskStateService(writer)
sub = OutcomeSubmission(
    task_kind="DIAGNOSIS",
    target="SUCCEEDED",
    summary="verified diagnosis",
    source_refs=("docs/03_runtime_recovery.md#L80",),
    artifact_ids=(f"art_{sys.argv[3]}",),
)
dl = int(time.monotonic() * 1000) + 5000
writer.submit(
    service.complete(context, sys.argv[2], 1, sub, "req-crash-complete", dl)
).result(timeout=5)
os._exit(78)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(path), task_id, point],
        cwd=ROOT,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 78, result.stderr.decode()

    with Writer(path) as recovered:
        rec_service = TaskStateService(recovered)
        snap_before = rec_service.snapshot(context, task_id)
        if point == "before_commit":
            assert snap_before["state"] == "RUNNING" and snap_before["version"] == 1
        else:
            assert snap_before["state"] == "SUCCEEDED" and snap_before["version"] == 2

        sub = OutcomeSubmission(
            task_kind="DIAGNOSIS",
            target="SUCCEEDED",
            summary="verified diagnosis",
            source_refs=("docs/03_runtime_recovery.md#L80",),
            artifact_ids=(f"art_{point}",),
        )
        first = recovered.submit(
            rec_service.complete(context, task_id, 1, sub, "req-crash-complete", deadline())
        ).result(timeout=5)
        second = recovered.submit(
            rec_service.complete(context, task_id, 1, sub, "req-crash-complete", deadline())
        ).result(timeout=5)
        assert first == second
        events = rec_service.replay(context, task_id)
        assert [e["event_type"] for e in events] == [
            "TASK_QUEUED",
            "TASK_STATE_CHANGED",
            "TASK_FINISHED",
        ]
        assert [e["version"] for e in events] == [0, 1, 2]
