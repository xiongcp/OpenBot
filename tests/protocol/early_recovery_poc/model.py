"""OB-091 test-only protocol model. No production tables, API or OS sandbox."""

import hashlib
import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

from openbot.contracts import CanonicalDocument, canonicalize
from openbot.domain.providers import ToolCall

from tests.fakes.ports import FakeChannel, FakeClock, FakeExecutor, FakeOutbox, crash_at

POINTS = (
    "before_claim",
    "claim_before_commit",
    "claim_after_commit",
    "dispatch_before_commit",
    "dispatch_after_commit",
    "effect_after_success",
    "result_before_commit",
    "result_after_commit",
)


class ProtocolPoc:
    def __init__(self, directory: Path, *, hard_exit=False, clock=None):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        existing = (directory / "control.sqlite").exists()
        self.clock = clock if clock is not None else FakeClock()
        self.clock_proven = not existing or clock is not None
        self.execution_allowed = not existing
        self.worker = FakeExecutor(directory / "external")
        self.outbox = FakeOutbox()
        self.hard_exit = hard_exit
        self.db = sqlite3.connect(directory / "control.sqlite", isolation_level=None)
        assert self.db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        assert self.db.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert self.db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS task(id TEXT PRIMARY KEY,state TEXT,cancel INTEGER DEFAULT 0);
          CREATE TABLE IF NOT EXISTS inbox(scope TEXT,event TEXT,digest TEXT,task TEXT,
            PRIMARY KEY(scope,event));
          CREATE TABLE IF NOT EXISTS context(k TEXT PRIMARY KEY,v INTEGER);
          INSERT OR IGNORE INTO context VALUES
            ('policy',1),('identity',1),('generation',1),('epoch',1);
          CREATE TABLE IF NOT EXISTS operation(id TEXT PRIMARY KEY,task TEXT REFERENCES task(id),
            state TEXT,proposal BLOB,binding TEXT,provider_key TEXT,resource TEXT);
          CREATE TABLE IF NOT EXISTS approval(operation TEXT PRIMARY KEY REFERENCES operation(id),
            state TEXT CHECK(state IN ('PENDING','APPROVED','CONSUMED')),nonce TEXT);
          CREATE TABLE IF NOT EXISTS attempt(operation TEXT REFERENCES operation(id),number INTEGER,
            dispatch TEXT UNIQUE,epoch INTEGER,state TEXT,PRIMARY KEY(operation,number));
          CREATE TABLE IF NOT EXISTS quarantine(resource TEXT PRIMARY KEY,operation TEXT);
          CREATE TABLE IF NOT EXISTS event(seq INTEGER PRIMARY KEY,event_type TEXT,operation TEXT);
          CREATE TABLE IF NOT EXISTS outbox(key TEXT PRIMARY KEY,payload TEXT);
          CREATE TRIGGER IF NOT EXISTS consumed_terminal BEFORE UPDATE ON approval
            WHEN OLD.state='CONSUMED' AND NEW.state<>'CONSUMED'
            BEGIN SELECT RAISE(ABORT,'CONSUMED is terminal'); END;
          CREATE TRIGGER IF NOT EXISTS consumed_replace BEFORE INSERT ON approval
            WHEN EXISTS(SELECT 1 FROM approval WHERE operation=NEW.operation AND state='CONSUMED')
            BEGIN SELECT RAISE(ABORT,'CONSUMED cannot be replaced'); END;
          CREATE TRIGGER IF NOT EXISTS approval_no_delete BEFORE DELETE ON approval
            BEGIN SELECT RAISE(ABORT,'authorization history cannot be deleted'); END;
          CREATE TRIGGER IF NOT EXISTS approval_binding
            BEFORE UPDATE OF operation,nonce ON approval
            BEGIN SELECT RAISE(ABORT,'immutable approval binding'); END;
          CREATE TRIGGER IF NOT EXISTS immutable_proposal
            BEFORE UPDATE OF proposal,binding,provider_key ON operation
            BEGIN SELECT RAISE(ABORT,'immutable authority'); END;
        """)
        self.epoch = self.value("epoch")
        self.call = ToolCall("call_seed7", "test.marker", b'{"marker":"ok"}')

    def fault(self, actual, requested):
        if self.hard_exit and actual == requested:
            os._exit(78)
        crash_at(actual, requested)

    @contextmanager
    def transaction(self, name, crash=None):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.fault(name + "_before_commit", crash)
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        self.fault(name + "_after_commit", crash)

    def value(self, key):
        return self.db.execute("SELECT v FROM context WHERE k=?", (key,)).fetchone()[0]

    def audit(self, name):
        cursor = self.db.execute(
            "INSERT INTO event(event_type,operation) VALUES(?,'op_seed7')", (name,)
        )
        self.db.execute("INSERT INTO outbox VALUES(?,?)", (str(cursor.lastrowid), name))

    def receive(self):
        channel = FakeChannel()
        event = channel.event()
        digest = CanonicalDocument.create(event).digest
        with self.transaction("receive"):
            old = self.db.execute(
                "SELECT digest,task FROM inbox WHERE scope=? AND event=?",
                (channel.scope, event["event_id"]),
            ).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError("Idempotency payload conflict")
                return old[1]
            self.db.execute("INSERT INTO task VALUES('tsk_seed7','RUNNING',0)")
            self.db.execute(
                "INSERT INTO inbox VALUES(?,?,?,'tsk_seed7')",
                (channel.scope, event["event_id"], digest),
            )
            self.audit("TASK_QUEUED")
        return "tsk_seed7"

    def propose(self, operation="op_seed7", task="tsk_seed7"):
        with self.transaction("propose"):
            if self.db.execute(
                "SELECT 1 FROM quarantine WHERE resource='workspace:seed7'"
            ).fetchone():
                raise ValueError("Resource quarantined, regardless of task/operation IDs")
            proposal = {
                "operation_id": operation,
                "task_id": task,
                "principal_id": "pri_seed7",
                "args": {"marker": "ok"},
                "tool_name": "test.marker",
                "policy": self.value("policy"),
                "identity": self.value("identity"),
                "generation": self.value("generation"),
                "expires": self.clock.utc_ms + 10000,
                "retry_class": "IDEMPOTENT_WRITE",
            }
            doc = CanonicalDocument.create(proposal)
            self.db.execute(
                "INSERT INTO operation VALUES(?,?,'AWAITING_APPROVAL',?,?,?,?)",
                (
                    operation,
                    task,
                    doc.canonical,
                    doc.digest,
                    "provider:" + operation,
                    "workspace:seed7",
                ),
            )
            self.db.execute(
                "INSERT INTO approval VALUES(?,'PENDING',?)",
                (operation, hashlib.sha256(b"synthetic-nonce-seed7").hexdigest()),
            )
            self.db.execute("UPDATE task SET state='WAITING_APPROVAL' WHERE id=?", (task,))
            self.audit("APPROVAL_REQUESTED")

    def approve(self, actor="pri_seed7", nonce=b"synthetic-nonce-seed7"):
        with self.transaction("approve"):
            row = self.db.execute(
                "SELECT state,nonce FROM approval WHERE operation='op_seed7'"
            ).fetchone()
            if actor != "pri_seed7" or hashlib.sha256(nonce).hexdigest() != row[1]:
                raise ValueError("Approval principal/nonce mismatch")
            if row[0] == "APPROVED":
                return
            if row[0] != "PENDING":
                raise ValueError("Approval terminal")
            self.check()
            self.db.execute("UPDATE approval SET state='APPROVED' WHERE operation='op_seed7'")
            self.db.execute("UPDATE operation SET state='READY' WHERE id='op_seed7'")
            self.db.execute("UPDATE task SET state='QUEUED' WHERE id='tsk_seed7'")
            self.audit("APPROVAL_DECIDED")

    def check(self):
        row = self.db.execute(
            "SELECT proposal,binding,resource FROM operation WHERE id='op_seed7'"
        ).fetchone()
        doc = CanonicalDocument(row[0])
        if doc.digest != row[1]:
            raise ValueError("Binding mismatch")
        proposal = doc.value()
        if (
            proposal["tool_name"] != self.call.tool_name
            or canonicalize(proposal["args"]) != self.call.arguments
        ):
            raise ValueError("Actual call differs from approved canonical proposal")
        if (
            self.db.execute("SELECT cancel FROM task WHERE id='tsk_seed7'").fetchone()[0]
            or self.clock.utc_ms >= proposal["expires"]
            or self.epoch != self.value("epoch")
            or any(proposal[k] != self.value(k) for k in ["policy", "identity", "generation"])
            or self.db.execute("SELECT 1 FROM quarantine WHERE resource=?", (row[2],)).fetchone()
        ):
            raise ValueError("Authorization precondition changed")

    def claim(self, crash=None):
        if not self.execution_allowed or not self.clock_proven:
            raise ValueError("Runtime isolation and current time evidence required")
        with self.transaction("claim", crash):
            self.check()
            state = self.db.execute("SELECT state FROM operation WHERE id='op_seed7'").fetchone()[0]
            if state != "READY":
                raise ValueError("Operation not READY")
            grant = self.db.execute(
                "SELECT state FROM approval WHERE operation='op_seed7'"
            ).fetchone()[0]
            if grant not in {"APPROVED", "CONSUMED"}:
                raise ValueError("No grant")
            self.db.execute("UPDATE approval SET state='CONSUMED' WHERE operation='op_seed7'")
            number = self.db.execute("SELECT coalesce(max(number),0)+1 FROM attempt").fetchone()[0]
            dispatch = "dsp_seed7_" + str(number)
            self.db.execute(
                "INSERT INTO attempt VALUES('op_seed7',?,?,?,'CLAIMED')",
                (number, dispatch, self.epoch),
            )
            self.db.execute("UPDATE operation SET state='CLAIMED' WHERE id='op_seed7'")
            self.audit("OPERATION_CLAIMED")
        return dispatch

    def dispatch(self, crash=None):
        if not self.execution_allowed or not self.clock_proven:
            raise ValueError("Runtime isolation and current time evidence required")
        with self.transaction("dispatch", crash):
            self.check()
            state = self.db.execute("SELECT state FROM operation WHERE id='op_seed7'").fetchone()[0]
            attempt = self.db.execute(
                "SELECT dispatch,epoch FROM attempt ORDER BY number DESC LIMIT 1"
            ).fetchone()
            if state != "CLAIMED" or attempt[1] != self.epoch:
                raise ValueError("No current claimed attempt")
            self.db.execute(
                "UPDATE attempt SET state='DISPATCHING' WHERE dispatch=?", (attempt[0],)
            )
            self.db.execute("UPDATE operation SET state='DISPATCHING' WHERE id='op_seed7'")
            self.audit("OPERATION_DISPATCHING")
        return attempt[0]

    def finish(self, receipt, crash=None, *, reconciled=False):
        dispatch = self.db.execute(
            "SELECT dispatch FROM attempt ORDER BY number DESC LIMIT 1"
        ).fetchone()[0]
        proposal = CanonicalDocument(
            self.db.execute("SELECT proposal FROM operation WHERE id='op_seed7'").fetchone()[0]
        ).value()
        expected = (
            "marker:" + dispatch + ":" + hashlib.sha256(canonicalize(proposal["args"])).hexdigest()
        )
        if receipt != expected or not self.worker.verify(dispatch, receipt):
            raise ValueError("Verified worker evidence required")
        with self.transaction("result", crash):
            attempt_epoch = self.db.execute(
                "SELECT epoch FROM attempt WHERE dispatch=?", (dispatch,)
            ).fetchone()[0]
            if not self.execution_allowed or (
                not reconciled
                and (attempt_epoch != self.epoch or self.epoch != self.value("epoch"))
            ):
                raise ValueError("Stale runtime result requires reconciliation")
            self.db.execute("UPDATE attempt SET state='SUCCEEDED' WHERE dispatch=?", (dispatch,))
            self.db.execute("UPDATE operation SET state='SUCCEEDED' WHERE id='op_seed7'")
            self.db.execute("UPDATE task SET state='SUCCEEDED' WHERE id='tsk_seed7'")
            self.db.execute("DELETE FROM quarantine WHERE operation='op_seed7'")
            self.audit("OPERATION_FINISHED")

    def run(self, crash=None):
        self.fault("before_claim", crash)
        self.claim(crash)
        dispatch = self.dispatch(crash)
        proposal = CanonicalDocument(
            self.db.execute("SELECT proposal FROM operation WHERE id='op_seed7'").fetchone()[0]
        ).value()
        bound_call = ToolCall(
            self.call.call_id, proposal["tool_name"], canonicalize(proposal["args"])
        )
        receipt = self.worker.execute(dispatch, bound_call)
        self.fault("effect_after_success", crash)
        self.finish(receipt, crash)
        for key, payload in self.db.execute(
            "SELECT key,payload FROM outbox ORDER BY cast(key AS INTEGER)"
        ):
            self.outbox.deliver(key, payload)

    def recover(self, old_isolated):
        self.execution_allowed = False
        with self.transaction("recover"):
            state = self.db.execute("SELECT state FROM operation WHERE id='op_seed7'").fetchone()[0]
            if state == "DISPATCHING":
                self.db.execute("UPDATE operation SET state='UNKNOWN' WHERE id='op_seed7'")
                self.db.execute("UPDATE task SET state='RECONCILING' WHERE id='tsk_seed7'")
                self.db.execute(
                    "INSERT OR IGNORE INTO quarantine VALUES('workspace:seed7','op_seed7')"
                )
                self.audit("OUTCOME_UNKNOWN")
            if old_isolated:
                if state in {"CLAIMED", "READY"} and not self.clock_proven:
                    raise ValueError("Cannot prove old grant TTL after restart")
                self.db.execute("UPDATE context SET v=v+1 WHERE k='epoch'")
                self.epoch = self.value("epoch")
                if state == "CLAIMED":
                    self.check()
                    self.db.execute("UPDATE attempt SET state='ABORTED' WHERE state='CLAIMED'")
                    self.db.execute("UPDATE operation SET state='READY' WHERE id='op_seed7'")
                    self.audit("SAFE_RETRY_READY")
        self.execution_allowed = old_isolated

    def reconcile(self, receipt):
        if self.snapshot()["operation"] != "UNKNOWN":
            raise ValueError("Not reconciling")
        self.finish(receipt, reconciled=True)

    def change(self, kind):
        if kind == "cancel":
            with self.transaction("cancel"):
                self.db.execute("UPDATE task SET cancel=cancel+1 WHERE id='tsk_seed7'")
                self.audit("CANCEL_REQUESTED")
        elif kind == "expiry":
            self.clock.advance(10000)
        else:
            with self.transaction("change"):
                self.db.execute("UPDATE context SET v=v+1 WHERE k=?", (kind,))

    def snapshot(self):
        def one(sql):
            row = self.db.execute(sql).fetchone()
            return row[0] if row else None

        return {
            "task": one("SELECT state FROM task WHERE id='tsk_seed7'"),
            "operation": one("SELECT state FROM operation WHERE id='op_seed7'"),
            "approval": one("SELECT state FROM approval WHERE operation='op_seed7'"),
            "provider_key": one("SELECT provider_key FROM operation WHERE id='op_seed7'"),
            "attempts": list(
                self.db.execute("SELECT number,dispatch,epoch,state FROM attempt ORDER BY number")
            ),
            "quarantine": [r[0] for r in self.db.execute("SELECT resource FROM quarantine")],
            "effects": self.worker.effects,
            "events": list(self.db.execute("SELECT seq,event_type FROM event ORDER BY seq")),
            "outbox": list(
                self.db.execute("SELECT key,payload FROM outbox ORDER BY cast(key AS INTEGER)")
            ),
        }

    def close(self):
        self.db.close()


if __name__ == "__main__":
    model = ProtocolPoc(Path(sys.argv[1]), hard_exit=True)
    model.receive()
    model.propose()
    model.approve()
    model.run(crash=sys.argv[2])
