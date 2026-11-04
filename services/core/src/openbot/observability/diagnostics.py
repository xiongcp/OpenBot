"""Unified local observability, low-cardinality metrics, and redacted diagnostics (OB-075)."""

from dataclasses import dataclass
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

    def __init__(self, *, redactor: RedactionPipeline) -> None:
        self._redactor = redactor
        self._logs: list[dict[str, Any]] = []
        self._metrics: list[dict[str, Any]] = []

    def record_log(
        self,
        *,
        context: TraceCorrelationContext,
        event: str,
        message: str,
        hidden_reasoning: str | None = None,
    ) -> dict[str, Any]:
        del hidden_reasoning  # Model hidden chain-of-thought is NEVER collected or stored!
        sanitized = self._redactor.sanitize_sink(
            sink="diagnostic", text=message, data_class="WORKSPACE"
        ).sanitized_text
        entry: dict[str, Any] = {
            "task_id": context.task_id,
            "operation_id": context.operation_id,
            "attempt_id": context.attempt_id,
            "event": event,
            "message": sanitized,
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
            "logs": list(self._logs),
            "metrics": list(self._metrics),
        }
