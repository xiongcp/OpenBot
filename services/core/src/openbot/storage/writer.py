"""One bounded writer owns whole transactions; cancellation of a waiter is not rollback."""

import sqlite3
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from threading import Condition, Event, Thread, get_ident
from types import TracebackType

from openbot.storage.migrate import connect


class StorageBusy(RuntimeError):
    pass


class StorageDeadlineExceeded(TimeoutError):
    pass


class StorageUnavailable(RuntimeError):
    pass


class RequestConflict(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LookupResult:
    payload_hash: str
    result: bytes


@dataclass(frozen=True, slots=True)
class WriterCommand:
    request_id: str
    payload_hash: str
    lane: str
    deadline_monotonic_ms: int
    apply: Callable[[sqlite3.Connection], bytes]
    lookup: Callable[[sqlite3.Connection], LookupResult | None]


class Writer:
    def __init__(self, path: Path, *, quotas: dict[str, int] | None = None):
        self._path = path
        self._quotas = dict(
            quotas
            if quotas is not None
            else {
                "normal": 32,
                "inbound": 8,
                "approval": 8,
                "cancel": 8,
                "result": 8,
            }
        )
        if not self._quotas or any(type(v) is not int or v < 1 for v in self._quotas.values()):
            raise ValueError("Writer quotas must be positive integers")
        self._lanes = tuple(
            k for k in ("cancel", "approval", "result", "inbound", "normal") if k in self._quotas
        )
        if len(self._lanes) != len(self._quotas):
            raise ValueError("Unknown writer command lane")
        self._queues: dict[str, deque[tuple[WriterCommand, Future[bytes]]]] = {
            key: deque() for key in self._lanes
        }
        self._condition = Condition()
        self._ready = Event()
        self._closing = False
        self._failure: BaseException | None = None
        self._cache: OrderedDict[str, tuple[str, Future[bytes]]] = OrderedDict()
        self._next_lane = 0
        self._thread = Thread(target=self._run, name="openbot-sqlite-writer", daemon=True)
        self._thread.start()
        if not self._ready.wait(5) or self._failure is not None:
            raise StorageUnavailable("Writer failed to initialize") from self._failure

    def submit(self, command: WriterCommand) -> Future[bytes]:
        if get_ident() == self._thread.ident:
            raise StorageUnavailable("Nested writer command refused")
        with self._condition:
            if self._closing or self._failure:
                raise StorageUnavailable("Writer is not accepting commands")
            if (
                command.lane not in self._queues
                or not command.request_id
                or not command.payload_hash
            ):
                raise ValueError("Invalid writer command")
            previous = self._cache.get(command.request_id)
            if previous:
                if previous[0] != command.payload_hash:
                    raise RequestConflict("Same request identifier with changed payload")
                if not previous[1].done():
                    return previous[1]
            queue = self._queues[command.lane]
            if len(queue) >= self._quotas[command.lane]:
                raise StorageBusy("Writer lane is full")
            future: Future[bytes] = Future()
            # This handle represents accepted durable work, not the caller's wait.
            future.set_running_or_notify_cancel()
            queue.append((command, future))
            self._cache[command.request_id] = command.payload_hash, future
            if len(self._cache) > 256:
                for key, (_, old) in list(self._cache.items()):
                    if old.done():
                        del self._cache[key]
                        break
            self._condition.notify()
            return future

    @staticmethod
    def _record(command: WriterCommand, record: LookupResult | None) -> bytes | None:
        if record is None:
            return None
        if record.payload_hash != command.payload_hash:
            raise RequestConflict("Persisted request payload changed")
        if type(record.result) is not bytes:
            raise StorageUnavailable("Persisted result must be immutable bytes")
        return record.result

    def lookup(self, command: WriterCommand) -> bytes | None:
        return self.read(lambda db: self._record(command, command.lookup(db)))

    def read[T](self, query: Callable[[sqlite3.Connection], T]) -> T:
        db = connect(self._path, readonly=True)
        try:
            return query(db)
        finally:
            db.close()

    def _take(self) -> tuple[WriterCommand, Future[bytes]] | None:
        with self._condition:
            while not any(self._queues.values()) and not self._closing:
                self._condition.wait()
            for offset in range(len(self._lanes)):
                index = (self._next_lane + offset) % len(self._lanes)
                queue = self._queues[self._lanes[index]]
                if queue:
                    self._next_lane = (index + 1) % len(self._lanes)
                    return queue.popleft()
            return None

    @staticmethod
    def _remaining(command: WriterCommand) -> int:
        return int(command.deadline_monotonic_ms - time.monotonic() * 1000)

    def _execute(self, db: sqlite3.Connection, command: WriterCommand) -> bytes:
        remaining = self._remaining(command)
        if remaining <= 0:
            raise StorageDeadlineExceeded("Writer queue deadline exceeded")
        db.execute(f"PRAGMA busy_timeout={min(250, remaining):d}")
        db.set_progress_handler(lambda: int(self._remaining(command) <= 0), 1000)
        committing = False
        try:
            db.execute("BEGIN IMMEDIATE")
            denied = {
                sqlite3.SQLITE_TRANSACTION,
                sqlite3.SQLITE_SAVEPOINT,
                sqlite3.SQLITE_PRAGMA,
                sqlite3.SQLITE_ATTACH,
                sqlite3.SQLITE_DETACH,
            }
            db.set_authorizer(
                lambda action, *args: sqlite3.SQLITE_DENY if action in denied else sqlite3.SQLITE_OK
            )
            result = self._record(command, command.lookup(db))
            if result is None:
                result = command.apply(db)
            if type(result) is not bytes or len(result) > 1_048_576:
                raise ValueError("Writer result must be bounded immutable bytes")
            if self._remaining(command) <= 0:
                raise StorageDeadlineExceeded("Writer execution deadline exceeded")
            db.set_authorizer(None)
            committing = True
            db.execute("COMMIT")
            return result
        except BaseException as exc:
            if committing:
                self._failure = exc
            db.set_progress_handler(None, 0)
            db.set_authorizer(None)
            if db.in_transaction:
                try:
                    db.execute("ROLLBACK")
                except sqlite3.Error as cleanup_error:
                    self._failure = cleanup_error
                    raise StorageUnavailable(
                        "Storage cleanup failed; query the stable request ID"
                    ) from exc
            if committing:
                raise StorageUnavailable("Commit failed; query the stable request ID") from exc
            if isinstance(exc, sqlite3.OperationalError):
                if self._remaining(command) <= 0:
                    raise StorageDeadlineExceeded("SQLite deadline exhausted") from exc
                if getattr(exc, "sqlite_errorcode", None) in {
                    sqlite3.SQLITE_BUSY,
                    sqlite3.SQLITE_LOCKED,
                }:
                    raise StorageBusy("SQLite lock deadline exhausted") from exc
                self._failure = exc
            raise
        finally:
            db.set_progress_handler(None, 0)
            db.set_authorizer(None)

    def _run(self) -> None:
        db = None
        try:
            db = connect(self._path)
            self._ready.set()
            while (item := self._take()) is not None:
                command, future = item
                try:
                    if self._failure:
                        raise StorageUnavailable("Writer failed; no new dispatch permitted")
                    result = self._execute(db, command)
                except BaseException as exc:
                    future.set_exception(exc)
                    if not isinstance(exc, Exception):
                        raise
                else:
                    future.set_result(result)
        except BaseException as exc:
            self._failure = exc
        finally:
            if db is not None:
                db.close()
            self._ready.set()
            with self._condition:
                for queue in self._queues.values():
                    while queue:
                        _, future = queue.popleft()
                        future.set_exception(StorageUnavailable("Writer stopped before commit"))

    def close(self) -> None:
        if get_ident() == self._thread.ident:
            raise StorageUnavailable("Writer cannot join itself")
        with self._condition:
            self._closing = True
            self._condition.notify_all()
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            raise StorageUnavailable("Writer has not drained; commit outcome must be queried")

    def __enter__(self) -> "Writer":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
