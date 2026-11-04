import hashlib
import json
import time

import pytest
from openbot.application.dispatch import DispatchService
from openbot.application.operations import OperationService
from openbot.application.recovery import RecoveryService
from openbot.application.state_machine import TaskStateService
from openbot.artifacts.store import ArtifactStore
from openbot.contracts import SchemaRegistry, canonicalize
from openbot.policy.approvals import ApprovalService
from openbot.policy.egress import EgressGuard
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.migrate import connect, load_migrations, migrate
from openbot.storage.writer import Writer
from openbot.tools.messages.draft import ContactCandidate, MessageDraftService
from openbot.tools.messages.send import (
    MessageSendEnvelope,
    MessageSendResult,
    MessageSendService,
)

from tests.integration.storage.test_migrations import ROOT
from tests.integration.storage.test_recovery import MemoryChallenges


def _deadline() -> int:
    return int(time.monotonic() * 1000) + 5000


class FakeMessageTransport:
    def __init__(self, *, qualified: bool = True, drop_after_send: bool = False) -> None:
        self.qualified = qualified
        self.drop_after_send = drop_after_send
        self.sent_envelopes: list[MessageSendEnvelope] = []

    def send_message(self, envelope: MessageSendEnvelope) -> MessageSendResult:
        self.sent_envelopes.append(envelope)
        if self.drop_after_send:
            raise ConnectionError("remote sent message then dropped connection before receipt")
        return MessageSendResult(
            status="SENT",
            provider_message_id=f"im_msg_{len(self.sent_envelopes)}",
        )


@pytest.fixture
def send_env(tmp_path):
    path = tmp_path / "send.sqlite"
    blob_root = tmp_path / "send_blobs"
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
            "VALUES(1,'pro_test1',1,1,1,'CONNECTED','ep_1',0,1000,1000)"
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
        manifest = {
            "name": "message.send",
            "version": "1.0.0",
            "effect": "EXTERNAL_WRITE",
            "retry_class": "RECONCILE_ONLY",
            "input_schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "draft_artifact_id": {"type": "string"},
                    "draft_sha256": {"type": "string"},
                    "account_id": {"type": "string"},
                    "recipient_id": {"type": "string"},
                },
                "required": ["draft_artifact_id", "draft_sha256", "account_id", "recipient_id"],
                "additionalProperties": False,
            },
        }
        raw = canonicalize(manifest)
        db.execute(
            "INSERT INTO tool_registry VALUES("
            "'message.send','1.0.0',?,NULL,'builtin',?,'ACTIVE',1000)",
            (hashlib.sha256(raw).hexdigest(), raw.decode()),
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
    dispatcher = DispatchService(writer, registry)
    recovery = RecoveryService(writer, registry)
    art_store = ArtifactStore(writer, blob_root)
    drafts = MessageDraftService(writer, tasks, art_store)
    egress = EgressGuard(
        profile_network_mode="CONNECTED",
        profile_allowed_domains=frozenset({"open.feishu.cn"}),
        workspace_allowed_domains=frozenset({"open.feishu.cn"}),
    )
    send_svc = MessageSendService(writer, ops, dispatcher, drafts, art_store, egress)
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
            drafts,
            send_svc,
            challenges,
        )
    finally:
        writer.close()


