# OpenBot 快速上手指南 / Getting Started Guide (OB-079)

## 中文说明

### 1. 环境准备与本地验证（macOS ARM64 试点）
1. 同步锁定依赖并运行完整验证：`uv sync --locked` 后执行 `.venv/bin/python scripts/verify.py`。
2. 启动受保护的本地控制面守护进程：`openbot daemon serve --profile-dir <dir>`，并通过 `openbot health --profile-dir <dir> --require-daemon` 核验运行态。
3. 任务创建、审批预览与决定、未知结果核对均通过本地认证 CLI：`openbot task create|show|cancel|resume --profile-dir <dir>`、`openbot approval preview|decide --profile-dir <dir>` 与 `openbot operation show|reconcile --profile-dir <dir>`（凭据存于 `0600` 的 `owner_cli.token`，禁止在命令行传 `--token`）。
4. 飞书安全配对（M2）：先在本地发起一次性短 TTL 挑战，远端回传后在本地确认 `tenant_key`/`app_id`/`open_id` 才可激活 owner。

### 2. 已验证能力与 M4 边界说明
- **当前已验证（M0—M3 本地）**：`Darwin arm64` 下 SQLite 23 表持久化、两次短事务派发、工作区 ACI 文件与补丁工具、受控进程与容器沙箱、结构化浏览器与 MCP 守卫、飞书受控契约与可观测性脱敏。
- **尚未启用或属于 M4 范围**：Windows/Linux 原生实机验收、真实飞书企业租户联调、以及 **M4 桌面 Tauri UI、代码签名公证安装包与自动升级（`OB-073`/`OB-074`/`OB-082`/`OB-083`）尚未实现**。

---

## English Summary

### 1. Setup & Local Workflow (macOS ARM64 Pilot)
1. Sync locked dependencies and run verification: `uv sync --locked && .venv/bin/python scripts/verify.py`.
2. Start the local control-plane daemon: `openbot daemon serve --profile-dir <dir>` and verify with `openbot health --profile-dir <dir> --require-daemon`.
3. Manage tasks, approvals, and reconciliation via the authenticated CLI: `openbot task create|show|cancel|resume --profile-dir <dir>`, `openbot approval preview|decide --profile-dir <dir>`, and `openbot operation show|reconcile --profile-dir <dir>`.
4. Feishu Pairing (M2): Generate a short-TTL local challenge and confirm the remote candidate (`tenant_key`/`app_id`/`open_id`) locally before activating owner authority.

### 2. Verified Capabilities & M4 Boundaries
- **Verified Locally (M0–M3 on Darwin arm64)**: 23-table SQLite persistence, two-transaction dispatch, workspace ACI tools, process/container isolation, browser/MCP guards, Feishu contract harness, and redacted observability.
- **Unverified or M4 Scope**: Native Windows/Linux hardware verification, live Feishu tenant credentials, and **M4 desktop Tauri UI, code-signed installers, and auto-upgrade (`OB-073`/`OB-074`/`OB-082`/`OB-083`) are not yet implemented**.
