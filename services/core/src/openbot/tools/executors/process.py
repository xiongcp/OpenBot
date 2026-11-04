"""Structured process.run execution contract, shell rejection, and isolated worker mapping."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from openbot.observability.redaction import RedactionPipeline, StreamingSecretRedactor

type ProcessOutcomeStatus = Literal["SUCCEEDED", "FAILED", "UNKNOWN"]

_SHELL_BINARIES = frozenset(
    {
        "sh",
        "bash",
        "zsh",
        "dash",
        "ksh",
        "csh",
        "tcsh",
        "fish",
        "cmd",
        "cmd.exe",
        "powershell",
        "pwsh",
    }
)
_SHELL_EXEC_FLAGS = frozenset({"-c", "/c", "/k", "-command", "-encodedcommand"})
_CODE_EXEC_BINARIES = frozenset(
    {
        "python",
        "python3",
        "pytest",
        "pip",
        "uv",
        "node",
        "npm",
        "npx",
        "pnpm",
        "yarn",
        "cargo",
        "rustc",
        "go",
        "make",
        "cmake",
        "git",
        "docker",
    }
)


def classify_command_security(
    action_label: str, argv: tuple[str, ...]
) -> Literal["CODE_EXECUTION"]:
    """Every interpreter, test runner, build tool, Git command, or rg --pre is CODE_EXECUTION.

    Action names like 'search', 'snapshot', or 'lint' never downgrade process execution
    into an unisolated read-only host call.
    """
    del action_label
    if not argv:
        raise ValueError("argv must be non-empty")
    return "CODE_EXECUTION"


@dataclass(frozen=True, slots=True)
class ProcessResourceLimits:
    memory_bytes: int = 134_217_728
    cpu_millis: int = 1000
    pids_limit: int = 64
    timeout_ms: int = 30_000
    max_output_bytes: int = 65_536


@dataclass(frozen=True, slots=True)
class ProcessExecutionPlan:
    operation_id: str
    attempt_id: str
    dispatch_id: str
    action_label: str
    executable: str
    argv: tuple[str, ...]
    workspace_snapshot_digest: str
    execution_backend: Literal["ISOLATED_CONTAINER", "ISOLATED_WORKER"]
    image_digest: str
    network_mode: Literal["NONE", "LOOPBACK_ONLY", "RESTRICTED_EGRESS"]
    isolated_home: str
    isolated_tmpdir: str
    env: dict[str, str]
    limits: ProcessResourceLimits

    def validate(self) -> None:
        if not self.executable.strip() or not self.argv:
            raise PermissionError("Executable and argv must be non-empty")
        if self.argv[0] != self.executable:
            raise PermissionError("argv[0] must match the locked executable")
        exe_name = Path(self.executable).name.lower()
        if exe_name in _SHELL_BINARIES or any(
            arg.lower() in _SHELL_EXEC_FLAGS for arg in self.argv[1:]
        ):
            raise PermissionError("Raw shell strings and shell -c wrappers are forbidden")
        if any(arg.startswith("--pre") for arg in self.argv):
            raise PermissionError("Hidden preprocessor execution (--pre) is forbidden")
        if self.execution_backend not in {"ISOLATED_CONTAINER", "ISOLATED_WORKER"}:
            raise PermissionError("Host execution backend is forbidden")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.image_digest):
            raise PermissionError("Pinned sha256 image_digest is required")
        if not re.fullmatch(r"[0-9a-f]{64}", self.workspace_snapshot_digest):
            raise PermissionError("Valid workspace_snapshot_digest is required")
        classify_command_security(self.action_label, self.argv)


@dataclass(frozen=True, slots=True)
class RawWorkerOutcome:
    client_pid: int | None
    container_id: str | None
    exit_code: int | None
    signal: str | None
    timed_out: bool
    cancelled: bool
    container_confirmed_stopped: bool
    stdout_chunks: tuple[bytes, ...]
    stderr_chunks: tuple[bytes, ...]


class IsolatedWorkerPort(Protocol):
    def run_isolated(self, plan: ProcessExecutionPlan) -> RawWorkerOutcome: ...


@dataclass(frozen=True, slots=True)
class ProcessExecutionResult:
    operation_id: str
    attempt_id: str
    dispatch_id: str
    status: ProcessOutcomeStatus
    exit_code: int | None
    signal: str | None
    timed_out: bool
    cancelled: bool
    client_pid: int | None
    container_id: str | None
    container_confirmed_stopped: bool
    image_digest: str
    network_mode: str
    stdout: str
    stderr: str
    output_truncated: bool
    error_code: str | None

    def to_receipt(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "attempt_id": self.attempt_id,
            "dispatch_id": self.dispatch_id,
            "status": self.status,
            "exit_code": self.exit_code,
            "signal": self.signal,
            "timed_out": self.timed_out,
            "cancelled": self.cancelled,
            "client_pid": self.client_pid,
            "container_id": self.container_id,
            "container_confirmed_stopped": self.container_confirmed_stopped,
            "image_digest": self.image_digest,
            "network_mode": self.network_mode,
            "output_truncated": self.output_truncated,
            "error_code": self.error_code,
        }


class ControlledProcessExecutor:
    """Execute locked ProcessExecutionPlan only when isolated backend is qualified."""

    def __init__(
        self,
        *,
        worker: IsolatedWorkerPort,
        isolation_backend_qualified: bool,
        redactor: RedactionPipeline,
        registered_secrets: tuple[str, ...] = (),
    ) -> None:
        self._worker = worker
        self._qualified = isolation_backend_qualified
        self._redactor = redactor
        self._secrets = registered_secrets

    def _collect_and_redact(self, chunks: tuple[bytes, ...], max_bytes: int) -> tuple[str, bool]:
        stream = StreamingSecretRedactor(registered_secrets=self._secrets)
        parts: list[str] = []
        for ch in chunks:
            parts.append(stream.feed(ch))
        parts.append(stream.flush())
        sanitized = self._redactor.sanitize_sink(
            sink="stdout", text="".join(parts), data_class="WORKSPACE"
        ).sanitized_text
        encoded = sanitized.encode("utf-8")
        if len(encoded) > max_bytes:
            clipped = encoded[:max_bytes].decode("utf-8", errors="ignore")
            return clipped, True
        return sanitized, False

    def execute(self, plan: ProcessExecutionPlan) -> ProcessExecutionResult:
        plan.validate()
        if not self._qualified:
            raise PermissionError(
                "CAPABILITY_UNAVAILABLE: isolated execution backend is not qualified; "
                "refusing host execution fallback"
            )

        raw = self._worker.run_isolated(plan)
        stdout_str, out_trunc = self._collect_and_redact(
            raw.stdout_chunks, plan.limits.max_output_bytes
        )
        stderr_str, err_trunc = self._collect_and_redact(
            raw.stderr_chunks, plan.limits.max_output_bytes
        )

        # Client exit never proves container stopped; unconfirmed container stop is UNKNOWN!
        if not raw.container_confirmed_stopped:
            status: ProcessOutcomeStatus = "UNKNOWN"
            err_code: str | None = "CONTAINER_STOP_UNCONFIRMED"
        elif raw.timed_out:
            status = "FAILED"
            err_code = "PROCESS_TIMEOUT"
        elif raw.cancelled:
            status = "FAILED"
            err_code = "PROCESS_CANCELLED"
        elif raw.signal is not None:
            status = "FAILED"
            err_code = f"SIGNAL_{raw.signal}"
        elif raw.exit_code == 0:
            status = "SUCCEEDED"
            err_code = None
        else:
            status = "FAILED"
            err_code = f"EXIT_{raw.exit_code}"

        return ProcessExecutionResult(
            operation_id=plan.operation_id,
            attempt_id=plan.attempt_id,
            dispatch_id=plan.dispatch_id,
            status=status,
            exit_code=raw.exit_code,
            signal=raw.signal,
            timed_out=raw.timed_out,
            cancelled=raw.cancelled,
            client_pid=raw.client_pid,
            container_id=raw.container_id,
            container_confirmed_stopped=raw.container_confirmed_stopped,
            image_digest=plan.image_digest,
            network_mode=plan.network_mode,
            stdout=stdout_str,
            stderr=stderr_str,
            output_truncated=out_trunc or err_trunc,
            error_code=err_code,
        )
