# CLI (中英双语 / Bilingual)

## 中文说明

- **入口与职责**：`openbot.cli` 提供本地命令行入口，所有任务、审批和未知动作核对命令均通过受保护的 loopback 本地控制 API（`/v1/*`）访问，**绝不直接打开 SQLite 或绕过 application/policy 层**。
- **支持命令**：
  - `openbot version` / `openbot health`
  - `openbot task create|show|cancel|resume`
  - `openbot approval preview|decide`（`APPROVE` 需使用 `owner_cli` 作用域 token 获取一次性 challenge nonce）
  - `openbot operation reconcile`（先上传内联核对证据生成 `OPERATION` 级 artifact，再提交核对结果）
- **安全与反旁路约束**：
  - 严禁 `--ignore-and-rerun`、`--force-success`、`--revive-consumed` 等客户端强制旁路开关（返回码 `6`）。
  - 人类可读输出统一经过 `sanitize_terminal_text` 过滤 ANSI CSI/OSC 控制序列与富文本标签，防止外部日志/路径伪造终端审批提示。
  - 客户端等待超时返回码 `5`（`WAIT_TIMEOUT_OUTCOME_UNKNOWN`），明确标注 `action_guaranteed_not_executed=false` 且要求重新查询状态，绝不谎称动作未执行。

## English Summary

- **Entrypoint & Responsibility**: `openbot.cli` provides the local CLI entrypoint. All task, approval, and unknown-operation reconciliation commands communicate strictly through the authenticated loopback control API (`/v1/*`) and **never open SQLite directly or bypass the application/policy layers**.
- **Supported Commands**:
  - `openbot version` / `openbot health`
  - `openbot task create|show|cancel|resume`
  - `openbot approval preview|decide` (`APPROVE` requires an `owner_cli`-scoped token to obtain a one-time challenge nonce)
  - `openbot operation reconcile` (uploads inline evidence to create an `OPERATION`-scoped artifact before submitting the reconciliation decision)
- **Safety & Non-Bypass Invariants**:
  - Client bypass flags (`--ignore-and-rerun`, `--force-success`, `--revive-consumed`) are rejected with exit code `6`.
  - Human-readable output strips ANSI CSI/OSC control sequences and rich-text markup tags via `sanitize_terminal_text` to prevent terminal injection or forged approval prompts.
  - Client wait timeouts return exit code `5` (`WAIT_TIMEOUT_OUTCOME_UNKNOWN`) with `action_guaranteed_not_executed=false` and `requery_required=true`, never falsely claiming that an action did not execute.
