import hashlib
import json
import time

import pytest
from openbot.application.state_machine import TaskStateService
from openbot.artifacts.store import ArtifactStore
from openbot.contracts import SchemaRegistry
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.migrate import connect, load_migrations, migrate
from openbot.storage.writer import Writer
from openbot.tools.workspace.patch import FileEditSpec, WorkspacePatchTool

from tests.integration.storage.test_migrations import ROOT


def _deadline() -> int:
    return int(time.monotonic() * 1000) + 5000


@pytest.fixture
def patch_env(tmp_path):
    path = tmp_path / "patch.sqlite"
    blob_root = tmp_path / "patch_blobs"
    ws_root = tmp_path / "workspace"
    journal_root = tmp_path / "journals"
    ws_root.mkdir()
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
    finally:
        db.close()

    context = InboundContext(
        "pro_test1", "pri_test1", 1, "local", "tenant1", "app1", "ses_test1", "wsp_test1"
    )
    registry = SchemaRegistry.from_directory(ROOT / "contracts")
    writer = Writer(path)
    inbox = Inbox(writer, registry)
    tasks = TaskStateService(writer)
    art_store = ArtifactStore(writer, blob_root)
    patch_tool = WorkspacePatchTool(ws_root, art_store, journal_root)
    try:
        yield ws_root, blob_root, context, writer, inbox, tasks, art_store, patch_tool
    finally:
        writer.close()


def test_propose_patch_does_not_modify_workspace_and_rejects_duplicate_match_or_hash_drift(
    patch_env,
):
    ws_root, blob_root, context, writer, inbox, tasks, _, patch_tool = patch_env
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": "patch-verify", "network_mode": "OFFLINE"}
    )
    task_id = json.loads(inbox.submit(context, "evt-pat-1", payload, _deadline()).result(5))[
        "task_id"
    ]
    writer.submit(tasks.command(context, task_id, 0, "RUNNING", "run-pat-1", _deadline())).result(5)

    # 1. Duplicate match in target file is refused at proposal time (never guesses)
    (ws_root / "dup.py").write_bytes(b"x = 1\nx = 1\n")
    with pytest.raises(ValueError, match="AMBIGUOUS_MULTIPLE_MATCHES"):
        patch_tool.propose_patch(
            context,
            task_id=task_id,
            edits=(FileEditSpec("dup.py", old_snippet="x = 1", new_snippet="x = 2"),),
            request_id="pat-dup",
            deadline_monotonic_ms=_deadline(),
        )

    # 2. Propose valid patch freezes old/new sha256 and exact new bytes Artifact without writing
    orig_bytes = b"def greet():\n    return 'old'\n"
    (ws_root / "app.py").write_bytes(orig_bytes)
    bundle = patch_tool.propose_patch(
        context,
        task_id=task_id,
        edits=(FileEditSpec("app.py", old_snippet="return 'old'", new_snippet="return 'new'"),),
        request_id="pat-ok-1",
        deadline_monotonic_ms=_deadline(),
    )
    assert (ws_root / "app.py").read_bytes() == orig_bytes
    assert bundle.files[0].old_sha256 == hashlib.sha256(orig_bytes).hexdigest()
    assert "-    return 'old'" in bundle.files[0].diff_preview
    assert "+    return 'new'" in bundle.files[0].diff_preview

    # 3. If user changes line endings (LF -> CRLF) or edits file before apply, apply refuses
    (ws_root / "app.py").write_bytes(b"def greet():\r\n    return 'old'\r\n")
    with pytest.raises(PermissionError, match="old_sha256|changed"):
        patch_tool.apply_patch(context, bundle)

    # Restore original bytes, then tamper with approved new-content artifact on disk -> refused
    (ws_root / "app.py").write_bytes(orig_bytes)
    art_path = blob_root / bundle.files[0].new_artifact_key
    saved_art = art_path.read_bytes()
    art_path.write_bytes(b"tampered new content")
    with pytest.raises((PermissionError, FileNotFoundError)):
        patch_tool.apply_patch(context, bundle)
    assert (ws_root / "app.py").read_bytes() == orig_bytes

    # Restore artifact and re-propose -> apply succeeds and writes exact frozen bytes
    bundle2 = patch_tool.propose_patch(
        context,
        task_id=task_id,
        edits=(FileEditSpec("app.py", old_snippet="return 'old'", new_snippet="return 'new'"),),
        request_id="pat-ok-2",
        deadline_monotonic_ms=_deadline(),
    )
    del saved_art
    report = patch_tool.apply_patch(context, bundle2)
    assert report.status == "APPLIED"
    assert report.claims_cross_file_atomicity is False
    assert (ws_root / "app.py").read_bytes() == b"def greet():\n    return 'new'\n"


def test_multi_file_commit_journal_rolls_back_first_file_when_second_file_fails(patch_env):
    ws_root, _, context, writer, inbox, tasks, _, patch_tool = patch_env
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": "patch-journal", "network_mode": "OFFLINE"}
    )
    task_id = json.loads(inbox.submit(context, "evt-pat-2", payload, _deadline()).result(5))[
        "task_id"
    ]
    writer.submit(tasks.command(context, task_id, 0, "RUNNING", "run-pat-2", _deadline())).result(5)

    (ws_root / "first.txt").write_bytes(b"first_old\n")
    (ws_root / "second.txt").write_bytes(b"second_old\n")

    bundle = patch_tool.propose_patch(
        context,
        task_id=task_id,
        edits=(
            FileEditSpec("first.txt", old_snippet="first_old", new_snippet="first_new"),
            FileEditSpec("second.txt", old_snippet="second_old", new_snippet="second_new"),
        ),
        request_id="pat-multi-1",
        deadline_monotonic_ms=_deadline(),
    )

    # Inject failure right when committing second.txt after first.txt has already been written
    report = patch_tool.apply_patch(context, bundle, inject_failure_on_path="second.txt")
    assert report.status == "ROLLED_BACK_AFTER_PARTIAL_FAILURE"
    assert report.claims_cross_file_atomicity is False
    assert report.recovery_actions["first.txt"] == "RESTORED_ORIGINAL"
    assert report.recovery_actions["second.txt"] == "FAILED_NOT_APPLIED"
    # Both files on disk match their exact original pre-patch contents
    assert (ws_root / "first.txt").read_bytes() == b"first_old\n"
    assert (ws_root / "second.txt").read_bytes() == b"second_old\n"
