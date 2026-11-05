# OpenBot MVP → v1.0.0 完整统一实施提示词（84 项任务 V1-001..084 · 140 项测试 · 含 UI 深度打磨、常驻鲁棒性与四层电脑控制）

你是本机 OpenBot 项目的集成开发者。目标是在现有 `main@2028229123a6fc1d44ec54a1c905ef4c9f09fa05` 分支实现上，完整交付统一版 `v1.0.0` 的全部 **84 项任务（`V1-001` 至 `V1-084`，其中 79 项为 `v1.0.0` 首发范围，5 项 `V1-056..060` 为 `post-v1`）** 与 **140 项验收测试（`100` 项继承用例 + `40` 项 `TC-V1-001..040`）**，通过全部八道放行门禁（`G1..G8`）。不要重新从零搭建项目；不要推倒重写刚刚合入 `main` 的模块；也不要把模块单测当作完整产品已交付。

## 一、已知上下文与最新 `main@20282291` 基线

目标仓库：https://github.com/xiongcp/OpenBot.git

本统一交接包已同步至最新默认分支 `main@2028229123a6fc1d44ec54a1c905ef4c9f09fa05`（PR #2 已将 `codex/agent-client-observability@12074191a9c609a310cc5579eb548021b78305c1` 合入 `main`，对应 Actions `contracts` 工作流 run `42005019676` 在 macOS/Linux/Windows 三平台均为 `399 passed, 2 skipped`）。

当前 `main@20282291` 已具备以下模块（实施时必须直接复用并在此基础上扩展加固，严禁从零重写）：
- **有界 Agent 运行编排**：`services/core/src/openbot/application/agent_runtime.py`，已连接审批与执行、保留工具结果对话角色、等待完成 trace 持久化并暴露安全中断原因。
- **客户端控制路由与鉴权**：`services/core/src/openbot/adapters/local_api/client_routes.py` 与 `server.py`，已暴露受认证 daemon 控制 API、绑定 principal、限制 gateway token，并优先捕获 `RequestConflict`。
- **客户端状态与桌面端初版**：`services/core/src/openbot/application/client_state.py` 与 `apps/desktop/` 双语工作流客户端初版及 `.github/workflows/desktop-client.yml`。
- **只读隔离 MCP 切片**：`services/core/src/openbot/tools/mcp/container_read.py` 及审批预览 `sha256:` 前缀修复。
- **飞书 SDK 锁定与共享入口**：`pyproject.toml` 已锁定 `lark-oapi==1.7.5`、注册 `openbot-feishu` 入口并将 `services/feishu_gateway/src` 纳入包发现路径；已新增 `services/feishu_gateway/src/openbot_feishu/live_gateway.py`。

## 二、挂载路径隔离与防 CI 冲突规则（必读）

1. **禁止覆盖仓库根目录同名文件**：请将本统一执行包解压挂载在 `plan/v1_0_0/`（或仓库外独立目录）。仓库根目录自带的 `tasks/backlog.json`（96 项 `OB-*`）、`tasks/TASKS.md`、`README.md` 与 `diagrams/`（含 7 张设计图）受 `validation/verify_design.py`、`validation/verify_components.py` 和 `scripts/sync_task_status.py` 校验。
2. **双台账路径区分**：凡提及原任务台账，指仓库根目录 `tasks/backlog.json`（`OB-001..096`）；凡提及本统一方案 84 项任务、140 项测试用例与 8 个门禁，均指 `plan/v1_0_0/tasks/backlog.json`（`V1-001..084`）、`plan/v1_0_0/testing/test_cases.json` 与 `plan/v1_0_0/testing/gates.json`。
3. **供应链校验清单联动（`release/checksums.json`）**：仓库 `ReleaseSupplyChainVerifier`（`supply_chain.py`）对 `release/checksums.json` 中列出的受控文件（`uv.lock`、`THIRD_PARTY_NOTICES.md`、`packaging/runtime-assets.json`、`components/source-reuse/feishu.json`、`components/source-reuse/browser-dom.json`）强制校验 SHA-256。任何修改这些受控文件的 commit 必须在同一提交内同步更新 `release/checksums.json`。
4. **CI 工作流分支触发核对**：除 `pr.yml`（`contracts`）与 `desktop-client.yml` 外，在执行 `V1-008` 时立即修复 `.github/workflows/{pr-gate,platform-macos,release-supply-chain,nightly-soak}.yml` 仅监听 `[mvp/macos-hardening]` 的问题，将 `main` 与发布分支纳入触发列表。

## 三、统一版 v1.0.0（84 项任务 V1-001..084）实施主线与优先级顺序

