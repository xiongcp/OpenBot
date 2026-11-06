# OpenBot 严格 MVP 核心验收操作手册

> **文档性质：执行前的验收设计及源码静态核对；44 个用例全部 NOT_RUN。** 本轮没有运行仓库测试、启动真实 macOS 产品、修改 OpenBot 代码或执行 commit/push。不能把本手册中的预期结果或当前 harness 返回值当作通过证据。

## 1. 范围、基线与使用顺序

本手册检查运行内核的授权、执行、故障恢复、持久化、数据出口与模型请求控制。它服务于 macOS MVP 验收；真实安装、launchd、Keychain、TCC、浏览器隔离、飞书租户、MCP 进程、Ollama 模型和平台兼容性由配套平台/集成用例补齐。通过这 44 项仍不能独立宣布三个操作系统全部发布就绪。

源码静态核对固定在仓库 `xiongcp/OpenBot` 的提交 `a223d36a659b7ecf32fca2b4890fc187d3e96e48`。本次完整阅读的 6 个文件列在第 7 节，所有源码结论都限定于这个提交和对应代码路径。实际执行必须重新记录被测提交、工作区差异摘要、依赖锁文件摘要、产品配置和安装产物 hash；不能直接用这个历史 SHA 的静态观察评价后续修复版本。

验收要求来自现有 v1.2 设计包的 `docs/03_runtime_recovery.md`、`04_security_approvals.md`、`05_storage_api.md`、`06_tools_providers.md`、`09_testing_operations.md` 及 `tasks/backlog.json`。这些是待验证的合同，不能证明真实代码已经实现。参考 DDL 的验证、对象状态模拟和生产进程验收分别记录，不能互相替代。

先按第 2 节确定入口与证据，再建立第 3–4 节的可重复故障夹具；随后执行第 6 节的 44 项。任一必需入口尚不存在，应留下可复现的“实施缺口”或“环境阻塞”，不能通过跳过断言、硬填 `verified=True` 或替换成模拟状态机把它标成 PASS。修复后按第 8 节完成逐问题 commit + push 闭环，最后在同一发布候选上重跑发布门禁。

### 1.1 证据层级必须明确

| 层级 | 能说明什么 | 不能据此声称什么 |
| --- | --- | --- |
| 源码静态阅读 | 某分支、常量、依赖和检查确实出现在指定 SHA | 该分支已在用户 Mac 执行、故障已复现或修复已通过 |
| 合同/模拟测试 | 对象输入输出、策略分支、标准向量、时钟逻辑 | 真实 socket、进程终止、OS 休眠、磁盘满或远端效果已经验证 |
| 产品模块集成 | 使用产品应用服务、生产 writer、实际 SQLite 与真实文件的局部合同 | 已覆盖真实 daemon 入口、进程隔离、实际提供方和安装形态 |
| 真实运行边界验收 | 在原生 macOS 的实际产品入口、执行器、SDK/transport 和目标边界取得独立证据 | 未测试架构、未测试系统版本、其他权限模式或三个操作系统都已通过 |

`requires_real_environment=true` 表示该用例必须触及真实进程、文件系统、SDK、网络或恢复边界。它不要求使用生产凭据或修改真实业务数据；优先使用专用 profile、测试凭据、无害目标和独立计数接收器。`false` 仍要求调用产品模块及该场景需要的真实 SQLite，不能复制一套“参考实现”代替被测实现。

可以用确定性模型输出强制提出某个动作，用本地测试服务制造明确的 HTTP 错误、流片段和一次无害效果。这样替换的是模型或外部目标，不是产品的审批、Broker、writer、恢复器或完成处理器。TC-CORE-039 分开执行“实际 SDK 连接故障服务”和“真实云服务最小调用”；前者证明受控请求/重试边界，后者证明真实服务证据。TC-CORE-042 另含真实云流式取消与未知费用分支，TC-CORE-043 对接其 usage/预算结算。真实 Ollama 和其他服务仍需配套集成测试，不自动继承云 Provider 的 PASS。

### 1.2 结果记录规则

每个用例有唯一 ID；每个参数分支也必须有独立结果。规划 JSON 保持 `NOT_RUN`，实际结果单独记录 `PASS`、`FAIL`、`BLOCKED` 或经范围审批的 `NOT_APPLICABLE`，并填写时间、环境、候选版本、分支、证据与问题 ID。

没有运行是 NOT_RUN，缺 SDK、缺真实 Mac、缺测试入口或无法取得可信证据是 BLOCKED。它们都不是 PASS。只有适用边界本身不存在的分支可以标不适用，例如产品只使用服务端 Python JCS、并无第二种 JCS 实现时，跨实现比较子项不适用；标准向量和服务端权威 hash 子项仍必须执行。

所有 44 项按 P0 门禁编排，因为它们检查重复副作用、越权、未知结果、数据泄漏或恢复真实性。某项包含不适用的可选工具分支时，只裁定该分支；不能把整项安全合同移出门禁。扩展性、UI 美观和长时间性能指标不在这 44 项内。

## 2. 执行前必须填写的仓库映射表

下面的名称是验收要求，不是对仓库已经存在命令的声明。由实施人员在冻结版本上查找现有入口，填入实际命令或调用路径，并在结果记录里保存。缺失项先开 issue；不要从历史设计包猜测 CLI 参数。

