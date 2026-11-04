import json
import time

import pytest
from openbot.application.dispatch import DispatchService
from openbot.application.operations import OperationService
from openbot.application.resources import ResourceRequest
from openbot.application.state_machine import TaskStateService
from openbot.artifacts.store import ArtifactLimits, ArtifactStore
from openbot.contracts import SchemaRegistry
from openbot.policy.approvals import ApprovalService
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.maintenance import DatabaseMaintenanceService
from openbot.storage.migrate import connect, load_migrations, migrate
from openbot.storage.writer import Writer

from tests.integration.storage.test_migrations import ROOT
from tests.integration.storage.test_recovery import MemoryChallenges, _register_tools


def _deadline() -> int:
    return int(time.monotonic() * 1000) + 5000


@pytest.fixture
def maint_env(tmp_path):
    path = tmp_path / "maint.sqlite"
    blob_root = tmp_path / "maint_blobs"
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
            "INSERT INTO channel_accounts("
            "account_id,channel,tenant_id,app_id,secret_ref,status,created_at) "
            "VALUES('acc_feishu_1','feishu','tenant1','app1','keychain:feishu_app_secret',"
            "'ACTIVE',1000)"
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
    art_store = ArtifactStore(writer, blob_root, limits=ArtifactLimits(default_ttl_ms=0))
    maint = DatabaseMaintenanceService(path, writer, art_store, blob_root)
    try:
        yield (
            tmp_path,
            path,
            blob_root,
            context,
            writer,
            inbox,
            tasks,
            ops,
            approvals,
            dispatcher,
            art_store,
            maint,
            challenges,
        )
    finally:
        writer.close()


def test_online_backup_interleaved_with_gc_and_restore_quarantines_unknown_and_revokes_grants(
    maint_env,
):
    (
        tmp_path,
        _,
        _,
        context,
        writer,
        inbox,
        tasks,
        ops,
        approvals,
        dispatcher,
        art_store,
        maint,
        challenges,
    ) = maint_env
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": "backup-restore", "network_mode": "OFFLINE"}
    )
    task_id = json.loads(inbox.submit(context, "evt-mnt-1", payload, _deadline()).result(5))[
        "task_id"
    ]
    writer.submit(tasks.command(context, task_id, 0, "RUNNING", "run-mnt-1", _deadline())).result(5)

    # Create an expired SESSION artifact (ttl_ms=0) that would be GC'd if not pinned during backup
    art = art_store.put(
        context,
        data=b"critical snapshot data",
        mime="text/plain",
        classification="WORKSPACE",
        scope_kind="SESSION",
        session_id="ses_test1",
        purpose="backup_test",
        ttl_ms=0,
        request_id="mnt-art-1",
        deadline_monotonic_ms=_deadline(),
    )

    # Operation 1: DISPATCHING (in-flight when backup is taken)
    prop1 = json.loads(
        ops.propose(
            context,
            task_id,
            "gui.click",
            '{"arg":"click1"}',
            {"workspace_generation": 1, "files": []},
            "WORKSPACE",
            {"kind": "LOCAL", "resource_ref": context.workspace_id},
            "prop-mnt-1",
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
        "apr-mnt-1",
        _deadline(),
    )
    writer.submit(tasks.command(context, task_id, 3, "RUNNING", "run2-mnt-1", _deadline())).result(
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
                "claim-mnt-1",
                _deadline(),
            )
        ).result(5)
    )
    writer.submit(
        dispatcher.begin_dispatch(
            context, op1, claimed1["attempt_id"], "ep_1", "exec_1", "disp-mnt-1", _deadline()
        )
    ).result(5)

    # Operation 2: APPROVED (READY, unconsumed when backup is taken)
    prop2 = json.loads(
        ops.propose(
            context,
            task_id,
            "fs.read",
            '{"arg":"read2"}',
            {"workspace_generation": 1, "files": []},
            "WORKSPACE",
            {"kind": "LOCAL", "resource_ref": context.workspace_id},
            "prop-mnt-2",
            _deadline(),
        )
    )
    op2, apr2 = prop2["operation_id"], prop2["approval_id"]
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
        "apr-mnt-2",
        _deadline(),
    )

    # Run online backup with concurrent GC interleaved while backup pin is active
    backup_dir = tmp_path / "backup_bundle"
    gc_ran_during_backup = False

    def interleaved_gc() -> None:
        nonlocal gc_ran_during_backup
        res = art_store.collect_garbage(
            context, request_id="gc-during-backup", deadline_monotonic_ms=_deadline()
        )
        # Must NOT tombstone 'art' while backup pin is held!
        assert art.object_id not in res["tombstoned_object_ids"]
        gc_ran_during_backup = True

    manifest = maint.create_backup(context, backup_dir, on_pinned_hook=interleaved_gc)
    assert gc_ran_during_backup is True
    assert manifest.status == "VERIFIED"
    assert manifest.contains_secret_values is False
    assert "keychain:feishu_app_secret" in manifest.secret_refs
    assert any(a["object_id"] == art.object_id for a in manifest.artifacts)

    # Restore into a fresh target directory with missing keychain secret_ref
    restored_db = tmp_path / "restored.sqlite"
    restored_blobs = tmp_path / "restored_blobs"
    report = maint.restore_backup(
        backup_dir,
        restored_db,
        restored_blobs,
        available_secret_refs=frozenset(),
    )
    assert report.reconfiguration_required is True
    assert "keychain:feishu_app_secret" in report.missing_secret_refs
    assert op1 in report.unknown_operations
    assert apr2 in report.revoked_approvals

    # Verify restored DB state:CONSUMED stays CONSUMED, APPROVED is REVOKED, DISPATCHING is UNKNOWN,
    # Task is in RECONCILING, and channel_accounts with missing secret_ref is DISABLED
    rdb = connect(restored_db, readonly=True)
    try:
        assert (
            rdb.execute("SELECT status FROM approvals WHERE approval_id=?", (apr1,)).fetchone()[0]
            == "CONSUMED"
        )
        assert (
            rdb.execute("SELECT status FROM approvals WHERE approval_id=?", (apr2,)).fetchone()[0]
            == "REVOKED"
        )
        assert (
            rdb.execute("SELECT state FROM operations WHERE operation_id=?", (op1,)).fetchone()[0]
            == "UNKNOWN"
        )
        assert (
            rdb.execute("SELECT state FROM operations WHERE operation_id=?", (op2,)).fetchone()[0]
            == "REVOKED"
        )
        assert (
            rdb.execute("SELECT state FROM tasks WHERE task_id=?", (task_id,)).fetchone()[0]
            == "RECONCILING"
        )
        assert (
            rdb.execute(
                "SELECT status FROM channel_accounts WHERE account_id='acc_feishu_1'"
            ).fetchone()[0]
            == "DISABLED"
        )
    finally:
        rdb.close()
