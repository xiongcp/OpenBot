import hashlib
import json
import time

import pytest
from openbot.application.dispatch import DispatchService
from openbot.application.operations import OperationService
from openbot.application.recovery import RecoveryService
from openbot.application.resources import ResourceRequest
from openbot.application.state_machine import TaskStateService
from openbot.contracts import ContractError, SchemaRegistry, canonicalize
from openbot.policy.approvals import ApprovalService
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.migrate import connect, load_migrations, migrate
from openbot.storage.writer import Writer

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


def _register_tools(db) -> None:
    tools = [
        ("fs.read", "READ", "SAFE_READ"),
        ("fs.patch", "LOCAL_WRITE", "IDEMPOTENT_WRITE"),
        ("provider.send", "EXTERNAL_WRITE", "PROVIDER_IDEMPOTENT"),
        ("gui.click", "EXTERNAL_WRITE", "RECONCILE_ONLY"),
    ]
    for name, effect, retry_class in tools:
        manifest = {
            "name": name,
            "version": "1.0.0",
            "effect": effect,
            "retry_class": retry_class,
            "input_schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {"arg": {"type": "string"}},
                "required": ["arg"],
                "additionalProperties": False,
            },
        }
        raw = canonicalize(manifest)
        db.execute(
            "INSERT INTO tool_registry VALUES(?, '1.0.0', ?, NULL, 'builtin', ?, 'ACTIVE', 1000)",
            (name, hashlib.sha256(raw).hexdigest(), raw.decode()),
        )


@pytest.fixture
def recovery_env(tmp_path):
    path = tmp_path / "recovery.sqlite"
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
    try:
        yield path, context, writer, inbox, tasks, ops, approvals, dispatcher, recovery, challenges
    finally:
        writer.close()


