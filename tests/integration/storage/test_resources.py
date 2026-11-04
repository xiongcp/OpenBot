import json
import time

import pytest
from openbot.application.resources import (
    OrderedResources,
    ResourceBusyError,
    ResourceCoordinator,
    ResourcePreconditionError,
    ResourceQuarantinedError,
    ResourceRequest,
    order_resources,
)
from openbot.contracts import SchemaRegistry
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.migrate import connect, load_migrations, migrate
from openbot.storage.writer import Writer

from tests.integration.storage.test_migrations import ROOT


def _deadline() -> int:
    return int(time.monotonic() * 1000) + 5000


def _task_payload(goal: str = "resource test") -> str:
    return json.dumps({"workspace_id": "wsp_test1", "goal": goal, "network_mode": "OFFLINE"})


@pytest.fixture
def env(tmp_path):
    path = tmp_path / "resources.sqlite"
    migrate(path, load_migrations(ROOT / "db/migrations"))
    db = connect(path)
    try:
        db.execute("INSERT INTO policy_revisions VALUES(1,?,'{}',1000,1000)", ("a" * 64,))
        db.execute(
            "INSERT INTO runtime_instances("
            "runtime_epoch,boot_id,supervisor_ref,state,started_at,heartbeat_at) "
            "VALUES('ep_active1','boot_1','sup_1','ACTIVE',1000,1000)"
        )
        db.execute(
            "INSERT INTO profile_config("
            "singleton,profile_id,schema_version,policy_version,identity_epoch,"
            "privacy_mode,active_runtime_epoch,last_fencing_token,created_at,updated_at) "
            "VALUES(1,'pro_test1',1,1,1,'OFFLINE','ep_active1',0,1000,1000)"
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
        db.execute(
            "INSERT INTO tool_registry VALUES("
            "'browser.write','1.0.0',?,NULL,'builtin','{\"name\":\"browser.write\"}','ACTIVE',1000)",
            ("c" * 64,),
        )
    finally:
        db.close()
    context = InboundContext(
        "pro_test1", "pri_test1", 1, "local", "tenant1", "app1", "ses_test1", "wsp_test1"
    )
    writer = Writer(path)
    inbox = Inbox(writer, SchemaRegistry.from_directory(ROOT / "contracts"))
    try:
        yield path, context, writer, inbox
    finally:
        writer.close()


def _seed_op_and_attempt(
    path,
    task_id: str,
    operation_id: str,
    attempt_id: str,
    ordinal: int = 1,
    runtime_epoch: str = "ep_active1",
    op_state: str = "CLAIMED",
    attempt_status: str = "CLAIMED",
    lease_keys: list[str] | None = None,
    unknown_reason: str | None = None,
) -> None:
    db = connect(path)
    try:
        dispatch_started = (
            1200 if attempt_status in {"DISPATCHING", "SUCCEEDED", "FAILED", "UNKNOWN"} else None
        )
        finished_at = (
            1500 if attempt_status in {"SUCCEEDED", "FAILED", "ABANDONED", "CANCELLED"} else None
        )
        completed_at = (
            1500
            if op_state in {"SUCCEEDED", "FAILED", "REJECTED", "EXPIRED", "REVOKED", "CANCELLED"}
            else None
        )
        db.execute(
            "INSERT INTO operations("
            "operation_id,task_id,ordinal,requested_by,workspace_id,workspace_generation,"
            "tool_id,tool_version,tool_manifest_digest,canonical_args_json,resource_snapshot_json,"
            "destination_json,data_class,authorization_kind,policy_version,identity_epoch,"
            "authorization_expires_at,binding_hash,retry_class,state,unknown_reason,"
            "created_at,updated_at,completed_at,proposal_canonical_json) "
            "VALUES(?,?,?,'pri_test1','wsp_test1',1,'browser.write','1.0.0',?,'{}','{}','{}',"
            "'WORKSPACE','POLICY_ALLOW',1,1,9000,?,'RECONCILE_ONLY',?,?,1000,1200,?,'{}')",
            (
                operation_id,
                task_id,
                ordinal,
                "c" * 64,
                f"{hash(operation_id) & ((1 << 256) - 1):064x}",
                op_state,
                unknown_reason,
                completed_at,
            ),
        )
        db.execute(
            "INSERT INTO operation_attempts("
            "attempt_id,operation_id,attempt_no,runtime_epoch,fencing_token,dispatch_id,"
            "executor_id,claim_cancel_revision,claim_policy_version,claim_identity_epoch,"
            "lease_set_json,status,created_at,dispatch_started_at,finished_at) "
            "VALUES(?,?,1,?,1,?,'exec_1',0,1,1,?,?,1000,?,?)",
            (
                attempt_id,
                operation_id,
                runtime_epoch,
                f"dsp_{attempt_id}",
                json.dumps(lease_keys or []),
                attempt_status,
                dispatch_started,
                finished_at,
            ),
        )
    finally:
        db.close()


def test_deterministic_resource_key_ordering_across_four_types():
    unordered = [
        ResourceRequest("EXTERNAL_ACCOUNT", "feishu_main"),
        ResourceRequest("DESKTOP_SESSION", "display_0"),
        ResourceRequest("BROWSER_PROFILE", "prof_b"),
        ResourceRequest("WORKSPACE", "wsp_test1", expected_generation=1, expected_version=0),
        ResourceRequest("BROWSER_PROFILE", "prof_a"),
    ]
    ordered: OrderedResources = order_resources(unordered)
    assert [item.resource_key for item in ordered] == [
        "workspace:wsp_test1",
        "browser_profile:prof_a",
        "browser_profile:prof_b",
        "desktop_session:display_0",
        "external_account:feishu_main",
    ]
    # Reversing input order produces identical canonical acquisition order
    assert order_resources(list(reversed(unordered))) == ordered


def test_single_active_task_fifo_queue_and_approval_wait_releases_locks(env):
    path, context, writer, inbox = env
    coord = ResourceCoordinator(writer)

    t1 = json.loads(inbox.submit(context, "evt-q1", _task_payload("first"), _deadline()).result(5))[
        "task_id"
    ]
    t2 = json.loads(
        inbox.submit(context, "evt-q2", _task_payload("second"), _deadline()).result(5)
    )["task_id"]

    # First claim_next_task picks t1 in FIFO order; second call while t1 is RUNNING cannot start t2
    claimed1 = json.loads(
        writer.submit(coord.claim_next_task(context, "ep_active1", "claim-1", _deadline())).result(
            5
        )
    )
    assert claimed1["task_id"] == t1 and claimed1["state"] == "RUNNING"
    with pytest.raises(ResourceBusyError):
        writer.submit(coord.claim_next_task(context, "ep_active1", "claim-2", _deadline())).result(
            5
        )

    # t1 acquires WORKSPACE + BROWSER_PROFILE leases
    _seed_op_and_attempt(path, t1, "op_t1", "att_t1")
    reqs = [
        ResourceRequest("BROWSER_PROFILE", "chrome_default"),
        ResourceRequest("WORKSPACE", "wsp_test1", expected_generation=1, expected_version=0),
    ]
    leased = json.loads(
        writer.submit(
            coord.acquire_leases(
                context, t1, "att_t1", "ep_active1", reqs, 30_000, "acq-1", _deadline()
            )
        ).result(5)
    )
    assert [entry["resource_key"] for entry in leased["leases"]] == [
        "workspace:wsp_test1",
        "browser_profile:chrome_default",
    ]
    assert [entry["fencing_token"] for entry in leased["leases"]] == [1, 2]

    # Parking t1 into WAITING_APPROVAL atomically releases HELD leases and frees the active slot
    parked = json.loads(
        writer.submit(
            coord.park_for_wait(context, t1, 1, "WAITING_APPROVAL", "park-t1-approval", _deadline())
        ).result(5)
    )
    assert parked["state"] == "WAITING_APPROVAL"
    assert parked["released_keys"] == ["browser_profile:chrome_default", "workspace:wsp_test1"]

    # Now t2 can claim the active slot and acquire browser_profile:chrome_default with fence > 2
    claimed2 = json.loads(
        writer.submit(coord.claim_next_task(context, "ep_active1", "claim-2b", _deadline())).result(
            5
        )
    )
    assert claimed2["task_id"] == t2 and claimed2["state"] == "RUNNING"


def test_concurrent_browser_writes_blocked_and_expired_lease_requires_stopped_epoch(env):
    path, context, writer, inbox = env
    coord = ResourceCoordinator(writer)

    t1 = json.loads(inbox.submit(context, "evt-b1", _task_payload("b1"), _deadline()).result(5))[
        "task_id"
    ]
    writer.submit(coord.claim_next_task(context, "ep_active1", "claim-b1", _deadline())).result(5)
    _seed_op_and_attempt(path, t1, "op_b1", "att_b1", ordinal=1)
    _seed_op_and_attempt(path, t1, "op_b2", "att_b2", ordinal=2)

    browser_req = [ResourceRequest("BROWSER_PROFILE", "prof_shared")]
    writer.submit(
        coord.acquire_leases(
            context, t1, "att_b1", "ep_active1", browser_req, 10, "acq-b1", _deadline()
        )
    ).result(5)

    # Even if expires_at passed, a second attempt cannot steal a HELD lease while epoch is ACTIVE
    db = connect(path)
    db.execute(
        "UPDATE resource_leases SET acquired_at=100,expires_at=200,version=version+1 "
        "WHERE resource_key='browser_profile:prof_shared'"
    )
    db.close()
    with pytest.raises(ResourceBusyError):
        writer.submit(
            coord.acquire_leases(
                context,
                t1,
                "att_b2",
                "ep_active1",
                browser_req,
                30_000,
                "acq-b2-steal",
                _deadline(),
            )
        ).result(5)

    # Reclaim requires old epoch STOPPED and old attempt never dispatched (CLAIMED/ABANDONED)
    db = connect(path)
    db.execute(
        "UPDATE runtime_instances SET state='STOPPED',ended_at=2000 "
        "WHERE runtime_epoch='ep_active1'"
    )
    db.execute(
        "INSERT INTO runtime_instances("
        "runtime_epoch,boot_id,supervisor_ref,state,started_at,heartbeat_at) "
        "VALUES('ep_active2','boot_2','sup_2','ACTIVE',2000,2000)"
    )
    db.execute(
        "UPDATE profile_config SET active_runtime_epoch='ep_active2',version=version+1,"
        "updated_at=2000 WHERE singleton=1"
    )
    db.execute(
        "UPDATE operation_attempts SET status='ABANDONED',version=version+1,"
        "recovery_evidence_ref='ev_stopped',finished_at=2000 WHERE attempt_id='att_b1'"
    )
    db.close()

    _seed_op_and_attempt(path, t1, "op_b3", "att_b3", ordinal=3, runtime_epoch="ep_active2")
    reclaimed = json.loads(
        writer.submit(
            coord.acquire_leases(
                context,
                t1,
                "att_b3",
                "ep_active2",
                browser_req,
                30_000,
                "acq-b3-reclaim",
                _deadline(),
            )
        ).result(5)
    )
    assert reclaimed["leases"][0]["fencing_token"] > 1


def test_reacquire_verifies_workspace_version_and_unknown_quarantine_blocks_new_ids(env):
    path, context, writer, inbox = env
    coord = ResourceCoordinator(writer)

    t1 = json.loads(inbox.submit(context, "evt-v1", _task_payload("v1"), _deadline()).result(5))[
        "task_id"
    ]
    writer.submit(coord.claim_next_task(context, "ep_active1", "claim-v1", _deadline())).result(5)
    _seed_op_and_attempt(path, t1, "op_v1", "att_v1", ordinal=1)

    ws_req = [ResourceRequest("WORKSPACE", "wsp_test1", expected_generation=1, expected_version=0)]
    writer.submit(
        coord.acquire_leases(
            context, t1, "att_v1", "ep_active1", ws_req, 30_000, "acq-v1", _deadline()
        )
    ).result(5)
    writer.submit(
        coord.park_for_wait(context, t1, 1, "WAITING_APPROVAL", "park-v1", _deadline())
    ).result(5)

    # User modifies workspace while task waits for approval (generation bumps to 2, version to 1)
    db = connect(path)
    db.execute(
        "UPDATE workspaces SET root_ref='synthetic-workspace-v2',generation=2,version=version+1,"
        "updated_at=3000 WHERE workspace_id='wsp_test1'"
    )
    db.execute(
        "UPDATE tasks SET state='QUEUED',version=version+1,updated_at=3000 WHERE task_id=?", (t1,)
    )
    db.close()

    writer.submit(
        coord.claim_next_task(context, "ep_active1", "claim-v1-again", _deadline())
    ).result(5)
    _seed_op_and_attempt(path, t1, "op_v2", "att_v2", ordinal=2)
    with pytest.raises(ResourcePreconditionError):
        writer.submit(
            coord.acquire_leases(
                context, t1, "att_v2", "ep_active1", ws_req, 30_000, "acq-v2-stale", _deadline()
            )
        ).result(5)

    # UNKNOWN operation on external_account:feishu_main quarantines resource across operations
    _seed_op_and_attempt(
        path,
        t1,
        "op_unk_ext",
        "att_unk_ext",
        ordinal=3,
        op_state="UNKNOWN",
        attempt_status="UNKNOWN",
        lease_keys=["external_account:feishu_main"],
        unknown_reason="network_drop",
    )
    _seed_op_and_attempt(path, t1, "op_v4", "att_v4", ordinal=4)
    with pytest.raises(ResourceQuarantinedError):
        writer.submit(
            coord.acquire_leases(
                context,
                t1,
                "att_v4",
                "ep_active1",
                [ResourceRequest("EXTERNAL_ACCOUNT", "feishu_main")],
                30_000,
                "acq-quarantined",
                _deadline(),
            )
        ).result(5)


def test_lease_set_mismatch_and_in_flight_park_are_rejected(env):
    path, context, writer, inbox = env
    coord = ResourceCoordinator(writer)

    t1 = json.loads(inbox.submit(context, "evt-m1", _task_payload("m1"), _deadline()).result(5))[
        "task_id"
    ]
    writer.submit(coord.claim_next_task(context, "ep_active1", "claim-m1", _deadline())).result(5)

    # Attempt declares a different lease_set_json than requested -> rejected
    _seed_op_and_attempt(
        path,
        t1,
        "op_mismatch",
        "att_mismatch",
        ordinal=1,
        lease_keys=["browser_profile:other"],
    )
    with pytest.raises(PermissionError):
        writer.submit(
            coord.acquire_leases(
                context,
                t1,
                "att_mismatch",
                "ep_active1",
                [ResourceRequest("BROWSER_PROFILE", "expected")],
                30_000,
                "acq-mismatch",
                _deadline(),
            )
        ).result(5)

    # Acquire valid lease, then transition attempt to DISPATCHING -> park_for_wait must be rejected
    _seed_op_and_attempt(
        path,
        t1,
        "op_disp",
        "att_disp",
        ordinal=2,
        lease_keys=["browser_profile:expected"],
    )
    writer.submit(
        coord.acquire_leases(
            context,
            t1,
            "att_disp",
            "ep_active1",
            [ResourceRequest("BROWSER_PROFILE", "expected")],
            30_000,
            "acq-disp",
            _deadline(),
        )
    ).result(5)
    db = connect(path)
    db.execute(
        "UPDATE operation_attempts SET status='DISPATCHING',dispatch_started_at=1500,"
        "version=version+1 WHERE attempt_id='att_disp'"
    )
    db.execute(
        "UPDATE operations SET state='DISPATCHING',version=version+1,updated_at=1500 "
        "WHERE operation_id='op_disp'"
    )
    db.close()

    with pytest.raises(PermissionError):
        writer.submit(
            coord.park_for_wait(
                context, t1, 1, "WAITING_APPROVAL", "park-while-dispatching", _deadline()
            )
        ).result(5)