| 待确认项 | 必须留下的实际信息 | 缺失时的处理 |
| --- | --- | --- |
| 候选与依赖 | 当前 commit、dirty diff 摘要、Python/SQLite 版本、锁文件 hash、SDK extras、平台/架构 | 无法重建版本则暂停结论；不能用全局环境凑出绿灯 |
| 真实 ingress | daemon 启停、监听地址、认证 CLI/HTTP 入口、ready 条件、实际 PID 与启动标识 | 进程内 `api.handle()` 只能作模块测试，TC-CORE-001/008 不可 PASS |
| 独立 profile | DB、WAL/SHM、Artifact、凭据引用、日志、配置及锁的真实目录 | 使用临时目录；不得覆盖用户真实配置、文件或凭据 |
| 四对象和恢复 | Task/Operation/Approval/Attempt 的查询入口、稳定请求 ID、版本字段、epoch/fence、资源 quarantine | 把对象身份映射到真实 schema；不能把 Task ID 当全部动作身份 |
| 生产执行与完成 | claim、第二派发事务、执行器、接收去重、结果 receipt、OutcomeVerifier、T5 提交 | 不能通过直接 SQL 填 SUCCEEDED 或返回常量绕过 |
| 存储与观察 | writer 入口、只读查询或一致备份导出、持久 lookup、队列/总 deadline、诊断路径 | 先验证查询不会改动库；不使用 live DB 的不完整文件拷贝 |
| 故障与外部证据 | 第 3 节屏障的真实落点、独立接收器、卷外控制器、进程身份/退出证据 | 没有落点时增加最小测试接缝，并清楚标注生产可用性边界 |
| Provider 与出口 | 真实 SDK 版本、重试所有者、请求开始日志、预算 ledger、网络观察范围、离线资产 | FakeProvider 只用于模型决策；真实请求计数另验 |
| 备份和清理 | 真实 backup、manifest/pin、GC、恢复/迁移入口、凭据不可用处理 | 文件存在不代表可恢复；必须实做隔离恢复 |

当前静态核对确认 `storage/writer.py` 有独立 writer 线程、完整事务包裹、持久 `lookup` 回调接口、受限队列和只读连接入口，可作为 TC-CORE-025–029 的生产集成切入点。它并不保证每一种 `WriterCommand` 都提供正确的持久 lookup，也不证明所有调用方在等待取消后都按正确语义处理。应逐个选择真实业务命令验证。

### 2.1 安全且可判定的测试材料

准备两个彼此独立的无害效果目标：一个只在测试目录写固定文件并产生 hash；另一个由单独进程接收受控动作，持久记录请求与效果。接收器、控制器和证据目录必须位于 OpenBot profile 之外，并在 Daemon 被终止时继续存活。接收器不能与被测状态机共用一个内存计数器。

对于不可幂等动作，接收器每次真实执行都递增效果计数，不能偷偷去重而掩盖 OpenBot 的重复执行。对于支持提供方幂等的分支，接收器另行实现明确、有期限的幂等语义，并记录多个请求如何映射到同一效果。两种语义分别运行，不能混用。

秘密测试使用专用 canary，分别代表 Channel、Provider A、Provider B 和普通宿主环境变量。只在受限 fixture 里保留 canary 原值；交付证据记录 hash、来源类别、发现位置和是否泄漏，不把真实用户秘密写入日志或提交 Git。

满盘测试使用独立、有限容量、可丢弃的测试卷，DB、WAL/SHM 与需要测试的 Artifact 必须实际位于该卷。控制器和证据写到卷外。先记录设备/挂载点/容量，再填充该测试卷；不填用户系统盘。故障后释放测试填充物，并走产品恢复路径，不删库或手动改状态绕过失败。

## 3. 确定性屏障与故障注入

### 3.1 协议

屏障必须由测试控制器明确选择 `run_id + Task/Operation/Attempt + barrier_name`，并提供 `ARMED → REACHED → RELEASED/ABORTED` 回执。控制器只有在收到 REACHED、且对应持久证据已确认后才发起取消、撤销、故障或释放另一个竞争者。每个等待都有上限与故障清理，超时本身是用例失败或阻塞，不能靠增加 sleep 直到偶然通过。

屏障名称是本手册建议的映射标识，不代表当前仓库已经提供同名函数或参数。它们应落在真实业务路径上，不能在路径旁边运行一个替代状态机。测试接缝要限制到隔离测试构建或受保护本地测试配置，不能增加公开远程“杀进程/改状态”接口。

审批撤销与 claim、取消与第二派发事务，需要分开执行两种线性化顺序：先让撤销/取消事务提交，再放行另一方；另一次先让 claim/派发提交，再处理撤销/取消。不要在持有 SQLite 写事务时阻塞并等待另一写事务先提交，那会制造测试自身的死锁。

真实 kill 用例必须记录目标 PID、启动时间/启动标识、所属执行域、终止请求、退出确认和重启后的新身份。退出某个父进程不能自动证明全部旧 worker 或容器已停止；旧域隔离证据由实际 supervisor 提供，不能手填 `old_epoch_isolated=True`。Mac 进程树、容器 VM 和 launchd 专项见配套平台用例。

### 3.2 必需屏障及正确判定

