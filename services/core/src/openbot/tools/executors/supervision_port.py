"""OS process-tree supervision port, PID reuse protection, and quarantine gating."""

import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class PlatformSupervisionBoundary:
    os_name: str
    primary_primitive: str
    escape_limitation_note: str
    rejected_crates: tuple[str, ...]
    cooperative_eof_or_drop_is_100_percent: Literal[False] = False


PLATFORM_CAPABILITY_BOUNDARIES: dict[str, PlatformSupervisionBoundary] = {
    "Darwin": PlatformSupervisionBoundary(
        os_name="Darwin",
        primary_primitive="POSIX process group (setpgid/killpg) + container ID tracking",
        escape_limitation_note=(
            "A child calling setsid() or double-forking can escape a POSIX process group; "
            "strong containment requires container or OS sandbox isolation."
        ),
        rejected_crates=("command-group",),
    ),
    "Linux": PlatformSupervisionBoundary(
        os_name="Linux",
        primary_primitive="cgroup v2 (cgroup.procs / cgroup.kill) or setpgid + PR_SET_PDEATHSIG",
        escape_limitation_note=(
            "Without delegated cgroup v2 or PID namespace, setsid() can escape process groups; "
            "PR_SET_PDEATHSIG is per-thread and cleared across setuid."
        ),
        rejected_crates=("command-group",),
    ),
    "Windows": PlatformSupervisionBoundary(
        os_name="Windows",
        primary_primitive=(
            "CreateProcessW(CREATE_SUSPENDED) -> AssignProcessToJobObject("
            "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, no BREAKAWAY) -> ResumeThread"
        ),
        escape_limitation_note=(
            "If AssignProcessToJobObject fails, the suspended process must be terminated "
            "before ResumeThread; WSL results never substitute for native Win32 Job proof."
        ),
        rejected_crates=("command-group",),
    ),
}


def validate_windows_job_spawn_order(*, job_assigned: bool) -> tuple[str, ...]:
    """Verify suspended creation -> Job assignment -> resume (or terminate on failure)."""
    if job_assigned:
        return (
            "CreateProcessW(CREATE_SUSPENDED)",
            "AssignProcessToJobObject(KILL_ON_JOB_CLOSE)",
            "ResumeThread",
        )
    return (
        "CreateProcessW(CREATE_SUSPENDED)",
        "AssignProcessToJobObject_FAILED",
        "TerminateProcess_before_ResumeThread",
    )


@dataclass(frozen=True, slots=True)
class ManagedWorkerIdentity:
    worker_id: str
    runtime_epoch: str
    operation_id: str
    attempt_id: str
    pid: int
    pgid: int
    process_start_token: str
    known_descendant_pids: tuple[int, ...] = ()
    container_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkerReclaimReport:
    worker_id: str
    runtime_epoch: str
    graceful_sent: bool
    forced_kill_sent: bool
    residual_pids: tuple[int, ...]
    container_reclaimed: bool
    old_domain_isolated: bool
    quarantine_required: bool
    new_dispatch_allowed: bool


