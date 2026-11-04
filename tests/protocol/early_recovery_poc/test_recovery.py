import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

import pytest

from tests.fakes.ports import CrashInjected, FakeClock
from tests.protocol.early_recovery_poc.model import POINTS, ProtocolPoc


@pytest.mark.parametrize("point", POINTS)
def test_crash_matrix_preserves_authority_and_effects(tmp_path, point):
    poc = ProtocolPoc(tmp_path)
    task = poc.receive()
    assert all(poc.receive() == task for _ in range(100))
    poc.propose()
    poc.approve()
    with pytest.raises(CrashInjected):
        poc.run(crash=point)
    before = poc.snapshot()
    poc.close()
    recovered = ProtocolPoc(tmp_path, clock=poc.clock)
    recovered.recover(old_isolated=True)
    after = recovered.snapshot()
    if before["operation"] in {"READY", "CLAIMED"}:
        recovered.run()
        assert recovered.snapshot()["operation"] == "SUCCEEDED"
        assert recovered.worker.effects == 1
        assert recovered.snapshot()["approval"] == "CONSUMED"
    elif before["operation"] == "DISPATCHING":
        assert after["operation"] == "UNKNOWN"
        assert after["task"] == "RECONCILING"
        assert after["quarantine"] == ["workspace:seed7"]
        with pytest.raises(ValueError):
            recovered.run()
        assert recovered.worker.effects == before["effects"]
        with pytest.raises(ValueError):
            recovered.reconcile("success")
    else:
        assert after["operation"] == "SUCCEEDED"
        assert after["effects"] == 1
    recovered.close()


@pytest.mark.parametrize(
    "change", ["cancel", "policy", "identity", "generation", "epoch", "expiry"]
)
def test_second_transaction_rechecks_and_prevents_effect(tmp_path, change):
    poc = ProtocolPoc(tmp_path)
    poc.receive()
    poc.propose()
    poc.approve()
    poc.claim()
    poc.change(change)
    with pytest.raises(ValueError):
        poc.dispatch()
    assert poc.worker.effects == 0
    assert poc.snapshot()["approval"] == "CONSUMED"
    poc.close()


def test_recovery_needs_old_runtime_isolation_and_new_attempt_identity(tmp_path):
    poc = ProtocolPoc(tmp_path)
    poc.receive()
    poc.propose()
    poc.approve()
    first = poc.claim()
    key = poc.snapshot()["provider_key"]
    poc.recover(old_isolated=False)
    with pytest.raises(ValueError):
        poc.claim()
    poc.recover(old_isolated=True)
    second = poc.claim()
    assert first != second
    assert poc.snapshot()["provider_key"] == key
    assert poc.snapshot()["approval"] == "CONSUMED"
    assert len(poc.snapshot()["attempts"]) == 2
    poc.close()


def test_unknown_quarantine_survives_new_operation_and_requires_verified_receipt(tmp_path):
    poc = ProtocolPoc(tmp_path)
    poc.receive()
    poc.propose()
    poc.approve()
    with pytest.raises(CrashInjected):
        poc.run(crash="effect_after_success")
    poc.recover(old_isolated=True)
    with pytest.raises(ValueError):
        poc.propose(operation="op_other1", task="tsk_other1")
    dispatch = poc.snapshot()["attempts"][0][1]
    receipt = poc.worker.execute(dispatch, poc.call)
    assert poc.worker.effects == 1
    poc.reconcile(receipt)
    assert poc.snapshot()["operation"] == "SUCCEEDED"
    assert poc.snapshot()["quarantine"] == []
    poc.close()


def test_consumed_approval_is_terminal_at_database_level(tmp_path):
    poc = ProtocolPoc(tmp_path)
    poc.receive()
    poc.propose()
    poc.approve()
    poc.claim()
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        poc.db.execute("UPDATE approval SET state='APPROVED'")
    poc.close()