| 屏障标识 | 必须放在哪里 | 对应故障/判断 | 主要用例 |
| --- | --- | --- | --- |
| `FP_INBOX_BEFORE_COMMIT` | T1 的全部持久化提交之前 | 请求无成功 ACK，重试不能留下半套 Task/inbox/outbox | 003–005、028 |
| `FP_INBOX_AFTER_COMMIT_BEFORE_ACK` | T1 COMMIT 已返回、入口 ACK 尚未发送 | 按原请求 ID 返回已提交结果 | 004、026 |
| `FP_APPROVAL_AFTER_COMMIT_BEFORE_ACK` | 审批决定、审计和 outbox 已提交，响应未返回 | 同决定重试不产生第二授权 | 010–011 |
| `FP_CLAIM_AFTER_COMMIT` | 消费 grant、Attempt 与 CLAIMED 已提交；尚未派发 | 真实重启后的安全恢复；CONSUMED 不复活 | 015、021–022 |
| `FP_DISPATCH_BEFORE_TX` | 第二派发事务 BEGIN 之前 | 让取消/策略变更先提交，随后派发必须复验 | 012–014、028 |
| `FP_DISPATCH_AFTER_COMMIT_BEFORE_SEND` | DISPATCHING COMMIT 已返回，执行器调用尚未开始 | 持久意图与外部事实有缝隙，恢复应核对 | 016 |
| `FP_EXECUTOR_RECEIVED_BEFORE_EFFECT` | 独立执行器已接收，实际副作用尚未提交 | 同 dispatch 重传、接收去重和旧域问题 | 020、022 |
| `FP_EFFECT_AFTER_COMMIT_BEFORE_REPLY` | 独立目标已经持久提交效果，回执尚未返回 | E=1 但本地结果未知，不得盲重放 | 017、019、029 |
| `FP_RESULT_BEFORE_COMMIT` | 收到真实回执、T5 尚未提交 | 结果持久化失败不能逆转真实外部效果 | 005、017、029 |
| `FP_RESULT_AFTER_COMMIT_BEFORE_DELIVERY` | 结果、审计、预算/通知合同已经提交，客户端尚未观察 | 查询/重连不重执行 | 018、044 |
| `FP_BACKUP_SNAPSHOT_READY_AND_GC_PINNED` | 一致备份快照及引用保护已形成，文件复制未结束 | 并发 GC 不破坏快照的 Artifact 引用 | 030–031 |
| `FP_ARTIFACT_AFTER_RENAME_BEFORE_DB` | Artifact 原子落地后，登记事务尚未完成 | 孤儿/缺失恢复、所有权与 GC 不误删 | 033 |
| `FP_PATCH_AFTER_FILE_1` | 多文件补丁实际替换第一文件后 | 部分提交和用户并发编辑可恢复、可解释 | 032 |
| `FP_PROVIDER_RETRY_READY` | 下一次真实 SDK 请求开始之前 | 取消/总 deadline/预算禁止新增请求 | 039、042–043 |
| `FP_PROVIDER_AFTER_FIRST_DELTA` | 实际流已收到首块、最终 usage 尚不可得 | 断流不是零费用证明，不触发隐藏工具或重试 | 040、042 |

在 DISPATCHING 提交后、真正发送前杀掉进程，测试控制器可能确知效果为 0。但如果生产恢复器只能看见已提交的派发意图，且没有可信无效果证据，它仍应保留 UNKNOWN/RECONCILING。不能把测试掌握的内存知识直接赠给恢复器；TC-CORE-016 专门防止这种假通过。

满盘时连 UNKNOWN 也可能无法写入数据库。TC-CORE-029 不要求一个不可写的库立刻改变状态；它要求停止新派发、不虚报成功、保留先前派发意图，并在存储恢复后核对真实结果。这个判定避免用不可能的断言逼出丢弃审计或清空数据库之类错误修复。

## 4. 独立证据与统一判定

### 4.1 每次运行的最小证据目录

证据应包含运行清单、每一分支的输入与顺序、脱敏 API 记录、只读数据库快照/查询结果、独立效果账本、实际网络请求记录、产品和旧执行域的身份/退出证据、产物 hash、异常诊断、用例结论及关联 issue。目录具体命名可以由仓库现有测试设施决定，但下面的关联字段不能缺失：

- `run_id`、用例/分支 ID、候选 commit、工作区差异摘要、产物 hash、锁文件 hash、配置摘要。
- Task、Operation、Approval、Attempt、dispatch、provider idempotency key、request ID、runtime epoch、fence、资源标识。
- Operation.version、审批/取消/策略版本、event 序号、outbox semantic key 与 revision。
- 所有屏障的到达、竞争事务提交、请求开始、效果提交、回执和结果提交的确定顺序。

“先后”优先由控制器握手、事务提交确认和关联 ID 确定，时间戳作为辅助；不同机器时钟的相近毫秒值不能单独证明因果顺序。摘要和截图用于阅读，原始结构化证据用于判定。

### 4.2 分开统计请求与效果

| 指标 | 观察者 | 用途 |
| --- | --- | --- |
| `N_send_started` | 产品网络/执行器调用边界，按请求 ID 记录 | 判断取消后是否新发请求；不能只看远端到达时间 |
| `N_received` | 独立接收器或提供方记录 | 判断真实网络请求数、隐藏 SDK 重试、重传 |
| `N_effect_committed` | 独立目标的持久账本或实际文件 hash/版本 | 判断真实业务副作用；不能由 Daemon 返回常量 |
| `N_grant_consumed` | 只读审批/审计与 claim 事务记录 | 判断一个 grant 是否仅消费一次，安全重试未复活审批 |
| 请求/预算记录 | Gateway 与预算持久 ledger | 将每次真实调用、预留、usage、未知费用及最终结算关联 |

