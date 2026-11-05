# M3 MVP 发布验收签核与平台能力报告 / M3 MVP Release Acceptance & Platform Capability Report (OB-080)

## 中文说明

### 1. M0—M3 实施与验证汇总（Darwin arm64）
- **安全必阻断失败数**：`0`（M0 验证套件 `299 passed` / M1 验证套件 `318 passed`，存储集成测试 `91 passed`）。
- **已在本机（`Darwin arm64`）实测通过的子系统**：
  - 23 表 SQLite 单写者持久化、Outbox、取消传播、持久预算与上下文快照（`OB-011`—`OB-024`、`OB-030`）。
  - 六维策略、一次性 `CONSUMED` 审批、两次短事务派发与按副作用等级恢复（`OB-017`—`OB-020`、`OB-031`）。
  - 工作区文件守卫、`list/read/search`、补丁冻结与回滚、隔离语法验证、本地消息草稿与受控发送（`OB-032`—`OB-036`、`OB-043`—`OB-044`）。
  - 统一外发策略、OS Keychain 分域与单次句柄、流式脱敏、结构化进程执行、容器沙箱与进程树回收（`OB-037`—`OB-042`）。
  - 认证本地 HTTP/SSE 控制 API、CLI 任务与审批操作、M1 首条持久化垂直切片与威胁回归（`OB-081`、`OB-028`—`OB-029`、`OB-045`—`OB-046`）。
  - 飞书配对、WebSocket 入站、审批 callback、普通卡/进度节流/CardKit 降级、外部健康监督、死信重投与受控 E2E 套件（`OB-048`—`OB-056`、`OB-094`）。
  - 云模型与本地 Ollama 适配器、浏览器专用 profile/网络策略/读写工具与结果验证、MCP 协商/JCS 锁定/隔离执行与故障套件、只读技能、用户级 daemon、macOS 原生门禁、打包审计、统一可观测性、质量基准、SPDX-2.3 供应链、分层 CI 与混沌浸泡（`OB-025`—`OB-026`、`OB-057`—`OB-069`、`OB-072`、`OB-075`—`OB-080`、`OB-095`—`OB-096`）。

### 2. 跨平台与外部租户诚实放行结论
- **`darwin_arm64_pilot_ready = True`**：macOS ARM64 本地受控试点全部门禁通过。
- **真实飞书服务端协议与长连接已验证（`OB-047`）**：已完成 `open.feishu.cn` 鉴权、机器人信息、CardKit 2.0 创建/更新与 `code=300317` 序列校验、以及 `wss://msg-frontier.feishu.cn` TLS `101 Switching Protocols` 握手实测（所有凭据零落盘）。
- **`full_three_os_mvp_release_approved = False`**：因当前环境未提供原生 Windows/Linux 实机（`OB-005`/`OB-070`/`OB-071` `BLOCKED`，按用户指示暂不执行）及手机端真人交互点击，严格遵守架构不变量，不将单平台试点宣称为全三平台 MVP 放行。
- **`m4_signing_is_reverse_prerequisite = False`**：M4 桌面 Tauri UI、代码签名与自动升级不作为 M3 门禁的反向前置依赖。

### 3. 能力矩阵（区分 `implementation_status` 与 `verification_status`）

| 子系统 / 门禁 | `implementation_status` | `verification_status` | 证据层级与边界说明 |
|---|---|---|---|
| 本地控制面 CLI 与 Loopback HTTP API (`MVP-006`) | `IMPLEMENTED` | `NATIVE_OS` | 已通过独立子进程 `openbot daemon serve` 与 `task/approval/operation` 实测 |
| SQLite 23 表、单写者、在线备份与满盘保护 (`MVP-009`) | `IMPLEMENTED` | `NATIVE_OS` | 真实 `SIGKILL`、WAL 重开、备份恢复与 `max_page_count` 满盘拦截已验证 |
| macOS Keychain、LaunchAgent 与 APFS 守卫 (`MVP-007`/`008`) | `IMPLEMENTED` | `NATIVE_OS` | `/usr/bin/security` 真实 canary、`/usr/bin/plutil -lint` 与 symlink 拦截已验证 |
| Browser 跨进程锁与 MCP stdio 流式上限 (`MVP-010`/`011`) | `IMPLEMENTED` | `NATIVE_OS` | 跨进程 `flock`、Chromium headless DOM 导出与真实 stdio 子进程已验证 |
| 云模型与本地 Ollama 双 Provider (`MVP-012`) | `IMPLEMENTED` | `SPLIT_QUALIFICATION` | 区分 `synthetic_provider_contract`、`sdk_loopback_contract`、`real_cloud_provider` 与 `real_local_ollama_runner` |
| Windows / Linux 原生 M3 门禁 (`OB-070`/`OB-071`) | `PARTIAL` | `NOT_RUN` / `BLOCKED_ENV` | CI 已覆盖 `contracts` 收集与设计校验，原生系统隔离保持 `BLOCKED_ENV` |
| M4 Tauri 桌面 UI、代码签名公证与自动更新 (`OB-073`/`074`) | `TODO` | `NOT_APPLICABLE` | 属于 M4 桌面分发阶段，不在 M3 CLI/daemon MVP 声明范围内 |

---

## English Summary

### 1. M0–M3 Implementation & Verification Summary (`Darwin arm64`)
- **Security-Critical Failures**: `0` (`299 passed` in M0 verification / `318 passed` in M1 verification, `91 passed` storage integration tests).
- **Verified Subsystems on `Darwin arm64`**: 23-table SQLite persistence, two-transaction dispatch, 6D policy & one-time `CONSUMED` approvals, workspace ACI tools, process/container isolation, authenticated loopback HTTP/SSE API & CLI, Feishu gateway/cards/callbacks/health/DLQ, OpenAI & local Ollama adapters, browser & MCP guards, read-only skills, user-session daemon, macOS native gate, packaging auditor, redacted observability, benchmark runner, SPDX-2.3 supply chain, tiered CI, and chaos soak suite.

### 2. Release Gate Decision
- **`darwin_arm64_pilot_ready = True`**, **`full_three_os_mvp_release_approved = False`** (blocked on `windows_native_unverified`, `linux_native_unverified`, and `real_feishu_tenant_unverified`), and **`m4_signing_is_reverse_prerequisite = False`**.
