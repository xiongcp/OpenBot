"""Unified local observability, low-cardinality metrics, and redacted diagnostics (OB-075)."""

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from openbot.observability.redaction import RedactionPipeline

_HIGH_CARDINALITY_LABEL_KEYS = frozenset(
    {
        "task_id",
        "operation_id",
        "attempt_id",
        "event_id",
        "outbox_id",
        "approval_id",
    }
)


@dataclass(frozen=True, slots=True)
class TraceCorrelationContext:
    task_id: str | None
    operation_id: str | None
    attempt_id: str | None


class ObservabilityHub:
    """Correlate structured logs, strip hidden reasoning/secrets, and bound metric cardinality."""

    remote_exporter_enabled: Literal[False] = False
    ui_online_proves_daemon_healthy: Literal[False] = False
    max_ring_entries: int = 2000

    def __init__(self, *, redactor: RedactionPipeline, max_entries: int = 2000) -> None:
        self._redactor = redactor
        self._max_entries = max(1, max_entries)
        self._logs: deque[dict[str, Any]] = deque(maxlen=self._max_entries)
        self._metrics: deque[dict[str, Any]] = deque(maxlen=self._max_entries)
        self._redaction_hits = 0

    def record_log(
        self,
        *,
        context: TraceCorrelationContext,
        event: str,
        message: str,
        hidden_reasoning: str | None = None,
    ) -> dict[str, Any]:
        del hidden_reasoning  # Model hidden chain-of-thought is NEVER collected or stored!
        res = self._redactor.sanitize_sink(sink="diagnostic", text=message, data_class="WORKSPACE")
        if res.sanitized_text != message:
            self._redaction_hits += 1
        entry: dict[str, Any] = {
            "task_id": context.task_id,
            "operation_id": context.operation_id,
            "attempt_id": context.attempt_id,
            "event": event,
            "message": res.sanitized_text,
        }
        self._logs.append(entry)
        return entry

    def record_metric(self, *, name: str, value: float, labels: dict[str, str]) -> dict[str, Any]:
        bounded_labels = {k: v for k, v in labels.items() if k not in _HIGH_CARDINALITY_LABEL_KEYS}
        rec: dict[str, Any] = {
            "name": name,
            "value": value,
            "labels": bounded_labels,
        }
        self._metrics.append(rec)
        return rec

    def export_explicit_diagnostic_bundle(self) -> dict[str, Any]:
        return {
            "explicitly_exported": True,
            "remote_exporter_enabled": False,
            "ring_buffer_maxlen": self._max_entries,
            "redaction_hits": self._redaction_hits,
            "logs": list(self._logs),
            "metrics": list(self._metrics),
        }

    def preview_diagnostic_bundle(self) -> dict[str, Any]:
        return {
            "files_included": ["logs.json", "metrics.json", "health_summary.json"],
            "log_entry_count": len(self._logs),
            "metric_entry_count": len(self._metrics),
            "redaction_hits": self._redaction_hits,
            "remote_upload_enabled": False,
        }


class RotatingRedactedLogWriter:
    """Bounded 10MB x 5 rotating redacted log file writer (V1-071)."""

    def __init__(
        self,
        log_path: Path,
        *,
        redactor: RedactionPipeline,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
    ) -> None:
        self._path = log_path.resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._redactor = redactor
        self._max_bytes = max(64, max_bytes)
        self._backups = max(1, backup_count)

    def write_line(self, line: str) -> None:
        safe = self._redactor.sanitize_sink(
            sink="diagnostic", text=line, data_class="WORKSPACE"
        ).sanitized_text
        payload = (safe + "\n").encode("utf-8")
        if self._path.is_file() and self._path.stat().st_size + len(payload) > self._max_bytes:
            self._rotate()
        with self._path.open("ab") as f:
            f.write(payload)

    def _rotate(self) -> None:
        oldest = self._path.with_name(f"{self._path.name}.{self._backups}")
        if oldest.is_file():
            oldest.unlink()
        for idx in range(self._backups - 1, 0, -1):
            src = self._path.with_name(f"{self._path.name}.{idx}")
            dst = self._path.with_name(f"{self._path.name}.{idx + 1}")
            if src.is_file():
                src.replace(dst)
        if self._path.is_file():
            self._path.replace(self._path.with_name(f"{self._path.name}.1"))