支持提供方幂等的重试可能产生多次请求、仅一次效果；不能把 `N_received > 1` 一概判成重复副作用。反过来，外层 `generate()` 只调用一次，也不能证明 SDK 只发一次网络请求。连接失败可能没有到达服务端，断流可能仍在远端计算；计费与效果都必须保留“未知”的表达。

### 4.3 四对象、恢复和数据库证据

Approval 的批准与 Operation 的 claim 不是同一个动作。READY 不代表已经执行；首次 claim 消费授权并建立 Attempt，第二派发事务还要复验取消、epoch/fence、有效期、策略、身份与资源。已消费的 Approval 不回到 APPROVED；同一 Operation 安全重试沿用已消费的授权关系，但必须重新满足本次尝试的条件。

Operation 的不可变提案、提供方幂等键和每次 Attempt 的 dispatch 身份分别核对。同 Attempt 的重传保留 dispatch ID；新 Attempt 使用新 dispatch ID。不能靠重新生成 Task、Operation 或 request ID 绕过未解决效果对应的资源 quarantine。

Task 只有在其相关在途或未知动作都按合同处理后才能进入相应终态。取消请求已记录，不表示已在途的动作没有发生。UNKNOWN 的解决需要证据来源、对象归属和 Operation.version；人工确认应保留人工来源，不能冒充提供方回执。普通 resume 不具有重新授权或解除 quarantine 的权力。

用只读连接、产品只读导出或一致备份读取数据库。不要通过测试连接直接改终态、解除锁、消费审批、回填 receipt 或删除审计；那会绕开被测合同。读操作尽量短，避免测试自己的长读事务影响 WAL/备份/清理行为。表名、字段名以当前迁移为准，不把设计包旧 DDL 的 SQL 直接套到实际库。

## 5. 执行分组与失败处置

| 阶段 | 运行内容 | 开始条件 |
| --- | --- | --- |
| A：映射与基线 | 真实入口、证据接收器、合同解析与基本完整链路 | 固定候选、隔离 profile、可记录真实效果 |
| B：权限与派发 | 审批绑定、竞争、撤销、取消、claim/dispatch | A 的正常对照可运行；屏障能控制两种顺序 |
| C：崩溃与未知 | 真实 kill、重传、旧 epoch、持久 quarantine、可信核对 | 独立接收器和旧域隔离证据有效 |
| D：存储与恢复 | writer、取消、背压、满盘、备份/GC、补丁/Artifact | 独立有限卷可回收；恢复目标默认不派发 |
| E：策略与模型 | 注入、数据出口、秘密、实际 SDK 请求/流/预算 | 可观测网络与已锁定 SDK；不能外发真实秘密 |
| F：同版本合并门禁 | 核心 + 真实 macOS/飞书/模型等集成 + release gate | 所有修复已分问题提交并 push；最终候选可重建 |

用例不是依靠前一用例遗留状态才能执行的一条长流水线。每个分支应能从明确 fixture 重建，尤其故障/满盘/取消分支不能污染随后正常对照。先保存失败现场的只读证据，再回收专用执行域；需要进一步核对的 UNKNOWN 不能通过清库“恢复绿色”。

发现批准前副作用、重复不可幂等效果、秘密外发、UNKNOWN 资源绕过或状态损坏时，停止该 profile 的新增写动作，保留现场并建立最高优先级 issue。停止不等于把在途动作当作不存在；先记录或核对其实际结果。其他独立且安全的测试 profile 可以继续，不必为了一个失败重跑所有无关检查。

每个 issue 记录最短复现步骤、失败用例与分支、候选 SHA、真实/模拟边界、期待值和实测值、证据路径、初步根因、修复范围、回归集合。不能只写“测试未通过”或“修好了”。证据不充分时应补充复现，不能凭当前 harness 的标签把代码判为已成功或已漏洞化。

## 6. 核心用例索引与逐项操作

以下逐项内容与 `core_cases.json` 一致。所有用例当前都是 **NOT_RUN**；每项 `evidence` 是执行时需要产生的证据，不是当前已取得的证据。

