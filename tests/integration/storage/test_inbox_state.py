import json
import sqlite3
import subprocess
import sys
import time
from dataclasses import replace

import pytest
from openbot.application.state_machine import TaskStateService
from openbot.contracts import SchemaRegistry
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.migrate import connect, load_migrations, migrate
from openbot.storage.writer import RequestConflict, Writer

from tests.integration.storage.test_migrations import ROOT


@pytest.fixture
def system(tmp_path):
    path = tmp_path / "state.sqlite"
    migrate(path, load_migrations(ROOT / "db/migrations"))
    db = connect(path)
    try:
        db.execute("INSERT INTO policy_revisions VALUES(1,?,'{}',1000,1000)", ("a" * 64,))
        db.execute(
            "INSERT INTO profile_config(singleton,profile_id,schema_version,policy_version,"
            "identity_epoch,privacy_mode,created_at,updated_at) "
            "VALUES(1,'pro_test1',1,1,1,'OFFLINE',1000,1000)"
        )
        db.execute(
            "INSERT INTO principals(principal_id,role,status,display_name,created_at) "
            "VALUES('pri_test1','OWNER','ACTIVE','synthetic owner',1000)"
        )
        db.execute(
            "INSERT INTO workspaces(workspace_id,root_ref,generation,status,created_at,updated_at) "
            "VALUES('wsp_test1','synthetic-workspace',1,'ACTIVE',1000,1000)"
        )
        db.execute(
            "INSERT INTO sessions(session_id,owner_id,workspace_id,status,created_at,updated_at) "
            "VALUES('ses_test1','pri_test1','wsp_test1','OPEN',1000,1000)"
        )
    finally:
        db.close()
    context = InboundContext(
        "pro_test1", "pri_test1", 1, "fake", "tenant1", "app1", "ses_test1", "wsp_test1"
    )
    writer = Writer(path)
    inbox = Inbox(writer, SchemaRegistry.from_directory(ROOT / "contracts"))
    try:
        yield path, context, writer, inbox
    finally:
        writer.close()


def payload(goal="synthetic task"):
    return json.dumps({"workspace_id": "wsp_test1", "goal": goal, "network_mode": "OFFLINE"})


def deadline():
    return int(time.monotonic() * 1000) + 5000


def test_inbox_dedupe_is_scoped_and_task_event_outbox_are_atomic(system):
    path, context, writer, inbox = system
    receipts = [
        json.loads(inbox.submit(context, "event-same", payload(), deadline()).result(timeout=5))
        for _ in range(100)
    ]
    assert len({r["task_id"] for r in receipts}) == 1
    other = json.loads(
        inbox.submit(replace(context, app_id="app2"), "event-same", payload(), deadline()).result(
            timeout=5
        )
    )
    assert other["task_id"] != receipts[0]["task_id"]
    db = connect(path, readonly=True)
    try:
        assert db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM inbox").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM outbox").fetchone()[0] == 2
    finally:
        db.close()
    with pytest.raises(RequestConflict):
        inbox.submit(context, "event-same", payload("changed"), deadline()).result(timeout=5)


def test_outbox_failure_does_not_ack_or_leave_partial_task(system):
    path, context, writer, inbox = system
    db = connect(path)
    db.execute(
        "CREATE TRIGGER fail_outbox BEFORE INSERT ON outbox "
        "BEGIN SELECT RAISE(ABORT,'synthetic full'); END;"
    )
    db.close()
    with pytest.raises(sqlite3.IntegrityError):
        inbox.submit(context, "event-failure", payload(), deadline()).result(timeout=5)
    db = connect(path, readonly=True)
    try:
        for table in ["tasks", "inbox", "events", "outbox", "budgets"]:
            assert db.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0
    finally:
        db.close()


def test_revoked_owner_stale_epoch_and_body_authority_do_not_create_tasks(system):
    path, context, writer, inbox = system
    for index, bad_context in enumerate(
        [replace(context, principal_id="pri_other1"), replace(context, identity_epoch=2)]
    ):
        with pytest.raises(PermissionError):
            inbox.submit(bad_context, f"event-bad-{index}", payload(), deadline()).result(timeout=5)
    with pytest.raises(ValueError):
        inbox.submit(
            context,
            "event-body",
            json.dumps(json.loads(payload()) | {"is_owner": True}),
            deadline(),
        )
    db = connect(path)
    db.execute(
        "UPDATE principals SET status='REVOKED',revoked_at=2000 WHERE principal_id='pri_test1'"
    )
    db.close()
    with pytest.raises(PermissionError):
        inbox.submit(context, "event-revoked", payload(), deadline()).result(timeout=5)


