# 断网、休眠与崩溃浸泡测试报告模板与说明 / Network, Sleep/Wake, and Crash Soak Report Template (OB-078)

## 中文说明
- **四类故障独立记录**：`ChaosSoakHarness`（`services/core/src/openbot/application/chaos_soak.py`）分别验证并记录：
  1. `dns_stall_and_tcp_half_open`（DNS 停滞与 TCP 半开外部监督重连）
  2. `system_sleep_wake_clock_jump`（休眠唤醒后 UTC/单调时钟分叉使短时授权安全失效）
  3. `sigkill_daemon_and_worker_recovery`（强杀/崩溃后 `RECONCILE_ONLY` 零盲目重放）
  4. `sqlite_backup_and_disk_full_guard`（备份与磁盘异常保护）
- **诚实耐久性边界**：明确设置 `physical_power_loss_tested = False`（进程强杀不等同于真实物理断电）与 `claims_100_percent_lossless_guarantee = False`（有限样本通过绝不写成 100% 无损保证）。

## English Summary
- **Separate Fault Class Accounting**: `ChaosSoakHarness` tracks `dns_stall_and_tcp_half_open`, `system_sleep_wake_clock_jump`, `sigkill_daemon_and_worker_recovery`, and `sqlite_backup_and_disk_full_guard` with `dangerous_blind_retry_count == 0`.
- **Honest Durability Boundary**: Explicitly sets `physical_power_loss_tested = False` and `claims_100_percent_lossless_guarantee = False`.