def _prepare_operation(
    context,
    writer,
    inbox,
    tasks,
    ops,
    approvals,
    dispatcher,
    challenges,
    tool_name: str,
    tag: str,
    *,
    enter_dispatching: bool,
    epoch: str = "ep_1",
) -> tuple[str, str, str, str]:
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": f"goal-{tag}", "network_mode": "OFFLINE"}
    )
    task_id = json.loads(inbox.submit(context, f"evt-{tag}", payload, _deadline()).result(5))[
        "task_id"
    ]
    writer.submit(tasks.command(context, task_id, 0, "RUNNING", f"run-{tag}", _deadline())).result(
        5
    )
    proposed = json.loads(
        ops.propose(
            context,
            task_id,
            tool_name,
            '{"arg":"val"}',
            {"workspace_generation": 1, "files": []},
            "WORKSPACE",
            {"kind": "LOCAL", "resource_ref": context.workspace_id},
            f"prop-{tag}",
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
        f"apr-{tag}",
        _deadline(),
    )
    writer.submit(tasks.command(context, task_id, 3, "RUNNING", f"run2-{tag}", _deadline())).result(
        5
    )
    resources = [ResourceRequest("WORKSPACE", "wsp_test1", expected_generation=1)]
    claimed = json.loads(
        writer.submit(
            dispatcher.claim(
                context, op_id, epoch, "exec_1", resources, 30_000, f"claim-{tag}", _deadline()
            )
        ).result(5)
    )
    att_id = claimed["attempt_id"]
    if enter_dispatching:
        writer.submit(
            dispatcher.begin_dispatch(
                context, op_id, att_id, epoch, "exec_1", f"disp-{tag}", _deadline()
            )
        ).result(5)
    return task_id, op_id, apr_id, att_id


def test_unisolated_old_epoch_blocks_takeover_and_turns_dispatching_into_unknown(recovery_env):
    path, context, writer, inbox, tasks, ops, approvals, dispatcher, recovery, challenges = (
        recovery_env
    )
    task_id, op_id, _, att_id = _prepare_operation(
        context,
        writer,
        inbox,
        tasks,
        ops,
        approvals,
        dispatcher,
        challenges,
        "provider.send",
        "uniso",
        enter_dispatching=True,
    )

    # Old worker NOT isolated -> DISPATCHING becomes UNKNOWN, Task enters RECONCILING, no takeover
    res = json.loads(
        writer.submit(
            recovery.recover_epoch(
                context,
                "ep_2",
                "boot_2",
                "sup_2",
                old_epoch_isolated=False,
                request_id="rec-uniso",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    assert res["takeover_allowed"] is False
    assert op_id in res["unknown_operations"]
    assert tasks.snapshot(context, task_id)["state"] == "RECONCILING"


def test_claimed_undispatched_and_retry_classes_recover_with_ticket_or_quarantine(recovery_env):
    path, context, writer, inbox, tasks, ops, approvals, dispatcher, recovery, challenges = (
        recovery_env
    )
    # 1. CLAIMED (never dispatched) -> old epoch isolated -> returns to READY with RecoveryTicket
    t_claimed, op_claimed, apr_claimed, att_claimed = _prepare_operation(
        context,
        writer,
        inbox,
        tasks,
        ops,
        approvals,
        dispatcher,
        challenges,
        "gui.click",
        "claimed-only",
        enter_dispatching=False,
    )
    writer.submit(
        recovery.recover_epoch(
            context,
            "ep_2",
            "boot_2",
            "sup_2",
            old_epoch_isolated=True,
            request_id="rec-ep2",
            deadline_monotonic_ms=_deadline(),
        )
    ).result(5)

    outcome_claimed, ticket_claimed = recovery.recover_operation(
        context,
        op_claimed,
        "ep_2",
        dispatch_was_sent=False,
        probe_status="NONE",
        request_id="rec-op-claimed",
        deadline_monotonic_ms=_deadline(),
    )
    assert outcome_claimed["operation_state"] == "READY"
    assert ticket_claimed is not None

    # Use minted RecoveryTicket to claim attempt 2 on ep_2: new dispatch_id, CONSUMED unchanged
    resources = [ResourceRequest("WORKSPACE", "wsp_test1", expected_generation=1)]
    reclaimed = json.loads(
        writer.submit(
            dispatcher.claim(
                context,
                op_claimed,
                "ep_2",
                "exec_2",
                resources,
                30_000,
                "reclaim-claimed",
                _deadline(),
                recovery_ticket=ticket_claimed,
            )
        ).result(5)
    )
    assert reclaimed["attempt_no"] == 2
    assert reclaimed["approval_status"] == "CONSUMED"
    # Release workspace lease so subsequent test cases can use wsp_test1
    writer.submit(
        tasks.cancel(context, t_claimed, 4, "cancel-claimed-cleanup", _deadline())
    ).result(5)
    db = connect(path)
    db.execute(
        "UPDATE resource_leases SET holder_attempt_id=NULL,runtime_epoch=NULL,state='RELEASED',"
        "acquired_at=NULL,expires_at=NULL,version=version+1,updated_at=3000"
    )
    db.close()

    # 2. DISPATCHING + SAFE_READ and IDEMPOTENT_WRITE (NOT_APPLIED) -> READY with ticket
    _, op_read, _, _ = _prepare_operation(
        context,
        writer,
        inbox,
        tasks,
        ops,
        approvals,
        dispatcher,
        challenges,
        "fs.read",
        "safe-read",
        enter_dispatching=True,
        epoch="ep_2",
    )
    writer.submit(
        recovery.recover_epoch(
            context,
            "ep_2b",
            "boot_2b",
            "sup_2b",
            old_epoch_isolated=True,
            request_id="rec-ep2b",
            deadline_monotonic_ms=_deadline(),
        )
    ).result(5)
    outcome_read, ticket_read = recovery.recover_operation(
        context,
        op_read,
        "ep_2b",
        dispatch_was_sent=True,
        probe_status="UNKNOWN",
        request_id="rec-op-read",
        deadline_monotonic_ms=_deadline(),
    )
    assert outcome_read["operation_state"] == "READY" and ticket_read is not None

    _, op_patch, _, _ = _prepare_operation(
        context,
        writer,
        inbox,
        tasks,
        ops,
        approvals,
        dispatcher,
        challenges,
        "fs.patch",
        "idem-write",
        enter_dispatching=True,
        epoch="ep_2b",
    )
    writer.submit(
        recovery.recover_epoch(
            context,
            "ep_2c",
            "boot_2c",
            "sup_2c",
            old_epoch_isolated=True,
            request_id="rec-ep2c",
            deadline_monotonic_ms=_deadline(),
        )
    ).result(5)
    outcome_patch, ticket_patch = recovery.recover_operation(
        context,
        op_patch,
        "ep_2c",
        dispatch_was_sent=True,
        probe_status="NOT_APPLIED",
        request_id="rec-op-patch",
        deadline_monotonic_ms=_deadline(),
    )
    assert outcome_patch["operation_state"] == "READY" and ticket_patch is not None

    # 3. DISPATCHING + PROVIDER_IDEMPOTENT (CONFIRMED_NOT_EXECUTED) -> READY with ticket
    t_prov, op_prov, _, att_prov = _prepare_operation(
        context,
        writer,
        inbox,
        tasks,
        ops,
        approvals,
        dispatcher,
        challenges,
        "provider.send",
        "prov-idem",
        enter_dispatching=True,
        epoch="ep_2c",
    )
    writer.submit(
        recovery.recover_epoch(
            context,
            "ep_3",
            "boot_3",
            "sup_3",
            old_epoch_isolated=True,
            request_id="rec-ep3",
            deadline_monotonic_ms=_deadline(),
        )
    ).result(5)
    outcome_prov, ticket_prov = recovery.recover_operation(
        context,
        op_prov,
        "ep_3",
        dispatch_was_sent=True,
        probe_status="CONFIRMED_NOT_EXECUTED",
        request_id="rec-op-prov",
        deadline_monotonic_ms=_deadline(),
    )
    assert outcome_prov["operation_state"] == "READY"
    assert ticket_prov is not None

    # 4. DISPATCHING + RECONCILE_ONLY -> stays UNKNOWN, no ticket minted, Task in RECONCILING
    t_rec, op_rec, _, _ = _prepare_operation(
        context,
        writer,
        inbox,
        tasks,
        ops,
        approvals,
        dispatcher,
        challenges,
        "gui.click",
        "reconcile-only",
        enter_dispatching=True,
        epoch="ep_3",
    )
    writer.submit(
        recovery.recover_epoch(
            context,
            "ep_4",
            "boot_4",
            "sup_4",
            old_epoch_isolated=True,
            request_id="rec-ep4",
            deadline_monotonic_ms=_deadline(),
        )
    ).result(5)
    outcome_rec, ticket_rec = recovery.recover_operation(
        context,
        op_rec,
        "ep_4",
        dispatch_was_sent=True,
        probe_status="UNKNOWN",
        request_id="rec-op-gui",
        deadline_monotonic_ms=_deadline(),
    )
    assert outcome_rec["operation_state"] == "UNKNOWN"
    assert ticket_rec is None
    assert tasks.snapshot(context, t_rec)["state"] == "RECONCILING"


def test_reconcile_unknown_rejects_unverified_or_model_provenance_and_accepts_artifact(
    recovery_env,
):
    path, context, writer, inbox, tasks, ops, approvals, dispatcher, recovery, challenges = (
        recovery_env
    )
    t_id, op_id, _, _ = _prepare_operation(
        context,
        writer,
        inbox,
        tasks,
        ops,
        approvals,
        dispatcher,
        challenges,
        "gui.click",
        "human-rec",
        enter_dispatching=True,
    )
    writer.submit(
        recovery.recover_epoch(
            context,
            "ep_2",
            "boot_2",
            "sup_2",
            old_epoch_isolated=True,
            request_id="rec-human-ep2",
            deadline_monotonic_ms=_deadline(),
        )
    ).result(5)

    # Current operation version after propose(0)->approve(1)->claim(2)->dispatch(3)->unknown(4) is 4
    # 1. Plain "CONFIRMED_SUCCEEDED" without evidence_artifact_ids is rejected by schema
    with pytest.raises(ContractError):
        recovery.reconcile_unknown(
            context,
            op_id,
            json.dumps(
                {"expected_version": 4, "outcome": "CONFIRMED_SUCCEEDED", "note": "success"}
            ),
            provenance_kind="USER_ATTESTED",
            request_id="rec-no-evidence",
            deadline_monotonic_ms=_deadline(),
        )

    # 2. Model output provenance is forbidden even if an artifact exists
    db = connect(path)
    db.execute(
        "INSERT INTO artifacts("
        "object_id,object_key,sha256,mime,bytes,classification,state,created_at) "
        "VALUES('art_rec1','key_rec1',?,'text/plain',16,'WORKSPACE','AVAILABLE',1000)",
        ("d" * 64,),
    )
    db.execute(
        "INSERT INTO artifact_refs("
        "ref_id,object_id,owner_id,scope_kind,operation_id,purpose,created_at) "
        "VALUES('ref_rec1','art_rec1','pri_test1','OPERATION',?,'reconciliation',1000)",
        (op_id,),
    )
    db.close()

    with pytest.raises(PermissionError):
        writer.submit(
            recovery.reconcile_unknown(
                context,
                op_id,
                json.dumps(
                    {
                        "expected_version": 4,
                        "outcome": "CONFIRMED_SUCCEEDED",
                        "evidence_artifact_ids": ["art_rec1"],
                    }
                ),
                provenance_kind="MODEL_OUTPUT",
                request_id="rec-model-prov",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)

    # 3. Valid USER_ATTESTED reconciliation with AVAILABLE artifact resolves UNKNOWN -> SUCCEEDED
    resolved = json.loads(
        writer.submit(
            recovery.reconcile_unknown(
                context,
                op_id,
                json.dumps(
                    {
                        "expected_version": 4,
                        "outcome": "CONFIRMED_SUCCEEDED",
                        "evidence_artifact_ids": ["art_rec1"],
                        "note": "verified screenshot",
                    }
                ),
                provenance_kind="USER_ATTESTED",
                request_id="rec-valid-user",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    assert resolved["operation_state"] == "SUCCEEDED"
    assert resolved["provenance"] == "USER_ATTESTED"
    db = connect(path, readonly=True)
    try:
        lease_state = db.execute(
            "SELECT state FROM resource_leases WHERE resource_key='workspace:wsp_test1'"
        ).fetchone()[0]
        assert lease_state == "RELEASED"
    finally:
        db.close()
