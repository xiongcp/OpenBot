# 当前状态与真正剩下的工作

## 结论

OpenBot 的 `codex/agent-client-observability` 分支已通过 PR #2 正式合入 `main`（最新提交 `20282291`）。当前 `main` 不仅具备扎实的控制面（SQLite Writer、Task/Operation/Approval/Attempt、本地认证 API、CLI），还已合入 `agent_runtime.py`（有界 Agent 审批与执行循环）、`client_routes.py`（受认证客户端控制 API）、`apps/desktop`（双语桌面工作流客户端初版）、`ContainerReadTool`（固定镜像只读 MCP 容器切片）以及 `live_gateway.py`（飞书共享入口、配对与表情回执清理，锁定 `lark-oapi==1.7.5`）。[R01–R05、R24、R25]

下一阶段的重点不再是从零编写上述模块，而是**在既有 `main@20282291` 基础上完成安全边界加固、真实进程崩溃恢复证明、生产级 MCP/Browser 隔离接线、可安装签名桌面包（`.app`/`.dmg`）构建以及真实环境（用户 Mac 与专用飞书租户）的发布门禁验收**。现在仍不宜仅根据绿色 CI 宣布 v1.0.0 已完成，也绝不能推倒重写已合入的新模块。

本次只读核对 GitHub 最新 `main` 代码、仓库信息和已有 CI，并结合两份历史附件更新方案；未连接用户 Mac，未执行新的本机产品测试，未修改、提交、推送、合并或部署产品代码。以下源码风险是待复现与修复线索，不是本次已经成功复现的攻击或故障。

## 固定审查快照（已同步至最新 `main`）

| 项目 | 结果 | 证据 |
|---|---|---|
| 默认分支 `main`（最新） | `20282291`（合入 PR #2，相对原 `98ee0365` 前进 20 个提交） | R01、R25 |
| 原活动分支 `codex/agent-client-observability` | `12074191`（已完全合入 `main`，Ahead 0，Behind 1 merge commit） | R02、R25 |
| 本轮 `main` 新增合入能力 | `agent_runtime.py`、`client_routes.py`、`apps/desktop`、`openbot_feishu/live_gateway.py`、`lark-oapi==1.7.5` 锁定、`RequestConflict` 优先捕获及 POSIX 跨平台类型保护 | R03、R04、R24、R25 |
| 产品版本与入口脚本 | `pyproject.toml` 为 `0.1.0.dev0`；脚本入口含 `openbot` 与 `openbot-feishu`；包发现已含 `services/core/src` 与 `services/feishu_gateway/src` | R05、R25 |
| GitHub 对外入口 | `description`/`homepage` 为空、Topics 为空、`has_pages=false`；Releases 和开放 PR 均为空 | R07 |

不能把任务台账中的已完成项直接换算成 v1.0.0 正式版完成度，也不能把新任务 `PLANNED` 解读成没有代码。执行时应在台账中核对“实现所在 SHA、测试范围、尚缺证据、是否进入候选版本”。

## 最新 `main` 分支 CI 的实际范围

`contracts` 工作流 run `42005019676` 对应 `main@20282291`，三平台全部 `success`；另有新增 `desktop-client.yml` 工作流。[R08、R25]

| 环境 | 实际结果 | 不能由此推导的结论 |
|---|---|---|
| `macos-15 / Darwin arm64` | `399 passed, 2 skipped, 0 deselected`（job `127169467135`） | 未证明用户干净 Mac 上已完成真实飞书人点审批、完整多工具容器隔离、Developer ID 签名安装和升级恢复 |
| `ubuntu-24.04 / x86_64` | `399 passed, 2 skipped, 0 deselected`（job `127169466748`） | 未证明原生 Linux 桌面产品安装、systemd 用户服务与浏览器沙箱边界 |
| `windows-2022 / AMD64` | `399 passed, 2 skipped, 0 deselected`（job `127169467112`） | 未证明 Windows 原生进程树隔离、凭据后端与正式安装包资格 |

跳过的 2 项为需要显式开启 `OPENBOT_NATIVE_TESTS` / `OPENBOT_NATIVE_MCP` 的原生 Docker 容器资格测试。应在相应专门门禁补齐真机证据，不能把 skip 自动算成必需能力 PASS。[R08、R09、R25]

## PR #2 合入 `main` 的 14 个增量提交盘点

在 `620311b4`（只读 MCP 容器切片与审批预览 `sha256:` 修复）之后，PR #2 又推进了 13 个功能/修复提交并合入 `main@20282291`，本计划已全部吸收：[R24、R25]

- **有界 Agent 运行编排（`7c936292`、`4ab8105e`、`fc8f8aa4`、`a72422eb`）**：新增 `services/core/src/openbot/agent_runtime.py` 与 `tests/integration/test_agent_runtime.py`，串联了有界 Agent 审批与执行、保留已验证工具结果的对话角色历史、等待运行完成 trace 持久化并暴露安全中断原因。
- **客户端控制 API 与权限加固（`743a934a`、`9d25a5d1`、`12074191`）**：新增 `services/core/src/openbot/adapters/local_api/client_routes.py` 与 `tests/contracts/local_api/test_client_routes.py`，暴露受认证 daemon 控制 API，绑定 principal 并限制 gateway token 权限，在 `server.py` 中优先于基类 `ValueError` 捕获 `RequestConflict`。
- **双语桌面工作流客户端初版（`b4af1ee5`）**：新增 `apps/desktop/` 与 `docs/evidence/desktop-client.md`，提供双语工作流视图、审批与配置控制初版。
- **飞书官方 SDK 锁定与共享入口（`8a4753e1`、`310c9ee6`、`77b1aa34`、`54e746eb`）**：在 `pyproject.toml` 锁定 `lark-oapi==1.7.5` 并将 `services/feishu_gateway/src` 纳入包发现路径；新增 `live_gateway.py` 共享飞书入口、本地配对、收到消息表情回应与任务完成后移除表情、配置冲突自动同步及心跳生命周期保护。
- **跨平台 POSIX 类型保护（`54b3fdbd`）**：为缺失 POSIX 文件与锁标志的平台补齐类型与分支保护，使 Windows CI 也能完整跑通 399 项测试。

