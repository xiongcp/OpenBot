# 统一可观测性与脱敏诊断包运维说明 / Unified Observability & Redacted Diagnostic Bundle Guide (OB-075)

## 中文说明
- **结构化关联与高基数标签隔离**：`ObservabilityHub` 在结构化日志中关联 `task_id`、`operation_id`、`attempt_id`，但强制从指标（metrics）标签中剥离高基数 ID（`_HIGH_CARDINALITY_LABEL_KEYS`），防止指标基数爆炸。
- **零隐藏推理采集与全量脱敏**：模型隐藏思维链（`hidden_reasoning`）一律丢弃不落盘；所有 SDK 调试日志、异常与显式导出的诊断包均经过 `RedactionPipeline` 脱敏。
- **默认无远程遥测上报**：`remote_exporter_enabled = False`，且桌面 UI 在线绝不等同于后台 daemon 健康（`ui_online_proves_daemon_healthy = False`）。

## English Summary
- **Trace Correlation & Low-Cardinality Metrics**: `ObservabilityHub` correlates `task_id`, `operation_id`, and `attempt_id` in structured logs while stripping high-cardinality IDs from metric labels.
- **Zero Hidden Reasoning & Redacted Diagnostics**: Drops model hidden reasoning chains, sanitizes all logs and explicit diagnostic bundles through `RedactionPipeline`, and disables remote telemetry exporters by default (`remote_exporter_enabled = False`).