def test_message_send_rejects_wrong_recipient_unqualified_adapter_and_disconnect_unknown(
    send_env,
):
    (
        _,
        context,
        writer,
        inbox,
        tasks,
        _,
        approvals,
        _,
        recovery,
        drafts,
        send_svc,
        challenges,
    ) = send_env
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": "send-msg", "network_mode": "CONNECTED"}
    )
    task_id = json.loads(inbox.submit(context, "evt-snd-1", payload, _deadline()).result(5))[
        "task_id"
    ]
    writer.submit(tasks.command(context, task_id, 0, "RUNNING", "run-snd-1", _deadline())).result(5)

    d1 = drafts.create_or_revise_draft(
        context,
        task_id=task_id,
        channel="feishu",
        account_id="acc_feishu_1",
        recipient_candidates=(ContactCandidate("ou_target_1", "Target 1"),),
        body_text="v1 body",
        request_id="snd-drf-1",
        deadline_monotonic_ms=_deadline(),
    )
    assert d1.draft_artifact_id is not None and d1.draft_sha256 is not None

    # Propose and approve message.send bound to d1
    proposed = send_svc.propose_send(
        context,
        task_id=task_id,
        draft_artifact_id=d1.draft_artifact_id,
        draft_sha256=d1.draft_sha256,
        account_id="acc_feishu_1",
        recipient_id="ou_target_1",
        request_id="snd-prop-1",
        deadline_monotonic_ms=_deadline(),
    )
    op_id, apr_id = proposed["operation_id"], proposed["approval_id"]
    approvals.decide(
        context,
        apr_id,
        json.dumps(
            {
                "expected_version": 1,
                "expected_binding_hash": proposed["binding_hash"],
                "decision": "APPROVE",
                "nonce": challenges.get(apr_id).decode(),
            }
        ),
        "snd-apr-1",
        _deadline(),
    )
    writer.submit(tasks.command(context, task_id, 3, "RUNNING", "run-snd-2", _deadline())).result(5)

    # 1. Owner progress grant or wrong recipient cannot authorize third-party send
    with pytest.raises(PermissionError, match="recipient_id|owner_progress"):
        send_svc.execute_approved_send(
            context,
            operation_id=op_id,
            runtime_epoch="ep_1",
            executor_id="exec_1",
            transport=FakeMessageTransport(qualified=True),
            caller_recipient_id="ou_wrong_recipient",
            is_owner_progress_only_grant=True,
            request_id="snd-exec-wrong",
            deadline_monotonic_ms=_deadline(),
        )

    # 2. Unqualified real adapter (before M2 qualification) fails with CAPABILITY_UNAVAILABLE
    with pytest.raises(PermissionError, match="CAPABILITY_UNAVAILABLE"):
        send_svc.execute_approved_send(
            context,
            operation_id=op_id,
            runtime_epoch="ep_1",
            executor_id="exec_1",
            transport=FakeMessageTransport(qualified=False),
            caller_recipient_id="ou_target_1",
            request_id="snd-exec-unqual",
            deadline_monotonic_ms=_deadline(),
        )

    # 3. Disconnect after remote send enters UNKNOWN/RECONCILING; RECONCILE_ONLY never resends
    dropping_transport = FakeMessageTransport(qualified=True, drop_after_send=True)
    out = send_svc.execute_approved_send(
        context,
        operation_id=op_id,
        runtime_epoch="ep_1",
        executor_id="exec_1",
        transport=dropping_transport,
        caller_recipient_id="ou_target_1",
        request_id="snd-exec-drop",
        deadline_monotonic_ms=_deadline(),
    )
    assert out["operation_state"] == "UNKNOWN"
    assert out["task_state"] == "RECONCILING"
    assert len(dropping_transport.sent_envelopes) == 1

    # Recovery on RECONCILE_ONLY message.send refuses to mint a retry ticket (never auto-resends!)
    writer.submit(
        recovery.recover_epoch(
            context,
            "ep_2",
            "boot_2",
            "sup_2",
            old_epoch_isolated=True,
            request_id="snd-rec-ep2",
            deadline_monotonic_ms=_deadline(),
        )
    ).result(5)
    rec_out, ticket = recovery.recover_operation(
        context,
        op_id,
        "ep_2",
        dispatch_was_sent=True,
        probe_status="UNKNOWN",
        request_id="snd-rec-op",
        deadline_monotonic_ms=_deadline(),
    )
    assert rec_out["operation_state"] == "UNKNOWN"
    assert ticket is None
    assert len(dropping_transport.sent_envelopes) == 1
