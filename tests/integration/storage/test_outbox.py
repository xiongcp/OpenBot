import hashlib
import json
import time

import pytest
from openbot.application.dispatch import DispatchService
from openbot.application.operations import OperationService
from openbot.application.outbox import (
    GatewaySendResult,
    OutboxEnvelope,
    OutboxService,
)
from openbot.application.resources import ResourceRequest
from openbot.application.state_machine import TaskStateService
from openbot.contracts import SchemaRegistry, canonicalize
from openbot.policy.approvals import ApprovalService
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.migrate import connect, load_migrations, migrate
from openbot.storage.outbox import OutboxStore
from openbot.storage.writer import RequestConflict, Writer

from tests.integration.storage.test_migrations import ROOT
from tests.integration.storage.test_recovery import MemoryChallenges


def _deadline() -> int:
    return int(time.monotonic() * 1000) + 5000


class ControlledGateway:
    """Deterministic gateway stub outside SQLite transactions."""

    def __init__(
        self,
        *,
        capabilities: frozenset[str] = frozenset({"upsert_revision"}),
        sdk_max_retries: int = 0,
    ) -> None:
        self._capabilities = capabilities
        self.sdk_max_retries = sdk_max_retries
        self.outcomes: list[GatewaySendResult | Exception] = []
        self.calls: list[OutboxEnvelope] = []
        self.in_transaction_Checks: list[bool] = []

    def capabilities(self) -> frozenset[str]:
        return self._capabilities

    def send(self, envelope: OutboxEnvelope) -> GatewaySendResult:
        self.calls.append(envelope)
        if not self.outcomes:
            return GatewaySendResult(
                status="SENT",
                provider_message_id=f"msg_{envelope.outbox_id}_{envelope.attempt_count}",
                remote_revision=envelope.revision,
                exact_once_supported="provider_idempotency" in self._capabilities,
            )
        nxt = self.outcomes.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