| ID | 用例 | 门禁 | 真实边界要求 | 状态 |
| --- | --- | --- | --- | --- |
| TC-CORE-001 | 真实本地入口贯通四对象与一次受控效果 | CORE_STATE | 必须 | NOT_RUN |
| TC-CORE-002 | Task 合法跃迁、终态守卫与只读回放 | CORE_STATE | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-003 | 入站去重、负载冲突与身份作用域 | CORE_STATE | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-004 | T1 提交前与提交后 ACK 丢失的恢复 | CORE_STATE | 必须 | NOT_RUN |
| TC-CORE-005 | 状态、审计、outbox 与完成结果的事务原子性 | CORE_STATE | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-006 | 严格 JSON、JCS 标准向量与本地 Schema 边界 | CORE_STATE | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-007 | 已批准提案不可变及旧新内容精确绑定 | APPROVAL_DISPATCH | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-008 | 真实本地 API 身份、作用域与对象归属 | POLICY_EGRESS | 必须 | NOT_RUN |
| TC-CORE-009 | 审批 nonce、TTL 与重启后的 challenge 保护 | APPROVAL_DISPATCH | 必须 | NOT_RUN |
| TC-CORE-010 | 同版本审批竞争与批准后合法撤销 | APPROVAL_DISPATCH | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-011 | 批准已提交但响应丢失不产生第二授权 | APPROVAL_DISPATCH | 必须 | NOT_RUN |
| TC-CORE-012 | 撤销 owner 或授权与 claim 的确定性竞态 | APPROVAL_DISPATCH | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-013 | 每次派发前复验期限、策略、身份与资源 | APPROVAL_DISPATCH | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-014 | CLAIMED 后取消与第二派发事务的线性化 | APPROVAL_DISPATCH | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-015 | claim 已提交、尚未派发时的真实进程崩溃 | APPROVAL_DISPATCH | 必须 | NOT_RUN |
| TC-CORE-016 | DISPATCHING 已提交、发包前崩溃仍须核对 | APPROVAL_DISPATCH | 必须 | NOT_RUN |
| TC-CORE-017 | 外部效果成功、回执落盘前崩溃不盲重放 | APPROVAL_DISPATCH | 必须 | NOT_RUN |
| TC-CORE-018 | 结果已提交、通知或 UI 响应丢失不重执行 | CORE_STATE | 必须 | NOT_RUN |
| TC-CORE-019 | 在途取消保留未知结果且阻止后续动作 | APPROVAL_DISPATCH | 必须 | NOT_RUN |
| TC-CORE-020 | 同一 Attempt 重传与 dispatch 接收去重 | APPROVAL_DISPATCH | 必须 | NOT_RUN |
| TC-CORE-021 | 同 Operation 安全重试、稳定幂等键与失效拒绝 | APPROVAL_DISPATCH | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-022 | 旧 epoch、过期租约与迟到结果不能制造双执行者 | APPROVAL_DISPATCH | 必须 | NOT_RUN |
| TC-CORE-023 | UNKNOWN 资源 quarantine 防新 Task/Operation ID 绕过 | APPROVAL_DISPATCH | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-024 | 核对证据、Operation.version 与人工确认来源 | APPROVAL_DISPATCH | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-025 | 单 writer 独占完整事务与连接约束 | STORAGE_RECOVERY | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-026 | 调用者取消或超时后查询真实提交结果 | STORAGE_RECOVERY | 必须 | NOT_RUN |
| TC-CORE-027 | 队列预留、公平性、总 deadline 与背压 | STORAGE_RECOVERY | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-028 | 派发前真实 SQLite 满盘或提交失败 | STORAGE_RECOVERY | 必须 | NOT_RUN |
| TC-CORE-029 | 外部成功后满盘导致结果不可持久化 | STORAGE_RECOVERY | 必须 | NOT_RUN |
| TC-CORE-030 | 在线备份与并发 GC 保持 DB/Artifact 一致 | STORAGE_RECOVERY | 必须 | NOT_RUN |
| TC-CORE-031 | 缺失或被篡改备份的恢复必须拒绝假完整 | STORAGE_RECOVERY | 必须 | NOT_RUN |
| TC-CORE-032 | 多文件补丁部分提交与用户脏改动保护 | STORAGE_RECOVERY | 必须 | NOT_RUN |
| TC-CORE-033 | Artifact 文件与数据库登记之间的崩溃缝隙 | STORAGE_RECOVERY | 必须 | NOT_RUN |
| TC-CORE-034 | 硬拒绝与本地确认不能被批准或工具 metadata 覆盖 | POLICY_EGRESS | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-035 | 提示注入、摘要与导入元数据不能洗白权限或数据 | POLICY_EGRESS | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-036 | OFFLINE、LOCAL_MODEL 与实际网络出口 | POLICY_EGRESS | 必须 | NOT_RUN |
| TC-CORE-037 | 秘密按用途最小注入与凭据不可用时拒绝 | POLICY_EGRESS | 必须 | NOT_RUN |
| TC-CORE-038 | 跨分片秘密过滤、异常日志与 scanner 隐式外发 | POLICY_EGRESS | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-039 | 实际 Provider 请求计数与唯一重试负责人 | PROVIDER | 必须 | NOT_RUN |
| TC-CORE-040 | 流式工具参数完整性、ID 对应与异常输出 | PROVIDER | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-041 | SDK 自动工具 helper、托管工具和扩展字段旁路 | PROVIDER | 必须 | NOT_RUN |
| TC-CORE-042 | Provider 取消、断流、deadline 与未知计费 | PROVIDER | 必须 | NOT_RUN |
| TC-CORE-043 | 并发预算预留、重复结算与空转熔断 | PROVIDER | 产品模块/合同集成 | NOT_RUN |
| TC-CORE-044 | outbox 重复、乱序与未知 ACK 不重执行业务 | CORE_STATE | 必须 | NOT_RUN |

完整44项操作卡已统一收入 [TEST_CASES.md](../cases/TEST_CASES.md) 和 [test_cases.json](../cases/test_cases.json)，每项均有失败诊断、修复方向与回归要求。

## 7. 针对实际仓库的六文件静态核对

### 7.1 证据来源与适用边界

以下是本轮读取实际源码后的观察，**不是执行结果**。它们说明现有特定 harness 或 gate 的证据能支持到哪一层，并给出下一步复现方式；不能据此推断仓库其他文件没有真实测试，或断言全部产品行为都存在同样问题。

