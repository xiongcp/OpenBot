# OpenBot macOS MVP：证据驱动的发布门禁

版本：2026-11-05。适用项目：[xiongcp/OpenBot](https://github.com/xiongcp/OpenBot)。本文件是验收规则，**不是已经通过验收的报告**。目前执行结果均从 `NOT_RUN` 开始，代码、测试、push、CI 和产物 SHA 只能在实际执行后填写。

## 1. 允许宣布的范围

默认目标为 **完整 macOS MVP**：按已经确认的 v1.2 / M3 功能基线，在明确的 Mac 硬件/架构、macOS build、安装路径和服务版本上，使全部原必需链路、安全边界、持久恢复、真实集成和交付行为通过验收。本轮限定的是平台证据范围，不删减原必需功能。它不能自动代表原工程计划 M3 的 Windows/Linux/macOS 三平台完成，也不能代表 M4 的 Tauri、签名公证桌面发布。

执行前冻结范围清单：当前交付的必需能力、明确不在本次发布中的能力、每个条件门禁的适用理由。原要求中的必需能力不能由执行代理自行删掉。能力已经声明提供，就必须验真；不能在看到失败后将其改为范围外。未知是否适用时先核对实际产品入口与原阶段，不填 `N/A` 掩盖缺口。**当前代码尚未实现的原必需能力应登记实现缺口，不能因此排除。**

真实云 Provider 与真实 Ollama 是两条独立必需链路，各自需要真实运行证据。只支持其中一种时，最多描述为收窄的 Mac 试点或局部验证，不能宣布完整 macOS MVP；完整目标仍有阻断。Tauri / M4 仍保持原阶段的条件门禁，不反向成为 CLI/daemon MVP 的无条件要求。

| 维度 | 可计入的证据 | 不足以支持的替代证据 |
|---|---|---|
| Apple Silicon | 真机 Darwin arm64；受测进程和所有 helper 的实际架构 | 测试 shell 是 arm64、手填 Darwin=true |
| Intel | 声明支持时，在 Intel Mac 上原生运行 | Apple Silicon 上的 Rosetta 或 Linux amd64 VM |
| Darwin 系统集成 | 用户登录会话中的 launchd、Keychain、文件系统、睡眠/网络等真实行为 | Docker Desktop 内部 Linux VM 或修改对象时钟 |
| CLI/daemon MVP | 实际安装、跨进程本地 API、daemon/worker 启停、真实恢复与隔离 | 仅 in-process harness 或参考设计校验 |
| Tauri/TCC/签名 | 若本次声称提供，对实际二进制和下载产物做真实验证 | 未签名试点、临时去 quarantine、关闭 Gatekeeper |
| 三平台 M3 | 每个声明平台及架构自己的完整证据 | macOS 通过后把 Windows/Linux 状态改成 PASS |

关闭界面/客户端不应杀死长期驻留 daemon；用户明确停止或卸载才按身份和归属回收对应资源。无法提供隔离后端的危险动作返回不可用，不能转为宿主机执行。

## 2. 缺陷严重度与测试优先级是两条轴

### 缺陷严重度

| 等级 | 定义及示例 | 对当前 MVP 的处理 |
|---|---|---|
| S0 | 未经授权产生外部效果、秘密泄漏、不可恢复数据损坏、隔离/身份边界失守 | 立即阻断发布；控制影响并修复，相关安全门禁全部重验 |
| S1 | 必需功能不可用、可确定重复副作用、UNKNOWN/取消/恢复失真、安装无法完成、发布证据可被伪造 | 当前范围阻断发布；必须闭环 |
| S2 | 局部非关键行为错误且有明确受控替代，未破坏安全与数据正确性 | 若触及任何必需需求仍阻断；只有已明确可延后的非必需项可保留 DEFERRED |
| S3 | 文字、布局或非关键体验瑕疵 | 可按原范围决定修复顺序；保留真实状态和影响 |

严重度不能只根据测试是否 P0/P1 推导；CI/测试入口错误也可能阻断全部验收。缺凭据本身是环境阻塞，不伪装成产品 bug 已修复；实际实现缺入口/适配器则属于实现缺口，不能一律归为缺环境。

### 测试优先级

| 优先级 | 内容 | 放行要求 |
|---|---|---|
| P0 | 授权、持久化、恢复、取消、隔离、数据出口、真实能力与证据基础 | 所有适用必需用例 PASS；FAIL/BLOCKED/NOT_RUN 都不放行 |
| P1 | 当前版本必需的真实端到端、安装与兼容性、已经承诺的用户行为 | 所有适用必需用例 PASS；不能用“优先级较低”跳过 |
| P2 | 本次范围外或明确可延后的增强、探索性检查 | 保留范围与结果；不得把原必需项降为 P2 以求通过 |

S0/S1 未关闭数必须为 0；这一条件并不自动允许所有 S2/S3，也不能代替用例门禁。`DEFERRED`、`BLOCKED` 和 `NOT_RUN` 都不是 `FIXED`。

## 3. 证据等级和状态

每条用例同时记录测试层级、实际环境和产品路径，不能只有一个 `passed: true`。

| 层级 | 能证明什么 | 仍需补什么 |
|---|---|---|
| 合同/单元 | Schema/JCS、状态守卫、明确输入输出、可控时钟和模型提案 | 实际 adapter、存储、进程、网络及服务行为 |
| 生产路径集成 | 真实 application/adapter/storage、SQLite、HTTP/stdio、故障注入 | 声明涉及的原生 OS 和真实外部服务 |
| 原生 macOS | Darwin、Keychain、launchd、进程组、文件系统、网络/睡眠等 | 未在本次机器/架构覆盖的变体 |
| 真实服务 | 专用飞书测试 app、真实云 Provider、真实本地模型、真实 Chromium/MCP | 其他服务版本/账号配置、供应商不可见内部行为 |
| 干净安装/交付 | 固定候选构建产物在新用户/目标环境的首用、卸载和资产完整性 | 未测试架构/签名模式，不自动外推 |

现有 44 个 `TC-CORE-*` 与 38 个 `TC-MAC-*` / `TC-INT-*` 是执行清单，初始均 `NOT_RUN`。核心用例也必须调用产品实际模块与真实 SQLite；参考 DDL 的历史校验不是当前实现结果。原生和集成用例不能由布尔参数、手填 attestation 或模拟对象代替。[R1–R4]

单条执行状态使用：`NOT_RUN`、`RUNNING`、`PASS`、`FAIL`、`BLOCKED_ENV`、`BLOCKED_CREDENTIALS`、`BLOCKED_DEPENDENCY`、`INCONCLUSIVE`。测试脚本 skip 必须记录原因；只有执行前已证明不适用的条件用例才可用 `NOT_APPLICABLE`，且带原范围依据。mandatory case 的 skip、超时、collect 错误或部分运行不得记 PASS。

问题状态使用：`OPEN`、`NOT_RUN`、`TRIAGED`、`REPRODUCED`、`FIXING`、`LOCAL_VERIFIED`、`COMMITTED`、`PUSH_UNKNOWN`、`PUSH_BLOCKED`、`PUSH_VERIFIED`、`CI_PENDING`、`CI_BLOCKED`、`FIXED`、`REOPENED`、`DEFERRED`。状态允许保留多个维度：例如 push 已确认而 CI 仍阻塞；不能用一个“完成”字段抹去未完成门禁。

## 4. 必须逐项通过的门禁

表中的用例范围是入口索引，不限制需要追加的具体回归。执行者必须把每个 G 项映射到本次实际适用的用例 ID、命令、证据和候选 SHA；缺失映射本身阻断放行。

| 门禁 | 必需验收 | 典型关联用例/证据 | 阻断例 |
|---|---|---|---|
| G00 仓库与固定候选 | 确认项目、push 目的地、分支、实际 baseline；最终 candidate SHA/tree 固定、可达；用户 dirty 内容未混入 | repo binding、parent/tree/diff、远端精确 ref 回执 | 把只读参考 SHA 当本机基线；只测未提交目录；目的地不明 |
| G01 可运行测试与 CI | 当前真实命令可收集执行；必需依赖存在；workflow 位于支持的位置，事件/过滤命中；实际 job 运行 | command manifest、collected/executed/skip、CI run/job/checkout SHA | collection errors、SDK skip冒充成功、子目录 YAML 未被发现 |
| G02 真实内核链路 | ingress→Task/Operation/Approval/Attempt→Broker→executor→真实效果→OutcomeVerifier→outbox；各入口与 DB 一致 | TC-CORE-001–006、018、044 | in-process transport 冒充 socket；直接 SQL 写成功；只断言能力标签集合 |
| G03 授权与两次短事务 | 授权摘要不可变；过期/nonce/policy/actor/cancel/resource/epoch 在必要阶段复核；CONSUMED 不退回 APPROVED | TC-CORE-007、009–014、020–022；竞争屏障与事务轨迹 | 批准后提案被修改；只 claim 复验；旧 grant/epoch 继续派发 |
| G04 UNKNOWN、取消与隔离资源 | 崩溃窗口保守 UNKNOWN；可信证据核对；取消终态无未决 DISPATCHING/UNKNOWN；新 ID 不绕过 quarantine | TC-CORE-015–017、019、023–024；独立效果接收器 | 因效果计数0就盲重跑；一句人工“成功”覆盖 DB；进程重启清 quarantine |
| G05 Writer 与存储故障 | 完整事务由唯一 writer 管理；稳定请求 ID 查 commit 结果；队列/背压；实际满盘/故障不触发未记账效果 | TC-CORE-025–029；真实 SQLite/文件系统故障 | caller 超时当 rollback；硬编码 blind_retry=0；未执行就追加 disk_full 标签 |
| G06 Artifact、补丁、备份恢复 | 旧/新 hash 与审批精确绑定；多文件部分提交可恢复；备份 DB/Artifact 一致并 pin GC；secret_ref 与真实秘密分开 | TC-CORE-030–033、TC-MAC-018、021 | parser 成功当安全写入；备份缺 artifact仍成功；真实秘密入备份 |
| G07 身份、策略、秘密与出口 | 本地认证、owner/对象作用域、硬拒绝、注入边界、用途最小凭据、日志脱敏、实际 egress | TC-CORE-008、034–038；TC-MAC-019、022；TC-INT-014 | 外部 hints/allowlist 提权；scanner联网；localhost 当无云证据 |
| G08 Provider 合同与真实双类型模型 | SDK 真实请求计数/唯一重试负责人；流式工具参数完整；禁自动执行 helper/托管工具旁路；预算/取消；至少一个真实云 Provider和真实 Ollama 本地模型分别留证 | TC-CORE-039–043；TC-INT-013、016及明确云模型子项 | mock Ollama 代表云和本地；取消后新 HTTP 请求；手填计费/egress attestation |
| G09 原生 macOS 运行与隔离 | 实际用户服务、唯一 profile 锁、正确进程身份、客户端退出不杀 daemon；真实睡眠/网络/重启；Docker生命周期和回收次序 | TC-MAC-001、003、008–019 | 父子重复排他锁自锁；只杀 CLI不收容器；缺沙箱转宿主机 |
| G10 真实飞书链路 | 专用测试 app、单 gateway、owner 身份与撤销、durable ACK去重、卡回调时钟/重投、发送 UNKNOWN、进程外 watchdog | TC-INT-001–006、016 | 只用直接调用回调对象；发送副作用重复；阻塞 SDK让控制面失联 |
| G11 受控 Browser 与 MCP | 真实 Chromium sandbox/资产/profile锁；Service Worker/重定向出口；下载上传；真实 stdio、manifest 变更、超时核对 | TC-INT-007–012、015 | route 拦截当全部出口控制；no-sandbox静默；tool hints绕过审批 |
| G12 安装、离线资产、恢复与供应链 | 干净Mac用户真实首用；锁定依赖和全部运行资产来源/hash/许可证；声明交付产物非空且逐个验证；恢复 secret_ref失效可处理 | TC-MAC-004–005、010、021；实际产物manifest、SBOM/来源/锁和构建记录 | 开发机缓存掩盖下载；只数 manifest文件；verified_artifacts=0仍 pilot_ready |
| G13 累计回归和长运行证据 | 当前候选重跑必需累计回归；真实故障/恢复、资源与预算观测；样本数、时长、峰值有原始依据 | 实际 soak/chaos日志、故障事件与计数、前后资源、前次修复回归 | 修改对象时间冒充睡眠；零样本通过；承诺未测性能百分位 |
| G14 对准候选的 CI 与最终结论 | 本地、真实门禁、CI、构建对应同一候选；CI实际checkout核对；每个阻断理由直接否决 ready | immutable candidate、run/attempt/job、证据索引与release评估负例 | 其他 SHA 绿灯嫁接；布尔ready输入；有blocking_reason仍ready |
| G15 已声明的条件交付能力 | Intel、Tauri/TCC、签名公证/离线Gatekeeper、升级仅按事先声明范围启用门禁 | TC-MAC-002、006–007、020–021的适用部分 | Rosetta冒充Intel；去 quarantine后说首次启动通过；失败后改为范围外 |

### 外部效果必须由独立观察方证明

效果接收器的账本与被杀的 daemon、它的 DB 和进程分离；用实际文件 hash、服务端持久 receipt 或有稳定 operation key 的受控接收器核对。记录至少三个不同指标：客户端/socket发送、服务端接收、逻辑效果。安全幂等重传可能带来多次请求但只产生一个效果，不能把所有计数强行写成 1。

DISPATCHING 已落盘后、发送前被 kill，即使测试知道服务器效果为 0，产品仍需要 UNKNOWN 和受信核对；测试信息不能越权成为生产恢复依据。所有关键竞态都要用屏障/事件分别控制两种线性化顺序，保留真实事务/进程时刻，而不是只重复 sleep 测试。

### 真实服务只在专用目标上产生受控效果

真实飞书用已授权测试 app/目标，真实模型使用最小必要请求和已知预算，浏览器/MCP写测试使用隔离的受控对象。凭据缺失可阻塞 G08/G10 的对应子项；不影响继续 G02–G07 等独立工作，但仍阻断最终范围完整放行。不得把真实用户数据或任意公开站点当故障注入目标。

### 长运行不以伪精确承诺代替测量

执行前记录计划持续时长、并发、工作负载、资源预算与停止条件。原需求已有具体阈值时遵守；未定义时先制定可审查的试验方案，报告实际样本和区间，不能自行声称“24小时无故障”“P99低于某值”或零泄漏。没有真实故障注入就不能报告相应恢复通过；进程/容器/连接/队列增长必须来自实际观测。

## 5. 固定候选 SHA 与 CI 门禁

修复引入提交叫 `introduced_by_sha`；实际通过所有对应验证的提交叫 `verified_on_sha`。通常相同。若后续修复另一个独立 CI 基线问题，则后者可以是包含前者的后续候选，但必须验证 ancestry、重跑相关测试，不能直接搬用旧结论。

最后冻结 `candidate_sha` / `candidate_tree`，所有最终必需测试和 CI 以它为对象。构建产物注明 `source_sha`、锁/依赖/资产摘要、构建步骤和实际文件 hash。提交自身不需要把自身 SHA 写进源文件；回执和发布清单在 Git 外生成并绑定候选，避免无限 amend/重建自引用。

PR CI 可能 checkout 合并合成提交，run 元数据与实际 checkout 也可能不同。按真正测试的代码记录三者，不能把合并提交结果当修复 head 结果。要验证修复 head，选择实际支持的 push / dispatch 工作流或明确 checkout它；要发布 merge候选，则把它作为新候选重新核对。只检查“有一个成功的 CI run”不合格。[G1][G2]

GitHub 仅识别支持位置的 workflow；在 `.github/workflows/` 子目录放 YAML 不满足自动发现要求。[G3] 当前参考 run `41949551726` 已失败，且上述 runner / Python / collection / 依赖安装存在独立问题线索。任何修复后的结论必须由新的真实 run 支持，不能把这些历史记录覆盖成 PASS。

可以在某个修复已经 push 并被远端确认后，保留 `CI_BLOCKED` 并继续修另一个独立 CI 根因；这只解决执行顺序死锁。**CI_BLOCKED 仍然不能放行，也不能把问题记为 FIXED。** push 未确认则不能累积下一项修复提交。

## 6. 发布评估器不能信任自报成功

发布结果必须从不可变执行记录导出，并验证来源、范围、代码和覆盖率。不能仅收集调用者传入的 `security_critical_failures=0` / `darwin_arm64_verified=true`。参考 `mvp_release_gate.py` 静态审查提示，存在已记录供应链阻断理由而 `pilot_ok` 仍可为真的路径；本机需要用受控负例复现，并按单问题流程修复。[R4]

最小必要判断语义如下，属于验收规则，不是仓库中已经存在的 API：

```text
先验条件：冻结且非空的 required_case_ids、required_gate_ids、expected_artifact_ids
候选条件：真实 candidate SHA/tree + 精确远端可达证据
证据条件：每条必需记录来源可核、未被篡改、关联当前 candidate 和环境
执行条件：每条必需用例实际执行、断言成立、无未解释 skip/超时/collect 错误
产物条件：声明交付清单中的每个产物存在并通过 hash/来源/完整性核验
CI条件：必需工作流/作业真正运行，实际 checkout 对准当前候选，结果通过
缺陷条件：S0/S1为0；不存在任何触及必需需求的未关闭缺陷
阻断条件：blocking_reasons 必须为空；任何一条均否决 ready
只有以上全部成立才可生成 PASS_MACOS_MVP
```

必须添加负例证明：空用例集、零执行数、零验证产物、缺证据、伪造 PASS、其他 SHA 的绿灯、未知 OS/arch、未触发 workflow、只有 mock 的真实服务项、任一 blocking_reason，都不会返回 ready。测试数量为 0 不能因“没有失败”而通过。

参考实现的 capability 名称集合、硬编码危险重试计数、未执行的 disk_full 标签和固定成功 Ollama transport，只能证明代码走过对应分支，不能满足 G05/G08/G09/G13 的现实证据。[R1–R3]

## 7. 证据保存与可公开摘要

原始证据放仓库外受限目录，并限定保留时间与采集范围。原始 HTTP、header/cookie、凭据、个人路径、聊天内容、用户 DB、截图、飞书账号/租户标识不得进入 Git 或公开 CI artifact。需要外发的摘要须去除秘密和 PII，只保留合成 fixture、相对源码路径、版本、用例 ID、退出码、数量、期望/实际以及不透明证据引用。

私有运行账本记录原始文件位置与完整性校验；公开摘要不暴露原始用户路径，也不以秘密哈希替代秘密。扫描离线运行，外部 allowlist 注释不生效，并做人工内容审查。记录命令 argv 中的安全参数，不记录敏感环境变量值。凭据是否可用可以记录，值不可记录。

## 8. 最终输出与放行结论

最后必须交付一个具体候选的：范围表、命令清单、用例结果、缺陷台账、每个修复的 commit/push/CI 回执、构建/产物清单、脱敏证据索引和尚未满足项。不得只有“全部测试通过”的一句话。

| 结论 | 含义 |
|---|---|
| NOT_RUN | 尚未执行本次完整验收；本方案当前初始状态 |
| FAIL | 已执行的必需行为不符合要求 |
| BLOCKED | 环境、凭据、CI、证据或其他依赖使必需门禁无法完成；可以有局部 PASS |
| PASS_MACOS_MVP | 固定候选在列明的 macOS/架构/服务/交付范围内全部必需门禁通过 |

FAIL 和 BLOCKED 可同时有多个原因，报告不要只保留其中一个。Windows/Linux 或未声明 Intel/M4 桌面能力保持各自真实状态；不能在最终表中填成通过。新提交、新产物、新运行配置或能力声明改变了测试对象，就要按影响重新验证，旧候选结论不得自动继承。逐问题 commit+push 的授权不自动包括 merge、tag、正式部署。

## 来源与核对入口

以下源文件是只读参考 SHA 的实现线索，执行时须核对本机当前版本；引用并不表示该实现已经通过测试。

- [R1 chaos_soak.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/chaos_soak.py)
- [R2 mvp_regression.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/mvp_regression.py)
- [R3 macos_gate.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/macos_gate.py)
- [R4 mvp_release_gate.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/mvp_release_gate.py)
- [R5 参考 CI run 41949551726](https://github.com/xiongcp/OpenBot/actions/runs/41949551726)
- [G1 GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [G2 GitHub events 与 SHA](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [G3 GitHub workflow 文件位置](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)
