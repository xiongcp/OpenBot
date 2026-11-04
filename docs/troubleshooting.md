# 常见故障处置与恢复手册 / Troubleshooting & Recovery Runbook (OB-079)

## 中文说明

### 1. 操作进入 `UNKNOWN` / 任务进入 `RECONCILING` 的标准核对流程
- 当外部操作在 `DISPATCHING` 阶段发生断连、进程崩溃或超时，系统会将 Operation 置为 `UNKNOWN`、Task 置为 `RECONCILING` 并冻结资源租约（quarantine）。
- **严禁忽略 `UNKNOWN` 直接重跑（CLI 明确拒绝 `--ignore-and-rerun`、`--force-success`、`--revive-consumed`）**。
- **正确恢复步骤**：
  1. 人工或通过外部回执核实该外部动作是否已实际生效。
  2. 执行 `openbot operation reconcile --operation-id <op_id> --expected-version <v> --outcome CONFIRMED_SUCCEEDED|CONFIRMED_NOT_EXECUTED --evidence-content "<核对证据>" --json`。
  3. 执行 `openbot task resume --task-id <task_id> --expected-version <v> --json` 恢复任务。

### 2. 停止任务、密钥轮换、备份恢复与脱敏诊断包
- **停止/取消任务**：执行 `openbot task cancel --task-id <task_id> --expected-version <v>`；取消会阻止新派发，但不会声称已发生的外部副作用已回滚。
- **密钥轮换与撤销**：通过 `SecretBroker.rotate` / `revoke` 更新或吊销 OS Keychain 凭据，使旧 worker 单次句柄立即失效；撤销飞书 owner 会递增 `identity_epoch`。
- **数据库备份恢复与诊断导出**：使用 `DatabaseMaintenanceService` 执行在线一致性备份与恢复校验；通过 `ObservabilityHub.export_explicit_diagnostic_bundle()` 显式导出经 `RedactionPipeline` 脱敏的诊断包。

---

## English Summary

### 1. Reconciling `UNKNOWN` Operations & `RECONCILING` Tasks
- Never ignore an `UNKNOWN` operation and blindly re-run it (`--ignore-and-rerun`, `--force-success`, and `--revive-consumed` are strictly forbidden).
- Verify whether the external action took effect, run `openbot operation reconcile --operation-id <id> --expected-version <v> --outcome CONFIRMED_SUCCEEDED|CONFIRMED_NOT_EXECUTED --evidence-content "<evidence>" --json`, and then run `openbot task resume`.

### 2. Cancellation, Secret Rotation, Backup/Restore, and Redacted Diagnostics
- Use `openbot task cancel` to stop future dispatches (never claiming already-executed external actions were rolled back), `SecretBroker.rotate`/`revoke` for credential rotation, `DatabaseMaintenanceService` for verified SQLite backups, and `ObservabilityHub.export_explicit_diagnostic_bundle()` for redacted diagnostics.
