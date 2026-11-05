# 架构补齐与接口设计

以下为面向当前实现的增量设计。保留已存在的控制面、Writer、审批和 API；不更换整个框架，也不让外部 Agent 框架获得工具执行权。

已有 TaskStateService.complete/verify_outcome 与持久 BudgetService，应直接复用。新 runtime 负责组合这些服务，不另造一套成功判定或预算数据库。[R21]

## 三处还需要单独修补的组合问题

**模型调用期限与取消。** 现有文本 SDK transport 已有较完整的真实取消与总期限，但 tool proposal 适配路径仍等待完整的字节列表，cancel 主要写内存标记。应统一成一个真实流式端口，让超时/取消能中止实际挂起请求，再把预算结算接到持久服务。不能因为 UI 已显示停止就认为网络调用已经结束。[R22]

**审批预览。** 620311b4 已修复 binding_hash 的 sha256: 前缀，不应重新列为未修问题；本地 API 的某些预览仍是固定 effect 或简略 preview 文本。[R24]需要从不可变提案生成真实目标、Diff、数据外发和有效期 DTO；用户看到的内容必须对应绑定摘要，不只是一个泛化的“允许执行”按钮。[R10]

**补丁日志恢复。** 文件旧/新 hash 与逐文件受控写入已有实现，应保留；当前 PatchCommitJournal 直接 write_bytes，并主要依靠对象内存 entries 恢复。补可重载的日志格式、摘要和持久化顺序，测试真实新进程在中途强杀后的部分恢复。不能把多文件部分完成声称成跨文件原子回滚。[R23]

## 运行时的最小组成

| 模块 | 输入与输出 | 约束 |
|---|---|---|
| Task ingress | CLI、桌面、飞书输入 → 同一持久 Task | 身份由服务端可信边界产生；重复请求返回同 Task |
| Scheduler | QUEUED Task → 单活动 run | 持久租约、资源锁和 epoch；进程出生时间/容器 ID 可核对 |
| AgentRuntime | 目标、运行配置、上下文 → 有界模型提案 | 模型请求在短事务之外；步数、时间、token、费用与重试有限 |
| ModelGateway | 已授权数据与请求 → 完整流式结果/usage | 固定适配器；禁隐藏重试与工具 helper；中断费用保守记账 |
| Broker | 不可变 Operation → READY/CLAIMED/DISPATCHING | 提案、批准、消费、派发分开；执行前再次验证身份/取消/策略/资源 |
| Executor adapters | 有效 dispatch → 实际工具回执 | 原生/容器边界分清；缺能力时明确不可用 |
| OutcomeVerifier | 产物、外部回执、未决动作 → 完成判断 | 模型说“完成”不直接设 SUCCEEDED；未知效果保持核对状态 |
| Client projection | 权威状态/events → 脱敏 DTO 与图 | 回放只读；不收集隐藏推理；不把 UI 临时状态写成事实 |
| Supervisor | 进程和执行域清单 → 可信存活/终止证明 | UI 不拥有 daemon 生命周期；不能仅凭 PID 或租约超时接管 |

## 第一条垂直切片怎么做

从真实 `openbot daemon serve` 启动 daemon，再通过认证 API 创建任务。调度器取得 run，模型读取已授权的工作区摘要并返回完整结构化提案。Broker 产生待审批 Operation，CLI/UI 的批准只让其 READY。调度器通过 claim 和 dispatch 复核后调用一个隔离、锁定版本的只读 MCP；将结果注册为 Artifact，由 OutcomeVerifier 检查内容/来源/未决动作，最后原子提交状态、审计与 outbox。

验收不能通过测试代码直接插入成功状态或逐个调用内部状态迁移。记录端到端 trace，并从实际执行器或独立受控服务器读取请求数和效果数；模型调用计费、工具接收与实际业务效果是三个不同指标。

## 持久状态与执行权

继续使用 Task、Operation、Approval、Attempt 四实体。Task 表示用户任务；Operation 表示一次不可变意图；Approval 表示对其绑定内容的授权；Attempt 表示某次实际派发。Operation 的 provider 幂等键稳定；新 Attempt 使用新 dispatch ID；同 Attempt 重传保持原 dispatch ID。