@dataclass(frozen=True, slots=True)
class EpochIsolationProof:
    supervisor_ref: str
    boot_id: str
    old_domain_isolated: bool
    residual_pids: tuple[int, ...]
    unreclaimed_containers: tuple[str, ...]
    supervisor_reachable: bool = True


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform != "win32":
        try:
            waited_pid, _ = os.waitpid(pid, os.WNOHANG)
            if waited_pid == pid:
                return False
        except ChildProcessError:
            pass
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class ProcessSupervisorService:
    """Supervise worker process groups and containers without mistaking UI exit for daemon stop."""

    def __init__(self, *, runtime_epoch: str) -> None:
        self._epoch = runtime_epoch
        self._daemon_running = True
        self._supervisor_reachable = True
        self._workers: dict[str, ManagedWorkerIdentity] = {}
        self._unreclaimable_containers: set[str] = set()
        self._simulated_residual_workers: dict[str, tuple[int, ...]] = {}

    def set_supervisor_reachable(self, reachable: bool) -> None:
        self._supervisor_reachable = reachable

    def set_worker_recovery_fault(
        self,
        worker_id: str,
        *,
        residual_pids: tuple[int, ...] = (),
        container_unreclaimable: bool = False,
    ) -> None:
        if residual_pids:
            self._simulated_residual_workers[worker_id] = residual_pids
        else:
            self._simulated_residual_workers.pop(worker_id, None)
        if container_unreclaimable:
            self._unreclaimable_containers.add(worker_id)
        else:
            self._unreclaimable_containers.discard(worker_id)

    def verify_and_isolate_epoch(
        self,
        *,
        supervisor_ref: str = "sup_2",
        boot_id: str = "boot_2",
        grace_ms: int = 100,
    ) -> EpochIsolationProof:
        if not self._supervisor_reachable:
            return EpochIsolationProof(
                supervisor_ref=supervisor_ref,
                boot_id=boot_id,
                old_domain_isolated=False,
                residual_pids=(),
                unreclaimed_containers=(),
                supervisor_reachable=False,
            )
        residuals: list[int] = []
        bad_containers: list[str] = []
        for wid, ident in list(self._workers.items()):
            sim_res = self._simulated_residual_workers.get(wid, ())
            c_ok = wid not in self._unreclaimable_containers
            rep = self.reclaim_worker(
                wid,
                current_start_token=ident.process_start_token,
                grace_ms=grace_ms,
                simulated_residual_pids=sim_res,
                container_reclaimed=c_ok,
            )
            for pid in rep.residual_pids:
                if pid not in residuals:
                    residuals.append(pid)
            if not rep.container_reclaimed and ident.container_id:
                bad_containers.append(ident.container_id)
            elif not rep.container_reclaimed:
                bad_containers.append(f"container:{wid}")
        isolated = len(residuals) == 0 and len(bad_containers) == 0
        return EpochIsolationProof(
            supervisor_ref=supervisor_ref,
            boot_id=boot_id,
            old_domain_isolated=isolated,
            residual_pids=tuple(residuals),
            unreclaimed_containers=tuple(bad_containers),
            supervisor_reachable=True,
        )

    def register_worker(
        self,
        *,
        worker_id: str,
        operation_id: str,
        attempt_id: str,
        pid: int,
        pgid: int,
        process_start_token: str,
        known_descendant_pids: tuple[int, ...] = (),
        container_id: str | None = None,
    ) -> ManagedWorkerIdentity:
        if not worker_id.strip() or not process_start_token.strip():
            raise ValueError("worker_id and process_start_token required")
        ident = ManagedWorkerIdentity(
            worker_id=worker_id,
            runtime_epoch=self._epoch,
            operation_id=operation_id,
            attempt_id=attempt_id,
            pid=pid,
            pgid=pgid,
            process_start_token=process_start_token,
            known_descendant_pids=known_descendant_pids,
            container_id=container_id,
        )
        self._workers[worker_id] = ident
        return ident

    def on_ui_window_closed(self, ui_client_id: str) -> dict[str, object]:
        """Closing a Tauri/desktop UI window never stops the resident daemon or workers."""
        return {
            "ui_client_id": ui_client_id,
            "daemon_running": self._daemon_running,
            "active_workers_count": len(self._workers),
            "workers_stopped": 0,
        }

    def reclaim_worker(
        self,
        worker_id: str,
        *,
        current_start_token: str,
        grace_ms: int = 100,
        simulated_residual_pids: tuple[int, ...] = (),
        container_reclaimed: bool = True,
    ) -> WorkerReclaimReport:
        ident = self._workers.get(worker_id)
        if ident is None:
            raise PermissionError(f"Unregistered worker cannot be signaled: {worker_id}")
        if current_start_token != ident.process_start_token:
            raise PermissionError(
                f"PID reuse detected for worker {worker_id} (pid={ident.pid}); refusing to kill"
            )

        graceful_sent = False
        forced_sent = False
        if _pid_alive(ident.pid):
            try:
                if sys.platform != "win32":
                    os.killpg(ident.pgid, signal.SIGTERM)
                else:
                    os.kill(ident.pid, signal.SIGTERM)
                graceful_sent = True
            except (ProcessLookupError, PermissionError):
                try:
                    os.kill(ident.pid, signal.SIGTERM)
                    graceful_sent = True
                except ProcessLookupError:
                    pass
            deadline = time.monotonic() + max(0.01, grace_ms / 1000)
            while time.monotonic() < deadline:
                if not _pid_alive(ident.pid) and not any(
                    _pid_alive(p) for p in ident.known_descendant_pids
                ):
                    break
                time.sleep(0.01)

        if sys.platform != "win32":
            hard_sig: int = signal.SIGKILL
        else:
            hard_sig = signal.SIGTERM
        if _pid_alive(ident.pid) or any(_pid_alive(p) for p in ident.known_descendant_pids):
            try:
                if sys.platform != "win32":
                    os.killpg(ident.pgid, hard_sig)
                else:
                    os.kill(ident.pid, hard_sig)
                forced_sent = True
            except (ProcessLookupError, PermissionError):
                pass
            for d_pid in (ident.pid, *ident.known_descendant_pids):
                if _pid_alive(d_pid):
                    try:
                        os.kill(d_pid, hard_sig)
                        forced_sent = True
                    except ProcessLookupError:
                        pass
            time.sleep(0.02)

        live_residuals: list[int] = list(simulated_residual_pids)
        for check_pid in (ident.pid, *ident.known_descendant_pids):
            if _pid_alive(check_pid) and check_pid not in live_residuals:
                live_residuals.append(check_pid)

        c_ok = container_reclaimed if ident.container_id is not None else True
        isolated = len(live_residuals) == 0 and c_ok
        if isolated:
            self._workers.pop(worker_id, None)

        return WorkerReclaimReport(
            worker_id=worker_id,
            runtime_epoch=ident.runtime_epoch,
            graceful_sent=graceful_sent,
            forced_kill_sent=forced_sent,
            residual_pids=tuple(live_residuals),
            container_reclaimed=c_ok,
            old_domain_isolated=isolated,
            quarantine_required=not isolated,
            new_dispatch_allowed=isolated,
        )
