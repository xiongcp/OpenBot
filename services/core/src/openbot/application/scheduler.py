"""Single-instance profile OS lock handoff, runtime_epoch activation, and single-task scheduling."""

import hmac
import os
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if os.name == "posix":
    import fcntl

from openbot.application.resources import ResourceBusyError, ResourceCoordinator
from openbot.application.state_machine import TaskStateService
from openbot.contracts import strict_json
from openbot.storage.inbox import InboundContext, authorize
from openbot.storage.writer import Writer


@dataclass(frozen=True, slots=True)
class DaemonHandoffTicket:
    profile_id: str
    supervisor_pid: int
    runtime_epoch: str
    boot_id: str
    handoff_token: str


class SingleInstanceSupervisorLock:
    """Exclusive non-blocking profile lock owned by supervisor, with child handoff verification."""

    def __init__(self, lock_path: Path, *, profile_id: str) -> None:
        if lock_path.is_symlink():
            raise PermissionError("Profile lock path must not be a symlink")
        self._path = lock_path
        self._profile_id = profile_id
        self._fd: int | None = None
        self._active_ticket: DaemonHandoffTicket | None = None

    def acquire_and_mint_handoff(self, *, runtime_epoch: str, boot_id: str) -> DaemonHandoffTicket:
        if self._fd is not None:
            raise PermissionError("Supervisor instance already holds profile lock")
        if os.name != "posix":
            raise PermissionError("CAPABILITY_UNAVAILABLE: POSIX flock required")
        fd = os.open(self._path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise PermissionError(
                f"PROFILE_LOCK_HELD: profile '{self._profile_id}' is already locked"
            ) from exc
        self._fd = fd
        ticket = DaemonHandoffTicket(
            profile_id=self._profile_id,
            supervisor_pid=os.getpid(),
            runtime_epoch=runtime_epoch,
            boot_id=boot_id,
            handoff_token="hnd_" + secrets.token_hex(24),
        )
        self._active_ticket = ticket
        return ticket

    def verify_child_daemon_handoff(
        self, ticket: DaemonHandoffTicket, *, provided_token: str | None = None
    ) -> bool:
        """Child daemon verifies supervisor ownership without re-locking the profile lock."""
        if self._fd is None or self._active_ticket is None:
            raise PermissionError("Supervisor does not hold the active profile lock")
        tok = ticket.handoff_token if provided_token is None else provided_token
        if ticket.profile_id != self._profile_id or not hmac.compare_digest(
            tok, self._active_ticket.handoff_token
        ):
            raise PermissionError("Invalid supervisor-to-daemon handoff token")
        return True

    def release(self) -> None:
        if self._fd is not None:
            try:
                if os.name == "posix":
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = None
                self._active_ticket = None


class ProfileSchedulerService:
    """Single-active-task scheduler enforcing supervisor handoff, epoch isolation, and fences."""

    def __init__(
        self,
        writer: Writer,
        tasks: TaskStateService,
        resources: ResourceCoordinator,
    ) -> None:
        self._writer = writer
        self._tasks = tasks
        self._resources = resources

    def schedule_next_task(
        self,
        context: InboundContext,
        *,
        handoff_ticket: DaemonHandoffTicket,
        old_workers_isolated: bool,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> dict[str, Any]:
        if handoff_ticket.profile_id != context.profile_id:
            raise PermissionError("Handoff ticket profile_id mismatch")
        if not old_workers_isolated:
            raise PermissionError(
                "Cannot schedule new execution while old_workers_isolated is False"
            )
        try:
            raw = self._writer.submit(
                self._resources.claim_next_task(
                    context,
                    handoff_ticket.runtime_epoch,
                    request_id,
                    deadline_monotonic_ms,
                )
            ).result(timeout=5)
        except ResourceBusyError:
            return {
                "claimed_task_id": None,
                "runtime_epoch": handoff_ticket.runtime_epoch,
            }
        parsed = dict(strict_json(raw))
        return {
            "claimed_task_id": str(parsed["task_id"]),
            "state": str(parsed["state"]),
            "version": int(parsed["version"]),
            "runtime_epoch": handoff_ticket.runtime_epoch,
        }

    def verify_worker_submission(
        self,
        context: InboundContext,
        *,
        worker_runtime_epoch: str,
        worker_fencing_token: int,
    ) -> bool:
        def query(db: sqlite3.Connection) -> bool:
            authorize(db, context)
            row = db.execute(
                "SELECT active_runtime_epoch,last_fencing_token "
                "FROM profile_config WHERE singleton=1"
            ).fetchone()
            if not row:
                raise PermissionError("Profile config missing")
            active_epoch, last_fence = str(row[0]), int(row[1])
            if (
                worker_runtime_epoch != active_epoch
                or worker_fencing_token <= 0
                or worker_fencing_token < last_fence
            ):
                raise PermissionError(
                    "Stale runtime_epoch or fencing_token rejected from expired worker"
                )
            return True

        return self._writer.read(query)
