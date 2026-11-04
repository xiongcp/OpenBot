import json
import time

import pytest
from openbot.application.resources import ResourceCoordinator
from openbot.application.scheduler import (
    ProfileSchedulerService,
    SingleInstanceSupervisorLock,
)
from openbot.application.state_machine import TaskStateService
from openbot.contracts import SchemaRegistry
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.migrate import connect, load_migrations, migrate
from openbot.storage.writer import Writer

from tests.integration.storage.test_migrations import ROOT


def _deadline() -> int:
    return int(time.monotonic() * 1000) + 5000


@pytest.fixture
def scheduler_env(tmp_path):
    path = tmp_path / "scheduler.sqlite"
    lock_path = tmp_path / "profile.lock"
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
    leases = ResourceCoordinator(writer)
    scheduler = ProfileSchedulerService(writer, tasks, leases)
    try:
        yield lock_path, context, writer, inbox, tasks, scheduler
    finally:
        writer.close()


def test_supervisor_lock_parent_child_handoff_without_self_deadlock_and_second_instance_rejection(
    scheduler_env,
):
    lock_path, _, _, _, _, _ = scheduler_env
    sup1 = SingleInstanceSupervisorLock(lock_path, profile_id="pro_test1")
    ticket = sup1.acquire_and_mint_handoff(runtime_epoch="ep_1", boot_id="boot_1")
    try:
        # 1. Child daemon verifies handoff ticket without re-locking profile.lock
        assert sup1.verify_child_daemon_handoff(ticket) is True
        with pytest.raises(PermissionError, match="handoff"):
            sup1.verify_child_daemon_handoff(ticket, provided_token="forged_token")

        # 2. Second supervisor competing for profile.lock fails immediately (non-blocking)
        sup2 = SingleInstanceSupervisorLock(lock_path, profile_id="pro_test1")
        with pytest.raises(PermissionError, match="PROFILE_LOCK_HELD"):
            sup2.acquire_and_mint_handoff(runtime_epoch="ep_2", boot_id="boot_2")
    finally:
        sup1.release()

    # 3. After parent supervisor releases/dies, a new supervisor instance can take over
    sup3 = SingleInstanceSupervisorLock(lock_path, profile_id="pro_test1")
    ticket3 = sup3.acquire_and_mint_handoff(runtime_epoch="ep_3", boot_id="boot_3")
    assert ticket3.runtime_epoch == "ep_3"
    sup3.release()


def test_single_active_task_slot_release_on_waiting_approval_and_stale_epoch_fence_rejection(
    scheduler_env,
):
    lock_path, context, writer, inbox, tasks, scheduler = scheduler_env
    sup = SingleInstanceSupervisorLock(lock_path, profile_id="pro_test1")
    ticket = sup.acquire_and_mint_handoff(runtime_epoch="ep_1", boot_id="boot_1")
    try:
        p1 = json.dumps({"workspace_id": "wsp_test1", "goal": "t1", "network_mode": "OFFLINE"})
        p2 = json.dumps({"workspace_id": "wsp_test1", "goal": "t2", "network_mode": "OFFLINE"})
        t1 = json.loads(inbox.submit(context, "evt-sch-1", p1, _deadline()).result(5))["task_id"]
        t2 = json.loads(inbox.submit(context, "evt-sch-2", p2, _deadline()).result(5))["task_id"]

        # 1. Schedule first task -> claims t1 into RUNNING; second returns None while t1 runs
        s1 = scheduler.schedule_next_task(
            context,
            handoff_ticket=ticket,
            old_workers_isolated=True,
            request_id="sch-claim-1",
            deadline_monotonic_ms=_deadline(),
        )
        assert s1["claimed_task_id"] == t1

        s_blocked = scheduler.schedule_next_task(
            context,
            handoff_ticket=ticket,
            old_workers_isolated=True,
            request_id="sch-claim-blocked",
            deadline_monotonic_ms=_deadline(),
        )
        assert s_blocked["claimed_task_id"] is None

        # 2. Park t1 into WAITING_APPROVAL -> releases compute slot so t2 can be scheduled!
        t1_ver = int(tasks.snapshot(context, t1)["version"])
        writer.submit(
            tasks.command(context, t1, t1_ver, "WAITING_APPROVAL", "wait-t1", _deadline())
        ).result(5)
        s2 = scheduler.schedule_next_task(
            context,
            handoff_ticket=ticket,
            old_workers_isolated=True,
            request_id="sch-claim-2",
            deadline_monotonic_ms=_deadline(),
        )
        assert s2["claimed_task_id"] == t2

        # 3. If old workers are NOT proven isolated, scheduler refuses to start new execution
        with pytest.raises(PermissionError, match="old_workers_isolated"):
            scheduler.schedule_next_task(
                context,
                handoff_ticket=ticket,
                old_workers_isolated=False,
                request_id="sch-unisolated",
                deadline_monotonic_ms=_deadline(),
            )

        # 4. Stale runtime_epoch or stale fencing_token from an expired worker is rejected
        with pytest.raises(PermissionError, match="Stale runtime_epoch|fencing_token"):
            scheduler.verify_worker_submission(
                context,
                worker_runtime_epoch="ep_stale_0",
                worker_fencing_token=0,
            )
    finally:
        sup.release()
