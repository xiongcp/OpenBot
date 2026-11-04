import json

import pytest
from openbot.adapters.local_api.server import (
    ApiRequest,
    LocalControlApiServer,
    ScopedTokenStore,
)
from openbot.application.cancellation import CancellationService
from openbot.application.dispatch import DispatchService
from openbot.application.operations import OperationService
from openbot.application.recovery import RecoveryService
from openbot.application.resources import ResourceRequest
from openbot.application.state_machine import TaskStateService
from openbot.artifacts.store import ArtifactStore
from openbot.contracts import SchemaRegistry
from openbot.policy.approvals import ApprovalService
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.migrate import connect, load_migrations, migrate
from openbot.storage.writer import Writer

from tests.integration.storage.test_migrations import ROOT
from tests.integration.storage.test_recovery import MemoryChallenges, _register_tools


@pytest.fixture
def local_api_env(tmp_path):
    path = tmp_path / "api.sqlite"
    blob_root = tmp_path / "api_blobs"
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
    artifacts = ArtifactStore(writer, blob_root)
    tokens = ScopedTokenStore()
    owner_token = tokens.issue(profile_id="pro_test1", principal_id="pri_test1", scope="owner_cli")
    gw_token = tokens.issue(
        profile_id="pro_test1", principal_id="pri_test1", scope="feishu_gateway"
    )
    ro_token = tokens.issue(
        profile_id="pro_test1", principal_id="pri_test1", scope="webview_readonly"
    )
    api = LocalControlApiServer(
        profile_id="pro_test1",
        default_context=context,
        writer=writer,
        registry=registry,
        tokens=tokens,
        inbox=inbox,
        tasks=tasks,
        operations=ops,
        approvals=approvals,
        recovery=recovery,
        cancellation=cancellation,
        artifacts=artifacts,
        challenges=challenges,
        min_retained_event_seq=2,
    )
    try:
        yield (
            api,
            context,
            writer,
            tasks,
            ops,
            dispatcher,
            recovery,
            owner_token,
            gw_token,
            ro_token,
        )
    finally:
        writer.close()


def _headers(token: str, **extra: str) -> dict[str, str]:
    base = {
        "Authorization": f"Bearer {token}",
        "Host": "127.0.0.1:8765",
        "X-OpenBot-Profile": "pro_test1",
    }
    base.update(extra)
    return base


