import hashlib
import sqlite3
import time
from threading import Event, get_ident

import pytest
from openbot.storage.migrate import Migration, load_migrations, migrate
from openbot.storage.writer import (
    LookupResult,
    RequestConflict,
    StorageBusy,
    StorageDeadlineExceeded,
    StorageUnavailable,
    Writer,
    WriterCommand,
)

from tests.integration.storage.test_migrations import ROOT


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "writer.sqlite"
    migrate(
        path,
        load_migrations(ROOT / "db/migrations")
        + [
            Migration(
                3,
                "writer_test_only",
                "CREATE TABLE test_results(request_id TEXT PRIMARY KEY,"
                "payload_hash TEXT,result BLOB) STRICT;",
            )
        ],
    )
    return path


def command(request_id, *, lane="normal", gate=None, fail=False, order=None, deadline=None):
    payload_hash = hashlib.sha256(request_id.encode()).hexdigest()

    def apply(db):
        if gate:
            gate[0].set()
            assert gate[1].wait(5)
        db.execute("INSERT INTO test_results VALUES(?,?,?)", (request_id, payload_hash, b'"done"'))
        if order is not None:
            order.append((request_id, get_ident()))
        if fail:
            raise ValueError("synthetic rollback")
        return b'"done"'

    def lookup(db):
        row = db.execute(
            "SELECT payload_hash,result FROM test_results WHERE request_id=?", (request_id,)
        ).fetchone()
        return LookupResult(*row) if row else None

    return WriterCommand(
        request_id,
        payload_hash,
        lane,
        int(time.monotonic() * 1000) + 5000 if deadline is None else deadline,
        apply,
        lookup,
    )


def test_actual_commit_is_queryable_after_caller_stops_waiting_and_after_restart(database):
    writer = Writer(database)
    gate = Event(), Event()
    cmd = command("req_commit", gate=gate)
    try:
        future = writer.submit(cmd)
        assert gate[0].wait(5)
        with pytest.raises(TimeoutError):
            future.result(timeout=0.001)
        assert not future.cancel()
        assert not future.done()
        gate[1].set()
        assert future.result(timeout=5) == b'"done"'
        assert writer.lookup(cmd) == b'"done"'
    finally:
        gate[1].set()
        writer.close()
    with Writer(database) as reopened:
        assert reopened.lookup(cmd) == b'"done"'
        assert reopened.submit(cmd).result(timeout=5) == b'"done"'


def test_normal_queue_full_does_not_drop_reserved_cancel_and_is_fair(database):
    gate = Event(), Event()
    order = []
    with Writer(database, quotas={"normal": 1, "cancel": 3}) as writer:
        running = writer.submit(command("req_first", gate=gate, order=order))
        assert gate[0].wait(5)
        normal = writer.submit(command("req_normal", order=order))
        with pytest.raises(StorageBusy):
            writer.submit(command("req_overflow"))
        controls = [
            writer.submit(command(f"req_cancel{i}", lane="cancel", order=order)) for i in range(3)
        ]
        gate[1].set()
        for future in [running, normal, *controls]:
            assert future.result(timeout=5) == b'"done"'
    ids = [r[0] for r in order]
    assert ids.index("req_normal") < ids.index("req_cancel2")
    assert len({r[1] for r in order}) == 1


def test_expired_queued_command_has_no_write(database):
    gate = Event(), Event()
    with Writer(database) as writer:
        first = writer.submit(command("req_blocker", gate=gate))
        assert gate[0].wait(5)
        expired = command("req_expired", deadline=int(time.monotonic() * 1000) - 1)
        future = writer.submit(expired)
        gate[1].set()
        first.result(timeout=5)
        with pytest.raises(StorageDeadlineExceeded):
            future.result(timeout=5)
        assert writer.lookup(expired) is None


def test_transaction_exception_rolls_back_and_next_command_can_commit(database):
    with Writer(database) as writer:
        bad = command("req_bad", fail=True)
        with pytest.raises(ValueError):
            writer.submit(bad).result(timeout=5)
        assert writer.lookup(bad) is None
        good = command("req_good")
        assert writer.submit(good).result(timeout=5) == b'"done"'
        assert writer.submit(good).result(timeout=5) == b'"done"'
        changed = WriterCommand(
            good.request_id,
            "a" * 64,
            good.lane,
            good.deadline_monotonic_ms,
            good.apply,
            good.lookup,
        )
        with pytest.raises(RequestConflict):
            writer.submit(changed)


def test_fatal_callback_completes_current_and_pending_handles(database):
    gate = Event(), Event()
    writer = Writer(database)
    original = command("req_fatal", gate=gate)

    def fatal(db):
        original.apply(db)
        raise KeyboardInterrupt("synthetic fatal writer exit")

    cmd = WriterCommand(
        original.request_id,
        original.payload_hash,
        original.lane,
        original.deadline_monotonic_ms,
        fatal,
        original.lookup,
    )
    future = writer.submit(cmd)
    assert gate[0].wait(5)
    pending = writer.submit(command("req_pending"))
    gate[1].set()
    try:
        with pytest.raises(KeyboardInterrupt):
            future.result(timeout=5)
        with pytest.raises(RuntimeError):
            pending.result(timeout=5)
    finally:
        writer.close()
    assert writer.lookup(original) is None


def test_commit_and_cleanup_failure_stop_accepting_new_commands(database, monkeypatch):
    import openbot.storage.writer as writer_module

    original_connect = writer_module.connect

    class BrokenCommit:
        def __init__(self, db):
            self.db = db

        def __getattr__(self, name):
            return getattr(self.db, name)

        def execute(self, sql, *args):
            if sql in {"COMMIT", "ROLLBACK"}:
                raise sqlite3.OperationalError("synthetic storage I/O failure")
            return self.db.execute(sql, *args)

    def failing_connect(path, **kwargs):
        db = original_connect(path, **kwargs)
        return db if kwargs.get("readonly") else BrokenCommit(db)

    monkeypatch.setattr(writer_module, "connect", failing_connect)
    with Writer(database) as writer:
        with pytest.raises((StorageUnavailable, sqlite3.OperationalError)):
            writer.submit(command("req_commit_io")).result(timeout=5)
        with pytest.raises(StorageUnavailable):
            writer.submit(command("req_must_not_start"))
