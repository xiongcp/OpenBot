import hashlib
import json
import time

import pytest
from openbot.application.operations import OperationService
from openbot.application.state_machine import TaskStateService
from openbot.artifacts.store import ArtifactLimits, ArtifactStore
from openbot.contracts import SchemaRegistry
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.migrate import connect, load_migrations, migrate
from openbot.storage.writer import Writer

from tests.integration.storage.test_migrations import ROOT
from tests.integration.storage.test_recovery import MemoryChallenges, _register_tools


def _deadline() -> int:
    return int(time.monotonic() * 1000) + 5000


@pytest.fixture
def artifact_env(tmp_path):
    path = tmp_path / "artifacts.sqlite"
    blob_root = tmp_path / "artifact_blobs"
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
    limits = ArtifactLimits(
        max_single_artifact_bytes=512,
        max_task_artifact_bytes=1024,
        max_preview_bytes=16,
        default_ttl_ms=60_000,
    )
    store = ArtifactStore(writer, blob_root, limits=limits)
    try:
        yield path, blob_root, context, writer, inbox, tasks, ops, store, challenges
    finally:
        writer.close()


def test_atomic_put_size_quotas_safe_download_headers_and_secret_preview_block(artifact_env):
    _, _, context, writer, inbox, tasks, _, store, _ = artifact_env
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": "artifact-store", "network_mode": "OFFLINE"}
    )
    task_id = json.loads(inbox.submit(context, "evt-art-1", payload, _deadline()).result(5))[
        "task_id"
    ]
    writer.submit(tasks.command(context, task_id, 0, "RUNNING", "run-art-1", _deadline())).result(5)

    # 1. Single artifact exceeding max_single_artifact_bytes (512) is rejected
    with pytest.raises(ValueError, match="max_single_artifact_bytes"):
        store.put(
            context,
            data=b"x" * 600,
            mime="text/plain",
            classification="WORKSPACE",
            scope_kind="TASK",
            task_id=task_id,
            purpose="oversized",
            request_id="art-oversize",
            deadline_monotonic_ms=_deadline(),
        )

    # 2. HTML/script payload keeps SENSITIVE classification (MIME never downgrades class)
    # and download forces attachment + sandbox CSP without exposing host path
    html_bytes = b"<script>alert('xss')</script>sensitive report body"
    rec = store.put(
        context,
        data=html_bytes,
        mime="text/html",
        classification="SENSITIVE",
        scope_kind="TASK",
        task_id=task_id,
        purpose="report",
        request_id="art-html-1",
        deadline_monotonic_ms=_deadline(),
    )
    assert rec.classification == "SENSITIVE"
    assert rec.sha256 == hashlib.sha256(html_bytes).hexdigest()

    dl = store.download(context, rec.object_id)
    assert dl.data == html_bytes
    assert dl.content_disposition == "attachment"
    assert "sandbox" in dl.content_security_policy
    assert dl.x_content_type_options == "nosniff"
    assert "host_path" not in dl.public_metadata()

    # Preview truncates to max_preview_bytes (16)
    prev = store.preview(context, rec.object_id)
    assert prev["preview_bytes"] == html_bytes[:16].decode("utf-8")
    assert prev["truncated"] is True

    # 3. SECRET artifact cannot be accessed via preview
    sec_rec = store.put(
        context,
        data=b"secret-material",
        mime="text/plain",
        classification="SECRET",
        scope_kind="TASK",
        task_id=task_id,
        purpose="redacted_diag",
        request_id="art-sec-1",
        deadline_monotonic_ms=_deadline(),
    )
    with pytest.raises(PermissionError, match="SECRET"):
        store.preview(context, sec_rec.object_id)


def test_orphan_cleanup_missing_blob_quarantine_and_gc_protection_for_pending_approval_and_backup(
    artifact_env,
):
    path, blob_root, context, writer, inbox, tasks, ops, store, _ = artifact_env
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": "artifact-gc", "network_mode": "OFFLINE"}
    )
    task_id = json.loads(inbox.submit(context, "evt-art-2", payload, _deadline()).result(5))[
        "task_id"
    ]
    writer.submit(tasks.command(context, task_id, 0, "RUNNING", "run-art-2", _deadline())).result(5)

    proposed = json.loads(
        ops.propose(
            context,
            task_id,
            "fs.patch",
            '{"arg":"patch1"}',
            {"workspace_generation": 1, "files": []},
            "WORKSPACE",
            {"kind": "LOCAL", "resource_ref": context.workspace_id},
            "prop-art-2",
            _deadline(),
        )
    )
    op_id = proposed["operation_id"]

    # 1. Artifact bound to AWAITING_APPROVAL operation is protected from GC even if TTL expired
    op_art = store.put(
        context,
        data=b"new file content for patch",
        mime="text/plain",
        classification="WORKSPACE",
        scope_kind="OPERATION",
        operation_id=op_id,
        purpose="patch_new_content",
        ttl_ms=0,
        request_id="art-op-bound",
        deadline_monotonic_ms=_deadline(),
    )
    assert store.verify_approved_digest(context, op_art.object_id, op_art.sha256) is True
    with pytest.raises(PermissionError, match="digest|sha256"):
        store.verify_approved_digest(context, op_art.object_id, "0" * 64)

    # 2. Simulate crash before DB registration by leaving an orphan file in staging/ and objects/
    orphan_staging = blob_root / "staging/.tmp_orphan"
    orphan_obj = blob_root / "objects/aa/art_unregistered.bin"
    orphan_obj.parent.mkdir(parents=True, exist_ok=True)
    orphan_staging.write_bytes(b"orphan1")
    orphan_obj.write_bytes(b"orphan2")

    # 3. Expired session artifact pinned by active backup is also protected until unpinned
    backup_art = store.put(
        context,
        data=b"backup snapshot ref",
        mime="text/plain",
        classification="WORKSPACE",
        scope_kind="SESSION",
        session_id="ses_test1",
        purpose="snapshot",
        ttl_ms=0,
        request_id="art-backup-pin",
        deadline_monotonic_ms=_deadline(),
    )
    pin_id = store.pin_for_backup([backup_art.object_id])

    gc_report = store.collect_garbage(
        context, request_id="art-gc-1", deadline_monotonic_ms=_deadline()
    )
    assert gc_report["orphan_files_removed"] == 2
    assert not orphan_staging.exists() and not orphan_obj.exists()
    # Neither op_art (pending approval) nor backup_art (pinned for backup) was tombstoned!
    assert op_art.object_id not in gc_report["tombstoned_object_ids"]
    assert backup_art.object_id not in gc_report["tombstoned_object_ids"]

    # Unpin backup -> now expired backup_art is eligible and tombstoned on next GC
    store.unpin_backup(pin_id)
    gc_report2 = store.collect_garbage(
        context, request_id="art-gc-2", deadline_monotonic_ms=_deadline()
    )
    assert backup_art.object_id in gc_report2["tombstoned_object_ids"]
    assert op_art.object_id not in gc_report2["tombstoned_object_ids"]

    # 4. If registered blob file is missing on disk, download marks artifact QUARANTINED in DB
    blob_file = blob_root / op_art.object_key
    blob_file.unlink()
    with pytest.raises(FileNotFoundError, match="QUARANTINED"):
        store.download(context, op_art.object_id)
    db = connect(path, readonly=True)
    try:
        st = db.execute(
            "SELECT state FROM artifacts WHERE object_id=?", (op_art.object_id,)
        ).fetchone()[0]
        assert st == "QUARANTINED"
    finally:
        db.close()