@pytest.fixture
def outbox_env(tmp_path):
    path = tmp_path / "outbox.sqlite"
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
        manifest = {
            "name": "fs.write",
            "version": "1.0.0",
            "effect": "LOCAL_WRITE",
            "retry_class": "IDEMPOTENT_WRITE",
            "input_schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        }
        raw = canonicalize(manifest)
        db.execute(
            "INSERT INTO tool_registry VALUES("
            "'fs.write', '1.0.0', ?, NULL, 'builtin', ?, 'ACTIVE', 1000)",
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
    store = OutboxStore(writer)
    service = OutboxService(writer, store)
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
            store,
            service,
            challenges,
        )
    finally:
        writer.close()


def test_outbox_coalesces_pending_revisions_and_protects_terminal_state(outbox_env):
    path, context, writer, inbox, _, _, _, _, store, service, _ = outbox_env
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": "outbox-coalesce", "network_mode": "OFFLINE"}
    )
    task_id = json.loads(inbox.submit(context, "evt-ob-1", payload, _deadline()).result(5))[
        "task_id"
    ]

    # Enqueue 3 progress updates under the same (target_key, semantic_key)
    r1 = json.loads(
        writer.submit(
            service.enqueue(
                context,
                task_id=task_id,
                target_key="feishu:chat_1",
                target={"chat_id": "chat_1"},
                semantic_key=f"card:{task_id}",
                payload={"state": "RUNNING", "step": 1, "terminal": False},
                delivery_class="UPSERT_REVISION",
                request_id="ob-enq-1",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    r2 = json.loads(
        writer.submit(
            service.enqueue(
                context,
                task_id=task_id,
                target_key="feishu:chat_1",
                target={"chat_id": "chat_1"},
                semantic_key=f"card:{task_id}",
                payload={"state": "RUNNING", "step": 2, "terminal": False},
                delivery_class="UPSERT_REVISION",
                request_id="ob-enq-2",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    r3 = json.loads(
        writer.submit(
            service.enqueue(
                context,
                task_id=task_id,
                target_key="feishu:chat_1",
                target={"chat_id": "chat_1"},
                semantic_key=f"card:{task_id}",
                payload={"state": "SUCCEEDED", "step": 3, "terminal": True},
                delivery_class="UPSERT_REVISION",
                request_id="ob-enq-3",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    assert (r1["revision"], r2["revision"], r3["revision"]) == (1, 2, 3)
    records = store.list_by_semantic_key(context, "feishu:chat_1", f"card:{task_id}")
    assert [rec.state for rec in records] == ["SUPERSEDED", "SUPERSEDED", "PENDING"]

    # Terminal state protection: non-terminal progress cannot overwrite terminal revision
    with pytest.raises(RequestConflict):
        writer.submit(
            service.enqueue(
                context,
                task_id=task_id,
                target_key="feishu:chat_1",
                target={"chat_id": "chat_1"},
                semantic_key=f"card:{task_id}",
                payload={"state": "RUNNING", "step": 4, "terminal": False},
                delivery_class="UPSERT_REVISION",
                request_id="ob-enq-stale-non-terminal",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)

    # Only revision 3 is delivered when gateway runs
    gw = ControlledGateway()
    dispatched = service.dispatch_next(
        context,
        runtime_epoch="ep_1",
        gateway=gw,
        target_key="feishu:chat_1",
        request_id="ob-disp-3",
        deadline_monotonic_ms=_deadline(),
    )
    assert dispatched is not None
    assert dispatched["state"] == "SENT"
    assert dispatched["revision"] == 3
    assert dispatched["exact_once_guaranteed"] is False
    assert len(gw.calls) == 1
    assert gw.calls[0].revision == 3


def test_late_or_duplicate_receipt_never_regresses_higher_delivered_revision(outbox_env):
    path, context, writer, inbox, _, _, _, _, store, service, _ = outbox_env
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": "outbox-late-receipt", "network_mode": "OFFLINE"}
    )
    task_id = json.loads(inbox.submit(context, "evt-ob-2", payload, _deadline()).result(5))[
        "task_id"
    ]

    # Enqueue revision 1 and claim it into IN_FLIGHT
    r1 = json.loads(
        writer.submit(
            service.enqueue(
                context,
                task_id=task_id,
                target_key="feishu:chat_2",
                target={"chat_id": "chat_2"},
                semantic_key=f"card:{task_id}",
                payload={"state": "RUNNING", "step": 1, "terminal": False},
                delivery_class="UPSERT_REVISION",
                request_id="ob-late-1",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    claim1 = store.claim_due(
        context,
        runtime_epoch="ep_1",
        lease_ttl_ms=10_000,
        target_key="feishu:chat_2",
        request_id="ob-claim-1",
        deadline_monotonic_ms=_deadline(),
    )
    assert claim1 is not None and claim1.outbox_id == r1["outbox_id"]

    # While revision 1 is IN_FLIGHT, terminal revision 2 is enqueued
    r2 = json.loads(
        writer.submit(
            service.enqueue(
                context,
                task_id=task_id,
                target_key="feishu:chat_2",
                target={"chat_id": "chat_2"},
                semantic_key=f"card:{task_id}",
                payload={"state": "SUCCEEDED", "step": 2, "terminal": True},
                delivery_class="UPSERT_REVISION",
                request_id="ob-late-2",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    assert r2["revision"] == 2

    # Revision 1 receipt arrives after revision 2 already exists -> recorded as SUPERSEDED,
    # so revision 2 remains PENDING and can then be delivered as the authoritative terminal state.
    res1 = json.loads(
        writer.submit(
            service.complete_delivery(
                context,
                outbox_id=claim1.outbox_id,
                lease_token=claim1.lease_token,
                expected_version=claim1.version,
                result=GatewaySendResult(
                    status="SENT",
                    provider_message_id="msg_rev1",
                    remote_revision=1,
                    exact_once_supported=False,
                ),
                request_id="ob-complete-1",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    assert res1["state"] == "SUPERSEDED"
    assert res1["superseded_by_higher_revision"] is True

    # Now revision 2 is delivered and becomes the highest delivered revision (2)
    gw = ControlledGateway()
    res2 = service.dispatch_next(
        context,
        runtime_epoch="ep_1",
        gateway=gw,
        target_key="feishu:chat_2",
        request_id="ob-disp-rev2",
        deadline_monotonic_ms=_deadline(),
    )
    assert res2 is not None and res2["state"] == "SENT" and res2["revision"] == 2
    assert store.highest_delivered_revision(context, "feishu:chat_2", f"card:{task_id}") == 2

    # Duplicate receipt submission for the same request_id is idempotent and does not regress
    dup1 = json.loads(
        writer.submit(
            service.complete_delivery(
                context,
                outbox_id=claim1.outbox_id,
                lease_token=claim1.lease_token,
                expected_version=claim1.version,
                result=GatewaySendResult(
                    status="SENT",
                    provider_message_id="msg_rev1",
                    remote_revision=1,
                    exact_once_supported=False,
                ),
                request_id="ob-complete-1",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    assert dup1 == res1
    assert store.highest_delivered_revision(context, "feishu:chat_2", f"card:{task_id}") == 2


def test_retry_budget_dead_letter_and_no_business_reexecution(outbox_env):
    (
        path,
        context,
        writer,
        inbox,
        tasks,
        ops,
        approvals,
        dispatcher,
        store,
        service,
        challenges,
    ) = outbox_env
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": "outbox-retry-dead", "network_mode": "OFFLINE"}
    )
    task_id = json.loads(inbox.submit(context, "evt-ob-3", payload, _deadline()).result(5))[
        "task_id"
    ]
    writer.submit(tasks.command(context, task_id, 0, "RUNNING", "run-ob-3", _deadline())).result(5)
    proposed = json.loads(
        ops.propose(
            context,
            task_id,
            "fs.write",
            '{"path":"a.txt"}',
            {"workspace_generation": 1, "files": []},
            "WORKSPACE",
            {"kind": "LOCAL", "resource_ref": context.workspace_id},
            "prop-ob-3",
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
        "apr-ob-3",
        _deadline(),
    )
    writer.submit(tasks.command(context, task_id, 3, "RUNNING", "run2-ob-3", _deadline())).result(5)
    writer.submit(
        dispatcher.claim(
            context,
            op_id,
            "ep_1",
            "exec_1",
            [ResourceRequest("WORKSPACE", "wsp_test1", expected_generation=1)],
            30_000,
            "claim-ob-3",
            _deadline(),
        )
    ).result(5)

    # Negative check: gateway with SDK auto-retry enabled is rejected (single retry owner invariant)
    bad_gw = ControlledGateway(sdk_max_retries=3)
    with pytest.raises(PermissionError, match="SDK retry"):
        service.dispatch_next(
            context,
            runtime_epoch="ep_1",
            gateway=bad_gw,
            target_key="feishu:chat_3",
            request_id="ob-bad-gw",
            deadline_monotonic_ms=_deadline(),
        )

    # Enqueue notification with max_attempts=2
    enq = json.loads(
        writer.submit(
            service.enqueue(
                context,
                task_id=task_id,
                target_key="feishu:chat_3",
                target={"chat_id": "chat_3"},
                semantic_key=f"notify:{task_id}",
                payload={"state": "RUNNING", "op": op_id},
                delivery_class="PROVIDER_IDEMPOTENT",
                provider_idempotency_key=f"obk_{op_id}",
                request_id="ob-enq-retry",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    outbox_id = enq["outbox_id"]

    gw = ControlledGateway(
        capabilities=frozenset({"provider_idempotency"}),
        sdk_max_retries=0,
    )
    # Attempt 1: gateway raises a library RuntimeError -> caught outside DB txn, retryable
    # with backoff_ms=0 so we can immediately test Attempt 2
    gw.outcomes = [
        RuntimeError("synthetic transport socket reset"),
        GatewaySendResult(
            status="RETRYABLE_ERROR",
            error_code="HTTP_503",
            retry_after_ms=0,
            exact_once_supported=True,
        ),
    ]
    attempt1 = service.dispatch_next(
        context,
        runtime_epoch="ep_1",
        gateway=gw,
        target_key="feishu:chat_3",
        max_attempts=2,
        base_backoff_ms=0,
        request_id="ob-try-1",
        deadline_monotonic_ms=_deadline(),
    )
    assert attempt1 is not None
    assert attempt1["state"] == "PENDING"
    assert attempt1["attempt_count"] == 1

    # Attempt 2 exhausts max_attempts=2 -> moves to DEAD letter
    attempt2 = service.dispatch_next(
        context,
        runtime_epoch="ep_1",
        gateway=gw,
        target_key="feishu:chat_3",
        max_attempts=2,
        base_backoff_ms=0,
        request_id="ob-try-2",
        deadline_monotonic_ms=_deadline(),
    )
    assert attempt2 is not None
    assert attempt2["state"] == "DEAD"
    assert attempt2["attempt_count"] == 2
    assert store.get(context, outbox_id).state == "DEAD"

    # Verify business operation_attempts count is STILL 1 (retries never re-run business ops)
    db = connect(path, readonly=True)
    try:
        att_count = db.execute(
            "SELECT count(*) FROM operation_attempts WHERE operation_id=?", (op_id,)
        ).fetchone()[0]
        assert att_count == 1
    finally:
        db.close()


def test_in_flight_recovery_across_restart_and_delivery_classes(outbox_env):
    path, context, writer, inbox, _, _, _, _, store, service, _ = outbox_env
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": "outbox-recovery", "network_mode": "OFFLINE"}
    )
    task_id = json.loads(inbox.submit(context, "evt-ob-4", payload, _deadline()).result(5))[
        "task_id"
    ]

    # 1. UPSERT_REVISION item in IN_FLIGHT
    u_enq = json.loads(
        writer.submit(
            service.enqueue(
                context,
                task_id=task_id,
                target_key="feishu:rec_upsert",
                target={"chat_id": "rec_upsert"},
                semantic_key=f"card:{task_id}",
                payload={"state": "RUNNING", "step": 1},
                delivery_class="UPSERT_REVISION",
                request_id="ob-rec-enq-1",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    store.claim_due(
        context,
        runtime_epoch="ep_1",
        lease_ttl_ms=10_000,
        target_key="feishu:rec_upsert",
        request_id="ob-rec-claim-1",
        deadline_monotonic_ms=_deadline(),
    )

    # 2. RECONCILE_ONLY item in IN_FLIGHT (no remote idempotency -> must become UNKNOWN on crash)
    r_enq = json.loads(
        writer.submit(
            service.enqueue(
                context,
                task_id=task_id,
                target_key="feishu:rec_only",
                target={"chat_id": "rec_only"},
                semantic_key=f"msg:{task_id}",
                payload={"text": "non-idempotent notification"},
                delivery_class="RECONCILE_ONLY",
                request_id="ob-rec-enq-2",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    store.claim_due(
        context,
        runtime_epoch="ep_1",
        lease_ttl_ms=10_000,
        target_key="feishu:rec_only",
        request_id="ob-rec-claim-2",
        deadline_monotonic_ms=_deadline(),
    )

    # While ep_1 is still ACTIVE, recovery is refused (cannot steal active epoch's IN_FLIGHT)
    with pytest.raises(PermissionError, match="STOPPED"):
        writer.submit(
            service.recover_in_flight(
                context,
                runtime_epoch="ep_1",
                request_id="ob-rec-active-fail",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)

    # Simulate restart: mark ep_1 STOPPED and activate ep_2
    db = connect(path)
    try:
        db.execute(
            "UPDATE runtime_instances SET state='STOPPED',ended_at=2000 WHERE runtime_epoch='ep_1'"
        )
        db.execute(
            "INSERT INTO runtime_instances("
            "runtime_epoch,boot_id,supervisor_ref,state,started_at,heartbeat_at) "
            "VALUES('ep_2','boot_2','sup_2','ACTIVE',2000,2000)"
        )
        db.execute(
            "UPDATE profile_config SET active_runtime_epoch='ep_2',"
            "version=version+1,updated_at=2000 WHERE singleton=1"
        )
    finally:
        db.close()

    recovered = json.loads(
        writer.submit(
            service.recover_in_flight(
                context,
                runtime_epoch="ep_2",
                request_id="ob-rec-ep2",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    assert u_enq["outbox_id"] in recovered["requeued_ids"]
    assert r_enq["outbox_id"] in recovered["unknown_ids"]
    assert store.get(context, u_enq["outbox_id"]).state == "PENDING"
    assert store.get(context, r_enq["outbox_id"]).state == "UNKNOWN"

    # Reconcile UNKNOWN outbox item with verified gateway receipt -> SENT
    reconciled = json.loads(
        writer.submit(
            service.reconcile_unknown(
                context,
                outbox_id=r_enq["outbox_id"],
                expected_version=store.get(context, r_enq["outbox_id"]).version,
                resolution="CONFIRMED_SENT",
                provider_receipt={"provider_message_id": "msg_reconciled_1", "verified": True},
                request_id="ob-reconcile-1",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    assert reconciled["state"] == "SENT"
    assert reconciled["exact_once_guaranteed"] is False