批准与派发之间存在用户编辑、撤销、取消和进程换代的时间窗口。所有这些条件必须在派发前复核。已经 CONSUMED 的授权不能退回 APPROVED。已有 UNKNOWN 的受保护资源保持 quarantine，不能换一个任务 ID 绕开。

不要新增一套平行“聊天成功状态”。UI 读取投影后的权威状态，必要时分别展示“任务已停止继续派发”和“过去动作仍在核对”。

## 真实恢复与故障注入

把崩溃控制器放到产品进程外。控制器在可确认的屏障点强杀实际 daemon/worker，独立效果服务持续保存 operation key、请求次数、效果次数和回执。至少覆盖 claim 已提交、dispatch 已提交但未发包、效果已发生但回执未落盘、结果已提交但响应丢失四个窗口。

重启先确认旧执行域归属与生存状态；由受信 Supervisor 采集启动时间、可执行身份、process group、容器 ID 和 epoch。不能确认已经隔离时保持 quarantine。恢复 API 请求只表达“请求核对”，不接受客户端用 `old_epoch_isolated=true` 证明事实。[R10、R11]

## ClientState 的复用与修补

2993593a 新增的 ClientState 已提供配置 CAS、run 起始配置快照、允许字段事件和脱敏等基础；其证据明确不代表完整热更新和 Agent 接线。[R03、R04]

保留现有 23 表与迁移体系，先审查复用 events/checkpoint 的查询与体积上限。事件应增加稳定幂等来源键；验证 run/task/operation/attempt/artifact 的归属，拒绝跨 run 引用；明确最大事件数、内容字节、保留期与分页。若在真实负载下现有 JSON 投影无法满足查询，再通过独立迁移新增索引/投影表，而不是提前无限扩展 schema。

建议事实事件最小 DTO：schema_version、event_id、seq、run_id、task_id、parent_event_id、kind、occurred_at、source、可选 operation_id/attempt_id、状态原因码、artifact_refs、redacted_summary。工具输入只展示允许字段；秘密、原始模型推理、全量环境变量不进入事件。

## 客户端 API 增量合同

以下路径是待实现/核对的目标合同，不能写成当前可调用保证。先同现有 OpenAPI 与 client-control 设计对齐，避免重复路由。[R04]

| 能力 | 目标接口/行为 | 负面验收 |
|---|---|---|
| 读取设置 | GET /v1/client/settings，返回 revision、有效配置和激活状态 | readonly 不读 secret；跨 profile 拒绝 |
| 预览设置 | POST /v1/client/settings/preview，返回 diff、canonical hash、expected revision | 无写入；重复键、未知字段拒绝 |
| 应用设置 | POST /v1/client/settings/apply，绑定 preview 与幂等 request_id | 过期 revision 冲突；旧配置完整保留 |
| 创建/启动任务 | 对齐现有 /v1/tasks 与明确的 start 行为 | 不让普通 readonly 或 gateway 调管理路径 |
| 运行事实 | snapshot + 分页 trace/SSE；cursor 对应持久 seq | 过保留期返回 410 后重取快照；不静默漏事件 |
| 审批/取消 | 复用原 nonce、TTL、binding、revision 合同 | 旧批准、重复回调、撤销后派发均有反例 |
| 独立健康 | daemon、provider、gateway、executor、client 分项 | UI 在线不代表模型/容器在线 |

状态码与错误体保持已有统一 error code；配置冲突使用可解释的 revision conflict；SSE 不把“连接恢复成功”当作“缺失事件已补齐”。

## 配置激活协议

模型/预算变更通常 NEXT_RUN，语言和显示偏好可 APPLIED；连接相关设置可 RECONNECTING；需要新进程/执行域的设置为 RESTART_REQUIRED；无效配置为 REJECTED。必须在服务端返回原因和受影响范围。

权限收紧、owner 撤销、禁止网络等安全变化立即影响下一次 dispatch，即使旧 run 保留起始配置快照，也不能使用旧快照越过新限制。权限放宽不自动扩大在途任务授权，必要时新建提案/重新审批。运行快照用于复现，不作为绕过当前策略的许可。

