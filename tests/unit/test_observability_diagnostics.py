from openbot.observability.diagnostics import (
    ObservabilityHub,
    TraceCorrelationContext,
)
from openbot.observability.redaction import RedactionPipeline


def test_observability_strips_reasoning_bounds_labels_and_redacts_diagnostics() -> None:
    secret = "sk-obs-secret-999999999999"
    hub = ObservabilityHub(redactor=RedactionPipeline(registered_secrets=(secret,)))
    assert hub.remote_exporter_enabled is False
    assert hub.ui_online_proves_daemon_healthy is False

    ctx = TraceCorrelationContext(
        task_id="tsk_high_card_1",
        operation_id="op_high_card_1",
        attempt_id="att_1",
    )
    entry = hub.record_log(
        context=ctx,
        event="sdk_debug",
        message=f"Header Bearer {secret}",
        hidden_reasoning="secret chain of thought",
    )
    assert secret not in entry["message"]
    assert "hidden_reasoning" not in entry
    assert "secret chain of thought" not in str(entry)

    # High-cardinality task_id / operation_id are stripped from metric labels!
    metric = hub.record_metric(
        name="openbot_outbox_age_ms",
        value=120.0,
        labels={"state": "PENDING", "task_id": "tsk_high_card_1", "operation_id": "op_1"},
    )
    assert "task_id" not in metric["labels"]
    assert "operation_id" not in metric["labels"]
    assert metric["labels"]["state"] == "PENDING"

    bundle = hub.export_explicit_diagnostic_bundle()
    assert secret not in str(bundle)
    assert bundle["explicitly_exported"] is True
