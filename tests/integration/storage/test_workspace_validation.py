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
from openbot.tools.workspace.validation import (
    IsolatedParserWorker,
    PinnedGrammarAsset,
    PinnedGrammarRegistry,
    WorkspaceValidationCoordinator,
)

from tests.integration.storage.test_migrations import ROOT


def _deadline() -> int:
    return int(time.monotonic() * 1000) + 5000


def test_pinned_grammar_rejects_workspace_binary_missing_asset_and_isolates_parser_crash(tmp_path):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    py_grammar = asset_dir / "python_grammar.bin"
    py_grammar.write_bytes(b"pinned-python-grammar-v1")
    py_sha = hashlib.sha256(py_grammar.read_bytes()).hexdigest()

    # 1. Reject grammar asset located inside the untrusted workspace
    ws_grammar = ws_root / "evil_grammar.so"
    ws_grammar.write_bytes(b"evil")
    with pytest.raises(PermissionError, match="workspace"):
        PinnedGrammarRegistry(
            workspace_root=ws_root,
            assets={
                ".py": PinnedGrammarAsset("python", ws_grammar, hashlib.sha256(b"evil").hexdigest())
            },
        )

    # 2. Unsupported language or missing offline grammar fails closed without network download
    reg = PinnedGrammarRegistry(
        workspace_root=ws_root,
        assets={".py": PinnedGrammarAsset("python", py_grammar, py_sha)},
    )
    with pytest.raises(ValueError, match="CAPABILITY_UNAVAILABLE"):
        reg.require_for_path("main.rs")

    # 3. Isolated subprocess parser worker handles deep nesting, oversized input, and crash
    worker = IsolatedParserWorker(reg, max_input_bytes=256, max_nesting_depth=8, timeout_ms=2000)
    ok_res = worker.parse("ok.py", b"def add(a, b):\n    return a + b\n")
    assert ok_res.valid is True
    assert ok_res.functional_correctness_proven is False

    deep_code = b"(" * 20 + b"1" + b")" * 20
    deep_res = worker.parse("deep.py", deep_code)
    assert deep_res.valid is False
    assert deep_res.error_code == "MAX_NESTING_DEPTH_EXCEEDED"

    crash_res = worker.parse("crash.py", b"x = 1", simulate_native_crash=True)
    assert crash_res.valid is False
    assert crash_res.error_code == "PARSER_WORKER_CRASHED"


def test_multi_file_validation_failure_reverts_only_operation_edits_and_preserves_user_files(
    tmp_path,
):
    path = tmp_path / "val.sqlite"
    blob_root = tmp_path / "blobs"
    ws_root = tmp_path / "workspace"
    journal_root = tmp_path / "journals"
    asset_dir = tmp_path / "assets"
    ws_root.mkdir()
    asset_dir.mkdir()
    py_grammar = asset_dir / "python_grammar.bin"
    py_grammar.write_bytes(b"pinned-python-grammar-v1")
    py_sha = hashlib.sha256(py_grammar.read_bytes()).hexdigest()

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
    try:
        inbox = Inbox(writer, registry)
        tasks = TaskStateService(writer)
        art_store = ArtifactStore(writer, blob_root)
        patch_tool = WorkspacePatchTool(ws_root, art_store, journal_root)
        grammars = PinnedGrammarRegistry(
            workspace_root=ws_root,
            assets={".py": PinnedGrammarAsset("python", py_grammar, py_sha)},
        )
        parser_worker = IsolatedParserWorker(grammars)
        coordinator = WorkspaceValidationCoordinator(patch_tool, parser_worker)

        payload = json.dumps(
            {"workspace_id": "wsp_test1", "goal": "val-tx", "network_mode": "OFFLINE"}
        )
        task_id = json.loads(inbox.submit(context, "evt-val-1", payload, _deadline()).result(5))[
            "task_id"
        ]
        writer.submit(
            tasks.command(context, task_id, 0, "RUNNING", "run-val-1", _deadline())
        ).result(5)

        # Unrelated user dirty file that must NEVER be wiped when validation rolls back!
        (ws_root / "user_uncommitted.py").write_bytes(b"user_work = 42\n")
        (ws_root / "mod_a.py").write_bytes(b"a = 1\n")
        (ws_root / "mod_b.py").write_bytes(b"b = 2\n")

        # Second file introduces a syntax error -> transaction reverts mod_a.py and mod_b.py
        # while keeping user_uncommitted.py completely untouched!
        bundle = patch_tool.propose_patch(
            context,
            task_id=task_id,
            edits=(
                FileEditSpec("mod_a.py", old_snippet="a = 1", new_snippet="a = 10"),
                FileEditSpec("mod_b.py", old_snippet="b = 2", new_snippet="def broken(:"),
            ),
            request_id="val-prop-1",
            deadline_monotonic_ms=_deadline(),
        )
        outcome = coordinator.apply_and_validate(context, bundle)
        assert outcome.status == "REVERTED_ON_SYNTAX_ERROR"
        assert outcome.functional_correctness_proven is False
        assert (ws_root / "mod_a.py").read_bytes() == b"a = 1\n"
        assert (ws_root / "mod_b.py").read_bytes() == b"b = 2\n"
        assert (ws_root / "user_uncommitted.py").read_bytes() == b"user_work = 42\n"
    finally:
        writer.close()