### 阶段 1：基线核对、核心安全修补与多工具 Runtime 编排（`V1-001..015`, `V1-020`, `V1-075`）
1. **范围、证据与 CI 触发修复（`V1-001..009`）**：建立事实基线，修复 4 个 CI workflow 分支触发与 `release/checksums.json` 联动。
2. **真实常驻 Daemon、流式取消与多工具动态编排（`V1-010..012`, `V1-075`）**：解除 `agent_runtime.py` 第 41–54 行与第 207 行只允许调用 `mcp_read_text(demo.txt)` 的硬编码，改为从 SQLite `tool_registry` 动态加载并路由 `workspace.list/read/search/propose_patch/apply_patch`、`mcp.*` 与 `browser.*`；统一流式模型端口、实时取消与持久 `BudgetService` 结算。
3. **修补三大核心安全与恢复缺口（`V1-013..015`, `V1-020`）**：
   - `V1-013`：移除 `/v1/runtime/recover-epoch` 对客户端 `old_epoch_isolated` 布尔值的信任，改由 `ProcessSupervisorService` 核验真实进程出生身份与容器状态。
   - `V1-014`：建立进程外真正强杀持有 SQLite Writer 的 daemon 恢复夹具（覆盖 4 个副作用窗口），替换 `vertical_slice.py` 强杀 `sleep(30)` 子进程的做法。
   - `V1-015`：移除 `policy/secrets/broker.py` 中 `security add-generic-password ... -w <secret>` 明文 `argv` 泄漏面，改用无回显 `stdin` 或原生 Security Framework 桥接。
   - `V1-020`：为 `PatchCommitJournal` 补齐带版本/摘要与 `fsync` 顺序的可重载磁盘格式，支持跨进程崩溃恢复。

### 阶段 2：四层混合电脑控制（Hybrid ACI）与多模型生态（`V1-016..019`, `V1-021`, `V1-027`, `V1-076..084`）
1. **L1 工作区与通用隔离 MCP 容器池（`V1-016`, `V1-017`, `V1-076`）**：补齐 MCP `init_timeout_ms`、持续排空 `stderr` 与 JSON-RPC ID 校验；将 `ContainerReadTool` 泛化为支持 `components/locks/mcp-catalog.json` 的通用 `McpContainerExecutor`，内置准入锁定 SHA-256 的 `git-inspector`、`sqlite-reader`、`doc-extractor` 三款无网隔离容器工具。
2. **L2 Playwright 真实 CDP 浏览器控制与高亮预览（`V1-018`, `V1-019`, `V1-077`, `V1-078`）**：替换 `--dump-dom` 与合成枚举 `driver_outcome`，接入常驻受管 Playwright 会话、全量网络出口拦截（重定向/子请求/Service Worker/下载检疫）、紧凑 ARIA 语义快照（绑定 `BoundElementRef`）、审批前目标元素红框高亮预览截图，以及点击前毫秒级复验文字与金额。
3. **L3/L4 macOS 原生辅助功能（AXUIElement）控制与物理键鼠 100ms 抢占暂停（`V1-079`, `V1-080` · 落地 `OB-084/085`）**：针对白名单应用提取 macOS `AXUIElement` 控件树（硬拦截钥匙串/密码框/安全输入窗口），执行前复验前台窗口焦点与 PID（防 `DESKTOP_FOCUS_DRIFT`），并监听物理键鼠——用户一动鼠标或按键，100ms 内立即中止派发并挂起为 `PAUSED_BY_USER_TAKEOVER`。
4. **多模型 Provider、飞书 2.0、可验证记忆与持久定时任务（`V1-021`, `V1-027`, `V1-081..084` · 落地 `OB-027/086/087`）**：核验本地 Ollama 权重 digest 与 `OFFLINE` 零外发；新增 Anthropic Claude 与 Google Gemini 零自动重试流式适配器；升级飞书折叠 Diff 卡片并在授权测试租户跑通真人回调；实装带 `source_ref` 可一键彻底删除的工作区记忆（`authoritative_grants=False`）；实装仅生成普通 `QUEUED Task` 的持久定时触发器。

### 阶段 3：桌面客户端 UI/UX 深度优化与常驻鲁棒性加固（`V1-022..026`, `V1-028..029`, `V1-061..074`）
1. **桌面端 UI/UX 七项全面打磨（`V1-022..026`, `V1-061..067`）**：
   - `V1-061`：四步可视化零配置首开向导（自动检测/启动 Daemon → 绑定工作区 → 原生直写 Keychain 密钥 → 运行 Doctor 自检）。
   - `V1-062`：Rust `HTTP/1.1 Keep-Alive` 连接池与 `/v1/tasks/{id}/events` SSE 增量实时推送，彻底替换 `app.js` 的 1800ms 全量五接口轮询，自动处理 `410` 快照恢复。
   - `V1-063`：双栏（Split）/ 单栏（Unified）语法高亮 Diff 审批工作台、新旧 `sha256` 徽章与实时秒级 TTL 倒计时。
   - `V1-064`：支持滚轮缩放、拖拽平移、状态筛选与右侧证据抽屉联动的自适应层次化 DAG 执行因果图。
   - `V1-065`：图形化三步 `UNKNOWN` 核对向导（Reconciliation Wizard），告别只用 CLI 执行 `operation reconcile`。
   - `V1-066` & `V1-067`：macOS 顶部菜单栏常驻托盘（MenuBar Tray，带审批角标与【紧急停止】按钮）、系统脱敏通知、符合 WCAG 2.2 AA 的深色/浅色双主题与 `Cmd+K` 全局快捷键。