## Browser 与 MCP 的边界

Browser 的页面拦截和代理只是控制手段。强网络声明需要实际阻断直连、UDP/QUIC、DNS/IP 变化、重定向、Service Worker、扩展、下载和控制 API 访问；代理退出时验证失败即停。记录 Chromium 自身 sandbox 与外层隔离各自的证据。不要用 `--no-sandbox` 或弱凭据参数消除弹窗后继续宣称同等安全。

MCP 严格固定已支持的协议版本与 server digest。初始化、工具列表、调用和退出均有总 deadline、帧/流量上限、并行 stderr 排空及进程清理；完整校验 JSON-RPC ID/result/error。新版 draft 的规则不能直接套用到当前锁定的 initialize 协议。metadata 的 readOnly/idempotent hints 是输入，最终 retry_class 由本地审核合同决定。[R13、W02]

620311b4 的专用 ContainerReadTool 已做真实 Docker 读切片，协议锁定 2025-03-26；复用该实现后再接生产准入，不把参考文档中的其他协议版本当作已支持。容器所有权与 cleanup 目前还需持久化到权威恢复链；正常 finally 清理不能证明实际 daemon SIGKILL 后也可重收。测试从锁文件读取受信镜像/server 摘要，不能每次对“当前可变文件”重算摘要后自动视为已准入。[R24、W02]

## 模型质量与上下文

先做短任务、少量明确工具和可核对产物。上下文包含目标、约束、当前批准范围、最小相关文件和来源，不把网页/技能内容升格成用户命令。紧凑工具 schema 只能裁去未开放能力，不能减掉服务端验证约束。文本 JSON 兼容解析如启用，仍要通过同一 schema、Broker 和预算。

空闲摘要和缓存优化放到性能问题有证据后实施；摘要保留来源和未决 Operation，不得“总结掉” UNKNOWN。先保证一次真实调用可追踪，再优化 token 和首字延迟。

## 四层混合电脑控制（Hybrid ACI）与常驻鲁棒性加固（V1-068 至 V1-084）

本统一版 v1.0.0 计划将原后续阶段的电脑控制、常驻自愈与生态扩展完整纳入 v1.0.0 交付闭环：[R14、R24、R25、W02、W05]

1. **L1 工作区与通用隔离 MCP 层（`V1-075`, `V1-076`）**：解除 `agent_runtime.py` 单文件 `demo.txt` 硬编码，动态路由 `workspace.list/read/search/propose_patch/apply_patch`，并将 `ContainerReadTool` 升级为通用 `McpContainerExecutor`（内置准入锁定 SHA-256 的 `git-inspector`、`sqlite-reader`、`doc-extractor`）。
2. **L2 Playwright 真实 CDP 浏览器层（`V1-077`, `V1-078`）**：替换 `--dump-dom`，通过受管 Playwright 会话提取绑定 `BoundElementRef` 的紧凑 ARIA 语义树；生成带红框标注的审批预览局部截图，并在点击前毫秒级复验文字与金额。
3. **L3/L4 macOS 原生 `AXUIElement` 控件树与物理键鼠抢占暂停（`V1-079`, `V1-080`）**：针对白名单应用提取原生窗口控件树（硬拦截钥匙串与密码窗口），派发前复验前台窗口焦点与 PID（防 `DESKTOP_FOCUS_DRIFT`），并监听物理键鼠输入——真人移动鼠标或按键 100ms 内立即挂起为 `PAUSED_BY_USER_TAKEOVER`。
4. **常驻自愈与 72h Chaos 浸泡（`V1-068` 至 `V1-074`）**：容器创建前先写 `container_intents` 预写日志确保跨 `SIGKILL` 100% 回收孤儿容器；5 分钟崩溃超 3 次触发安全维护态；支持 Mac 合盖睡眠唤醒时钟对齐、SQLite WAL 空闲自动截断、512MB 磁盘低水位硬拦截、`deque(maxlen=2000)` 环形诊断缓冲、三态熔断器断点续跑、`openbot doctor --fix-safe` 与 72 小时 Chaos 浸泡门禁。