## 当前能力分层（基于 `main@20282291`）

| 层 | `main@20282291` 已有成果 | 走向 v1.0.0 仍要完成的工作 |
|---|---|---|
| 控制面与编排 | SQLite Writer、四实体状态机、认证 API、CLI 入口、`agent_runtime.py` 有界运行切片 | 在真实 `openbot daemon serve` 常驻进程中完成多场景端到端验收、流式取消中断与配额熔断 |
| 任务执行与工具 | OpenAI/Ollama 适配器、文件补丁、Browser、只读 MCP 容器切片（`demo.txt`）、飞书 `live_gateway.py` | 通用 MCP 期限/stderr/元数据准入、Browser 真实网络出口与受批写动作核对、可重载补丁恢复日志 |
| 客户端与 API | `ClientState`、`client_routes.py`、`apps/desktop` 双语客户端初版 | 运行中配置收紧实时阻断、过期游标 `410` 快照恢复、精确目标/Diff 审批预览、原生安全 IPC 边界复核 |
| 原生运行与恢复 | daemon Popen、plist 生成、基础恢复服务与垂直切片 | 移除 `/v1/runtime/recover-epoch` 对客户端布尔值的信任、进程外真实 SIGKILL daemon 恢复证据、移除 Keychain `security -w` 明文 argv |
| 发布与供应链 | `build_pilot_bundle.py` 清单、SPDX 试点与 5 文件 `checksums.json` | 真正构建可安装 `.app`/`.dmg`、launchd/SMAppService 注册、Developer ID 签名公证、备份迁移升级状态机、全量最终资产 SBOM |
| 对外展示与官网 | 大量设计/证据 MD，README 已增补客户端与飞书说明 | 将根 README 改为面向用户的产品入口、解决根 `LICENSE` 缺失与 ADR/SBOM 冲突、建设 `apps/website` 并与真实发行清单联动 |

## 接下来优先补齐的十项重点

1. **真实常驻 Daemon 端到端闭环（复用 `agent_runtime.py`）**：通过真实 `openbot daemon serve` 与 CLI/桌面/飞书入口完成七条核心产品场景，验证多步边界、预算结算与 `OutcomeVerifier`。
2. **恢复隔离可信证明（`V1-013`）**：`/v1/runtime/recover-epoch` 目前仍接收 `old_epoch_isolated` 布尔值（缺省 `true`）；必须改为由服务端 Supervisor 根据实际进程创建身份与容器状态生成隔离证明。[R10]
3. **进程外真实 Daemon 强杀证据（`V1-014`）**：`vertical_slice.py` 目前仍强杀临时 `sleep(30)` 子进程再正常 `writer.close()`；必须对真正持有 SQLite Writer 的 daemon 进程在四个副作用窗口注入 `SIGKILL` 并核对 `UNKNOWN` 恢复。[R11]
4. **秘密不进入 `argv`（`V1-015`）**：`broker.py` 的 Keychain 写入仍通过 `security ... -w <secret>` 传参；需改为非回显 stdin 或受控原生桥接，并做全链路 canary 扫描。[R12]
5. **MCP 有界协议与生产准入（`V1-016`、`V1-017`）**：复用 `ContainerReadTool`，补齐通用 client 的 `init_timeout_ms` 阻塞读写、持续排空 `stderr`、完整 JSON-RPC ID 校验、从受信 lock 消费摘要及 daemon 被强杀后的孤儿容器回收。[R13、R24]
6. **Browser 实际出口与写动作核对（`V1-018`、`V1-019`）**：把重定向、子请求、DNS 变化、下载隔离区与受控网络出口真正接通，并用独立目标效果核对替换传入 `driver_outcome` 字符串的合成路径。[R14]
7. **可重载文件补丁日志（`V1-020`）**：为 `PatchCommitJournal` 补齐带版本/摘要与 `fsync` 顺序的磁盘格式，支持新进程在崩溃后重新加载恢复，不谎称跨文件全局原子回滚。[R23]
8. **客户端 API、审批 Diff 与桌面安全边界（`V1-022`..`V1-026`）**：在 `client_routes.py` 与 `apps/desktop` 基础上补齐运行中收紧策略实时阻断、游标过期 `410` 恢复、真实文件 Diff 审批预览以及受限原生 IPC 反例验证。[R03、R04、R25]
9. **真实飞书租户与本地模型门禁（`V1-021`、`V1-027`）**：基于已合入的 `live_gateway.py` 与 `ollama.py`，在授权飞书测试租户完成真人点按审批、取消、断网重连闭环，并锁定本地模型真实权重 digest 与 `OFFLINE` 零外发证据。[R15、R25]
10. **可安装签名桌面包、升级事务与公示一致性（`V1-029`..`V1-055`）**：交付真正可安装的签名公证 `.app`/`.dmg`、用户会话服务、一致性备份与升级状态机、根 `LICENSE` 决议、面向用户的 README 以及同源联动的 `apps/website`。[R16–R20]