def test_task_cas_event_outbox_and_replay_have_one_authoritative_result(system):
    path, context, writer, inbox = system
    task = json.loads(
        inbox.submit(context, "event-state", payload(), deadline()).result(timeout=5)
    )["task_id"]
    service = TaskStateService(writer)
    command = service.command(context, task, 0, "RUNNING", "request-state-1", deadline())
    first_raw = writer.submit(command).result(timeout=5)
    first = json.loads(first_raw)
    assert first["state"] == "RUNNING" and first["version"] == 1
    assert writer.submit(command).result(timeout=5) == first_raw
    with pytest.raises(ValueError):
        writer.submit(
            service.command(context, task, 0, "PAUSED", "request-state-stale", deadline())
        ).result(timeout=5)
    with pytest.raises(PermissionError):
        writer.submit(
            service.command(context, task, 1, "SUCCEEDED", "model-final", deadline())
        ).result(timeout=5)
    events = service.replay(context, task)
    assert [event["event_type"] for event in events] == ["TASK_QUEUED", "TASK_STATE_CHANGED"]
    assert service.snapshot(context, task)["version"] == 1


def test_generic_state_port_cannot_bypass_cancel_use_case(system):
    path, context, writer, inbox = system
    task = json.loads(
        inbox.submit(context, "event-cancel", payload(), deadline()).result(timeout=5)
    )["task_id"]
    service = TaskStateService(writer)
    with pytest.raises(PermissionError):
        writer.submit(
            service.command(context, task, 0, "CANCELLED", "request-cancel", deadline())
        ).result(timeout=5)
    assert service.snapshot(context, task)["state"] == "QUEUED"


def test_request_id_scope_is_identical_after_writer_restart(system):
    path, context, writer, inbox = system
    first = json.loads(
        inbox.submit(context, "event-first", payload(), deadline()).result(timeout=5)
    )["task_id"]
    second = json.loads(
        inbox.submit(context, "event-second", payload(), deadline()).result(timeout=5)
    )["task_id"]
    service = TaskStateService(writer)
    writer.submit(
        service.command(context, first, 0, "RUNNING", "one-global-request", deadline())
    ).result(timeout=5)
    with pytest.raises(RequestConflict):
        writer.submit(
            service.command(context, second, 0, "RUNNING", "one-global-request", deadline())
        ).result(timeout=5)
    writer.close()
    with Writer(path) as restarted:
        service = TaskStateService(restarted)
        with pytest.raises(RequestConflict):
            restarted.submit(
                service.command(context, second, 0, "RUNNING", "one-global-request", deadline())
            ).result(timeout=5)
        assert service.snapshot(context, second)["state"] == "QUEUED"


@pytest.mark.parametrize("point", ["before_commit", "after_commit_before_ack"])
def test_process_exit_at_inbound_commit_boundary_never_duplicates_task(system, point):
    path, context, writer, inbox = system
    writer.close()
    code = r"""
import os, sys, time
from pathlib import Path
from openbot.contracts import SchemaRegistry
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.writer import Writer
import openbot.storage.inbox as module
context = InboundContext(
    "pro_test1", "pri_test1", 1, "fake", "tenant1", "app1", "ses_test1", "wsp_test1")
if sys.argv[2] == "before_commit":
    original = module.emit_state
    def crash(*args, **kwargs):
        original(*args, **kwargs)
        os._exit(77)
    module.emit_state = crash
writer = Writer(Path(sys.argv[1]))
inbox = Inbox(writer, SchemaRegistry.from_directory(Path("contracts")))
raw = (b'{"workspace_id":"wsp_test1","goal":"synthetic task",'
       b'"network_mode":"OFFLINE"}')
inbox.submit(context, "event-process-crash", raw,
    int(time.monotonic()*1000)+5000).result(timeout=5)
os._exit(77)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(path), point],
        cwd=ROOT,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 77, result.stderr.decode()
    with Writer(path) as recovered:
        before = recovered.read(lambda db: db.execute("SELECT count(*) FROM tasks").fetchone()[0])
        assert before == (point == "after_commit_before_ack")
        retried = Inbox(recovered, SchemaRegistry.from_directory(ROOT / "contracts"))
        first = retried.submit(context, "event-process-crash", payload(), deadline()).result(
            timeout=5
        )
        second = retried.submit(context, "event-process-crash", payload(), deadline()).result(
            timeout=5
        )
        assert first == second
        for table in ["tasks", "inbox", "events", "outbox", "budgets"]:
            count = recovered.read(
                lambda db, name=table: db.execute("SELECT count(*) FROM " + name).fetchone()[0]
            )
            assert count == 1
