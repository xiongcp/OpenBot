"""Deterministic M0 doubles. These do not qualify real models or OS isolation."""

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from openbot.domain.providers import ModelRequest, ModelResponse, ToolCall


@dataclass
class FakeClock:
    utc_ms: int = 1_000_000
    monotonic_ms: int = 0
    boot_id: str = "boot-fixed-seed-7"

    def advance(self, milliseconds: int) -> None:
        self.utc_ms += milliseconds
        self.monotonic_ms += milliseconds


class FakeProvider:
    def __init__(self, spelling="compact"):
        self.spelling = spelling
        self.closed = False
        self.calls = 0

    def capabilities(self):
        return frozenset({"function_proposals"})

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if self.closed or request.reserved_cost_units < 1:
            raise ValueError("Provider closed or budget missing")
        self.calls += 1
        from openbot.boundaries import ModelCallDto
        from openbot.contracts import CanonicalDocument

        dto = ModelCallDto.model_validate_json(
            '{"tool_name":"test.marker","args":{"marker":"ok"}}'
            if self.spelling == "compact"
            else '{ "args": { "marker": "ok" }, "tool_name": "test.marker" }'
        )
        call = ToolCall("call_demo1", dto.tool_name, CanonicalDocument.create(dto.args).canonical)
        return ModelResponse((call,), 1, 1, False)

    async def cancel(self, request_id):
        self.closed = True

    async def close(self):
        self.closed = True


class FakeExecutor:
    """A marker ledger models a remote receipt, separate from control-plane DB."""

    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "worker.sqlite"
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS markers(dispatch TEXT PRIMARY KEY, digest TEXT)")

    def execute(self, dispatch_id: str, call: ToolCall) -> str:
        digest = hashlib.sha256(call.arguments).hexdigest()
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT digest FROM markers WHERE dispatch=?", (dispatch_id,)
            ).fetchone()
            if row and row[0] != digest:
                raise ValueError("Dispatch binding changed")
            db.execute("INSERT OR IGNORE INTO markers VALUES(?,?)", (dispatch_id, digest))
        return "marker:" + dispatch_id + ":" + digest

    @property
    def effects(self):
        with sqlite3.connect(self.path) as db:
            return db.execute("SELECT count(*) FROM markers").fetchone()[0]

    def verify(self, dispatch_id: str, receipt: str) -> bool:
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT digest FROM markers WHERE dispatch=?", (dispatch_id,)
            ).fetchone()
        return row is not None and receipt == "marker:" + dispatch_id + ":" + row[0]


@dataclass
class FakeSupervisor:
    old_epoch_isolated: bool = False


class FakeChannel:
    scope = "fake:tenant:app"

    def event(self):
        return {"event_id": "evt_seed7", "text": "write a synthetic marker"}


class FakeOutbox:
    def __init__(self):
        self.delivered = []

    def deliver(self, key, payload):
        if key not in [k for k, _ in self.delivered]:
            self.delivered.append((key, payload))


class CrashInjected(RuntimeError):
    pass


def crash_at(actual, requested):
    if actual == requested:
        raise CrashInjected(actual)
