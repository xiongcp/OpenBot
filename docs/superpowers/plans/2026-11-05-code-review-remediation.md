# OpenBot 代码审查与改进实施计划

> 执行本计划时使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans`，逐项补失败测试、最小修复、复核证据。本轮仅审查、验证与制定计划，不授权自动修改安全策略、提交、推送、部署或发布。

**Goal:** 保留既有控制面，把当前实现收敛为可真实运行、可安全恢复、可独立验收的本地 Agent 产品。

**Architecture:** 沿用单 owner/profile、Python daemon、SQLite Writer、Task/Operation/Approval/Attempt、统一 Broker 和薄客户端。先修复权限、恢复、结果与证据链，再补齐真实产品路径；不另建第二套状态机，不复制其他 Agent 的自治执行循环。

**Tech Stack:** Python 3.12、SQLite、现有模型适配器、容器/MCP/浏览器工具、Tauri 2 与静态 ES modules、飞书 gateway。

**Spec:** [产品范围](file:///Users/admin-1234/work/OpenBot/docs/00_scope.md#L11)、[架构不变量](file:///Users/admin-1234/work/OpenBot/AGENTS.md#L9)、[组件复用边界](file:///Users/admin-1234/work/OpenBot/docs/12_component_reuse.md#L43)、[v1 任务与验收](file:///Users/admin-1234/work/OpenBot/plan/v1_0_0/tasks/backlog.json#L6)。本报告中的修复项是当前审查建议，不代表原有状态记录已经被改写。

## 全局约束

- 模型只能提出动作；身份、授权、策略、预算、派发与结果判定由可信服务端控制。
- 所有副作用经过同一 Broker；UI、飞书、Skill、MCP、Provider 不能旁路执行。
- 保留审批一次性消费、两阶段派发复核、UNKNOWN/RECONCILING 与取消语义。
- 无经资格验证的隔离后端时拒绝不可信执行；不降级宿主 shell，不隐式云回退。
- 真实凭据不进入源码、普通日志、模型上下文、WebView、产物或诊断包。
- 涉及公共 schema、数据库迁移、锁文件、安全策略的实施，先修改相应 ADR/合同再编码；本轮不做这些修改。
- 原生平台、真实服务、合成测试、静态代码审查分别报告；其他项目的能力不能充当 OpenBot 的验收证据。
- 不扩展为企业多租户、分布式服务或通用插件市场；优先完成 macOS ARM64 上可复核的窄产品范围。

## 1. 审查基线与方法

- 日期：2026-11-05（本地）；验证日志使用 UTC，因此部分时间为 2026-11-06。
- 源码：`main@3407a30b4f3d47ab0bcd273037e4387ebfa43e1b`。
- Git tree：`eb0920af4f2c603acfd2c482e5472617a0ea5b45`。开始审查时工作区干净。
- 环境：Darwin arm64；本机 Python 3.12.14。仓库 CI 准备脚本指定 Python 3.12.12，本次结果不冒充该解释器或其他机器上的结果。
- 方法：项目范围/合同对照、分域源码审查、调用路径核验、现有测试、临时合成反例、本地开源实现对照。
- 范围覆盖核心运行时/存储/审批、模型/工具/飞书、桌面/原生/发布、测试/CI/验收证据。属于风险导向的跨模块审查，不是逐行无遗漏证明、云安全扫描或完整渗透测试。
- 本轮不使用真实模型密钥、不发送飞书消息、不启动用户生产 profile、不注册系统服务、不签名发布、不复制上游源码。

### 1.1 代码规模盘点

以下是 Git 跟踪的源码文件与物理行数（含空行、注释），仅用于说明审查范围，不作为质量或完成度指标。

| 范围 | 文件数 | 行数 |
|---|---:|---:|
| core Python | 108 | 22,651 |
| 飞书 gateway Python | 11 | 1,723 |
| Python tests | 109 | 16,669 |
| desktop JS/TS/Rust | 14 | 1,318 |
| native 源码 | 4 | 105 |

### 1.2 状态记录不能直接当产品完成率

[根任务表](file:///Users/admin-1234/work/OpenBot/tasks/backlog.json#L1) 的 96 项状态为 DONE 4、VERIFIED 12、IN_PROGRESS 67、BLOCKED 3、TODO 10；[v1 任务表](file:///Users/admin-1234/work/OpenBot/plan/v1_0_0/tasks/backlog.json#L35) 的 84 项全部 VERIFIED。

这两份表范围不同，不能仅凭数字认定互相矛盾：原三平台 M3 与 macOS 首发范围应保留区别。但当前记录缺少足以自动核验“哪个能力、哪个平台、哪个候选制品通过哪个真实测试”的连接。尤其 [公开能力状态](file:///Users/admin-1234/work/OpenBot/docs/project-status.json#L17) 已把多个能力标 VERIFIED/NATIVE，而 [README](file:///Users/admin-1234/work/OpenBot/README.md#L9) 仍描述真实运行编排待补、桌面任务 TODO；首页、历史任务和公开状态必须由同一证据模型派生。

## 2. 项目到底做什么

OpenBot 的目标是**由用户控制、运行在本机、可通过飞书和桌面/CLI 操作的任务型 AI 助手**：在授权工作区检索与理解代码、生成补丁、申请批准、执行受控工具、保存产物，并在取消、断网、进程重启后给出可信状态。

它不只是聊天界面，也不是模型 Provider 的简单包装。核心差异在于把“模型建议”“用户批准”“真正派发”“可核验结果”拆开管理。Task 代表用户目标，Operation 代表具体动作，Approval 绑定批准内容，Attempt 代表一次执行尝试；未知结果不能直接当失败重试，更不能凭模型文字宣称成功。

当前仓库已不只是设计包：已有实质运行时、控制 API、工作区工具、桌面工程和测试。但“存在实现”和“已完成真实产品链路、原生隔离或发行资格”仍是不同结论。应把它定位为**正在收敛的本地 Agent 工程原型与控制面实现**，本次证据不足以认可对外完整 v1 RC 声明。

## 3. 已独立复现的验收证据问题

### R-E01 · P1：RC 元数据校验不核对用例失败与门禁成功之间的矛盾

**证据：** [validate_plan.py:325](file:///Users/admin-1234/work/OpenBot/plan/v1_0_0/tools/validate_plan.py#L325)、[同文件:474](file:///Users/admin-1234/work/OpenBot/plan/v1_0_0/tools/validate_plan.py#L474)、[同文件:503](file:///Users/admin-1234/work/OpenBot/plan/v1_0_0/tools/validate_plan.py#L503)。RC 模式只检查任务/门禁状态标签；用例允许 FAIL/null result；RC 分支还没有执行 execution 分支中的 SHA 格式检查。

**本轮合成反例：** 仅在内存中把 140 个用例全部改为 FAIL、result 清空，把 84 个任务 verified_on_sha/commit_sha 清空；`cases()`、`task_fields()`、`gates()` 仍接受这些数据，返回 140/84/8。未修改仓库任务记录。

**影响：** 该脚本明确自称“不是产品测试”，这一点应保留；缺陷是即使作为 RC 记录一致性检查，它仍会放过相互矛盾的状态。因此不能把其 PASS 用作产品放行证据。

**修复与验收：** 必需用例非 PASS、无结果证据、候选 SHA/制品不符、未获明确范围决策的 SKIPPED/NOT_APPLICABLE，均阻断对应门禁；由用例结果派生门禁状态，而不是相信手填 PASS。增加上述反例的永久回归。

### R-E02 · P1：验证 run 可覆盖旧失败，日志哈希写入后未被验证

**证据：** [scripts/verify.py:69](file:///Users/admin-1234/work/OpenBot/scripts/verify.py#L69) 对已有 run 目录使用 `exist_ok=True`，随后覆盖报告与同名日志；[同文件:175](file:///Users/admin-1234/work/OpenBot/scripts/verify.py#L175) 验证状态/run_id/source_sha/退出码，却不读取日志并校验其哈希，也不要求固定的检查集合。

**本轮合成反例：** 在全新临时目录用相同 run_id 先执行退出 1 的命令，再执行成功命令，旧失败被覆盖；随后修改、删除日志，`validate_verification_report()` 均返回 True。仅删除了本反例自己创建的合成日志。

**影响：** 失败历史和原始证据不能可靠保留，报告可在缺证据时被接受。当前该验证函数的调用仅在测试中找到，因此这是验收基础设施缺陷，不是已证明的线上权限绕过。

**修复与验收：** run 目录排他创建且不可复用；验证完整预期检查集合、命令/阶段、结束状态、候选树/锁/制品、日志存在与哈希。相同 ID 重跑必须拒绝，或生成新的 run ID 并保留关联，不能覆盖原 run。

### R-E03 · P1：完成记录只有统一 SHA 文本，不足以支持真实环境验收

[140 用例表](file:///Users/admin-1234/work/OpenBot/plan/v1_0_0/testing/test_cases.json#L16) 中 139 个 PASS 的 result 都是同一条 `Verified on d38d77eaa7381b106a8f3302ca3c62c192d848b0`；另外一项为 Intel/Rosetta 延期。118 项声明需要真实环境，且 140 项都标 BOUND_AND_VERIFIED。

这不能证明这些测试从未在其他地方运行；但当前字段没有逐用例的命令、退出码、日志/制品摘要、环境和收集者绑定，本轮也没有获得这些真实运行证据。应撤回无法证实的公开完成声明或改为“实现存在/合成验证/待原生验证”，不要把全部模块推倒重做，也不要未经复核批量修改原 OB 任务。

### R-E04 · P2：默认 CI 不执行可选 SDK 故障用例，桌面 CI 缺跨层联动触发

[pyproject.toml:23](file:///Users/admin-1234/work/OpenBot/pyproject.toml#L23) 将 OpenAI SDK 放在可选组；[pr.yml:19](file:///Users/admin-1234/work/OpenBot/.github/workflows/pr.yml#L19) 和 [pr-gate.yml:19](file:///Users/admin-1234/work/OpenBot/.github/workflows/pr-gate.yml#L19) 仅同步默认组。默认绿灯不能证明 SDK 序列化、故障、取消链路通过；应增加独立锁定 SDK 组的 loopback job，保持基础环境检查独立。

[desktop-client.yml:4](file:///Users/admin-1234/work/OpenBot/.github/workflows/desktop-client.yml#L4) 的 paths 只关注桌面和构建脚本，后端 client API/合同变化不会触发桌面联动检查。需要跨层合同测试及相应触发路径，而不只增加截图或投影单测。

合成反例源码：[evidence_probes.py](file:///tmp/openbot-review-20261105/evidence_probes.py)；结果：[evidence_probe_results.json](file:///tmp/openbot-review-20261105/evidence_probe_results.json)。这些临时证据未加入产品源码，后续实施应把相应断言纳入仓库测试。

## 4. 工具、文件与飞书审查

分级：P1 表示首发必须修复的正确性、安全或发布证据问题；P2 表示有明确缺陷，但影响面受限或对应路径尚未默认启用。没有发现经本轮证明的 P0，不等于证明不存在。置信度与严重性分开：下面注明主审复现、独立审查合成反例或静态核验。

可达性：A＝真实入口已接线；B＝运行时支持，但是否暴露给模型取决于配置/工厂；C＝独立适配器或资格验证 helper，不能当作默认生产路径已启用。

### R-I01 · P1 / A：飞书事件持久接收后没有 ACK 给 worker

- **证据：** [live_gateway.py:273](file:///Users/admin-1234/work/OpenBot/services/feishu_gateway/src/openbot_feishu/live_gateway.py#L273) 只打印 `forward_event()` 的返回结果；[worker:329](file:///Users/admin-1234/work/OpenBot/services/feishu_gateway/src/openbot_feishu/live_gateway.py#L329) 则等待 stdin 的 `ACK\n`，7 秒后报持久接收未确认。
- **触发/影响：** 正常飞书事件已被 daemon 接收，worker 回调仍失败，触发渠道重投递/错误。不能由此直接推断工具副作用重复，inbox 去重仍是另一层保护。
- **验证：** 独立审查使用真实合成子进程与返回 201 的假 daemon，事件接收一次、子进程因未收到 ACK 退出；主审核对了双方协议代码。未连接真实飞书。
- **修复：** durable admission 成功后发送与事件关联的确认；失败不确认；表情/展示 API 不阻塞确认路径。验收成功、失败、重复、连续两个事件，以及确认丢失后重投递。

### R-F01 · P1 / B：文件已写入但 journal 未标 APPLIED 时，恢复误报“未应用”

- **证据：** [patch.py:197](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/tools/workspace/patch.py#L197) 先原子替换文件，再更新 journal；[commit_journal.py:152](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/tools/workspace/commit_journal.py#L152) 对非 APPLIED 项直接记 `FAILED_NOT_APPLIED`，没有核对磁盘。写后 journal flush 抛错也可能走该分支。
- **触发/影响：** 文件替换后、journal 持久化前进程死亡；下一次恢复错误报告没有修改，实际上工作区已有新内容。会误导用户后续核对和重试。
- **主审合成复现：** 临时文件 `old\n`，备份与 PREPARED 已持久化，调用 `write_atomic(..., b'new\n', ...)` 后直接重新加载 journal；恢复返回 `FAILED_NOT_APPLIED`，磁盘仍为 `new\n`。
- **修复：** PREPARED/失败不等于未执行，必须用旧/新内容摘要核对；无法确定则保留 UNKNOWN/冲突。逐个注入 rename 前后、目录 fsync、journal flush 失败；不得覆盖用户随后修改的文件，不宣称跨文件原子性。

### R-F02 · P2 / B：文件大小限制发生在完整读取之后

- **证据：** [filesystem_guard.py:152](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/tools/filesystem_guard.py#L152) 的读取循环一直读到 EOF；[read.py:174](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/tools/workspace/read.py#L174) 等上层随后才检查预算。
- **影响/验证：** 独立审查以 64 字节限制读取 2 MiB 合成文件，完整读取后才拒绝；目录列表路径也会读取内容。大文件可使 daemon 内存和取消延迟失控，不必构造外部攻击流量。
- **修复：** 把字节上限、总 deadline、取消检查放在文件句柄读取层；先 fstat，再最多读取 limit+1，应对读取中增长；列表不为元数据读取整个正文。

### R-F03 · P2 / B：只观察目标路径就会创建目录

- **证据：** [filesystem_guard.py:187](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/tools/filesystem_guard.py#L187) 的 `observe()` 调用 `create_dirs=True`；它被补丁提案前的观察使用。
- **主审复现：** 空临时工作区调用 `observe('not-approved/nested/file.txt')` 后，这两个目录已存在，未经过批准。
- **修复：** 观察必须无副作用；不存在的父路径返回缺失状态或拒绝，目录创建只能作为批准动作执行。验证提案失败、拒绝、取消均不改变工作区；不要用“目录不是文件”豁免授权边界。

### R-A01 · P2 / C：MCP 检查的 executable 与实际启动 argv 不绑定

- **证据：** [mcp/client.py:32](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/tools/mcp/client.py#L32) 检查 `manifest.executable`、digest 字符串形状；[实际启动:122](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/tools/mcp/client.py#L122) 使用独立 `manifest.argv`，直接启动宿主子进程。
- **验证：** 独立合成反例中 executable 为 `/usr/bin/false`，argv 为 Python，握手仍成功；主审核验字段没有形成执行物绑定。
- **修复：** 准入对象绑定真实可执行文件、argv 和已验证资产摘要；不可信 MCP 必须交给合格隔离执行器。校验拒绝须发生在 spawn 前。不能把当前直接 Popen helper 当成沙箱证明。

### R-A02 · P2 / C：MCP 初始化有超时，tools/call 没有总 deadline

- **证据：** [mcp/client.py:195](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/tools/mcp/client.py#L195) 写入、`read_bounded_stream()` 及超长行的 drain 均可阻塞；只限制字节量不能限制等待时间。
- **验证：** 独立合成 server 握手后保持静默，调用直到外部 watchdog 回收该测试进程才返回。未使用真实第三方 MCP。
- **修复：** 写、读、drain 共享绝对 deadline；取消/超时后回收并核验进程状态，结果不明记 UNKNOWN，不换 request ID 自动重发。

### R-A03 · P2 / C：容器 intent 被清除不代表容器已回收

- **证据：** [container_executor.py:205](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/tools/mcp/container_executor.py#L205) 正常返回固定 `cleanup_verified=True`，finally 无条件 mark_reclaimed；[reaper:221](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/tools/mcp/container_executor.py#L221) 缺少回收 callback 时默认成功。
- **验证：** 独立合成 runner 抛 TimeoutError 后 intent 仍被清除；不提供引擎回收回调也宣称已回收。未启动容器。
- **修复：** 必须凭已登记容器身份和引擎的 stop/wait/remove 结果清除 intent；引擎不可用、进程死亡或缺回调时保留待回收状态。将“请求回收”和“证实回收”分开。

### R-A04 · P2 / C：LOCAL_MODEL_RUNNER 标签可让远端绕过 OFFLINE 判定

- **证据：** [egress.py:133](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/policy/egress.py#L133) 使用 `surface == LOCAL_MODEL_RUNNER or is_loopback`，有 attestation 就提前 ALLOW；OFFLINE 远端拒绝在后面。
- **验证：** 独立合成请求使用 OFFLINE、空域名白名单、远端地址和该 surface，得到 `VERIFIED_LOCAL_LOOPBACK`。未发现默认 daemon 会构造该组合，不上升为已证实线上出口绕过。
- **修复：** 必须同时核对实际目的地址与 attestation；远端不能因标签变成本地。覆盖所有 surface×网络模式×目的地矩阵，特别是重定向、代理及 attestation 目标不匹配。

### R-A05 · P2 / C：Ollama 请求忽略总 deadline，响应无累计字节限制

- **证据：** [ollama.py:169](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/providers/ollama.py#L169) 不检查请求 deadline；[transport:83](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/providers/ollama.py#L83) 用 socket timeout 和无界 `resp.read()`。
- **验证：** 独立假 transport 收到已经过期的请求，仍被调用并结算成功。本地模型不自动云回退这一点应保留。
- **修复：** 派发前检查剩余时间，传输中执行累计字节、总时限和取消；不能把 socket 单次读超时当总预算，也不能把中断 usage 当 0。

### R-A06 · P2 / C：浏览器只检查入口 URL，不约束后续网络请求

- **证据：** [browser/session.py:150](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/tools/executors/browser/session.py#L150) 核对初始 host 后直接启动 Chromium；没有把重定向、iframe、子资源请求交给出口判定，且继承环境、`communicate()` 完整缓冲输出。
- **边界：** 静态路径缺陷；本轮没有启动真实浏览器证明网络泄漏，不能将另一处 network-policy 单测当作此入口已受保护。
- **修复：** 将该执行入口与真实强制出口连接，使用最小环境和有界输出；先双 loopback server 测允许页跳向拒绝目标，再在资格环境测 Service Worker/WebSocket 等流量。失败时不使用 no-sandbox。

## 5. 桌面、安装与发布审查

### R-D01 · P1：批准界面没有呈现完整写入影响

- **证据：** [app.js:104](file:///Users/admin-1234/work/OpenBot/apps/desktop/ui/app.js#L104) 只使用 `args_preview`，忽略截断、diff 和漂移字段；[client_routes.py:87](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/adapters/local_api/client_routes.py#L87) 不展开 bundle 的已暂存文件，预览只剩 bundle ID。
- **验证：** 独立调用真实预览序列化：bundle 的目标/diff 为空；长 inline 补丁截断部分未显示，但完整批准内容会被执行。主审确认两端字段处理。
- **影响：** 不是越过后端 Approval，而是用户批准时缺少实际影响信息，写操作不得以这种确认视为合格 UX。
- **修复：** 服务端从已绑定 canonical Operation/Artifact 生成权威预览；支持完整分页/展开、多文件与原始内容摘要；不能只因截断预览有摘要就认为用户已知情，无法确认时禁批。显示过期/漂移，提交仍由服务器复验。

### R-D02 · P1：UNKNOWN 核对合同不一致，主 UI 未接通核对闭环

- **证据：** [Rust IPC:151](file:///Users/admin-1234/work/OpenBot/apps/desktop/src-tauri/src/lib.rs#L151) 发送 `CONFIRMED_NOT_EXECUTED`，而 [reconciliation.schema.json:14](file:///Users/admin-1234/work/OpenBot/contracts/reconciliation.schema.json#L14) 要求 `CONFIRMED_FAILED_NO_EFFECT`；[app.js:158](file:///Users/admin-1234/work/OpenBot/apps/desktop/ui/app.js#L158) 只有状态提示。
- **验证：** 独立真实 schema 校验拒绝前者、接受后者。向导 helper 的测试却把错误值当合法，所以 helper 绿灯不证明真实 API 可用。
- **修复：** 对齐 schema、IPC 和 UI，接通证据上传/归属校验/版本 CAS/提交与结果反馈；KEEP_UNKNOWN 不得被显示为成功，“确认无副作用”也不能自动触发重放。

### R-D03 · P1 / 安装接线缺口：daemon 健康不代表能服务桌面

- **证据：** [daemon_installer.py:85](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/daemon_installer.py#L85)、[同文件:186](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/daemon_installer.py#L186) 的启动参数没有 `--workspace-root`；[cli.py:667](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/cli.py#L667) 仅在该参数存在时挂载 ClientRoutes。
- **影响：** installer 启动的实例可以 health 成功，但 client snapshot 返回 404。安装器尚未接入默认桌面启动；plist 的 RunAtLoad/KeepAlive 为 false，不能仅凭 plist 文件称常驻服务已完成。
- **修复：** 明确 profile/workspace 绑定和受管启动方式；验收真实 snapshot、任务创建、关闭窗口后可访问及重连，不止 GET health。注册用户服务仍需用户授权。

### R-D04 · P1：停止操作只信任旧 PID，可能误终止无关进程

- **证据：** [daemon_installer.py:143](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/daemon_installer.py#L143) 读 session PID；[stop_daemon:231](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/daemon_installer.py#L231) 即使 health 不成功也可能 SIGTERM/SIGKILL，没有进程出生身份核验。
- **触发：** daemon 退出后残留 session，PID 被系统复用，再调用 stop/restart/uninstall。
- **验证：** 独立 mock 信号的反例确认 `running=false, health_ok=false` 仍选择对旧 PID 发信号；没有终止真实进程。主审核对该分支。
- **修复：** 使用受管服务句柄或平台可核验实例身份；无法证明所有权时不发信号。停止完成必须以实例确实退出为准，不能删 session 就宣称停止。

### R-D05 · P1 / 发布阻断：签名与升级结果由输入标签替代真实动作证据

- **证据：** [packaging_auditor.py:119](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/packaging_auditor.py#L119) 信任 `signature_verified`，比较的是与 candidate.version 独立传入的 target_version；[maintenance.py:353](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/storage/maintenance.py#L353) 接受 `candidate_health_ok` 后直接返回 UPGRADED_ACTIVE，没有执行候选替换、迁移、启动验证。
- **验证：** 独立合成候选 0.1.0、当前 1.0.0、另传 target 2.0.0、签名 true，得到 verified=true；主审核对了验证与升级函数。备份/恢复本身有实质代码，不应一并说成空壳。
- **边界：** helper 未连接生产 updater，不是已证实远程更新漏洞；但不足以支撑“真实安全升级与回滚已经验收”。
- **修复：** 从真实签名清单绑定版本、通道、摘要与撤销信息；升级状态从实际文件/进程/数据库切换事实产生。若首发不做自动更新，明确采用经过验证的手动更新路径，不必为功能数量赶制 updater。

### R-D06 · P2：设置等操作后，审批按钮会保持禁用

- **证据：** [app.js:20](file:///Users/admin-1234/work/OpenBot/apps/desktop/ui/app.js#L20) 的 finally 只恢复 `[data-mutation]`；[审批按钮:113](file:///Users/admin-1234/work/OpenBot/apps/desktop/ui/app.js#L113) 没有该属性；[render key:143](file:///Users/admin-1234/work/OpenBot/apps/desktop/ui/app.js#L143) 不含 busy/时间变化。
- **验证：** 独立内存 DOM 加载真实 app.js，路径为“初始可用→切换语言→禁用→普通轮询仍禁用→重连恢复”。这不是浏览器或真实 Tauri 窗口验收。
- **修复：** 统一 mutation/busy 状态与有效期刷新；测试待批准时修改设置、请求成功/失败/冲突、TTL 到期后的交互。

### R-D07 · P2 / 未接线能力：所谓 SSE 客户端面对的是一次性 JSON

- **证据：** [stream.rs:17](file:///Users/admin-1234/work/OpenBot/apps/desktop/src-tauri/src/stream.rs#L17) 期待 SSE 帧；[server.py:518](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/adapters/local_api/server.py#L518) 对应路由返回 JSON；[app.js:171](file:///Users/admin-1234/work/OpenBot/apps/desktop/ui/app.js#L171) 实际每 1.8 秒轮询，没有接入此 helper。
- **影响边界：** 当前轮询不能被称为已实现 SSE；但没有证据说明当前轮询必然丢事件。读取 `.json()` 的“SSE”测试不是流式传输测试。
- **修复：** 二选一并明确产品合同：保留有界轮询并如实标注，或实现真 SSE 后接入；后者需真实连接验证 Content-Type、分片、重复、断线、慢消费者及游标过期重取 snapshot。

### R-D08 · P2：官网声明的测试入口不存在

[apps/website/package.json:7](file:///Users/admin-1234/work/OpenBot/apps/website/package.json#L7) 指向 `tests/website.test.mjs`。主审实际运行该命令，退出 1：`Could not find 'apps/website/tests/website.test.mjs'`。

修复不是删除 test script 让 CI 看起来绿：补齐与官网真实入口一致的内容/链接/双语/能力声明测试，或更正为已有且有效的测试入口。本轮未部署网站。

## 6. 本地开源项目对照：学习模式，不迁移它们的信任边界

### 6.1 来源与方法

- Hermes：`/Users/admin-1234/.hermes/hermes-agent`，HEAD `b200f5bc60e31588ba2cb60e288029c4a54ba5fa`；[顶层许可证](file:///Users/admin-1234/.hermes/hermes-agent/LICENSE#L1) 为 MIT。
- LangAlpha：`/Users/admin-1234/work/LangAlpha`，HEAD `29baaf16ef348427e646f785e0a156ad8e399343`；[顶层许可证](file:///Users/admin-1234/work/LangAlpha/LICENSE#L1) 为 Apache-2.0。
- 独立审查前后核验两仓库 HEAD/工作树不变；主审抽查持久化门、Skill 加载副作用、停止原因归一化、归档覆盖门。
- 仅源码学习：未启动上游程序、未读 Hermes 上层私人配置/会话/凭据、未复制代码。顶层许可证不替代每个依赖和第三方片段的来源/NOTICE 审查。

### 6.2 九条借鉴与明确拒绝项

| 主题 | 上游证据 | 对 OpenBot 的决定与验收 |
|---|---|---|
| 有限 Agent 循环 | [Hermes conversation_loop.py:1745](file:///Users/admin-1234/.hermes/hermes-agent/agent/conversation_loop.py#L1745)、[turn_tool_validation.py:72](file:///Users/admin-1234/.hermes/hermes-agent/agent/turn_tool_validation.py#L72) | **经 Broker 适配。** 保留有限步骤/请求/时间预算；文本与调用同轮不提前完成，截断参数零派发。不能照搬默认极大迭代上限。 |
| 工具前后持久化门 | [turn_tool_round.py:130](file:///Users/admin-1234/.hermes/hermes-agent/agent/turn_tool_round.py#L130) | **采用失败即停模式。** 调用落盘失败不执行；结果落盘失败不喂回模型。不把聊天恢复提示当幂等保证；OpenBot 从 Operation/Attempt 重建，而非缺 tool result 就重发。 |
| 上下文压缩视图 | [Hermes context_compressor.py:5434](file:///Users/admin-1234/.hermes/hermes-agent/agent/context_compressor.py#L5434)、[LangAlpha middleware.py:359](file:///Users/admin-1234/work/LangAlpha/src/ptc_agent/agent/middleware/compaction/middleware.py#L359) | **采用模式。** 先裁旧工具正文、保护调用/结果配对，归档覆盖成功才裁 checkpoint；绝不压缩掉权威审批与动作账本。摘要失败时原始证据仍可访问。 |
| Skill 发现/加载/激活 | [skills_tool.py:229](file:///Users/admin-1234/.hermes/hermes-agent/tools/skills_tool.py#L229)、[加载安装依赖:668](file:///Users/admin-1234/.hermes/hermes-agent/tools/skills_tool.py#L668) | **目录和懒加载可借鉴，加载即安装不可复制。** 读 Skill 无副作用；来源/版本/哈希进入加载证据；安装与执行独立审批；同名不静默覆盖。 |
| 飞书流式呈现 | [stream_consumer.py:102](file:///Users/admin-1234/.hermes/hermes-agent/gateway/stream_consumer.py#L102)、[Feishu adapter.py:1706](file:///Users/admin-1234/.hermes/hermes-agent/plugins/platforms/feishu/adapter.py#L1706) | **经 outbox 适配。** 合并更新同一消息，取消后旧 delta 失效；所查路径是消息编辑，不是 CardKit 原生流式验收。卡片显示不能抢先成为授权事实。 |
| Provider 公共和私有协议字段 | [transports/types.py:15](file:///Users/admin-1234/.hermes/hermes-agent/agent/transports/types.py#L15)、[client_lifecycle.py:441](file:///Users/admin-1234/.hermes/hermes-agent/agent/client_lifecycle.py#L441) | **采用归一化模式，拒绝不明即成功。** 单一重试负责人，每次请求计预算；未知 finish reason 不映射成正常完成，私有回放字段不跨 Provider。 |
| 终端与模型审批便利性 | [terminal_tool.py:817](file:///Users/admin-1234/.hermes/hermes-agent/tools/terminal_tool.py#L817)、[approval.py:792](file:///Users/admin-1234/.hermes/hermes-agent/tools/approval.py#L792) | **不要复制。** 默认宿主 local、模型 guardian 直接批准、某些隔离环境跳提示，不符合 OpenBot 不变量。无隔离拒绝；模型 approve 不改变 Approval。 |
| 实际访问来源面板 | [LangAlpha provenance:358](file:///Users/admin-1234/work/LangAlpha/src/ptc_agent/agent/middleware/provenance/middleware.py#L358)、[trace 边界:750](file:///Users/admin-1234/work/LangAlpha/src/ptc_agent/agent/middleware/provenance/middleware.py#L750) | **经可信 Attempt/result 适配。** 区分发现、加载、返回、答案引用；不可信 trace 不能制造执行证明，提取失败明确降级，不能替代强审计。 |
| 失败场景与评测 | [Hermes persistence tests:230](file:///Users/admin-1234/.hermes/hermes-agent/tests/agent/test_tool_call_incremental_persistence.py#L230)、[compaction eval](file:///Users/admin-1234/.hermes/hermes-agent/evals/compaction/runner.py#L1) | **优先迁移测试思想。** 存储失败零执行、派发后崩溃 UNKNOWN、重复审批、取消晚到结果；摘要质量、事实召回与副作用安全分开测，不迁移上游通过率。 |

优先学习顺序是**持久化/终止与预算 → 上下文/Skill → 渠道展示/来源面板**；不引入 Hermes 整体运行时或 LangAlpha 全框架。OpenBot 现有 Broker 和持久动作语义值得保留，问题是实际接线和验证尚未与设计强度一致。

## 7. 本轮实际验证记录

### 7.1 主审命令与结果

| 验证 | 实际结果 | 能证明什么 / 不能证明什么 |
|---|---|---|
| 原环境 `scripts/verify.py --phase M1` | 退出 1；pytest **418 passed, 8 skipped**；组件资格检查失败，其余检查通过 | 原 `.venv` 只有基础组，缺可选 SDK；不能归因为产品测试失败，也不能把 M1 称全通过 |
| 原环境 `scripts/check_components.py M0` | 退出 0；24 包，scope=local development and contracts only | 基础合同环境合格，不授予 runtime 能力 |
| 离线临时环境 `uv sync --locked --offline --group provider-openai` | 退出 0；缓存安装，不改原环境或锁文件 | 补齐本轮 SDK 依赖，不等于真实 Provider 已验证 |
| 临时 SDK 环境完整 M1 verify | **8 项检查退出 0**；pytest **441 passed, 2 skipped, 1 warning，30.66 秒** | lint/format/types/components/design 等通过；两个 native 容器测试跳过；线程异常警告仍需处理 |
| SDK fault/probe/SSE 指定测试 | **26 passed，3.48 秒** | SDK 合同/loopback/合成 streaming 行为；不是真实云模型 |
| RC 元数据校验 `--mode rc --no-write` | 退出 2；11 passed、0 failed、1 skipped；PARTIAL | 因 PyYAML 不在原环境中跳过一项；该脚本不是产品测试 |
| 六个验收证据反例 | 六项均复现 | 可接受失败用例/空 SHA/矛盾门禁、覆盖 run、修改或删除日志仍通过 |
| 文件观察/恢复合成反例 | 两项均复现 | observe 创建目录；写后未落 journal 的文件被误报未应用 |
| `node --test apps/desktop/tests/projection.test.mjs` | **7 passed** | 投影和辅助模块；不证明主 app.js 交互、真实 WebView 或原生窗口 |
| `node --test apps/website/tests/website.test.mjs` | 退出 1，测试文件不存在 | 官网测试入口确实不可执行 |

复现完整 M1 的命令（需要保留临时环境，或以相同锁重新建立）：

```bash
UV_PROJECT_ENVIRONMENT=/tmp/openbot-review-20261105/m1-env \
  uv sync --locked --offline --group provider-openai \
  --python /Users/admin-1234/work/OpenBot/.venv/bin/python