2. **系统长驻鲁棒性七项加固（`V1-028..029`, `V1-068..074`）**：
   - `V1-068`：容器创建前落盘 `container_intents` 预写日志（确保跨 `SIGKILL` 100% 自动清收孤儿容器）与 Supervisor 崩溃风暴熔断看门狗（5 分钟超 3 次进入安全维护态）。
   - `V1-069`：macOS 合盖睡眠/唤醒探测，唤醒后 3 秒内对齐 `ClockSnapshot`、主动重连飞书 WebSocket 与模型连接池。
   - `V1-070` & `V1-071`：SQLite Writer 空闲期自动执行 `PRAGMA wal_checkpoint(TRUNCATE)`、写前 512MB 磁盘低水位硬拦截，以及将 `DiagnosticsCollector` 内存列表改为 `deque(maxlen=2000)` + 10MB×5 轮转脱敏日志。
   - `V1-072`..`074`：外部网关三态自适应熔断器（`CLOSED/OPEN/HALF_OPEN`）与任务中途断点续跑、72 小时混合故障注入（Chaos Soak）零泄漏门禁、以及 `openbot doctor --fix-safe` 一键自检修复工具。

### 阶段 4：签名桌面发行包、GitHub 文档、双语官网与 RC 汇总门禁（`V1-030..055`）
1. **可安装签名 `.app`/`.dmg`、升级事务与全量 SBOM（`V1-030..036`）**：区分核心内置资产（80–120MB）与首次启用按需下载向导；完成 `SMAppService` / `launchd` 注册、Developer ID 签名公证、保留 quarantine 的干净 Mac VM 首开验证、一致性备份升级状态机与全量资产 SBOM。
2. **根 `LICENSE` 决议、面向用户的 README 与双语静态官网（`V1-040..055`）**：落盘根 `LICENSE`（Apache-2.0）解决 ADR/SBOM 冲突；建立 `docs/project-status.json` 能力事实源；在 `apps/website` 建设 Astro + Starlight 双语静态官网并与真实发行 manifest 联动。
3. **真机全生命周期、72h 浸泡与 RC 发布彩排（`V1-037..039`）**：汇聚全部 78 项前置任务与 140 项测试用例证据，通过 `python3 plan/v1_0_0/tools/validate_plan.py --mode rc` 校验后正式发布 `v1.0.0`。

## 四、不可妥协的十条架构不变量

1. 模型/技能/网页 DOM/AX 控件/MCP 元数据与记忆内容均为不可信输入（`TAINTED_EXTERNAL`）；服务端可信身份与 6 维确定性策略决定权限。
2. 所有外部效果经过同一 Broker；Approval 批准只到 `READY`，`CONSUMED` 永不复活，`claim`/`begin_dispatch` 分两次短事务复验。
3. 副作用未知保持 `UNKNOWN`/`RECONCILING` 及资源 quarantine；不能用新 Task/Operation ID 或 UI“重试”绕过。
4. 恢复证明来自真实 Supervisor/执行域，客户端布尔值、租约过期或单一 PID 均不是隔离证明。
5. 运行配置快照不能放宽当前限制；权限收紧（切换 `OFFLINE`、撤销 owner、撤销 TCC）立即阻断下一次模型/工具/飞书派发。
6. 缺隔离后端明确返回 `CAPABILITY_UNAVAILABLE`，严禁回退宿主裸 Shell（`sh -c`）；不复制日常浏览器 profile，不解密用户 cookie。
7. 秘密不进 `argv`、普通 `env`、WebView DOM、Git、日志或 Artifact；诊断导出先预览与脱敏。
8. 数据库 Writer 事务短小有界；网络/模型流/人工审批/容器启停等待均在事务外。
9. 桌面动作执行期间，真人物理键鼠输入拥有最高抢占权（100ms 内中断派发并转入 `PAUSED_BY_USER_TAKEOVER`）。
10. 关闭桌面 UI 不停止后台 daemon；事件图与历史回放均为纯只读投影，永不重新触发模型或工具。

## 五、每问题的原子交付循环

1. 用真实入口（`openbot daemon serve` / CLI / HTTP API / `apps/desktop`）或受控反例复现问题。
2. 定位根因，优先复用 `main@20282291` 已有服务做最小修改；不删除负例、不降低断言、不将必需测试改 skip。
3. 运行相关正反例、任务绑定的 `required_test_ids` 与 `.venv/bin/python scripts/verify.py`（以及 `python3 plan/v1_0_0/tools/validate_plan.py --mode execution`）。
4. 检查 `git diff`，只暂存本问题明确文件（若改了受控资产同步暂存 `release/checksums.json`），创建原子 commit，执行普通 fast-forward push 并核验远端 SHA 与 CI 结果。