固定提交：[`a223d36a659b7ecf32fca2b4890fc187d3e96e48`](https://github.com/xiongcp/OpenBot/commit/a223d36a659b7ecf32fca2b4890fc187d3e96e48)。所有下列来源均为该项目的一手源码。引用中的行号用于定位本次冻结版本，不作为后续版本的稳定接口。

| 来源 | 完整路径与可打开链接 | Git blob SHA |
| --- | --- | --- |
| S1 | [services/core/src/openbot/application/mvp_regression.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/mvp_regression.py) | `f2bacfca3b41fc9f4048efd105f04350e9019650` |
| S2 | [services/core/src/openbot/application/mvp_release_gate.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/mvp_release_gate.py) | `2bb5803414f00bec680f886e8d53fb7819b7f41a` |
| S3 | [services/core/src/openbot/application/chaos_soak.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/chaos_soak.py) | `de2f8c30396217a7addf115a4c04ed7d5142c96d` |
| S4 | [tests/integration/scenarios/mvp/test_mvp_capability_regression.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/tests/integration/scenarios/mvp/test_mvp_capability_regression.py) | `f89894642122f208fabe670e12bee1d0b19dc092` |
| S5 | [services/core/src/openbot/application/vertical_slice.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/vertical_slice.py) | `d7b7a0fd0549ccb1e526d2742f28ee6da6d58ee8` |
| S6 | [services/core/src/openbot/storage/writer.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/storage/writer.py) | `c97a94884abe0013d256f07254ffeac7b72143ff` |

### SR-CORE-01：模型能力标签超过本分支实际覆盖

**源码事实。** S1 第 20–23 行的 `_OfflineOllamaTransport` 返回固定内容与 token 数；第 50–57 行构造本地模型声明、固定权重摘要和 `runner_offline_egress_verified=True`，实际 transport 仍为该 stub。第 59–61 行依据这一结果加入 `cloud_and_local_providers`。这个分支没有调用云提供方，也没有打开 Ollama socket。[来源 S1](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/mvp_regression.py)

**尚不能支持的结论。** 不能将其计作实际云 SDK 请求、真实 Ollama 权重加载、工具能力或离线网络出口已通过。这个 stub 仍可用于适配器输入/输出合同测试；问题是将其覆盖范围扩大成能力实证。

**下一步复现与修复。** 在隔离目录运行现有 suite 并记录它是否在没有真实模型服务时仍输出该标签；这是待执行负例，不是本次已运行结果。拆分报告中的“合同模拟”“实际 SDK”“真实本地模型”和“真实云服务”证据字段，以请求记录、模型实例与资产摘要绑定能力声明。执行 TC-CORE-036、039–043，并配套真实服务用例；不靠多加一个 `verified=True` 修复。

### SR-CORE-02：能力汇总测试主要断言自报标签

**源码事实。** S4 调用 `suite.run_all()` 后检查失败计数、两个边界布尔值和六个 subsystem 字符串集合。它自身没有新增独立网络、进程、外部效果或数据库结果 oracle。S1 的三个操作系统完成声明显式为假，这一范围限制是有价值的，应保留。[来源 S4](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/tests/integration/scenarios/mvp/test_mvp_capability_regression.py)；[来源 S1](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/mvp_regression.py)

**尚不能支持的结论。** 六个字符串齐全不等于六种真实产品能力或一条完整业务链已验收。底层 harness 可能包含真实局部代码，也可能包含合成数据；汇总必须保留这种层级差别。

**下一步复现与修复。** 运行 TC-CORE-001 时对照真实入口、Broker、效果、完成处理器和 outbox 五处独立证据；再给汇总器输入“子标签存在但实际证据缺失/来自其他 SHA”的负例。汇总器应拒绝将其提升为产品验收 PASS。既有集合测试可保留作报告格式回归。

### SR-CORE-03：soak 中满盘和备份标签没有对应故障操作

**源码事实。** S3 第 57–58 行直接把 `sqlite_backup_and_disk_full_guard` 加入已验证列表；该方法没有执行备份、恢复或制造磁盘满。返回中的 `dangerous_blind_retry_count` 为常量 0。报告显式不宣称断电实测或百分之百不丢数据，这两个限制是正确的，应保留。[来源 S3](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/chaos_soak.py)

**尚不能支持的结论。** 不能把 `sample_count` 或这条标签当成 SQLITE_FULL、在线备份/GC 或真实效果没有重放的证据。磁盘故障通过也不能由日志中出现 disk 字样推导。

**下一步复现与修复。** 分别执行 TC-CORE-028、029、030–031，保存卷外证据、实际存储错误、备份 manifest 和隔离恢复结果。报告只从执行完成的结构化 case result 聚合；没有执行的 fault class 留 NOT_RUN，不能预先加入 verified 列表。若当前实现没有对应生产入口，登记实施缺口。

### SR-CORE-04：DNS/半开与休眠分支目前是逻辑模拟

**源码事实。** S3 使用固定 consumer/PID 与 `now_ms` 调用 watchdog，使用两个手工构造的 `ClockSnapshot` 检查 TTL，然后加入 DNS/TCP 和休眠标签。该文件没有真实 DNS 阻塞、TCP 半开或 Mac 休眠操作。[来源 S3](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/chaos_soak.py)

**尚不能支持的结论。** 它能覆盖部分健康与时钟逻辑，不能证明实际长连接、OS 休眠后旧授权、唤醒重连或后台进程的行为。

**下一步复现与修复。** 把现有逻辑测试标为确定性模拟，补齐平台手册中的真实网络/休眠证据。核心侧执行 TC-CORE-009、013、021、036、042；真实系统时间无需由核心用例修改。平台专项验证唤醒后的真实进程、连接和授权状态。

### SR-CORE-05：“crash” 方法没有实际进程崩溃与重启

**源码事实。** S5 的 `run_fault_crash_scenario()` 在同一 harness/writer 中调用恢复服务，传入 `old_epoch_isolated=True`。`after_effect_before_receipt` 分支以赋值把 `fault_effect_count_at_crash` 设为 1；返回的 `blind_replay_count` 为 0 常量，`resolved_operation_state` 为成功字符串。该方法没有实际终止 Daemon、隔离旧执行域或重开数据库。S3 根据这些值把 SIGKILL 场景加入 verified。[来源 S5](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/vertical_slice.py)；[来源 S3](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/chaos_soak.py)

**尚不能支持的结论。** 它可以是部分恢复分支的合同测试，但不能证明 SIGKILL 后持久化恢复、真实副作用数、旧执行域清理或无重复执行。S5 报告中的 `real_production_services_called=False` 应保留，且不能在上层汇总时丢失。

**下一步复现与修复。** TC-CORE-015–018 与 022 使用独立进程和真实退出/重新打开；效果计数来自独立接收器。把 test harness 的固定计数改为明确模拟字段或真实观测，不能简单改名称后继续用它作发布证明。运行失败时同时保留旧域和新域证据，而不是追加 sleep。

### SR-CORE-06：未发生效果的分支同样用合成文本确认成功

**源码事实。** S5 第 591–636 行将 `after_dispatch_before_effect` 与 `after_effect_before_receipt` 放在同一大分支；两者都通过 CLI 核对提交 `CONFIRMED_SUCCEEDED`，证据内容是 `verified-receipt-{crash_point}` 这种本地合成字符串。前一分支并未在该方法中完成真实效果。[来源 S5](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/vertical_slice.py)

**尚不能支持的结论。** 这不能证明生产 reconciliation 会验证证据真实性、效果归属或无效果结果。它也不能单独证明普通攻击者在真实 API 上可以越权强制成功，因为还需要核对真实认证、权限、证据导入和来源标记；本轮没有运行这一攻击路径。

**下一步复现与修复。** 执行 TC-CORE-016、024，分别提供无来源字符串、另一对象 receipt、可信无效果证据、可信成功 receipt 和人工确认。必须区分 PROVIDER_VERIFIED 与 USER_ATTESTED；后者若被产品允许，须经过明确的受限用户确认并保留来源，不能因为文本包含 verified 就升级为提供方证明。UNKNOWN 没有被可信解决前保留 quarantine，不以假成功结束测试。

### SR-CORE-07：完成 helper 绕过待验收的生产完成合同

**源码事实。** S5 第 227–261 行的 `_complete_operation_and_task()` 用 SQL 将 Attempt、Operation、Task 写成 SUCCEEDED、receipt 设为 `{}`，其 lookup 总是返回 None。它没有在该 helper 中调用生产 OutcomeVerifier，也没有在同一事务中创建完成审计/outbox；正常片段随后在另一个事务单独 enqueue 通知。这里真实 SQLite 和实际文件补丁确实存在，不能把整个片段描述成纯虚构。[来源 S5](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/vertical_slice.py)

**尚不能支持的结论。** 它不验证生产完成流程的事务原子性、稳定请求 ID、receipt 验证或故障后的结果核对。测试能读到 SUCCEEDED，并不说明 OutcomeVerifier 已完成工作。

**下一步复现与修复。** TC-CORE-001、005、018、026 必须调用生产完成服务。对每个完成持久化步骤注入失败，核对状态、事件、预算与 outbox 合同。保留 helper 仅作内部 fixture 时，要使其无法被误用为产品验收入口；不要把 lookup=None 的结果用于证明跨重启幂等。

### SR-CORE-08：进程内 API 与宿主 sleep 子进程不证明真实网络或容器隔离

**源码事实。** S5 `_InProcessTransport.request()` 直接调用 `self._api.handle(req)`；`_MemoryChallenges` 是字典；`_OfflineSyntheticGateway` 仅向列表追加发送 ID 后返回成功。正常片段启动的是宿主 Python 的短暂 sleep 子进程，注册时手填启动 token；这个片段没有展示容器执行域中的真实命令。文件写入和 supervisor 局部调用是真实代码路径。[来源 S5](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/vertical_slice.py)

**尚不能支持的结论。** 它不能独立证明真实 listener 身份边界、nonce 重启恢复、通知提供方语义、容器/进程隔离或旧域回收。

**下一步复现与修复。** 核心执行 TC-CORE-001、008、009、022、044；平台用例检查真实 worker/container 身份、资源和清理。测试启动令牌必须从可验证的真实进程身份取得，不能让证明者与被证明的输入都由测试自行填同一常量。

### SR-CORE-09：pilot 的布尔条件没有纳入已记录的供应链阻断

**源码事实。** S2 第 37–38 行在未验证 Darwin 或供应链产物计数为 0 时追加阻断原因；第 46 行的 `pilot_ok` 仅由 `security_critical_failures == 0` 和 `darwin_arm64_verified` 组成。因此当供应链返回零验证产物且其余这两个条件为真时，代码表达式仍可给出 pilot-ready，同时存在供应链阻断原因。是否实际环境允许到达这一分支，需要执行负例确认。函数接收平台/租户布尔值，本文件自身没有把它们绑定到运行证据、候选 SHA 或产物 hash。[来源 S2](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/mvp_release_gate.py)

**尚不能支持的结论。** 不能把返回的 pilot-ready 自动解释成同一候选及其产物的严格 macOS MVP 门禁全部通过。函数外是否已有证据核对需另查，不能从本文件假定有或没有。

**下一步复现与修复。** 在 gate 单元测试中注入“零验证产物”的确定结果，验证 pilot 不能就绪；再用真实隔离发行目录分别测试缺件、hash 不符、来源于其他 SHA 和完整匹配的情况。门禁明确区分 Mac pilot 与全三系统门禁，但两者适用的共同必选条件都必须满足。接受结构化、可追溯的验收结果，不能以任意 `True` 替代证据。这是发布门禁专项的修复项，不另外增加第 45 个核心用例。

### SR-CORE-10：生产 writer 已有可用实现面，仍需真实故障证明

**源码事实。** S6 有独立 writer 线程和多 lane 队列、按剩余 deadline 设置 busy timeout、完整 `BEGIN IMMEDIATE`/`COMMIT` 包裹、禁止命令内部自行事务/PRAGMA/ATTACH 等操作的 authorizer、只读连接入口、每个命令的持久 lookup 回调，以及提交异常后的停止接收/查询真实结果路径。Future 在接受后不让等待方直接取消底层工作。这些是实际实现，不应在计划里重新当作“全部尚未编写”。[来源 S6](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/storage/writer.py)

**尚未验证的部分。** 每个应用命令是否都正确实现 lookup；队列保留是否在真实负载下有效；调用方取消是否误报回滚；实际锁争用、deadline、提交失败、满盘、停止与恢复时是否保持合同。接受入队也不等于命令已经持久提交。

**下一步复现与修复。** TC-CORE-025–029 直接覆盖这个生产 writer 及真实调用方，取消用例清空内存缓存影响后重启再查。只修复实际失败的路径，不为了“统一”而另造第二个 writer 或把所有工作迁移到替代参考实现。

## 8. 每个问题单独修复、commit 和 push

用户要求每修复一个问题都单独 commit + push。这里规定执行闭环；本轮没有替用户运行这些 Git 操作，也没有声称存在已推送修复。

1. **先定一个问题的边界。** 用一个 issue 标识一个根因或一个不可拆开的缺陷。写明失败用例/分支、冻结 SHA、真实和模拟边界、证据、预期与实测。多条用例可能属于同一个根因；反过来，多个独立根因不能放在一个“修复全部测试”的提交中。
2. **留下失败复现。** 先让最小回归在修复前稳定失败。竞态必须由屏障确定顺序；故障必须发生在真实目标边界。缺失测试设施本身可以作为单独问题交付，但它的落地不能直接把尚未执行的产品用例变成 PASS。
3. **实施最小修复。** 同一个问题的业务修复、必要测试和对应文档可以在同一提交。不得通过删断言、降低权限守卫、忽略 UNKNOWN、把失败改 warning、加长 sleep、硬填成功计数或调整标签绕过。
4. **运行明确回归集合。** 先跑失败复现，再跑该用例 `regression` 中有影响的相邻合同；权限、持久化、恢复和通用 SDK 路径的修复需要对应跨模块回归。记录命令的实际参数、退出码、真实证据和环境；不要把其他候选的历史绿灯复用到当前修复。
5. **审查本问题 diff。** 核对没有混入用户原有改动、其他根因、真实凭据或敏感测试产物。只暂存本问题需要的文件；避免笼统收集整个工作区。用户数据、第三方缓存与自动生成巨大证据不应混进修复提交。
6. **生成独立 commit。** 提交消息包含 issue ID、具体根因与行为变化。保存本地 commit SHA 和测试证据关联；提交后确认没有额外改动，并对必要 smoke/回归在该 commit 上补齐最终证据绑定。
7. **立即 push 这一问题的提交。** 使用仓库实际已确认的 remote/branch，不猜测分支，不 force push，不重写用户历史。确认远端分支实际包含刚才的 commit SHA 后，才把问题记为“已推送”。已有授权的正常 push 无需重复征求确认。
8. **处理阻塞并继续。** 若远端鉴权、网络或策略阻断 push，保留本地 SHA、复现/修复/测试结果及真实错误，明确标记 PUSH_BLOCKED；不能声称已推送。继续不冲突的取证或修复工作，按照配套 Git 流程处理阻塞。
9. **最终重新汇总。** 每个问题都留 issue→失败证据→修复 commit→回归证据→远端 SHA 的链路。发布候选变化后重算证据适用性；最终门禁必须对应同一候选 SHA、安装产物 hash、配置与架构，并保留尚未运行/阻塞项。

建议问题记录至少有：`issue_id`、`severity`、`root_cause`、`failing_cases`、`reproduction`、`candidate_sha_before`、`fix_commit_sha`、`regression_results`、`evidence_paths`、`remote_branch`、`remote_sha_verified`、`status`。字段是建议的数据合同，不声明当前仓库已存在同名 issue 系统或命令。

## 9. 交付与结论记录

执行完成后，报告先写“这一候选在这一 Mac/架构/配置上哪些门禁通过”，再列阻断、残余未知和不适用边界。准确列出实际运行/通过/失败/阻塞的用例与分支数量；不能把 `sample_count`、函数名或当前规划数量当实测数量。

针对真实故障的结果，至少给出外部效果计数、持久对象状态与恢复结论的相互印证。针对数据出口和 SDK 请求，给出实际受观测进程/网络范围、请求开始/接收计数和预算对应关系。针对修复，给出每个独立 commit 及远端确认结果。报告里明确真实 Mac、真实飞书、真实模型等环境证据来自哪些配套用例；缺一项就保留对应门禁未通过，不由核心模拟结果补齐。

本手册与 JSON 的当前状态维持 **44 / 44 NOT_RUN**。源码阅读只形成待复现事项，没有改变任何产品用例状态。