env -u OPENBOT_NATIVE_TESTS -u OPENBOT_NATIVE_MCP \
  /tmp/openbot-review-20261105/m1-env/bin/python scripts/verify.py \
  --phase M1 --output-dir /tmp/openbot-review-20261105 \
  --run-id isolated-sdk-3407a30 --timeout-seconds 300
```

**重跑必须改用新 run_id，避免 R-E02 覆盖既有证据。** [完整报告](file:///tmp/openbot-review-20261105/isolated-sdk-3407a30/m1-verification.json)、[测试原始日志](file:///tmp/openbot-review-20261105/isolated-sdk-3407a30/m1-unit-contract-protocol.log)、[原环境报告](file:///tmp/openbot-review-20261105/baseline-3407a30/m1-verification.json) 位于临时目录，不能作为永久发布档案。

### 7.2 不能忽略的绿色测试警告

[日志:9](file:///tmp/openbot-review-20261105/isolated-sdk-3407a30/m1-unit-contract-protocol.log#L9) 记录 `PytestUnhandledThreadExceptionWarning`：工作区禁用路径触发 PermissionError 后，运行线程尝试转 PAUSED，发生 `RequestConflict: Task version or transition conflict`。测试仍返回成功。

这是本轮直接观察到的运行线程收尾/测试生命周期缺口；仅靠该日志尚不能区分并发取消、测试 teardown 或其他版本竞争，不据此宣布所有生产任务会崩溃。实施时必须固定反例、join worker、核对最终持久状态，并把未处理线程异常设为失败，不能过滤该 warning 或捕获后返回成功。

### 7.3 未验证范围

- 真实云 Provider、真实飞书账号/长连接/CardKit、真实 Ollama 推理未验证。
- Docker/MCP native 两项显式跳过；浏览器 sandbox/真实网络封锁、macOS AX/UI 自动化未实际资格验收。
- 未运行真实 Tauri 窗口/浏览器交互；当前 PATH 无 Cargo/rustc，未重新编译原生客户端。
- 未注册 launchd 服务，未执行真实安装、签名、公证、quarantine 首开、实际升级/回滚。
- 未进行真实 72 小时 soak、睡眠唤醒、长期资源占用测试；短时 chaos/单测不替代这些证据。
- 未验证原生 Windows/Linux/Intel；不把平台条件分支、mock 或其他机器结果当本机证明。
- 独立审查的合成反例与主审核验均已区分；源码路径存在和测试通过不等于功能已接入默认产品。

## 8. 记忆、定时任务与 Skill 的实际边界

### R-M01 · P2 / 独立 helper：记忆过期不清理摘要缓存，且没有持久化

[application/memory.py:31](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/memory.py#L31) 使用两个进程内 dict；[recall_active:81](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/memory.py#L81) 检查 TTL，但 [cached_summary:115](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/memory.py#L115) 不检查时间或重建缓存。

**主审复现：** ttl=1ms 的记忆在过期时 `recall_active()` 为零条，`cached_summary()` 仍包含原文；新建服务实例无旧数据。格式正确的 source_ref 也只是正则校验，不是访问原始证据后核验。

**可达性：** services 目录的符号调用搜索未发现 Memory 服务接入 CLI/API/runtime；不能声称已造成默认用户记忆泄漏。公开的 VERIFIED/NATIVE 仍需降为符合实际的状态。

**修复：** 所有召回出口共享有效期/作用域规则；如保留长期记忆能力，走现有 SQLite Writer 持久化，source_ref 绑定真实用户输入/文件证据，纠正、遗忘、缓存与归档删除规则明确化。若不纳入首发，保留 helper 但不宣传已具备持久记忆。

### R-M02 · P2 / 发布能力缺口：DurableSchedule 只返回回执，并未创建持久 Task

[cron_triggers.py:38](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/cron_triggers.py#L38) 把 schedule 保存在 dict；[evaluate_due:49](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/cron_triggers.py#L49) 先改内存 next_due，再生成随机 task_id 和 QUEUED 字符串，没有调用 TaskStateService/Writer。回执上的 `bypasses_approval_broker=False` 不证明走过 Broker。

**主审复现：** 第一个实例返回 QUEUED 回执，新实例对同 schedule 返回 None；静态符号搜索未发现真实调度循环调用该类。此处不能说“数据库中的任务创建成功”，也不能说定时唤醒具备跨进程去重。

**修复：** schedule、due occurrence 和普通 Task 的创建使用现有短事务，唯一键绑定 schedule+计划触发时刻；掉电、睡醒、重复 tick 不丢也不重复创建。触发仅提交普通目标，不继承过去动作的批准。区分固定间隔与本地墙钟计划的 DST 语义。可从首发范围移除，但不能继续标持久原生验收通过。

### R-M03 · P2 / 加载边界：Skill 声明摘要未与实际内容核对

[skills.py:66](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/skills.py#L66) 只验证元数据 schema/能力白名单，直接返回传入的 sha256 和正文，没有计算正文摘要。

**主审复现：** 传入全 a 的 64 位摘要和不匹配正文，loader 接受并返回。默认 runtime 的内置 demo 自行计算摘要，所以本轮未证明默认 demo 被替换；问题在通用加载边界，外部 Skill 接入前必须修复。

**修复：** 明确哈希覆盖的精确 UTF-8 字节，先比较再返回 LoadedReadOnlySkill，记录实际加载内容；拒绝同名不同源静默替换。保留读取不安装、不执行、生成草稿不激活的现有优点。

**定位修正：** Skill 并非完全没有接线：[AgentRuntime:821](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/agent_runtime.py#L821) 已加载内置 demo 并记录来源事件；缺的是外部目录/版本准入流程。Memory/Cron 的独立 helper 状态不能套用到整个 Skill 功能。

## 9. 核心运行时、预算与恢复审查

以下独立审查使用临时 SQLite、真实核心服务/默认模型工厂及合成 transport；主审核对了关键函数。未向外部 Provider 发请求，也未制造真实第三方副作用。

### R-R01 · P1：预算预留被拒绝后，模型请求仍会发出

- **证据：** [runtime_budget.py:15](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/runtime_budget.py#L15) 等待 reserve 命令，却丢弃回执；[budgets.py:391](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/budgets.py#L391) 在额度不足时返回 `admitted:false`，不是抛异常。
- **反例：** 任务 token limit=0，经 client API/default factory 启动后，transport 被调用 **1 次**，数据库预算预留 **0 条**；随后结算冲突、任务 PAUSED。
- **影响：** 即使明确没有额度，仍可能产生一次付费请求；“最后暂停了”不能抵消已经发生的请求。
- **修复：** 解析 durable receipt，非明确 admitted=true 不允许进入 transport；覆盖 token、时间和调用次数上限，以及动态缩减预算。所有失败均断言零实际 transport 调用，不只断言 PAUSED。

### R-R02 · P1：模型拒绝或未做任务的文本，被提升为“已核验成功”

- **证据：** [agent_runtime.py:907](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/agent_runtime.py#L907) 将任意非空文本保存后记录 OUTCOME_VERIFIED，再提交 `DIAGNOSIS/SUCCEEDED`；来源引用固定为当前 Task ID。
- **反例：** 用户目标是读 demo.txt 并总结；假模型回答“无法访问 demo.txt；没有读取”。最终 Task **SUCCEEDED**，Operation **0**，工具执行 **0**，却有“已核验”结果。
- **合同依据：** [docs/03_runtime_recovery.md:79](file:///Users/admin-1234/work/OpenBot/docs/03_runtime_recovery.md#L79) 明确 final 文本只能申请完成，需核对来源、产物、必要测试和未解决动作。
- **修复：** 按可信任务类型/验收要求核对真实 Operation/Artifact/来源证据，再产生完成事件；Task ID 不能证明目标完成。拒绝、澄清、不支持的目标应明确暂停/失败/部分结果，不能一律成功；也不能要求纯聊天一定调用工具。

### R-R03 · P1：固定预留 4096，与实际模型输入规模无关

- **证据：** [agent_runtime.py:862](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/agent_runtime.py#L862) 每次 ModelRequest 固定 4096；[runtime_budget.py:20](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/runtime_budget.py#L20) 将其直接作为 reserved_tokens。
- **反例：** 约一万字符的已接受目标，额度 5000；请求体 30,482 UTF-8 字节；合成 SSE usage 为输入 5980/输出 20。预留 4096，结算 6000，最终 SUCCEEDED。usage 是注入值，不是假称实测 tokenizer 结果。
- **修复：** 复用已有预算估算能力，覆盖序列化历史、工具 schema 和最大输出；无可信 tokenizer 时采用明确保守上界。超出预算在发送前拒绝或压缩，不能靠事后结算追认；未知价格不能用 0 冒充免费。

### R-R04 · P1：默认工厂只发布 demo 工具，真实 workspace 工具未接入模型接口

- **证据：** [runtime_factory.py:53](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/runtime_factory.py#L53) 的 manifests 仅为 `mcp_read_text` 或空集；这正是 daemon 使用的工厂。
- **反例：** 五个 workspace 工具已登记，默认工厂发出的请求仍只声明 demo 工具；注入 `workspace.read` 调用后 ProviderFailure，未产生 Operation。
- **影响：** 现有 search/read/propose/apply 实现并不等于普通用户能从默认模型接口使用它们；通过的 V1-075 测试使用替代模型，绕开该工厂。
- **修复：** 发布“已准入 ∩ 当前配置许可 ∩ 运行时有支持 executor”的显式工具集合；不能把整个 ACTIVE registry 全暴露。增加默认工厂＋合成 SDK transport 的完整多轮测试，再做独立真实模型验收。

### R-R05 · P1：拒绝审批后线程退出，但任务占位不释放

- **证据：** [agent_runtime.py:704](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/agent_runtime.py#L704) 把拒绝/过期当异常；[收尾:946](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/agent_runtime.py#L946) 仅处理 RUNNING→PAUSED；[start:341](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/agent_runtime.py#L341) 拒绝已有 run 重启。
- **反例：** 默认工厂提出 demo read，真实审批 API 拒绝；Operation=REJECTED，Task=QUEUED，运行线程已退出。新任务启动 409 ONE_ACTIVE_RUN_REQUIRED；原任务启动 409 RUN_ALREADY_STARTED_OR_REQUIRES_RECONCILIATION。
- **修复：** 区分拒绝、过期、取消、未知结果和普通故障；对无已发生副作用的拒绝，返回有界工具拒绝结果继续规划，或提交真实失败/暂停并允许合法恢复。不得让用户必须额外取消一个隐藏僵尸任务，也不能盲目重放历史 run。

### R-S01 · P1：正常 daemon 重启没有建立新 runtime epoch 或恢复中断动作

- **证据：** [cli.py:532](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/cli.py#L532) 在已有 profile 时立即返回；[启动:621](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/cli.py#L621) 并未在宣布就绪前调用恢复器。CLI 默认 epoch 为 ep_1。
- **反例：** 已有数据库含 ep_1 和 DISPATCHING 动作，启动 helper 传 ep_restart：数据库仍是 ep_1、动作仍 DISPATCHING；旧 epoch 验证成功，新 epoch 被拒绝，而 session 可以宣称新参数。
- **影响：** 使用默认值会复用旧执行身份；指定新值则运行时和数据库不一致。不能凭单实例文件锁就证明旧外部执行域已隔离。
- **修复：** 在可信 supervisor 证实旧执行域隔离后，由服务器生成新 epoch，在恢复事务处理旧动作，再创建一致的服务上下文和对外 session；隔离失败不进入 ready。真正进程重启与旧 worker 晚到结果须另行实测。

### R-S02 · P1：身份轮换后，启动仍硬编码 identity_epoch=1

- **证据：** [cli.py:652](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/cli.py#L652) 的 InboundContext 固定 principal/session 与 identity epoch；[storage/inbox.py:38](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/storage/inbox.py#L38) 按权威配置校验。
- **反例：** 合成数据库将身份 epoch 更新为 2，截获真实启动构造出的 context 仍为 1；authorize 拒绝 `Trusted profile/owner/session context is no longer valid`。
- **修复：** 从经校验的现有 owner/profile/session 记录建立本地可信上下文，不把迁移/身份恢复写成测试初始值。新认证 owner 能继续工作，旧 token/session/approval 仍失效，不能为可用性恢复已撤销授权。

### R-S03 · P1 / 执行门语义：同幂等键可读回取消前的 DISPATCHING 成功回执

- **证据：** [dispatch.py:426](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/dispatch.py#L426) lookup 返回历史 receipt；[writer.py:197](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/storage/writer.py#L197) 命中后跳过 apply，而取消、epoch、lease、授权复核在 apply 内。
- **反例：** 先成功进入 DISPATCHING，再提交 cancel_revision=1。同 key 重发 `/dispatch` 返回 **200/DISPATCHING**，换新 key 返回 **403**。
- **边界：** 证明的是旧执行门成功被读回，不是已观察到第二次外部发送。历史幂等回执本身可合法保留，不能粗暴取消整个 Writer 的幂等语义。
- **修复：** 明确区分“查询历史提交结果”与“此刻允许 executor 发送”；任何作为继续发送依据的回执必须复验当前条件，或携带只能被可信执行层消费一次的派发许可。验证取消、过期、epoch 替换、lease 失效后的同 key 重试，不只测试新 key。

### R-S04 · P2：恢复修改了任务状态，但没有对应 task 事件/outbox

- **证据：** [recovery.py:167](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/recovery.py#L167) 直接将 task 改 RECONCILING；[事件:218](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/recovery.py#L218) 仅插入无 task_id/operation_id 的 Runtime 事件，没有通知 outbox。
- **反例：** Task=RECONCILING、version=5；任务事件数 **7→7**，任务 outbox 数 **5→5**，新事件关联为 Runtime/NULL/NULL。
- **修复：** 状态修改、关联 task/operation 事件、必要 outbox 在同一短事务提交；事件或 outbox 插入失败必须整体回滚。snapshot 与任务事件流在恢复后应一致。

### 9.1 未采纳的误报与保留的设计能力

独立审查曾将“owner 上传文字证据后解除 UNKNOWN”评为漏洞；主审对照 [恢复合同:88](file:///Users/admin-1234/work/OpenBot/docs/03_runtime_recovery.md#L88) 和 [API:388](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/adapters/local_api/server.py#L388)，确认系统明确支持 **USER_ATTESTED 人工核对**，API 也保存这一 provenance，而非冒充 PROVIDER_VERIFIED。因此本报告**不把授权用户提交人工判断本身列为缺陷**，也不建议删除人工核对能力。

需要保留的边界是：调用者确为授权用户、证据作用域匹配、结论明确、版本匹配、人工与机器证据区别展示，以及不能把模型生成文本自动提交成用户证言。没有证据证明这些接口已被模型旁路使用时，不应将其称为权限绕过。

### 9.2 补充分域测试记录

- 运行时 reviewer：现有 runtime 测试及 V1-075 主路径 **10 passed**；额外合成脚本复现 R-R01 至 R-R05，默认工厂真实参与、网络/DNS/子进程受测试审计钩子禁止。
- 恢复 reviewer：dispatch/recovery/cancellation/scheduler/resources/approvals/writer/policy 的现有测试 **66 passed，3.03 秒**；额外临时数据库脚本验证 R-S01 至 R-S04。
- 集成 reviewer：飞书/出口/工作区读/journal 相关现有测试 **17 passed**，另做局部反例。
- 上述数字与完整 441 项有重叠，**不能相加宣称总测试数**。临时反例不替代下一阶段纳入仓库的回归用例。

## 10. 完整改进计划

### 10.1 收敛策略

1. **不推倒重做。** 继续使用现有 Writer、审批、Operation/Attempt、Artifact 和准入合同，修接线与事实判定，不建立第二套聊天状态机。
2. **先窄闭环，后广功能。** 推荐首发验收范围为 macOS ARM64、本地工作区 search/read/propose/approve/apply、可靠拒绝/取消/恢复、桌面和飞书真实入口。范围批准前，不擅自删除已承诺能力。
3. **对扩展能力采用明确的范围决策。** 通用 MCP、浏览器/AX、多 Provider、持久记忆、定时任务、自动更新，要么完成对应资格门，要么明确延期并同步公开声明；不能用未接线 helper 保留 VERIFIED 标签。
4. **不把人工核对改成只能机器核对。** 保留 USER_ATTESTED，但 UI/事件必须明确其来源；Provider 验证和用户确认不是同一可信等级。
5. **完整计划不等于立即执行授权。** 以下任务均未实施；涉及 schema/迁移/锁/安全策略先更新现有合同/ADR，系统服务、真实账号、发布及远程写入另按授权执行。

### 10.2 依赖与优先级

负责人是建议的工程角色，不代表已分配给某位人员；工作量 S/M/L 仅表示相对复杂度，不是工期承诺。

| 任务 | 交付物 | 前置 | 角色 / 工作量 | 覆盖发现 |
|---|---|---|---|---|
| CR-01 | 不可覆盖、可验真验证记录 | 无 | 验证工程 / S | E02 |
| CR-02 | 用例→门禁→公开状态的证据绑定 | CR-01 | Release Integrator / M | E01、E03 |
| CR-03 | 预算拒绝零请求、保守逐请求预留 | 无 | Core / M | R01、R03 |
| CR-04 | 证据驱动终态、拒绝/异常正确收尾 | CR-03 | Core / M | R02、R05、线程警告 |
| CR-05 | 可信启动 epoch/identity 恢复 | 无 | Core + Native / L | S01、S02 |
| CR-06 | 派发重试与恢复事件一致性 | CR-05 | Core / M | S03、S04 |
| CR-07 | 飞书 durable ACK 与重投递闭环 | 无 | Channel / S | I01 |
| CR-08 | 无副作用、有界文件观察/读取 | 无 | Tool / M | F02、F03 |
| CR-09 | 补丁崩溃边界的真实恢复 | CR-08、CR-06 | Tool + Storage / M | F01 |
| CR-10 | 默认工厂的真实工作区多轮链路 | CR-03、CR-04、CR-09 | Runtime Integrator / M | R04 |
| CR-11 | 完整批准预览与按钮状态 | CR-09、CR-10 | Desktop + Core / M | D01、D06 |
| CR-12 | UNKNOWN 核对与事件传输合同 | CR-06、CR-11 | Desktop + Core / M | D02、D07 |
| CR-13 | 安装启动可用、停止不误杀 | CR-05 | Native / M | D03、D04 |
| CR-14 | MCP 执行物绑定、deadline、回收证明 | CR-06 | Tool + Native / L | A01、A02、A03 |
| CR-15 | 所有模型/浏览器入口的真实出口与资源约束 | CR-03、CR-14 | Security + Tool / L | A04、A05、A06 |
| CR-16 | Skill 哈希与上下文视图 | CR-04、CR-10 | Runtime / M | M03、上游借鉴 |
| CR-17 | 记忆全出口 TTL 与可选持久化 | CR-02、CR-16 | Storage / M | M01 |
| CR-18 | 持久 schedule→普通 Task 原子触发 | CR-04、CR-05、CR-06 | Scheduler / M | M02 |
| CR-19 | 真实手动更新/升级回滚，或完整签名 updater | CR-01、CR-13 | Release + Native / L | D05 |
| CR-20 | CI 跨层验证、官网入口、文档一致性 | CR-01、CR-02、CR-10、CR-12 | QA + Docs / M | E04、D08 |
| CR-21 | 同候选制品上的产品/原生资格验收 | 首发范围内任务完成 | Integrator + QA / L | 所有纳入首发能力 |

可并行的首批是 CR-01、CR-03、CR-05、CR-07、CR-08；实现必须独立 worktree，Writer/合同/CLI 等共享文件由 Integrator 合并。CR-17/18 不必阻塞缩小范围的首发，但需先完成 CR-02 的延期记录，不能静默漏掉。

### CR-01：让验证证据不可被同名覆盖

**修改：** [scripts/verify.py](file:///Users/admin-1234/work/OpenBot/scripts/verify.py)；**测试：** [test_verify_runner.py](file:///Users/admin-1234/work/OpenBot/tests/unit/test_verify_runner.py)。保持 run_id/source_sha/phase 接口，新增校验要求由实际采集内容产生，不接受自报布尔值。

- [ ] 增加失败回归：同 run_id 先失败再成功、日志被改/删除、检查集合缺失/重复、阶段或候选不匹配。
- [ ] run 目录改为排他创建；校验原始日志字节摘要、固定检查与命令、COMPLETE、candidate/tree/lock；发布证据另绑定制品，开发验证不能假造制品 hash。
- [ ] 运行 `.venv/bin/python -m pytest tests/unit/test_verify_runner.py -q`；断言旧失败内容完全保留，新运行使用新 ID，且报告加载失败不得 fallback 成功。

### CR-02：用真实证据派生 RC 与公开状态

**修改：** [validate_plan.py](file:///Users/admin-1234/work/OpenBot/plan/v1_0_0/tools/validate_plan.py)、[mvp_release_gate.py](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/mvp_release_gate.py)、v1 用例/门禁记录、公开状态；**测试：** [test_v1_baseline_and_gates.py](file:///Users/admin-1234/work/OpenBot/tests/unit/test_v1_baseline_and_gates.py)。对应 V1-003/036/040/046。

- [ ] 将本轮三种 RC 元数据反例写入永久测试；同时构造有效最小证据，保证不是一律拒绝。
- [ ] 定义 capability×platform×candidate×test×run 的引用；RC 模式检查用例结果与门禁一致、SHA 有效且对应候选、日志与制品可验证、native 标签有相应收集记录。
- [ ] 将未获证据支持的状态降为实现存在/合成验证/待原生验证或明确延期；保留根任务与 macOS v1 范围差异、历史记录和理由。
- [ ] 运行 `.venv/bin/python -m pytest tests/unit/test_v1_baseline_and_gates.py -q` 及 `.venv/bin/python plan/v1_0_0/tools/validate_plan.py --mode rc --no-write`；真实证据缺失时预期阻断，不能手填 PASS 使其通过。

### CR-03：让预算成为派发前的硬门

**修改：** runtime_budget、agent_runtime、[budgets.py](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/budgets.py)、必要 Provider 请求构造；**测试：** [test_budgets.py](file:///Users/admin-1234/work/OpenBot/tests/integration/storage/test_budgets.py)、[test_agent_runtime.py](file:///Users/admin-1234/work/OpenBot/tests/integration/test_agent_runtime.py)。对应 OB-023、V1-011。

- [ ] 固定默认工厂反例：token_limit=0 后 transport 调用为零；时间/调用次数/并发预留耗尽同样为零，pause reason 保留。
- [ ] `RuntimeBudget.reserve()` 解析 receipt，admitted 不为 true 时抛固定预算拒绝错误；没有 reservation 的请求不可进入 transport，不能在 settle 阶段才发现。
- [ ] 对实际序列化历史和完整工具 schema 估算，另限制最大输出；长 Unicode、超大 tool result、多轮历史覆盖。现有 OfflineVocabularyEstimator 的已映射分支仍是 UTF-8/4，不是真实 tokenizer，不能仅因词表 hash 合格便认为估算是上界。
- [ ] 运行 `.venv/bin/python -m pytest tests/integration/storage/test_budgets.py tests/integration/test_agent_runtime.py -q`；验证不足额度无请求、已发生请求恰有一次预留/结算或 UNKNOWN，不重复计费、不把未知量清零。

### CR-04：正确判定完成、拒绝与异常收尾

**修改：** agent_runtime、runtime_results、[state_machine.py](file:///Users/admin-1234/work/OpenBot/services/core/src/openbot/application/state_machine.py)、必要 client_state；**测试：** runtime 与 [test_v1_runtime_and_streaming.py](file:///Users/admin-1234/work/OpenBot/tests/integration/test_v1_runtime_and_streaming.py)。对应 OB-014、V1-010/012。

- [ ] 分别测试未读文件就拒绝、请求澄清、无工具纯聊天、部分完成、拒绝/过期审批、取消与异常竞争；只有任务合同满足才 SUCCEEDED。
- [ ] 完成入口消耗真实 Operation/Artifact/source_refs；OUTCOME_VERIFIED 不能先于完成校验持久化。拒绝/过期回到有界规划或真实终态，不遗留 QUEUED 僵尸 run。
- [ ] 线程收尾和 teardown 等待明确完成，版本竞争按当前持久状态处理；复现已有 RequestConflict 警告，禁止裸忽略异常。
- [ ] 运行 `.venv/bin/python -m pytest tests/integration/test_agent_runtime.py tests/integration/test_v1_runtime_and_streaming.py -q -W error::pytest.PytestUnhandledThreadExceptionWarning`；新任务可启动，旧已发生副作用仍正确 UNKNOWN。

### CR-05：把启动与恢复接成同一可信路径

**修改：** cli、scheduler、recovery、当前 InboundContext 初始化；**测试：** [test_client_daemon.py](file:///Users/admin-1234/work/OpenBot/tests/integration/cli/test_client_daemon.py)、[test_recovery.py](file:///Users/admin-1234/work/OpenBot/tests/integration/storage/test_recovery.py)。对应 V1-013/014/029。

- [ ] 临时 profile 中创建中断 DISPATCHING，再走真实启动路径；断言新旧 epoch、session 声明与数据库一致。身份轮换为 2 后启动不得再次使用 1。
- [ ] 从权威 profile/owner/session 建上下文；新 epoch 由可信启动生成，先验证旧执行域隔离，再恢复并对外 ready。隔离失败必须保持不可接管，不通过客户端布尔值授权。
- [ ] 测正常启动、旧 worker 晚到、未知外部效果、过期审批、重复启动、身份轮换和撤销；运行 `.venv/bin/python -m pytest tests/integration/cli/test_client_daemon.py tests/integration/storage/test_recovery.py -q`，随后单独进行真实子进程崩溃验收。

### CR-06：区分历史回执与当前派发许可，补齐恢复事件

**修改：** dispatch、recovery、Writer 命令接入点、任务事件/outbox；**测试：** storage dispatch/recovery/cancellation/outbox。对应 OB-018/019/020/024、V1-012/013。

- [ ] 先复现同 key 在取消、grant 到期、lease 失效、epoch 更换后的旧 200 回执；明确历史查询可读，但不能成为新发送许可。
- [ ] 在最终可信执行门校验当前条件与一次性消费；不移除通用幂等、不生成新 ID 重放非幂等动作。
- [ ] recover_epoch 为每个受影响 Task/Operation 提交关联事件和必要 outbox；在事件/outbox 插入点注入错误，验证状态整体回滚。
- [ ] 运行 `.venv/bin/python -m pytest tests/integration/storage/test_dispatch.py tests/integration/storage/test_recovery.py tests/integration/storage/test_cancellation.py tests/integration/storage/test_outbox.py -q`；再用独立效果计数器验证零新派发，而不只看 HTTP 状态。

### CR-07：飞书 ACK 跟随 durable admission，不跟随展示成功

**修改：** live_gateway 及必要 ingress 结果协议；**测试：** [test_feishu_live_gateway.py](file:///Users/admin-1234/work/OpenBot/tests/unit/test_feishu_live_gateway.py)、[test_client_ingress.py](file:///Users/admin-1234/work/OpenBot/tests/integration/feishu/test_client_ingress.py)。对应 V1-027/082。

- [ ] 合成 worker 用真实 stdin/stdout 协议，要求 durable 201/已接收重复事件获得正确确认；失败、未提交事件不确认，连续事件不能错配 ACK。
- [ ] 把 reaction/card 更新移出确认关键路径；重投递仍由稳定 inbox 身份去重，不在渠道层直接执行工具。
- [ ] 运行 `.venv/bin/python -m pytest tests/unit/test_feishu_live_gateway.py tests/integration/feishu/test_client_ingress.py -q`；合成故障通过后，再经授权用专用真实飞书账号验证长连接和重连。

### CR-08：观察纯读取，资源限制下沉到文件句柄

**修改：** filesystem_guard、workspace/read；**测试：** [test_filesystem_guard.py](file:///Users/admin-1234/work/OpenBot/tests/unit/test_filesystem_guard.py)、[test_workspace_read_tools.py](file:///Users/admin-1234/work/OpenBot/tests/unit/test_workspace_read_tools.py)。对应 OB-032/033/034。

- [ ] 新增 observe 缺失父目录不创建目录的 RED 测试；现有正向新建测试显式在 fixture 创建父目录，不能继续依赖观察的隐藏副作用。
- [ ] 读取层引入最大字节/总时限/取消，限制最多 limit+1；测试文件持续增长、符号链接/硬链接/父目录竞态，大文件列表不能整文件读入。
- [ ] 运行 `.venv/bin/python -m pytest tests/unit/test_filesystem_guard.py tests/unit/test_workspace_read_tools.py -q`；用读取计数和工作区前后清单证明有界且无副作用。

### CR-09：按磁盘事实恢复补丁 journal

**修改：** workspace/patch、commit_journal；**测试：** [test_workspace_patch.py](file:///Users/admin-1234/work/OpenBot/tests/integration/storage/test_workspace_patch.py)、[test_v1_security_and_recovery.py](file:///Users/admin-1234/work/OpenBot/tests/unit/test_v1_security_and_recovery.py)。对应 V1-020。

- [ ] 针对每个文件做 write/rename/fsync/mark_applied 前后故障；PREPARED+磁盘新 hash 必须识别已写，不报 FAILED_NOT_APPLIED。
- [ ] 按 old/new/第三种 hash 决定未变/可恢复/用户冲突；journal/备份损坏保持不确定；恢复结果只有经再次观察才能写入。
- [ ] 运行 `.venv/bin/python -m pytest tests/integration/storage/test_workspace_patch.py tests/unit/test_v1_security_and_recovery.py -q`；至少再加入真实子进程 `os._exit` 边界测试，验证用户后改文件不被覆盖、多文件不冒充原子事务。

### CR-10：默认工厂而不是假模型承载工作区闭环

**修改：** runtime_factory、agent_runtime、准入 manifest 集合；**测试：** runtime/SDK 集成。对应 V1-010/075。

- [ ] 用实际 model_factory＋合成 SDK transport 捕获 tools；应只含已准入且有 executor、当前配置允许的五项工作区工具，未知 registry 条目不透传。
- [ ] 走 client API→真实工厂→search/read→propose→owner approve→apply→follow-up→OutcomeVerifier；Provider 层保留原始调用/结果关联，而非每步灌固定“read complete”提示。
- [ ] 运行 `.venv/bin/python -m pytest tests/integration/test_agent_runtime.py tests/integration/test_v1_runtime_and_streaming.py tests/integration/test_sdk_sse_transport.py -q`；断言禁用工具零派发、修改符合批准字节、拒绝/漂移/预算不足都不写文件。

### CR-11：批准内容完整可理解，按钮状态与服务端一致

**修改：** client_routes、app.js、已有 diff helper；**测试：** [test_v1_desktop_ui_and_routes.py](file:///Users/admin-1234/work/OpenBot/tests/unit/test_v1_desktop_ui_and_routes.py)、桌面 [projection.test.mjs](file:///Users/admin-1234/work/OpenBot/apps/desktop/tests/projection.test.mjs)，新增 [approval-flow.test.mjs](file:///Users/admin-1234/work/OpenBot/apps/desktop/tests/approval-flow.test.mjs) 主 UI 回归。对应 V1-025/063。

- [ ] API 预览从 bundle/Artifact 展开多文件目标、完整可访问 diff、旧/新摘要、漂移/截断/TTL；对比批准绑定和最终字节。
- [ ] 主 app.js 接入这些字段，无法确认影响时禁批；统一 busy/mutation/TTL，切换语言或失败操作后可恢复，不只测试未接线 helper。
- [ ] 运行 Python routes 测试和 `node --test apps/desktop/tests/*.test.mjs`；启动真实开发客户端/浏览器验证键盘、长 diff、过期/断线/版本冲突，查看控制台并保留截图；没有 UI 环境不得标完成。

### CR-12：核对向导使用真实合同，传输能力如实实现

**修改：** reconciliation schema（仅在合同确需变更时）、Rust lib/stream、reconcile_wizard、app.js、server；**测试：** [test_local_api_contracts.py](file:///Users/admin-1234/work/OpenBot/tests/contracts/local_api/test_local_api_contracts.py)、桌面测试。对应 V1-023/062/065。

- [ ] 使用 `CONFIRMED_FAILED_NO_EFFECT` 与真实证据数量/归属/CAS 约束贯通 UI→IPC→API→恢复器；保留 USER_ATTESTED 标识和 KEEP_UNKNOWN，不暗示人工确认是 Provider 证明。
- [ ] 首先使现有轮询合同准确、cursor 过期能恢复；如果首发要求 SSE，则真实服务端持续发送 SSE，客户端实际接入，不能保留 JSON helper 测试冒充流式。
- [ ] 运行 `.venv/bin/python -m pytest tests/contracts/local_api -q`、桌面 Node/Rust 测试；用真实 loopback 连接和主 UI 验证断线、重复、慢消费者、过期 cursor、核对冲突，核对后不会自动重放原副作用。

### CR-13：安装启动要能服务桌面，停止必须核对实例身份

**修改：** daemon_installer、cli、原生 supervisor 接入；**测试：** [test_user_daemon_installer.py](file:///Users/admin-1234/work/OpenBot/tests/unit/test_user_daemon_installer.py)、CLI daemon 集成。对应 V1-029/061/068。

- [ ] 安装器传递并验证 workspace-root/profile 绑定，ready 包含真实 client_snapshot 和创建任务能力，不只 health。
- [ ] stop/restart/uninstall 用可信进程身份；过期 session、PID 复用、health 失败不得直接发信号；确认退出前不报告停止或启动替代实例。
- [ ] 运行相关单元/CLI 测试（信号先 mock），随后在经授权的专用 user-service 环境验证真实安装、窗口关闭、重启、崩溃、停止/卸载且工作区保留，不操作用户现有服务。

### CR-14：MCP 生命周期返回可验证事实

**修改：** mcp/client、container_executor、现有容器 ownership/intent 接入；**测试：** [test_mcp_client.py](file:///Users/admin-1234/work/OpenBot/tests/unit/test_mcp_client.py)、[test_mcp_fault_and_malicious_server.py](file:///Users/admin-1234/work/OpenBot/tests/integration/mcp/test_mcp_fault_and_malicious_server.py)、[test_v1_hybrid_aci_l1_to_l4.py](file:///Users/admin-1234/work/OpenBot/tests/unit/test_v1_hybrid_aci_l1_to_l4.py)。对应 V1-016/017/068/076。

- [ ] 拒绝 executable/argv/实际资产 digest 不一致，验证 spawn 计数为零；不可信 MCP 只能使用准入隔离器。
- [ ] 整个 tools/call 的写、读、drain 共享 deadline；静默、半帧、超长输出、stderr 洪流、取消均有界，结果不明不得换 ID 重发。
- [ ] runner 失败或引擎不可用不清除 intent；唯有匹配 ownership 的真实 stop/wait/remove 成功才记录 reclaimed。
- [ ] 运行 `.venv/bin/python -m pytest tests/unit/test_mcp_client.py tests/integration/mcp tests/unit/test_v1_hybrid_aci_l1_to_l4.py -q`；再独立启用专用 native 容器资格测试，验证宿主客户端退出后也无遗留登记容器。

### CR-15：统一出口、总 deadline 与输出边界

**修改：** egress、ollama、browser/session 与受控网络执行接入；**测试：** [test_egress_policy.py](file:///Users/admin-1234/work/OpenBot/tests/unit/test_egress_policy.py)、[test_ollama_provider.py](file:///Users/admin-1234/work/OpenBot/tests/unit/test_ollama_provider.py)、[test_browser_session.py](file:///Users/admin-1234/work/OpenBot/tests/unit/test_browser_session.py)。对应 V1-018/019/021。

- [ ] LOCAL_MODEL_RUNNER 必须验证实际本地目的地，OFFLINE 远端一律不发；覆盖代理/重定向/attestation 地址不匹配。
- [ ] Ollama 过期请求零 transport 调用，累计字节、总时限、取消生效；浏览器最小环境、有界输出、每次请求由真实出口强制约束。
- [ ] 运行上述三个测试文件和 browser integration；双 loopback 证明拒绝重定向与子资源，再经授权验证真实 sandbox/Service Worker/WebSocket。无隔离或无强制出口时拒绝，不降级宿主或云端。

### CR-16：学习上游的上下文组织，不复制权限便利性

**修改：** skills、agent_runtime 的上下文投影、来源事件；**测试：** [test_skills_loader.py](file:///Users/admin-1234/work/OpenBot/tests/unit/test_skills_loader.py)、runtime 测试。对应 OB-066、V1-010；新增压缩属于增强项。

- [ ] 先补 Skill 内容摘要不匹配拒绝测试，加载前按精确 UTF-8 字节核验；内置 demo 同样经过该边界。
- [ ] 外部 Skill 采用来源/版本/哈希固定的只读目录与懒加载，发现/读取不安装依赖、不执行预处理脚本；生成草稿不能自动激活。
- [ ] 上下文压缩只构建模型视图，保留权威 Operation/Approval/Artifact；摘要引用原始来源，归档可读才裁历史，工具调用/结果配对不拆。
- [ ] 运行 skills/runtime 测试；故障矩阵包含摘要失败、来源缺失、同名不同源、文件加载后变化、恶意摘要指令。先采纳模式，不复制上游代码；复制需求另走 component qualification。

### CR-17：记忆所有读取出口遵守 TTL，再决定是否持久化

**修改：** memory、必要 Writer 迁移与 API 接线；**测试：** [test_v1_providers_feishu_memory_cron.py](file:///Users/admin-1234/work/OpenBot/tests/unit/test_v1_providers_feishu_memory_cron.py)，新增 [test_memory_lifecycle.py](file:///Users/admin-1234/work/OpenBot/tests/integration/storage/test_memory_lifecycle.py)。对应 V1-083。

- [ ] 固定“recall 空但 cache 仍返回”的反例；把 `cached_summary` 改为接受同一受控 now_ms 并调用相同过滤逻辑，更新全部调用者，不保留绕过 TTL 的旧出口。
- [ ] 若保留首发持久记忆，先定义 schema/source_ref 可信绑定、owner/workspace、TTL、更正和 hard-forget 的归档/缓存语义，再用现有 Writer 保存；不先引入向量数据库。
- [ ] 运行 memory 单元与新增生命周期测试，覆盖进程重启、TTL、跨工作区、来源变化、敏感信息、纠正/遗忘后所有缓存出口；备份仍含历史内容时不能宣传“所有介质零残留”。

### CR-18：定时触发产生真实持久 Task，不生成虚拟成功回执

**修改：** cron_triggers、现有 scheduler/TaskStateService/Writer，必要迁移；**测试：** [test_scheduler.py](file:///Users/admin-1234/work/OpenBot/tests/integration/storage/test_scheduler.py)，新增 [test_cron_triggers.py](file:///Users/admin-1234/work/OpenBot/tests/integration/storage/test_cron_triggers.py)。对应 V1-084。

- [ ] 先定义 schedule 与 occurrence 唯一键、状态和所有者合同；创建 Task、记录 occurrence、推进 next_due 在同一短事务，无网络调用。
- [ ] 用真实临时数据库和重启测试合并漏触发、重复 tick、数据库提交前后退出、时钟前后跳及 DST；相同 occurrence 最多一个 Task，未提交不能丢失。
- [ ] 触发仅进入普通 QUEUED/规划，动作重新经当前策略和批准；运行 scheduler/cron 测试并从真实 API 查询创建的 Task，不能只断言 receipt.task_state 字符串。

### CR-19：发布与更新从真实制品事实得出结果

**修改：** packaging_auditor、storage/maintenance、已有 build/release 检查；**测试：** [test_v1_release_packaging_and_upgrade.py](file:///Users/admin-1234/work/OpenBot/tests/unit/test_v1_release_packaging_and_upgrade.py)、[test_maintenance.py](file:///Users/admin-1234/work/OpenBot/tests/integration/storage/test_maintenance.py)。对应 V1-031 至 039。

- [ ] 先拒绝 candidate.version 与比较版本不匹配、无有效签名、摘要不符、错误通道、降级和撤销；`signature_verified` 不再是未核验调用方可传入的放行依据。
- [ ] 推荐先交付真实手动升级/备份/回滚路径；若保留自动 updater，则替换、迁移、候选启动、健康验证、激活、回滚全部从实际步骤生成状态，不接受 candidate_health_ok 代替动作。
- [ ] 测试每个切换点进程退出，验证重启后能恢复、UNKNOWN 不丢、旧凭据/数据库权限不放宽；再执行真实 .app/DMG、签名/公证、quarantine 首开和升级验证。发布到外部仍须授权。

### CR-20：CI 与文档覆盖实际产品入口

**修改：** 现有 PR/desktop workflows、官网测试入口、README/project-status/troubleshooting/AGENTS 中过期项目描述；**测试：** [test_v1_docs_website_and_rc_closure.py](file:///Users/admin-1234/work/OpenBot/tests/unit/test_v1_docs_website_and_rc_closure.py)、新增 [website.test.mjs](file:///Users/admin-1234/work/OpenBot/apps/website/tests/website.test.mjs)。对应 V1-040 至 060。

- [ ] 增加独立锁定 provider-openai 组的 CI；desktop 触发包含后端 API/合同；未处理线程异常作为失败，测试结束确认无遗留 worker。
- [ ] 补真实官网 test script、内部链接、双语、下载/支持平台、能力事实一致性测试；改正 troubleshooting 的错误核对枚举，保留历史设计文档的历史身份。
- [ ] 运行完整 M0/M1、桌面测试、官网声明命令、发布组件检查；变更 CI/AGENTS/公开状态时按仓库授权和审查执行，不能借本报告自动修改权限或发布范围。

### CR-21：以同一候选的真实用户场景结束整改

**输入：** 首发范围内所有任务的 code/test/evidence receipt；**产出：** 指向同一候选源码树、锁文件和制品的可复核资格结果，而不是新的手填完成表。对应 V1-004/007/009/014/036/037/038/073。

- [ ] 临时合成 profile 运行默认工厂的黄金路径和负向矩阵；本地独立效果账本记录真实写入/发送次数，不靠实现自身计数器自证。
- [ ] 真实专用环境验证：桌面创建→模型请求→搜索/读取→完整批准→精确写入→核验结果；飞书入口/ACK；拒绝、预算不足、取消、断线、DISPATCHING 后杀 daemon、旧 worker 晚到、UNKNOWN 人工核对。
- [ ] 按纳入范围执行容器/浏览器/AX/Keychain/用户服务/安装升级资格；未运行的项保持 NOT_RUN/BLOCKED，不套用其他平台结果。
- [ ] 72h soak 真正持续 72h 并记录资源曲线、睡醒/断网/磁盘等刺激，长期测试与短时故障单测分开；无硬件/凭据时记录阻塞和责任，不估测通过。
- [ ] 仅当同候选必需测试通过、日志/制品完整、没有未处理线程异常、所有 P1 已修或经明确范围移除，才重新发布 RC 资格结论；此前不把本轮 441 项通过换算为完成百分比。

### 10.3 首批可直接加入的 RED 回归示例

以下代码是**计划中的测试**，本轮没有写入 tests，也没有修改产品代码；当前行为已由合成反例验证，应先看到这些断言失败，再实施最小修复。

在 `tests/unit/test_verify_runner.py` 中复用现有 `_load_verify_module`：

```python
def test_same_run_id_cannot_replace_failure(tmp_path):
    mod = _load_verify_module()
    kwargs = dict(output_root=tmp_path, run_id="fixed", timeout_seconds=5)
    code, report = mod.run_verification(
        **kwargs,
        commands_override=[("probe", [sys.executable, "-c", "raise SystemExit(1)"])],
    )
    assert code == 1
    original = report.read_bytes()
    with pytest.raises(FileExistsError):
        mod.run_verification(
            **kwargs,
            commands_override=[("probe", [sys.executable, "-c", "print('ok')"])],
        )
    assert report.read_bytes() == original
```

在 `tests/unit/test_filesystem_guard.py`：

```python
def test_observe_missing_parent_is_read_only(tmp_path):
    guard = WorkspaceFileGuard(tmp_path)
    with pytest.raises(FileNotFoundError):
        guard.observe("unapproved/nested/file.txt")
    assert list(tmp_path.iterdir()) == []
```

在 `tests/integration/storage/test_workspace_patch.py`：

```python
def test_prepared_journal_reconciles_write_before_mark_applied(tmp_path):
    import hashlib
    from openbot.tools.filesystem_guard import WorkspaceFileGuard
    from openbot.tools.workspace.commit_journal import PatchCommitJournal

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "sample.txt"
    target.write_bytes(b"old\n")
    guard = WorkspaceFileGuard(workspace)
    snapshot = guard.observe("sample.txt")
    journal = PatchCommitJournal(tmp_path / "journals", "review")
    journal.record_Backup(
        relative_path="sample.txt",
        old_bytes=b"old\n",
        old_sha256=snapshot.sha256,
        new_sha256=hashlib.sha256(b"new\n").hexdigest(),
    )
    guard.write_atomic("sample.txt", b"new\n", snapshot)
    reloaded = PatchCommitJournal.load(journal.journal_path)
    actions = reloaded.recover_partial_failure(guard)
    assert actions["sample.txt"] == "RESTORED_ORIGINAL"
    assert target.read_bytes() == b"old\n"
```

在 `tests/unit/test_skills_loader.py`（新增固定错误码是 CR-16 的预期接口）：

```python
def test_skill_digest_must_match_loaded_bytes():
    loader = ReadOnlySkillLoader(
        schema_path=ROOT / "contracts/schemas/skill_manifest.schema.json"
    )
    spec = SkillManifestSpec(
        skill_id="skl_review",
        name="Review",
        version="1.0.0",
        source_uri="local://review",
        license="MIT",
        sha256="a" * 64,
        required_capabilities=("workspace.read",),
        instructions_markdown="Not the content represented by that digest",
    )
    with pytest.raises(PermissionError, match="SKILL_CONTENT_DIGEST_MISMATCH"):
        loader.load_readonly_skill(spec)
```

这些小测试不能替代 CR-03/04/05/10 的真实工厂与数据库集成测试；它们的作用是把本轮已发现的错误保留下来，而不是堆高测试数量。

## 11. 结论与执行边界

OpenBot 的价值不是“又一个能调用工具的聊天机器人”，而是**可信授权、持久执行账本和可恢复状态驱动的本地任务助手**。现有实现和测试值得保留；当前最大的差距是代码内部的强合同没有贯穿默认模型工厂、启动恢复、用户批准、真实工具生命周期和发布证据。

建议从 CR-01/03/05/07/08 的独立小批开始，随后集成默认工作区闭环；不先扩功能或照搬 Hermes 执行权限。每批按 RED→最小修复→定向测试→集成测试→独立审查→证据回执推进。提交、推送、真实服务、系统安装及发布均不在本轮授权范围内。