@pytest.mark.parametrize(
    "point", ["claim_before_commit", "claim_after_commit", "effect_after_success"]
)
def test_real_process_exit_leaves_recoverable_sqlite(tmp_path, point):
    result = subprocess.run(
        [sys.executable, "-m", "tests.protocol.early_recovery_poc.model", str(tmp_path), point],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 78, result.stderr
    poc = ProtocolPoc(tmp_path, clock=FakeClock())
    poc.recover(old_isolated=True)
    assert poc.snapshot()["operation"] == (
        "UNKNOWN" if point == "effect_after_success" else "READY"
    )
    assert poc.worker.effects == (1 if point == "effect_after_success" else 0)
    poc.close()


def test_caller_stops_waiting_but_approval_commit_is_queryable(tmp_path):
    poc = ProtocolPoc(tmp_path)
    poc.receive()
    poc.propose()
    poc.close()
    started, release = Event(), Event()

    def writer():
        started.set()
        assert release.wait(5)
        model = ProtocolPoc(tmp_path)
        model.approve()
        model.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(writer)
        assert started.wait(5)
        with pytest.raises(TimeoutError):
            future.result(timeout=0.001)
        assert not future.cancel()
        release.set()
        future.result(timeout=5)
    model = ProtocolPoc(tmp_path)
    assert model.snapshot()["approval"] == "APPROVED"
    assert model.snapshot()["operation"] == "READY"
    model.close()


def test_unapproved_actual_arguments_have_zero_effect(tmp_path):
    from openbot.domain.providers import ToolCall

    model = ProtocolPoc(tmp_path)
    model.receive()
    model.propose()
    model.approve()
    model.call = ToolCall("call_changed", "test.marker", b'{"marker":"UNAPPROVED"}')
    with pytest.raises(ValueError):
        model.run()
    assert model.worker.effects == 0
    model.close()


def test_reopened_runtime_cannot_dispatch_without_old_domain_isolation(tmp_path):
    model = ProtocolPoc(tmp_path)
    model.receive()
    model.propose()
    model.approve()
    model.claim()
    model.close()
    model = ProtocolPoc(tmp_path)
    model.recover(old_isolated=False)
    with pytest.raises(ValueError):
        model.dispatch()
    assert model.worker.effects == 0
    model.close()


def test_consumed_approval_cannot_be_replaced_or_deleted(tmp_path):
    import sqlite3

    model = ProtocolPoc(tmp_path)
    model.receive()
    model.propose()
    model.approve()
    model.claim()
    row = model.db.execute("SELECT operation,nonce FROM approval").fetchone()
    for sql, parameters in [
        ("INSERT OR REPLACE INTO approval VALUES(?,'APPROVED',?)", row),
        ("DELETE FROM approval", ()),
    ]:
        with pytest.raises(sqlite3.IntegrityError):
            model.db.execute(sql, parameters)
    assert model.snapshot()["approval"] == "CONSUMED"
    model.close()


def test_stale_epoch_result_needs_explicit_verified_reconciliation(tmp_path):
    model = ProtocolPoc(tmp_path)
    model.receive()
    model.propose()
    model.approve()
    model.claim()
    dispatch = model.dispatch()
    receipt = model.worker.execute(dispatch, model.call)
    model.change("epoch")
    with pytest.raises(ValueError):
        model.finish(receipt)
    model.recover(old_isolated=True)
    assert model.snapshot()["operation"] == "UNKNOWN"
    model.reconcile(receipt)
    assert model.snapshot()["operation"] == "SUCCEEDED"
    model.close()


def test_restart_cannot_turn_expired_grant_into_valid_grant(tmp_path):
    model = ProtocolPoc(tmp_path)
    model.receive()
    model.propose()
    model.approve()
    model.claim()
    model.change("expiry")
    model.close()
    recovered = ProtocolPoc(tmp_path)
    with pytest.raises(ValueError):
        recovered.recover(old_isolated=True)
    assert recovered.worker.effects == 0
    recovered.close()