def test_task_lifecycle_approval_preview_secret_omission_reconcile_and_sse_cursors(local_api_env):
    api, context, writer, tasks, ops, dispatcher, recovery, owner_token, _, _ = local_api_env

    # 1. Health & Create Task + Idempotency conflict check (409 on same key with different goal)
    h = api.handle(ApiRequest("GET", "/v1/health", headers=_headers(owner_token)))
    assert h.status_code == 200

    create_body = json.dumps(
        {"workspace_id": "wsp_test1", "goal": "api-task", "network_mode": "OFFLINE"}
    )
    r1 = api.handle(
        ApiRequest(
            "POST",
            "/v1/tasks",
            headers=_headers(owner_token, **{"Idempotency-Key": "idem-task-1"}),
            body=create_body,
        )
    )
    assert r1.status_code == 201
    task_id = r1.json()["task_id"]

    r_conflict = api.handle(
        ApiRequest(
            "POST",
            "/v1/tasks",
            headers=_headers(owner_token, **{"Idempotency-Key": "idem-task-1"}),
            body=json.dumps(
                {"workspace_id": "wsp_test1", "goal": "changed-goal", "network_mode": "OFFLINE"}
            ),
        )
    )
    assert r_conflict.status_code == 409

    # 2. Propose operation -> ApprovalPreview never exposes SECRET -> fetch challenge -> decide
    writer.submit(tasks.command(context, task_id, 0, "RUNNING", "api-run-1", 999999999999)).result(
        5
    )
    proposed = json.loads(
        ops.propose(
            context,
            task_id,
            "gui.click",
            '{"arg":"secret_btn"}',
            {"workspace_generation": 1, "files": []},
            "WORKSPACE",
            {"kind": "LOCAL", "resource_ref": context.workspace_id},
            "api-prop-1",
            999999999999,
        )
    )
    op_id, apr_id = proposed["operation_id"], proposed["approval_id"]

    prev = api.handle(
        ApiRequest("GET", f"/v1/approvals/{apr_id}/preview", headers=_headers(owner_token))
    )
    assert prev.status_code == 200
    assert prev.json()["data_class"] in {"PUBLIC", "WORKSPACE", "SENSITIVE"}
    assert "nonce" not in json.dumps(prev.json())

    chal = api.handle(
        ApiRequest("POST", f"/v1/approvals/{apr_id}/challenge", headers=_headers(owner_token))
    )
    assert chal.status_code == 200
    nonce = chal.json()["nonce"]

    dec = api.handle(
        ApiRequest(
            "POST",
            f"/v1/approvals/{apr_id}/decide",
            headers=_headers(owner_token, **{"Idempotency-Key": "idem-apr-1"}),
            body=json.dumps(
                {
                    "expected_version": 1,
                    "expected_binding_hash": proposed["binding_hash"],
                    "decision": "APPROVE",
                    "nonce": nonce,
                }
            ),
        )
    )
    assert dec.status_code == 200
    assert dec.json()["operation_state"] == "READY"

    # 3. OperationSnapshot includes version; transition to UNKNOWN and test evidence + reconcile
    op_snap = api.handle(
        ApiRequest("GET", f"/v1/operations/{op_id}", headers=_headers(owner_token))
    )
    assert op_snap.status_code == 200
    assert isinstance(op_snap.json()["version"], int)

    writer.submit(tasks.command(context, task_id, 3, "RUNNING", "api-run-2", 999999999999)).result(
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
                "api-claim-1",
                999999999999,
            )
        ).result(5)
    )
    writer.submit(
        dispatcher.begin_dispatch(
            context, op_id, claimed["attempt_id"], "ep_1", "exec_1", "api-disp-1", 999999999999
        )
    ).result(5)
    writer.submit(
        recovery.recover_epoch(
            context,
            "ep_2",
            "boot_2",
            "sup_2",
            old_epoch_isolated=True,
            request_id="api-rec-ep2",
            deadline_monotonic_ms=999999999999,
        )
    ).result(5)

    # Evidence upload rejects host_path and accepts bounded inline content
    bad_ev = api.handle(
        ApiRequest(
            "POST",
            f"/v1/operations/{op_id}/evidence",
            headers=_headers(owner_token),
            body=json.dumps({"host_path": "/etc/passwd", "content": "x"}),
        )
    )
    assert bad_ev.status_code == 400

    good_ev = api.handle(
        ApiRequest(
            "POST",
            f"/v1/operations/{op_id}/evidence",
            headers=_headers(owner_token, **{"Idempotency-Key": "idem-ev-1"}),
            body=json.dumps({"content": "verified screenshot receipt", "mime": "text/plain"}),
        )
    )
    assert good_ev.status_code == 201
    art_id = good_ev.json()["object_id"]

    cur_op_ver = api.handle(
        ApiRequest("GET", f"/v1/operations/{op_id}", headers=_headers(owner_token))
    ).json()["version"]
    rec_res = api.handle(
        ApiRequest(
            "POST",
            f"/v1/operations/{op_id}/reconcile",
            headers=_headers(owner_token, **{"Idempotency-Key": "idem-rec-1"}),
            body=json.dumps(
                {
                    "expected_version": cur_op_ver,
                    "outcome": "CONFIRMED_SUCCEEDED",
                    "evidence_artifact_ids": [art_id],
                }
            ),
        )
    )
    assert rec_res.status_code == 200
    assert rec_res.json()["operation_state"] == "SUCCEEDED"

    # 4. SSE cursor checks: conflict between after_seq and Last-Event-ID -> 400; expired -> 410
    sse_conflict = api.handle(
        ApiRequest(
            "GET",
            f"/v1/tasks/{task_id}/events",
            headers=_headers(owner_token, **{"Last-Event-ID": "5"}),
            query={"after_seq": "3"},
        )
    )
    assert sse_conflict.status_code == 400

    sse_gone = api.handle(
        ApiRequest(
            "GET",
            f"/v1/tasks/{task_id}/events",
            headers=_headers(owner_token),
            query={"after_seq": "1"},
        )
    )
    assert sse_gone.status_code == 410

    sse_ok = api.handle(
        ApiRequest(
            "GET",
            f"/v1/tasks/{task_id}/events",
            headers=_headers(owner_token),
            query={"after_seq": "2"},
        )
    )
    assert sse_ok.status_code == 200
    assert len(sse_ok.json()["events"]) >= 1
