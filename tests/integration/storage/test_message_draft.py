import json
import time

import pytest
from openbot.application.state_machine import TaskStateService
from openbot.artifacts.store import ArtifactStore
from openbot.contracts import SchemaRegistry
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.migrate import connect, load_migrations, migrate
from openbot.storage.writer import Writer
from openbot.tools.messages.draft import ContactCandidate, MessageDraftService

from tests.integration.storage.test_migrations import ROOT


def _deadline() -> int:
    return int(time.monotonic() * 1000) + 5000


@pytest.fixture
def draft_env(tmp_path):
    path = tmp_path / "draft.sqlite"
    blob_root = tmp_path / "draft_blobs"
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
    drafts = MessageDraftService(writer, tasks, art_store)
    try:
        yield path, context, writer, inbox, tasks, art_store, drafts
    finally:
        writer.close()


def test_ambiguous_recipient_enters_waiting_input_and_revision_produces_new_immutable_hash(
    draft_env,
):
    _, context, writer, inbox, tasks, art_store, drafts = draft_env
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": "draft-msg", "network_mode": "OFFLINE"}
    )
    task_id = json.loads(inbox.submit(context, "evt-drf-1", payload, _deadline()).result(5))[
        "task_id"
    ]
    writer.submit(tasks.command(context, task_id, 0, "RUNNING", "run-drf-1", _deadline())).result(5)

    # 1. Ambiguous recipient name (2 contacts named 'Alex') moves Task to WAITING_INPUT
    # and refuses to produce a sendable draft artifact!
    ambiguous = drafts.create_or_revise_draft(
        context,
        task_id=task_id,
        channel="feishu",
        account_id="acc_feishu_1",
        recipient_candidates=(
            ContactCandidate("ou_alex_1", "Alex (Engineering)"),
            ContactCandidate("ou_alex_2", "Alex (Finance)"),
        ),
        body_text="Hello Alex",
        attachment_artifact_ids=(),
        request_id="drf-ambig-1",
        deadline_monotonic_ms=_deadline(),
    )
    assert ambiguous.status == "WAITING_INPUT"
    assert ambiguous.sendable is False
    assert ambiguous.draft_artifact_id is None
    assert tasks.snapshot(context, task_id)["state"] == "WAITING_INPUT"

    # Resume task WAITING_INPUT -> QUEUED -> RUNNING after user clarifies recipient
    cur_ver = int(tasks.snapshot(context, task_id)["version"])
    writer.submit(
        tasks.command(context, task_id, cur_ver, "QUEUED", "q-drf-2", _deadline())
    ).result(5)
    writer.submit(
        tasks.command(context, task_id, cur_ver + 1, "RUNNING", "run-drf-2", _deadline())
    ).result(5)

    # 2. Unambiguous stable recipient ID produces immutable draft artifact v1 with 0 network calls
    att = art_store.put(
        context,
        data=b"attachment content",
        mime="text/plain",
        classification="WORKSPACE",
        scope_kind="TASK",
        task_id=task_id,
        purpose="draft_attachment",
        request_id="drf-att-1",
        deadline_monotonic_ms=_deadline(),
    )
    d1 = drafts.create_or_revise_draft(
        context,
        task_id=task_id,
        channel="feishu",
        account_id="acc_feishu_1",
        recipient_candidates=(ContactCandidate("ou_alex_1", "Alex (Engineering)"),),
        body_text="Draft v1 body",
        attachment_artifact_ids=(att.object_id,),
        request_id="drf-v1",
        deadline_monotonic_ms=_deadline(),
    )
    assert d1.status == "DRAFT_READY"
    assert d1.sendable is True
    assert d1.revision == 1
    assert d1.recipient_id == "ou_alex_1"
    assert d1.draft_sha256 is not None

    # 3. Editing draft body produces revision 2 with a distinct draft_sha256; old hash is stale
    d2 = drafts.create_or_revise_draft(
        context,
        task_id=task_id,
        channel="feishu",
        account_id="acc_feishu_1",
        recipient_candidates=(ContactCandidate("ou_alex_1", "Alex (Engineering)"),),
        body_text="Draft v2 edited body",
        attachment_artifact_ids=(att.object_id,),
        prior_revision=d1.revision,
        request_id="drf-v2",
        deadline_monotonic_ms=_deadline(),
    )
    assert d2.revision == 2
    assert d2.draft_sha256 != d1.draft_sha256
    assert (
        drafts.verify_latest_draft_binding(context, d1.draft_artifact_id, d1.draft_sha256) is False
    )
    assert (
        drafts.verify_latest_draft_binding(context, d2.draft_artifact_id, d2.draft_sha256) is True
    )
