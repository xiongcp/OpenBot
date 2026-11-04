# M1 最小本地 Alpha 原型边界与验收说明 / M1 Minimal Local Alpha Prototype Acceptance & Boundary Report (OB-046)

## 中文说明

### 1. 原型范围与端到端能力（M1 Local Alpha）
- **从空配置一键验证**：`services/core/src/openbot/application/local_prototype.py`（`LocalAlphaPrototypeRunner`）与 `tests/integration/scenarios/local_prototype/test_local_prototype.py` 从空白目录初始化 SQLite 23 表与工作区，通过 CLI 和认证本地控制 API 完成：`workspace.read` 读取文件 → `workspace.propose_patch` 冻结补丁与 Artifact SHA-256 → CLI 审批（一次性 `CONSUMED`）→ `workspace.apply_patch` 与受监管隔离进程回收 → 崩溃重启后通过稳定 ID 重查与核对恢复。
- **OB-091（M0 协议 PoC）与 OB-029（M1 垂直切片）的差异**：
  - `OB-091` 仅在 `tests/protocol/` 中用 MockWorker 验证 8 个崩溃点与数据库触发器语义。
  - `OB-029` / `OB-046` 接入了认证本地控制 API（`LocalControlApiServer`）、CLI（`openbot.cli`）、工作区路径/符号链接守卫（`WorkspaceFileGuard`）、Artifact 存储（`ArtifactStore`）、进程树回收（`ProcessSupervisorService`）、持久 Outbox（`OutboxService`）与 7 类安全威胁回归语料（`M1ThreatRegressionSuite`）。

### 2. 已启用组件与试点环境
- **当前已验证试点环境**：`Darwin arm64`（macOS ARM64），Python 3.12（`.venv` 24 包 / `.venv-m1` 35 包）。
- **已准入并接入的 M0/M1 组件**：`sqlite3`、`rfc8785`（JCS UTF-16 码元排序与重复键拒绝）、`pydantic-jsonschema`（Draft 2020-12 校验）、`openai-python-sdk`（`max_retries=0` 离线故障夹具验证）、`httpx`、`cli-toolchain`。

### 3. 明确未支持或未实测能力（诚实边界）
- **未实测原生操作系统**：`Windows-native`（Win32 Job Object、WinVaultKeyring）、`Linux-native`（cgroup v2、SecretService）尚未在原生机器实测。
- **未接入真实外部租户与生产凭据**：真实飞书租户（`real_feishu_tenant`）与真实云端/本地模型推理凭据尚未配置实测。
- **M2/M3 待推进能力**：飞书长连接网关与卡片回调、本地模型路由、桌面 Tauri/React 控制台、浏览器受控自动化（Playwright）与桌面 GUI 受控适配器（`claims_full_mvp_complete = False`）。

### 4. 可复现验证命令
- `PYTHONPATH=services/core/src .venv-m1/bin/python -m pytest tests/integration/scenarios/local_prototype/test_local_prototype.py -q`（1 passed）

---

## English Summary

### 1. Prototype Scope & End-to-End Capabilities (M1 Local Alpha)
- **Empty-Config Verification**: `services/core/src/openbot/application/local_prototype.py` (`LocalAlphaPrototypeRunner`) and `tests/integration/scenarios/local_prototype/test_local_prototype.py` bootstrap a fresh SQLite database and workspace from an empty directory, executing `workspace.read` → `workspace.propose_patch` (frozen Artifact SHA-256) → CLI approval (`CONSUMED`) → `workspace.apply_patch` and supervised worker reclaim → crash recovery and reconciliation via CLI and the authenticated Local Control API.
- **Difference Between OB-091 (M0 PoC) and OB-029/OB-046 (M1 Gate)**: `OB-091` verified state-machine transitions using MockWorker in `tests/protocol/`, whereas `OB-029`/`OB-046` integrate the authenticated Local Control API, CLI, `WorkspaceFileGuard`, `ArtifactStore`, `ProcessSupervisorService`, `OutboxService`, and `M1ThreatRegressionSuite`.

### 2. Pilot OS & Enabled Components
- **Verified Pilot OS**: `Darwin arm64` (macOS ARM64), Python 3.12 (`.venv` 24 locked packages / `.venv-m1` 35 locked packages).
- **Enabled Components**: `sqlite3`, `rfc8785`, `pydantic-jsonschema`, `openai-python-sdk` (`max_retries=0` offline fault-verified), `httpx`, `cli-toolchain`.

### 3. Unsupported or Unverified Capabilities (Honest Boundary)
- **Unverified Native OS Targets**: `Windows-native` and `Linux-native` remain unverified on native hardware.
- **Unverified External Tenants/Credentials**: `real_feishu_tenant` and `real_production_cloud_model_credentials` are not claimed as verified.
- **Remaining M2/M3 Scope**: Feishu gateway/cards, local model provider, Tauri/React desktop console, Playwright browser automation, and desktop GUI automation (`claims_full_mvp_complete = False`).

### 4. Reproducible Command
- `PYTHONPATH=services/core/src .venv-m1/bin/python -m pytest tests/integration/scenarios/local_prototype/test_local_prototype.py -q` (`1 passed`)
