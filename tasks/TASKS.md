# OpenBot 详细工程任务清单

版本 1.2 · 2026年11月4日 · 96项任务 · 初始为TODO，当前状态与证据随实施同步

本清单可交给Codex或Claude Code逐项实施。原OB-001—088编号保留，新增OB-089—096组件准入与协议/来源/供应链门禁；原任务中76项修订了执行合同、验收或依赖，12项仅补复用边界及来源。任务是待实施的工程合同，本设计包没有声称OpenBot产品已经实现或真实组件已经通过资格验证。

机器事实源：[backlog.json](backlog.json)。需求映射：[requirements_traceability.md](requirements_traceability.md)。本轮变化：[REVISION_v1_2.md](REVISION_v1_2.md) 与 [revision_delta.json](revision_delta.json)。组件选择及资格：[catalog.json](../components/catalog.json)、[12_component_reuse.md](../docs/12_component_reuse.md)、[13_component_qualification.md](../docs/13_component_qualification.md)。

## 执行规则

1. ID表示稳定任务身份，不是执行顺序。OB-081认证本地API在M1，先于完整CLI/gateway；OB-089/090/091虽编号靠后但属于M0。按DAG和已有证据领取一个任务或严格受限子任务，禁止一次生成全仓。
2. M0只安装当期最小依赖组，用标准向量和FakeClock/SQLite/JCS/MockWorker验证协议。OB-008在M0只做配置/fake拒绝合同；真实Ollama和网络证据留在M3的OB-026。
3. OB-029是完整M1切片，保留原依赖，并接通真实本地API、权限、Artifact与受限执行路径；演示可以FakeProvider/OFFLINE。M0 PoC不能代替它，mock也不能证明真实模型、飞书或OS能力。
4. 组件先按当前阶段准入，再经Port/Adapter使用。domain不导入模型/飞书/浏览器/MCP/容器SDK；库不接管状态、授权、两短事务、UNKNOWN、预算和egress。
5. `outputs`是未来实现仓库将创建/修改的路径；不是声称源码已存在。`docs_refs`是当前设计包已有文件。代码片段的NO_COPY决定可完成来源审查，不强制vendoring或整仓安装。
6. 安全、恢复和供应链随阶段形成证据。M3的CI/浸泡/全资产核验用于扩大和整合已有门禁，不能成为推迟M0/M1安全工作的理由。
7. 保留用户工作区脏修改。共享contract、migration序号、锁文件、组件目录和release manifest有单一owner；组件升级引起执行/绑定语义变化时重新审查旧授权。

## 状态、规模与复用字段

TODO是工程任务状态，后续可按TODO → READY → IN_PROGRESS → REVIEW → VERIFIED → DONE推进；BLOCKED记录缺接口/环境/证据。它不同于产品Task/Operation状态。真实组件资格初始为NOT_RUN；候选被列出、文档完成、import成功均不等于能力可用。

P0/P1表示所属阶段的优先级，P2为后续能力。S/M/L仅相对复杂度与审查规模，不是工时；L任务先拆成可独立验证的PR。

| 新字段 | 类型 | 含义 |
|---|---|---|
| component_refs | string[] | 引用catalog中的相关候选/已选择/被限制组件；本身不表示允许安装或已通过资格 |
| reuse_type | string | 本任务的工程职责：control_owned、dependency_adapter、source_review、native_primitive、qualification、deferred |
| reuse_notes | string[] | 明确适配范围、自研权威、禁止行为与NO_COPY/替代选择 |

这三个字段须与任务PDF完整同步。reuse_type属于任务分类，与组件catalog的DEFAULT_ADAPTER/GATED_CANDIDATE/REFERENCE_ONLY/DEFERRED/REJECTED_MVP选择类别独立。

## 状态协议与目录基线

Task使用QUEUED、RUNNING、WAITING_APPROVAL、WAITING_INPUT、WAITING_RESOURCE、RECONCILING、PAUSED、SUCCEEDED、PARTIAL、FAILED、CANCELLED；Operation结果不明为UNKNOWN，错误码为OUTCOME_UNKNOWN。权威状态表加审计事件，回放不执行工具。

Approval从APPROVED首次消费到CONSUMED后不可逆；仅恢复器能为同一Operation复验原期限、policy、actor/identity、cancel和resource，决定是否允许安全重试。dispatch_id属于Attempt，同Attempt重传不变、新Attempt新ID；provider_idempotency_key属于Operation。CLAIMED→DISPATCHING第二短事务再查取消、epoch、resource，提交后才派发。人工reconcile提交可核对证据，不允许一句success覆盖账本，也不能绕过UNKNOWN资源quarantine。

实现目录保持services/core/src/openbot、apps/cli、apps/desktop、services/feishu_gateway、native/supervisor、contracts、db/migrations与tests。23表和14API不因组件复用新增。CLI/gateway/Tauri经认证API调用application，不直连SQLite。

## 阶段门槛

| 阶段 | 项数 | 范围 | 退出条件 |
|---|---:|---|---|
| M0 设计、最小基线与协议PoC | 13 | 范围/生命周期、最小仓库、合同/fake夹具、组件目录和标准向量。 | OB-001—010、OB-089—091；纯协议PoC无需真实Provider/飞书/容器。 |
| M1 本地内核与安全工具 | 37 | 权威状态、恢复/审批、认证API/CLI、首个Provider、ACI/隔离worker、组件故障与首发OS原语。 | OB-029完整真实本地链路、OB-045反例、OB-046本地Alpha；OB-092/093完成当期准入。 |
| M2 飞书远程闭环 | 11 | 一个活动gateway、配对、callback、普通卡/降级、健康/死信、模板采纳或NO_COPY。 | OB-047—056、OB-094；真实测试租户完成审批/取消/重启/断网闭环。 |
| M3 MVP与三平台CLI | 25 | 第二本地Provider、受控Browser/MCP、技能、诊断、真实评测、三平台CLI完整安装和供应链。 | OB-067能力、OB-072安装、OB-076评测、OB-095源码决定、OB-096全资产与OB-080发布门槛。 |
| M4 Tauri桌面Beta与签名升级 | 4 | Tauri/接管、签名安装、更新/迁移恢复。 | OB-073/074/082/083；M3已有供应链基线，M4增加桌面签名与更新验证。 |
| P2 后续独立能力 | 6 | 原生Anthropic、单OS GUI、可核对记忆、持久定时与多设备/团队ADR。 | OB-027/084—088分别决策并验收；未准入不进入MVP默认runtime。 |

## 依赖顺序与并行领取

下面是一条校验通过的拓扑顺序；分组只是便于阅读，不是日程承诺。多个代理可领取依赖已满足且文件owner不冲突的任务，不能绕过前置门禁。原有依赖全部保留，新增依赖无环且没有跨阶段逆向边。

**M0 设计、最小基线与协议PoC**

- OB-001 → OB-002 → OB-003 → OB-004 → OB-005 → OB-089 → OB-006 → OB-007
- OB-008 → OB-009 → OB-010 → OB-090 → OB-091

**M1 本地内核与安全工具**

- OB-011 → OB-012 → OB-013 → OB-014 → OB-017 → OB-018 → OB-021 → OB-023
- OB-024 → OB-031 → OB-032 → OB-036 → OB-037 → OB-043 → OB-092 → OB-038
- OB-039 → OB-025 → OB-093 → OB-015 → OB-016 → OB-019 → OB-020 → OB-022
- OB-030 → OB-033 → OB-034 → OB-040 → OB-041 → OB-035 → OB-042 → OB-044
- OB-081 → OB-028 → OB-029 → OB-045 → OB-046

**M2 飞书远程闭环**

- OB-047 → OB-048 → OB-049 → OB-050 → OB-054 → OB-055 → OB-094 → OB-051
- OB-052 → OB-053 → OB-056

**M3 MVP与三平台CLI**

- OB-026 → OB-057 → OB-058 → OB-062 → OB-063 → OB-064 → OB-065 → OB-066
- OB-068 → OB-069 → OB-070 → OB-071 → OB-072 → OB-075 → OB-078 → OB-095
- OB-059 → OB-060 → OB-061 → OB-067 → OB-076 → OB-079 → OB-096 → OB-077
- OB-080

**M4 Tauri桌面Beta与签名升级**

- OB-073 → OB-082 → OB-083 → OB-074

**P2 后续独立能力**

- OB-027 → OB-084 → OB-085 → OB-086 → OB-087 → OB-088

## Definition of Ready

- 前置任务接口与证据可用；明确当前任务输入/输出、状态/取消/恢复语义、允许修改路径与owner。
- 涉及组件时已明确当前阶段、catalog类别、来源/许可证与必要锁定范围；真实未验证组件先跑任务规定的PoC，不能默认为可用。
- 已准备有界的正向与负向fixture；真实服务使用受控租户/数据；不能用生产秘密或无约束实际副作用试探。
- 共享协议/迁移/依赖锁的唯一owner明确；NO_COPY有比较依据即可，不为完成清单强制引入上游代码。

## Definition of Done

- 完成规定行为、反例与可重复证据；涉及持久化、网络或副作用时断言真实提交/请求/效果次数，不只看模型文字或库返回值。
- 状态、API、错误和配置符合合同；稳定请求ID可查询超时后的持久结果，UNKNOWN继续核对，不能以放宽policy、删断言或host兜底过关。
- 组件来源、实际版本/资产hash、许可证/NOTICE、当前依赖组、资格与产物一致；运行时不下载latest、grammar/词表/浏览器或未批准模型。
- 输出与诊断过滤并保持原数据分类；未动任务范围外数据；实际平台/服务证据和mock分别记录，未验证能力如实标记。
- 仅重跑受影响门禁及必需回归，记录上游升级/窄补丁退出条件和残余风险；纯文档/NO_COPY决定不虚构运行测试。

## 任务总表

| ID | 任务 | 阶段 | 优先级 | 规模 | 复用职责 | 前置依赖 |
|---|---|---|---|---|---|---|
| OB-001 | 冻结用户场景与MVP边界 | M0 | P0 | S | 自研控制面 | 无 |
| OB-002 | 定义信任边界和动作副作用类别 | M0 | P0 | M | 自研控制面 | OB-001 |
| OB-003 | 冻结daemon与客户端生命周期 | M0 | P0 | S | 原生原语适配 | OB-001 |
| OB-004 | 核验依赖和许可证 | M0 | P0 | M | 准入与验证 | OB-001 |
| OB-005 | 建立最小仓库和工具链 | M0 | P0 | M | 准入与验证 | OB-001, OB-004 |
| OB-006 | 定义事件与命令协议 | M0 | P0 | M | 依赖薄适配 | OB-002, OB-005, OB-089 |
| OB-007 | 定义工具和模型Provider契约 | M0 | P0 | M | 自研控制面 | OB-002, OB-006 |
| OB-008 | 定义配置与网络模式 | M0 | P0 | M | 依赖薄适配 | OB-002, OB-005, OB-089 |
| OB-009 | 统一错误与时钟语义 | M0 | P0 | S | 自研控制面 | OB-006, OB-007 |
| OB-010 | 建立确定性系统测试夹具 | M0 | P0 | M | 准入与验证 | OB-005, OB-006, OB-007, OB-009 |
| OB-011 | 实现带版本的数据库迁移 | M1 | P0 | M | 依赖薄适配 | OB-006, OB-009, OB-091 |
| OB-012 | 实现串行写事务与数据库背压 | M1 | P0 | M | 依赖薄适配 | OB-011 |
| OB-013 | 实现持久inbox与作用域去重 | M1 | P0 | M | 自研控制面 | OB-006, OB-011, OB-012 |
| OB-014 | 实现任务状态与事件原子提交 | M1 | P0 | M | 自研控制面 | OB-011, OB-012, OB-013 |
| OB-015 | 实现单实例daemon和调度租约 | M1 | P0 | M | 原生原语适配 | OB-003, OB-014, OB-093 |
| OB-016 | 实现执行资源锁与会话排队 | M1 | P0 | M | 自研控制面 | OB-015 |
| OB-017 | 实现动作意图与执行attempt日志 | M1 | P0 | M | 自研控制面 | OB-007, OB-011, OB-014 |
| OB-018 | 实现审批决定与一次性授权 | M1 | P0 | M | 依赖薄适配 | OB-002, OB-014, OB-017, OB-090 |
| OB-019 | 实现执行前授权claim和再校验 | M1 | P0 | M | 自研控制面 | OB-016, OB-017, OB-018, OB-031 |
| OB-020 | 实现按副作用类型恢复 | M1 | P0 | M | 自研控制面 | OB-009, OB-015, OB-017, OB-019 |
| OB-021 | 实现durable outbox及投递状态 | M1 | P0 | M | 自研控制面 | OB-012, OB-014, OB-017 |
| OB-022 | 实现取消和停止传播 | M1 | P0 | M | 自研控制面 | OB-014, OB-016, OB-019, OB-020 |
| OB-023 | 实现任务预算和熔断 | M1 | P0 | M | 依赖薄适配 | OB-007, OB-014, OB-017 |
| OB-024 | 实现上下文快照与摘要 | M1 | P0 | M | 自研控制面 | OB-007, OB-014, OB-017, OB-023 |
| OB-025 | 实现首个云模型适配器 | M1 | P0 | M | 依赖薄适配 | OB-007, OB-008, OB-009, OB-023, OB-024, OB-037, OB-038, OB-039, OB-092 |
| OB-026 | 实现Ollama或第二Provider | M3 | P1 | M | 依赖薄适配 | OB-007, OB-008, OB-009, OB-023, OB-024, OB-037, OB-038, OB-039, OB-092 |
| OB-027 | 补充Anthropic原生Provider | P2 | P2 | M | 后续阶段适配 | OB-025, OB-026, OB-092 |
| OB-028 | 提供CLI任务和审批操作 | M1 | P0 | M | 依赖薄适配 | OB-008, OB-014, OB-018, OB-020, OB-022, OB-081, OB-092 |
| OB-029 | 交付首条持久化垂直切片 | M1 | P0 | M | 准入与验证 | OB-010, OB-020, OB-021, OB-022, OB-023, OB-025, OB-028, OB-036, OB-041, OB-042 |
| OB-030 | 实现数据库备份恢复与保留策略 | M1 | P1 | M | 依赖薄适配 | OB-011, OB-012, OB-014, OB-020 |
| OB-031 | 实现确定性策略评估器 | M1 | P0 | M | 自研控制面 | OB-002, OB-007, OB-008, OB-018 |
| OB-032 | 实现工作区路径与文件访问守卫 | M1 | P0 | M | 原生原语适配 | OB-002, OB-008, OB-031 |
| OB-033 | 实现list read search文件工具 | M1 | P0 | M | 依赖薄适配 | OB-007, OB-019, OB-032, OB-092 |
| OB-034 | 实现补丁提议与受授权应用 | M1 | P0 | M | 依赖薄适配 | OB-007, OB-016, OB-019, OB-032, OB-033, OB-036, OB-092 |
| OB-035 | 实现显式语言验证与修改事务 | M1 | P1 | M | 依赖薄适配 | OB-034, OB-041, OB-092 |
| OB-036 | 实现Artifact存储与可信元数据 | M1 | P0 | M | 自研控制面 | OB-011, OB-017, OB-032 |
| OB-037 | 实现统一数据外发策略 | M1 | P0 | M | 自研控制面 | OB-002, OB-008, OB-031, OB-036 |
| OB-038 | 实现密钥存储与最小注入 | M1 | P0 | M | 依赖薄适配 | OB-008, OB-031, OB-092 |
| OB-039 | 实现敏感数据输出过滤 | M1 | P0 | M | 依赖薄适配 | OB-036, OB-037, OB-038, OB-092 |
| OB-040 | 实现结构化进程执行协议 | M1 | P0 | M | 自研控制面 | OB-007, OB-009, OB-019, OB-031, OB-038, OB-039 |
| OB-041 | 实现worker隔离与资源上限 | M1 | P0 | M | 原生原语适配 | OB-002, OB-016, OB-036, OB-040, OB-093 |
| OB-042 | 实现worker进程树取消与回收 | M1 | P0 | M | 原生原语适配 | OB-003, OB-022, OB-040, OB-041, OB-093 |
| OB-043 | 实现本地消息草稿 | M1 | P1 | S | 自研控制面 | OB-007, OB-036, OB-037 |
| OB-044 | 实现消息发送用例与受控适配端口 | M1 | P1 | M | 自研控制面 | OB-017, OB-018, OB-019, OB-020, OB-037, OB-043 |
| OB-045 | 交付安全工具威胁回归 | M1 | P0 | M | 准入与验证 | OB-029, OB-031, OB-032, OB-034, OB-037, OB-039, OB-041, OB-042 |
| OB-046 | 发布最小本地Alpha边界说明 | M1 | P0 | S | 准入与验证 | OB-029, OB-033, OB-034, OB-040, OB-041, OB-045 |
| OB-047 | 核验飞书真实租户协议与权限 | M2 | P0 | M | 准入与验证 | OB-004, OB-006, OB-008, OB-092 |
| OB-048 | 实现安全配对与owner撤销 | M2 | P0 | M | 自研控制面 | OB-002, OB-008, OB-013, OB-018, OB-047, OB-081 |
| OB-049 | 实现飞书WebSocket入站适配 | M2 | P0 | M | 依赖薄适配 | OB-013, OB-047, OB-048, OB-081 |
| OB-050 | 实现飞书审批callback处理 | M2 | P0 | M | 依赖薄适配 | OB-018, OB-019, OB-047, OB-048, OB-049 |
| OB-051 | 实现普通卡片与结果回执 | M2 | P0 | M | 依赖薄适配 | OB-021, OB-037, OB-047, OB-049, OB-094 |
| OB-052 | 实现进度卡节流与更新顺序 | M2 | P1 | M | 自研控制面 | OB-021, OB-051 |
| OB-053 | 实现CardKit与更新通道降级 | M2 | P1 | M | 依赖薄适配 | OB-047, OB-051, OB-052, OB-094 |
| OB-054 | 实现网关健康探测与重连 | M2 | P0 | M | 依赖薄适配 | OB-009, OB-021, OB-049 |
| OB-055 | 实现死信检视与安全重投 | M2 | P1 | M | 自研控制面 | OB-013, OB-020, OB-021, OB-049, OB-054 |
| OB-056 | 飞书端到端真实验收 | M2 | P0 | M | 准入与验证 | OB-025, OB-045, OB-048, OB-050, OB-051, OB-054 |
| OB-057 | 实现专用浏览器profile与会话锁 | M3 | P1 | M | 依赖薄适配 | OB-007, OB-016, OB-031, OB-037, OB-039, OB-042, OB-092 |
| OB-058 | 实现浏览器网络与下载策略 | M3 | P1 | M | 依赖薄适配 | OB-032, OB-036, OB-037, OB-057, OB-041 |
| OB-059 | 实现结构化浏览器读工具 | M3 | P1 | M | 依赖薄适配 | OB-007, OB-019, OB-057, OB-058, OB-095 |
| OB-060 | 实现浏览器写动作提案与确认 | M3 | P1 | M | 自研控制面 | OB-017, OB-018, OB-019, OB-059 |
| OB-061 | 建立浏览器结果验证回归 | M3 | P1 | M | 准入与验证 | OB-020, OB-059, OB-060 |
| OB-062 | 实现MCP版本协商与生命周期 | M3 | P1 | M | 依赖薄适配 | OB-004, OB-007, OB-009, OB-038, OB-092 |
| OB-063 | 实现MCP注册与工具元数据锁定 | M3 | P1 | M | 依赖薄适配 | OB-002, OB-031, OB-037, OB-062, OB-090 |
| OB-064 | 实现MCP进程和网络权限 | M3 | P1 | M | 依赖薄适配 | OB-019, OB-037, OB-038, OB-041, OB-062, OB-063, OB-042 |
| OB-065 | 建立MCP恶意与故障服务器测试 | M3 | P1 | M | 准入与验证 | OB-062, OB-063, OB-064 |
| OB-066 | 实现只读技能指令加载 | M3 | P1 | M | 自研控制面 | OB-002, OB-008, OB-024, OB-031 |
| OB-067 | 交付全MVP能力集回归 | M3 | P1 | M | 准入与验证 | OB-026, OB-056, OB-061, OB-065, OB-066 |
| OB-068 | 实现用户级daemon安装与卸载 | M3 | P1 | M | 原生原语适配 | OB-003, OB-005, OB-008, OB-028, OB-042, OB-093 |
| OB-069 | 建立macOS原生运行门禁 | M3 | P1 | M | 准入与验证 | OB-032, OB-042, OB-068 |
| OB-070 | 建立Windows原生运行门禁 | M3 | P1 | M | 准入与验证 | OB-032, OB-042, OB-068 |
| OB-071 | 建立Linux原生运行门禁 | M3 | P1 | M | 准入与验证 | OB-032, OB-042, OB-068 |
| OB-072 | 建立可复现打包与运行资源清单 | M3 | P1 | M | 准入与验证 | OB-004, OB-005, OB-069, OB-070, OB-071, OB-089 |
| OB-073 | 实现版本升级和迁移恢复 | M4 | P1 | M | 依赖薄适配 | OB-011, OB-020, OB-030, OB-072, OB-080 |
| OB-074 | 完成桌面安装签名与发布供应链 | M4 | P1 | M | 准入与验证 | OB-004, OB-072, OB-073, OB-082, OB-083 |
| OB-075 | 实现统一可观测性与诊断 | M3 | P1 | M | 依赖薄适配 | OB-009, OB-015, OB-021, OB-023, OB-039, OB-054 |
| OB-076 | 建立真实任务质量基准集 | M3 | P1 | M | 准入与验证 | OB-067, OB-075 |
| OB-077 | 建立分层CI门禁 | M3 | P1 | M | 准入与验证 | OB-010, OB-045, OB-067, OB-069, OB-070, OB-071, OB-072, OB-096 |
| OB-078 | 建立断网休眠与崩溃浸泡 | M3 | P1 | M | 准入与验证 | OB-020, OB-022, OB-030, OB-042, OB-054, OB-075 |
| OB-079 | 完成上手与故障处置文档 | M3 | P1 | M | 准入与验证 | OB-056, OB-067, OB-068, OB-072, OB-075 |
| OB-080 | 完成MVP发布验收与风险登记 | M3 | P1 | S | 准入与验证 | OB-067, OB-072, OB-076, OB-077, OB-078, OB-079, OB-096 |
| OB-081 | 在M1实现认证本地HTTP与SSE控制API | M1 | P0 | M | 依赖薄适配 | OB-006, OB-008, OB-014, OB-018, OB-020, OB-022, OB-031, OB-038, OB-039, OB-092 |
| OB-082 | 实现Tauri任务与审批UI | M4 | P1 | M | 依赖薄适配 | OB-003, OB-081, OB-089 |
| OB-083 | 实现桌面接管与事件回放 | M4 | P1 | M | 自研控制面 | OB-016, OB-022, OB-075, OB-082 |
| OB-084 | 为一个OS实现原生桌面观察 | P2 | P2 | L | 后续阶段适配 | OB-002, OB-016, OB-037, OB-039, OB-042, OB-082, OB-089 |
| OB-085 | 实现受限桌面写动作 | P2 | P2 | L | 后续阶段适配 | OB-017, OB-018, OB-019, OB-084 |
| OB-086 | 实现可验证记忆与删除 | P2 | P2 | M | 自研控制面 | OB-024, OB-030, OB-037, OB-066 |
| OB-087 | 实现持久定时触发器 | P2 | P2 | M | 后续阶段适配 | OB-013, OB-014, OB-015, OB-023, OB-056, OB-089 |
| OB-088 | 评估第二设备和团队扩展边界 | P2 | P2 | M | 自研控制面 | OB-080, OB-083 |
| OB-089 | 建立组件准入目录和分阶段依赖门禁 | M0 | P0 | M | 准入与验证 | OB-004, OB-005 |
| OB-090 | 验证Schema与JCS标准合同向量 | M0 | P0 | M | 准入与验证 | OB-006, OB-007, OB-010, OB-089 |
| OB-091 | 交付最小claim/dispatch崩溃协议PoC | M0 | P0 | M | 准入与验证 | OB-009, OB-010, OB-090 |
| OB-092 | 建立组件副作用和重试取消故障契约 | M1 | P0 | M | 准入与验证 | OB-007, OB-008, OB-009, OB-010, OB-089, OB-090, OB-091 |
| OB-093 | 验证首发OS的Supervisor与隔离后端能力 | M1 | P0 | M | 准入与验证 | OB-003, OB-004, OB-007, OB-008, OB-010, OB-089, OB-091 |
| OB-094 | 审查飞书模板的最小源码复用 | M2 | P1 | S | 源码参考/摘取审查 | OB-004, OB-047, OB-089, OB-092 |
| OB-095 | 审查DOM提取脚本的最小源码复用 | M3 | P1 | M | 源码参考/摘取审查 | OB-057, OB-058, OB-089, OB-092 |
| OB-096 | 验收全量交付资产来源与供应链 | M3 | P0 | M | 准入与验证 | OB-004, OB-067, OB-072, OB-089, OB-094, OB-095 |

## M0 设计、最小基线与协议PoC

### OB-001

**冻结用户场景与MVP边界**

阶段 M0 · 优先级 P0 · 状态 DONE · 能力域 Lead · 规模 S

**需求** [RQ01](requirements_traceability.md#rq01)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** 无

**先读设计** [00_scope.md](../docs/00_scope.md)；[10_project_plan.md](../docs/10_project_plan.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)

**风险** HIGH。范围漂移会让编码代理提前实现多租户或GUI并挤占安全闭环。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** 无直接组件引用

**复用边界（reuse_notes）**

- 保留单owner/profile/device和阶段边界；把组件建议与已准入实现分开，复用不扩大产品范围。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 将U1/U2需求映射为S01–S06与M0–M4/P2交付边界，区分原要求、默认假设和未确认项。
2. 写清单owner/profile/device、单活动gateway以及三平台逐个取得支持资格的规则。
3. 按输入约束冻结本轮范围，并记录变更必须同步ADR、合同、任务与验收。

**目标输出路径**

- `docs/00_scope.md`
- `docs/adr/0001-scope-baseline.md`

**正向验收**

冻结一个OS用户、profile、owner、设备和单活动gateway；M0至M4/P2边界与S01–S06场景明确；三平台支持根据真实能力报告授予，MVP不要求桌面GUI控制。

**反例与禁止行为**

- 不得把本地Alpha当作完整MVP，或把未测OS标为supported。

**验证方法**

用3个主场景和5个失败场景逐项映射到需求ID；评审不出现“支持所有任务”。

**必须提交的证据**

- 提供更新后的范围/ADR/清单及决策理由，明确原要求、建议和未验证假设。
- 给出与任务验收对应的评审检查结果；涉及spike时记录环境、最小命令和实际观察，不以文档代替实测。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第1、19–26页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-002

**定义信任边界和动作副作用类别**

阶段 M0 · 优先级 P0 · 状态 DONE · 能力域 Security · 规模 M

**需求** [RQ04](requirements_traceability.md#rq04)、[RQ05](requirements_traceability.md#rq05)、[RQ06](requirements_traceability.md#rq06)

**前置依赖** OB-001

**先读设计** [02_architecture.md](../docs/02_architecture.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。错误威胁模型会把高风险能力当作默认安全。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** `model-runner`

**复用边界（reuse_notes）**

- 明确任何组件、源码片段、重试器、MCP hints均不拥有身份/授权/派发权；增加组件主动联网、执行、下载和遥测威胁。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 列资产、攻击者、信任边界与数据出口，明确同一OS用户完全失陷的边界。
2. 分别定义effect与五种retry_class，为每类附失败窗口及处理办法。
3. 将路径、任意代码、工具注入和审批残余风险映射到负责模块与验证任务。
4. 把SDK自动工具/Provider托管工具、隐藏重试、运行期下载、网络验证、配置/hook执行和源码摘取纳入信任边界。

**目标输出路径**

- `docs/04_security_approvals.md`
- `docs/adr/0002-trust-and-effects.md`

**正向验收**

资产/边界/攻击者假设可核对；效果与retry_class分开定义；使用SAFE_READ、IDEMPOTENT_WRITE、PROVIDER_IDEMPOTENT、RECONCILE_ONLY、NON_RETRYABLE，说明审批不等于执行隔离。 组件品牌、许可证、annotations或官方helper均不赋予执行权；明确已观察网络范围与同用户失陷的残余边界。

**反例与禁止行为**

- 不能把Docker、argv、审批或schema pinning中的任一项描述成完整安全保证。
- 不得因组件来自官方就放开其所有API、remote MCP、服务端工具或自动工具循环。

**验证方法**

列出入站、模型、网页、MCP、文件、操作系统各边界及防护/残余风险；每类有失败用例。

**必须提交的证据**

- 提供更新后的范围/ADR/清单及决策理由，明确原要求、建议和未验证假设。
- 给出与任务验收对应的评审检查结果；涉及spike时记录环境、最小命令和实际观察，不以文档代替实测。
- 组件边界图和威胁条目到现有Policy/Broker/隔离门禁的映射。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第3、8–9、13页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-003

**冻结daemon与客户端生命周期**

阶段 M0 · 优先级 P0 · 状态 DONE · 能力域 Runtime · 规模 S

**需求** [RQ01](requirements_traceability.md#rq01)、[RQ11](requirements_traceability.md#rq11)

**前置依赖** OB-001

**先读设计** [02_architecture.md](../docs/02_architecture.md)；[00_scope.md](../docs/00_scope.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[10_project_plan.md](../docs/10_project_plan.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。生命周期相互绑定会破坏远程可用性并遗留worker。

**复用职责（reuse_type）** `native_primitive` · 原生原语适配

**关联组件（component_refs）** `profile-locks`、`processkit-process-wrap`、`windows-sys`、`ur-taking-me-with-you`、`service-manager`

**复用边界（reuse_notes）**

- 生命周期ADR不变；锁/用户服务/进程监管允许复用经过OB-093实测的OS原语封装，不许宣称通用crate自动保证整树清理。
- 实际OS、架构、backend和配置组合须独立提供证据；统一API、正常退出或进程组不能自动证明所有强杀与逃逸场景均可回收。

**实施步骤**

1. 写用户级supervisor、daemon、gateway、worker和UI的父子及连接关系。
2. 定义常驻/ephemeral、关闭窗口、stop、logout、睡眠、重启和崩溃的事件矩阵。
3. 用最小监督spike确认首发OS的锁与清理能力，未知能力写入限制。
4. 将profile锁、原生进程清理和用户级服务分为独立原语；指定唯一锁持有者，父子交接/健康检查不得再次争抢同一排他锁。

**目标输出路径**

- `docs/02_architecture.md`
- `docs/adr/0003-daemon-lifecycle.md`

**正向验收**

默认常驻模式由用户级supervisor托管；CLI/Tauri退出不停止daemon；开发ephemeral模式显式标识；显式stop执行drain、停止新dispatch和worker回收。 监督与状态归属由OpenBot定义，原语候选经OB-093后决定；不把command-group作为新增默认依赖。

**反例与禁止行为**

- 关闭Tauri或断开CLI不得终止常驻daemon；不得把正常退出回调当成SIGKILL保证。
- 父supervisor持锁时daemon不得阻塞式重取同一profile排他锁；不能以Rust Drop或管道EOF保证所有强杀场景。

**验证方法**

生命周期表覆盖关闭窗口、登出、休眠、daemon崩溃、worker崩溃和重启；无相互矛盾要求。

**必须提交的证据**

- 提供更新后的范围/ADR/清单及决策理由，明确原要求、建议和未验证假设。
- 给出与任务验收对应的评审检查结果；涉及spike时记录环境、最小命令和实际观察，不以文档代替实测。
- 标出锁拥有者、句柄/凭据交接、重启接管和每类清理对象的生命周期矩阵。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第4、13–14页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-004

**核验依赖和许可证**

阶段 M0 · 优先级 P0 · 状态 DONE · 能力域 Lead · 规模 M

**需求** [RQ01](requirements_traceability.md#rq01)、[RQ11](requirements_traceability.md#rq11)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-001

**先读设计** [00_scope.md](../docs/00_scope.md)；[01_gap_review.md](../docs/01_gap_review.md)；[02_architecture.md](../docs/02_architecture.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[07_feishu.md](../docs/07_feishu.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[10_project_plan.md](../docs/10_project_plan.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。依赖错误和许可证缺口会在实现或发布阶段造成返工。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `command-group`、`service-manager`、`pathspec`、`pyinstaller`、`astrbot`

**复用边界（reuse_notes）**

- 核验当前阶段最小组合；后续候选不提前安装或标已锁定。command-group不新增默认依赖；许可证按具体文件/版本/分发方式评估。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 从官方来源为当前候选记录精确版本或待锁定状态、包/文件许可证、分发方式、接口、可替换实现和已知副作用。
2. 冻结M0实际需要的最小工具/合同组合，后续SDK/浏览器/桌面候选留待各自阶段PoC；仅做必要可行性spike，不预认证全套依赖。
3. 区分直接依赖、原语参考、源码摘取及不采用项；将证据交OB-089机器清单，复杂原生能力交OB-093、真实飞书协议交OB-047。

**目标输出路径**

- `docs/dependency-evidence.md`
- `THIRD_PARTY_NOTICES.md`
- `docs/spikes/component-selection.md`

**正向验收**

当前M0实际使用的Python/SQLite/工具/合同组件有明确版本及许可证证据；后续SDK、浏览器、OS组合登记为待所属阶段准入，未实测不标通过。区分原材料建议、官方可见事实与本项目真实PoC；不凭star数、Issue标题或报告版本范围选架构。

**反例与禁止行为**

- 不得运行时拉取latest或复制许可证不明代码；单个Issue不能替代真实版本验证。
- 不得把候选清单变成M0批量安装命令，或把AGPL/GPL笼统宣称为违法；MPL、双许可、bootloader例外和非包资产逐项核验。

**验证方法**

依赖清单逐个可追溯官方URL与版本；复制代码时记录原许可证与归属。 核对command-group弃用与service-manager平台边界，保留未决证据；后续组件不因报告列出版本就标已锁定。

**必须提交的证据**

- 提供更新后的范围/ADR/清单及决策理由，明确原要求、建议和未验证假设。
- 给出与任务验收对应的评审检查结果；涉及spike时记录环境、最小命令和实际观察，不以文档代替实测。
- 当前阶段来源/许可证证据、后续候选状态及每个否决或延期决定的理由。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第15–19、26页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-005

**建立最小仓库和工具链**

阶段 M0 · 优先级 P0 · 状态 BLOCKED · 能力域 Platform · 规模 M

**需求** [RQ01](requirements_traceability.md#rq01)、[RQ11](requirements_traceability.md#rq11)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-001、OB-004

**先读设计** [02_architecture.md](../docs/02_architecture.md)；[00_scope.md](../docs/00_scope.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** MEDIUM。工具链不可复现会放大多代理集成冲突。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `cli-toolchain`

**复用边界（reuse_notes）**

- uv及必要开发工具先锁；仅安装当前bootstrap需要的批准依赖，禁止M0一次uv add全部候选；CI从第一批PR执行组件清单一致性。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 建立services/core、apps/cli、contracts及当前任务必需的可导入最小包，使用uv锁定当前已核准工具；不建立全部业务空壳。
2. 配置lint/type/单元与合同测试及三OS基础CI，把依赖准入检查接到后续OB-089提供的检查器。
3. 提供version/health样例和fake入口；验证最小依赖安装，模块import不联网、不创建daemon、不读取用户秘密。

**目标输出路径**

- `pyproject.toml`
- `uv.lock`
- `services/core/src/openbot`
- `apps/cli`
- `.github/workflows/pr.yml`
- `tests/contracts`

**正向验收**

建立Python 3.12初始验证基线、uv锁、最小CLI和domain导入；lint/type/test统一；只建当前任务必需模块；M0已有三OS基础CI。 依赖按dev-contracts/core等分组，M2/M3/M4/P2组件不进入M0默认环境；后续缺可选组不会破坏核心导入。

**反例与禁止行为**

- 导入模块不得联网、创建daemon或读取用户秘密；不能一次生成全部业务空壳冒充实现。
- 不得在M0一次安装lark、Playwright/MCP、全部Provider、Tauri或GUI/调度候选；不得运行期自动补包。

**验证方法**

三个OS运行安装、版本输出、一个有效测试；锁文件可复现；模块import无网络或外部进程。 空环境记录实际安装包树、锁和import网络/进程观察范围。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留最小可运行样例或golden fixture，以及对应静态/合同验证输出。
- M0最小锁文件及安装清单，后续组未被默认解析/导入的验证。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第19、26页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-089

**建立组件准入目录和分阶段依赖门禁**

阶段 M0 · 优先级 P0 · 状态 VERIFIED · 能力域 Lead · 规模 M

**需求** [RQ07](requirements_traceability.md#rq07)、[RQ11](requirements_traceability.md#rq11)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-004、OB-005

**先读设计** [00_scope.md](../docs/00_scope.md)；[10_project_plan.md](../docs/10_project_plan.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)

**风险** HIGH。候选组件被自动安装、许可证/传递依赖不明、import或首次使用发生副作用。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `cli-toolchain`、`sbom-tools`

**复用边界（reuse_notes）**

- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。
- component_refs表示相关组件或被审查边界，不表示自动安装或已准入；按catalog类别和当前阶段执行。

**实施步骤**

1. 依照components/catalog.json合同记录候选来源、复用方式、所属阶段/依赖组、选择类别和NOT_RUN资格状态；实际版本/摘要/文件许可证/NOTICE在实施准入时填入，不伪造锁定结果。
2. 检查器比较catalog、各生态实际锁及资产清单；只允许当前阶段通过准入的功能组进入目标环境，后续候选不进入core默认依赖。
3. 建立版本/配置/源码更新的差异和受影响Q门禁规则；license/来源/资产缺失或状态不符阻止该能力启用，不自动换备用库。

**目标输出路径**

- `components/catalog.json`
- `components/dependency-lock.template.json`
- `scripts/check_components.py`
- `tests/components/admission`

**正向验收**

空环境bootstrap只装当前最小dev-contracts/core集合；Feishu/Browser/MCP/Tauri/P2候选仍可登记而不安装。实际启用组件可追溯来源、精确锁、LICENSE/NOTICE、配置/平台与资格证据；未准入、跨阶段默认安装和锁/目录不一致fixture能够阻断。

**反例与禁止行为**

- 不得把报告推荐/宽松许可证/star数当作准入批准；不得因安装方便把全部候选放入core默认组。

**验证方法**

分别生成最小bootstrap与一个选定后续组的安装/导入清单，模拟未核准包、错误阶段、遗漏资产hash和许可证不明，验证检查器拒绝；NOT_RUN不能自动变为通过。

**必须提交的证据**

- 组件目录样例、每组解析清单、锁diff、许可证原文定位、拒绝fixture运行记录。
- 记录精确来源/版本、OS/架构/配置、测试命令与限制；本包只定义门禁，真实结果未实施前保持NOT_RUN。

**来源与修订依据**

U3《OpenBot 开源组件复用评估》PDF物理第15–19、26页提出复用方向；本任务为v1.2工程补足与修正，以docs_refs中设计及官方证据为准。

### OB-006

**定义事件与命令协议**

阶段 M0 · 优先级 P0 · 状态 VERIFIED · 能力域 Runtime · 规模 M

**需求** [RQ02](requirements_traceability.md#rq02)、[RQ10](requirements_traceability.md#rq10)

**前置依赖** OB-002、OB-005、OB-089

**先读设计** [05_storage_api.md](../docs/05_storage_api.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。协议漂移可能破坏去重、授权与恢复。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `pydantic-jsonschema`

**复用边界（reuse_notes）**

- 用Pydantic/jsonschema做边界校验，领域对象深层不可变；拒绝未知权威字段、重复JSON键，完整合同一致性在OB-090验证。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 按docs/05定义Inbound/Runtime事件字段、版本、作用域与错误。
2. 实现边界校验和golden样例，建立DB seq与客户端去重规则。
3. 明确业务事件持久化、token流临时化以及未知版本处理。
4. 以准入的Pydantic/jsonschema封装严格JSON边界：进入dict前拒绝重复键，约束类型转换/extra，深层冻结或保存不可变canonical bytes；格式/refs合同交OB-090验证。

**目标输出路径**

- `contracts/schemas`
- `services/core/src/openbot/domain/events.py`

**正向验收**

事件有schema_version、event_id、trace/correlation和source；RuntimeEvent使用DB seq；入站身份由可信边界产生；任务状态表权威，events仅审计与增量流。 Pydantic frozen不充当深层不可变证明；外部修改嵌套dict/list不能改变已持久化提案。Draft2020-12完整验证、使用中的format显式检查，引用只来自审核本地注册表。

**反例与禁止行为**

- 外部is_owner/role字段不得成为可信身份；回放事件不得发起工具调用。
- 禁止静默保留重复键最后值、自动强制类型转换权威字段或联网获取远程Schema。

**验证方法**

黄金JSON双向验证；未知字段/版本策略明确；恶意外部身份字段不能成为授权依据。 测试嵌套变异、重复键、错误UUID/时间、未知字段、未知/远程ref与有界schema解析。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留最小可运行样例或golden fixture，以及对应静态/合同验证输出。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第6–7、20页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-007

**定义工具和模型Provider契约**

阶段 M0 · 优先级 P0 · 状态 VERIFIED · 能力域 Runtime · 规模 M

**需求** [RQ05](requirements_traceability.md#rq05)、[RQ07](requirements_traceability.md#rq07)、[RQ09](requirements_traceability.md#rq09)

**前置依赖** OB-002、OB-006

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[05_storage_api.md](../docs/05_storage_api.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。适配器绕过统一合同会形成隐藏执行路径。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** `pydantic-jsonschema`、`model-runner`

**复用边界（reuse_notes）**

- Provider/Tool合同保留自有权威字段；完整Draft2020-12验证、明确format策略、只用本地受控refs；半包或schema失败无派发。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 定义Text/ImageRef/ToolCall/ToolResult、Provider能力和标准错误。
2. 定义ToolProposal与manifest，标注模型可填字段和daemon补齐的权威字段。
3. 用两个fake Provider和一个fake executor验证同一合同。
4. 固定Provider允许的基础请求API/字段和完整schema验证，普通function只产生提案；禁自动tool_runner/Agent Runner、未纳管Provider托管工具及任意extra_body/extra_headers透传。

**目标输出路径**

- `contracts/schemas/tool_proposal.schema.json`
- `services/core/src/openbot/domain/tools.py`
- `services/core/src/openbot/domain/providers.py`

**正向验收**

工具与Provider使用明确的proposal/result与message块；manifest声明effect、retry_class、取消、reconcile和限制；模型仅填工具参数，不能伪造权威身份、policy或dispatch token。 校验器支持约定的Draft2020-12组合/本地ref/format与输入上限；模型、页面或插件不能改endpoint、认证头、policy或server-side tools。

**反例与禁止行为**

- 半包tool args、未知工具或外部自报readOnlyHint不得直接派发。
- 任何官方SDK自动工具helper、remote MCP或托管执行工具均不得绕过Broker；工具Schema不直接注册可执行Python函数。

**验证方法**

两种不同Provider的fake实现共用同套契约；原始模型消息不会直接传给executor。 用canary函数计数验证批准前为0；恶意extra_body/remote MCP/认证覆盖请求被拒绝。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留最小可运行样例或golden fixture，以及对应静态/合同验证输出。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第7、9、20页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-008

**定义配置与网络模式**

阶段 M0 · 优先级 P0 · 状态 VERIFIED · 能力域 Security · 规模 M

**需求** [RQ01](requirements_traceability.md#rq01)、[RQ06](requirements_traceability.md#rq06)

**前置依赖** OB-002、OB-005、OB-089

**先读设计** [00_scope.md](../docs/00_scope.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。模式歧义会造成用户未授权的数据离机。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `model-ollama`、`model-runner`

**复用边界（reuse_notes）**

- 配置/目录原语可复用；M0定义模式和runner禁云/egress资格合同并用fake验证，真实本地证明到OB-026完成，localhost不单独作保证。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 定义带版本的profile配置和CONNECTED/LOCAL_MODEL/OFFLINE语义。
2. 实现启动校验、显式能力禁用和最小权限默认值。
3. 把各连接工厂接到模式策略，输出冲突和不可用原因。
4. M0定义各依赖组/连接工厂、runner禁云、允许模型和egress证据字段，用fake连接/空缓存资产fixture验证冲突与拒绝；真实Provider/runner和实际出口分别留在其所属阶段完成。

**目标输出路径**

- `contracts/schemas/config.schema.json`
- `services/core/src/openbot/config.py`
- `config/openbot.example.toml`

**正向验收**

CONNECTED、LOCAL_MODEL、OFFLINE三个枚举及独立数据出口规则一致；OFFLINE禁用飞书和外网Browser/MCP；本地模型失败不云回退；配置版本化并默认最小权限。 localhost和模型名不单独证明本地推理；LOCAL_MODEL限定实际本地模型，OFFLINE约束OpenBot及受管执行域的全部出口。无可核验证据返回CAPABILITY_UNAVAILABLE，不声称整台电脑断网。 本任务交付配置合同与最小fake拒绝门禁；真实Ollama/model/runner资格在OB-026验证，不要求M0安装或调用M3组件。

**反例与禁止行为**

- OFFLINE不得仍连飞书；LOCAL_MODEL失败不得自动切云模型。
- 不得让loopback服务转云模型/web search或隐式代理绕过模式；运行期不得拉取模型或资产。

**验证方法**

M0测试配置冲突、空secret、错误目录、非法权限、假连接工厂与空缓存资产缺失；OFFLINE和LOCAL_MODEL错误配置/转云请求在fake合同中被拒绝，最小启动无意外网络。真实本地runner/模型及实际egress证据由OB-026/Q04提供。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留最小可运行样例或golden fixture，以及对应静态/合同验证输出。
- 模式配置/依赖组/runner准入字段、fake拒绝与最小启动的网络观察范围；真实本地模型证据明确标为OB-026待验证。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第14、20页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-009

**统一错误与时钟语义**

阶段 M0 · 优先级 P0 · 状态 VERIFIED · 能力域 Runtime · 规模 S

**需求** [RQ03](requirements_traceability.md#rq03)、[RQ10](requirements_traceability.md#rq10)

**前置依赖** OB-006、OB-007

**先读设计** [03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[05_storage_api.md](../docs/05_storage_api.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。错误与时间语义不一致会造成误重试和过期授权继续执行。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** 无直接组件引用

**复用边界（reuse_notes）**

- 错误/UTC/单调钟语义自研；SDK timeout/取消映射不得直接等于可重试或已回滚。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 冻结错误码、retryable与UNKNOWN关联，区分业务失败、拒绝和结果不明。
2. 抽象UTC clock与monotonic clock，并定义休眠/回拨/重启处理。
3. 为接口、工具和日志建立一致的序列化。
4. 区分调用方等待超时、数据库实际提交、SDK取消确认和外部效果状态；deadline覆盖排队/连接/读取/提交相关等待，不能只设置busy_timeout。

**目标输出路径**

- `contracts/schemas/error.schema.json`
- `services/core/src/openbot/domain/errors.py`

**正向验收**

错误code/message/retryable/trace_id一致；OUTCOME_UNKNOWN指Operation UNKNOWN、Task RECONCILING；持久时间用UTC毫秒，进程timeout用单调钟，重启敏感TTL需复验。 超时不自动推断回滚或可重试；已进入提交段的结果必须能按稳定请求标识核对。

**反例与禁止行为**

- timeout不能默认当FAILED可重试；客户端时间不能决定授权有效性。
- 不得将CancelledError统一映射为“未执行”或把所有Exception交通用retry装饰器。

**验证方法**

覆盖时钟回拨、睡眠后过期、Provider超时与策略拒绝；不会把所有Exception都重试。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留最小可运行样例或golden fixture，以及对应静态/合同验证输出。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第3、20页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-010

**建立确定性系统测试夹具**

阶段 M0 · 优先级 P0 · 状态 VERIFIED · 能力域 QA · 规模 M

**需求** [RQ03](requirements_traceability.md#rq03)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-005、OB-006、OB-007、OB-009

**先读设计** [03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。没有可控故障夹具会遗漏最危险的提交窗口。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `httpx`、`pydantic-jsonschema`

**复用边界（reuse_notes）**

- pytest/respx/hypothesis按开发组准入；夹具计数真实HTTP尝试与外部副作用，能模拟返回前成功、调用方取消后提交、SDK重试。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 实现fake模型、平台、时钟、执行器和supervisor端口。
2. 让测试可在指定事务前后崩溃并统计真实模拟副作用次数。
3. 建立seed和fixture隔离，使同一场景可复现。
4. 增添fake HTTP逐次请求计数、分片/退避取消、Writer等待取消后实际commit和隐式下载夹具；respx仅证明其拦截transport，另记录进程/网络探针覆盖范围。

**目标输出路径**

- `tests/fakes`
- `tests/scenarios`
- `tests/chaos/faults`

**正向验收**

提供fake模型、fake飞书、fake时钟、可控executor和崩溃点；场景断言面向用户结果和副作用次数。 夹具能检测SDK重试叠加、取消后新请求、外部成功本地未知以及caller取消后实际事务结果；实际SDK接入验证在所属阶段执行；不以单一HTTP mock声称全进程无网络。

**反例与禁止行为**

- 测试不得依赖生产账号；fake永远成功不能作为恢复验证。
- 不得使用永远成功的Mock掩盖未知效果，也不能把普通Python异常当断电实测。

**验证方法**

同一seed重复执行输出一致；夹具可模拟“外部成功但本地超时”。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留最小可运行样例或golden fixture，以及对应静态/合同验证输出。
- 可重放seed、网络尝试/副作用计数器、writer提交前后取消与反例fixture。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第20、26页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-090

**验证Schema与JCS标准合同向量**

阶段 M0 · 优先级 P0 · 状态 VERIFIED · 能力域 Runtime · 规模 M

**需求** [RQ02](requirements_traceability.md#rq02)、[RQ04](requirements_traceability.md#rq04)、[RQ07](requirements_traceability.md#rq07)、[RQ09](requirements_traceability.md#rq09)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-006、OB-007、OB-010、OB-089

**先读设计** [04_security_approvals.md](../docs/04_security_approvals.md)；[05_storage_api.md](../docs/05_storage_api.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)

**风险** HIGH。浅不可变、JSON歧义或不一致规范化导致批准绑定发生变化。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `pydantic-jsonschema`、`rfc8785`

**复用边界（reuse_notes）**

- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。
- component_refs表示相关组件或被审查边界，不表示自动安装或已准入；按catalog类别和当前阶段执行。

**实施步骤**

1. 用完整Draft2020-12校验器与审核本地Schema Registry，明确strict/coercion、extra、format与大小/递归/引用上限；进入普通dict前拒绝重复JSON键，未知/远程ref不联网。
2. Python权威Canonicalizer调用获准RFC8785实现，使用独立标准golden vectors验证UTF-16码元排序、负零/指数、数值域、Unicode及非法输入；不在测试中重写同样排序算法充当oracle。
3. 测试深层不可变/规范字节持久化和对外拷贝，frozen=True不替代嵌套变异防护；若实际存在第二JCS实现才跨实现比较字节/hash，不要求不用JCS的UI另实现。

**目标输出路径**

- `tests/contracts/canonicalization`
- `tests/contracts/schema`
- `contracts/golden`

**正向验收**

Python权威端的canonical bytes与SHA-256匹配经过核实的标准向量；覆盖非BMP与BMP键排序、负零/指数、嵌套、大整数边界，拒绝重复键、非有限数、非法Unicode/键和合同不支持数值。完整schema组合/本地refs/extra/指定format有反例；已批准内容不受外部嵌套变异影响。只有实际第二实现才比较同值字节与hash。

**反例与禁止行为**

- 不得用json.dumps(sort_keys=True)或Unicode码点排序代替JCS；不得让远程refs、重复键、隐式类型转换或默认忽略format放行。
- 不得把Pydantic frozen当深层不可变，也不得为了测试人为新增UI哈希授权逻辑。

**验证方法**

固定向量断言规范字节和hash，输入解析层拒绝重复键；注入嵌套变异、错误UUID/时间/格式、未知ref/远程URL、过深schema，观察零网络。第二实现不存在时明确NOT_APPLICABLE，不能伪报跨语言测试通过。

**必须提交的证据**

- 标准向量来源及所选库版本/hash、正负fixture和Python输出；schema/format/ref边界与深层变异结果。
- 实际第二实现存在时附跨实现比较；不存在时记录NOT_APPLICABLE及Python权威边界。
- 记录网络观察范围，证明被拒绝ref没有触发下载。

**来源与修订依据**

U3《OpenBot 开源组件复用评估》PDF物理第6–7、20–21页提出复用方向；本任务为v1.2工程补足与修正，以docs_refs中设计及官方证据为准。

### OB-091

**交付最小claim/dispatch崩溃协议PoC**

阶段 M0 · 优先级 P0 · 状态 VERIFIED · 能力域 QA · 规模 M

**需求** [RQ02](requirements_traceability.md#rq02)、[RQ03](requirements_traceability.md#rq03)、[RQ04](requirements_traceability.md#rq04)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-009、OB-010、OB-090

**先读设计** [03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[05_storage_api.md](../docs/05_storage_api.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)

**风险** HIGH。等真实组件全部完成才发现claim/dispatch协议不可恢复。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `sqlite3`、`rfc8785`

**复用边界（reuse_notes）**

- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。
- component_refs表示相关组件或被审查边界，不表示自动安装或已准入；按catalog类别和当前阶段执行。

**实施步骤**

1. 在测试目录用FakeChannel/Provider、FakeClock、真实临时SQLite、标准JCS及计数MockWorker组成最小协议模型；不增加正式表/API或第二生产调度器。
2. 在claim前后、CLAIMED→DISPATCHING前后及fake外部成功后本地确认前注入崩溃；插入取消/epoch/resource变化和caller等待取消。
3. 保存不变量与反例供M1重用，分别核验CONSUMED、Attempt/Operation标识、未知效果/quarantine与证据核对；OB-029仍做真实本地端口/隔离路径完整集成。

**目标输出路径**

- `tests/protocol/early_recovery_poc`
- `docs/evidence/protocol-poc.md`

**正向验收**

不需任何云key、飞书、完整CLI或容器；CONSUMED不逆转，同Attempt重传ID不变、新Attempt新ID且provider键稳定；派发前复核失败效果计数0，已派发无回执保持UNKNOWN/RECONCILING并阻断资源；无证据人工success不能强改。

**反例与禁止行为**

- 不得省略第二事务，不能把fake成功证明M1系统完成；不把PoC表加入正式23表基线或新增API。
- 禁止把M0临时测试模型或MockWorker通过写成完整M1实现/真实OS隔离已经完成。

**验证方法**

一条离线命令运行固定seed/故障矩阵；查询临时库与MockWorker效果计数，验证派发前失败为0、未知结果不重发、换Task/Operation也不能越过quarantine。无需真实Provider、完整CLI、飞书或容器。

**必须提交的证据**

- 一条可运行PoC命令、seed/故障位置、SQLite快照、dispatch与效果计数、失败反例。
- 记录精确来源/版本、OS/架构/配置、测试命令与限制；本包只定义门禁，真实结果未实施前保持NOT_RUN。

**来源与修订依据**

U3《OpenBot 开源组件复用评估》PDF物理第3、20–21、26页提出复用方向；本任务为v1.2工程补足与修正，以docs_refs中设计及官方证据为准。


## M1 本地内核与安全工具

### OB-011

**实现带版本的数据库迁移**

阶段 M1 · 优先级 P0 · 状态 VERIFIED · 能力域 Runtime · 规模 M

**需求** [RQ02](requirements_traceability.md#rq02)

**前置依赖** OB-006、OB-009、OB-091

**先读设计** [05_storage_api.md](../docs/05_storage_api.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。迁移或约束错误会丢失任务与授权证据。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `sqlite3`、`aiosqlite`、`yoyo-migrations`

**复用边界（reuse_notes）**

- 优先标准库sqlite3，aiosqlite仅经过PoC后可选；顺序checksum迁移自有，禁止ORM隐式写入/级联或无理由再加迁移框架。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 逐项实现docs/05表、唯一键、外键、状态约束和查询索引。
2. 编写顺序迁移和checksum记录，提供旧版本fixture及损坏版本拒绝。
3. 验证全新建库、升级、中断与重启后的完整性。
4. 优先sqlite3专属writer线程，aiosqlite仅是经准入的驱动可选项；版本/checksum迁移器继续自有，不因选库引入隐式ORM写入或第二迁移框架。

**目标输出路径**

- `db/migrations`
- `services/core/src/openbot/storage/migrate.py`
- `tests/integration/storage`

**正向验收**

实现docs/05逻辑表和约束、版本与checksum迁移；MVP不提前建embedding/schedule；旧11表如存在仅走显式迁移；迁移前后完整性可检查。 每个实际连接明确设置并读回WAL/FULL/foreign_keys，不凭任何驱动默认值断言耐久性。

**反例与禁止行为**

- 不能覆盖用户现有库、跳过不兼容版本或静默修改已发布migration。
- 不得将基线DDL直接等同完整迁移器，或宣称ORM必然不安全来替代本项目事务证据。

**验证方法**

新库→最新与旧版本→最新均成功；中断迁移不留下半版本；不支持版本启动时明确退出。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。
- 所选驱动/SQLite构建版本和实际PRAGMA读回、迁移失败恢复记录。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第7–8、20–21页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-012

**实现串行写事务与数据库背压**

阶段 M1 · 优先级 P0 · 状态 VERIFIED · 能力域 Runtime · 规模 M

**需求** [RQ02](requirements_traceability.md#rq02)、[RQ03](requirements_traceability.md#rq03)

**前置依赖** OB-011

**先读设计** [05_storage_api.md](../docs/05_storage_api.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。提交与执行顺序破坏会使系统做过动作却无记录。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `sqlite3`、`aiosqlite`

**复用边界（reuse_notes）**

- sqlite3默认、aiosqlite可选；完整WriterCommand事务由唯一writer独占，稳定request_id关联持久结果，caller取消不等于回滚。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 以稳定request_id的完整WriterCommand作为唯一写入口，writer独占BEGIN到COMMIT/ROLLBACK；业务协程不能获得可写连接。
2. 实现有界队列、审批/取消/入站/结果的保留容量与公平性、总deadline及读回WAL/FULL/FK；驱动串行SQL不替代完整事务所有权。
3. caller取消/timeout只结束等待，不假称底层回滚；通过已有幂等记录及Task/Operation/事件关联重查持久结果，实际提交后才能ACK。
4. 注入入队、事务开始、commit前后取消和队列拥塞，确认命令不相互提交/回滚；提交结果不明时禁盲重放和新派发。

**目标输出路径**

- `services/core/src/openbot/storage/writer.py`

**正向验收**

单writer队列有界、短事务、关闭/背压协议；审批/取消/入站有配额；WAL、FULL、foreign_keys实际校验；busy_timeout不超过调用剩余deadline；提交失败阻止新派发。 WriterCommand携带稳定请求ID并关联可重查的持久结果；使用aiosqlite也不把共享写连接暴露给适配器。caller等待取消、deadline与实际commit结果分别记录。

**反例与禁止行为**

- 事务内不得await网络/人工或嵌套等待writer；队列满不得静默丢弃。
- 不得因Future取消或超时回复“已回滚”，也不得重发同一非幂等写命令猜测结果；父/子协程不得穿插同一连接事务。

**验证方法**

并发读写与队列满验证无任务静默丢弃；故障时调用方收到确定错误；事务回滚后可继续。 同时运行两个写命令，在入队/执行/commit前后取消调用者并按同一请求ID重查；普通队列满时取消/结果仍可提交，高优洪峰不无限饿死其他请求。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。
- 稳定request_id与权威结果关联、提交点日志、队列配额/公平性和取消反例。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第7、20页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-013

**实现持久inbox与作用域去重**

阶段 M1 · 优先级 P0 · 状态 VERIFIED · 能力域 Runtime · 规模 M

**需求** [RQ02](requirements_traceability.md#rq02)、[RQ08](requirements_traceability.md#rq08)

**前置依赖** OB-006、OB-011、OB-012

**先读设计** [05_storage_api.md](../docs/05_storage_api.md)；[02_architecture.md](../docs/02_architecture.md)；[07_feishu.md](../docs/07_feishu.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)

**风险** HIGH。去重作用域错误会丢任务或重复创建任务。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** `sqlite3`

**复用边界（reuse_notes）**

- 持久作用域去重与ACK提交边界不变；不能改用SDK内存去重。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 规范source_scope与外部event幂等键，保存payload hash。
2. 把inbox、Task与初始event/outbox封成一个事务用例。
3. 实现重复返回与同key异payload冲突，并注入ACK前后崩溃。

**目标输出路径**

- `services/core/src/openbot/storage/inbox.py`

**正向验收**

source_scope包含channel、tenant、app与profile；inbox与TaskQueued同事务；成功只在提交后返回；同幂等键不同payload返回冲突，重复请求查询原Task。

**反例与禁止行为**

- 未持久提交不得ACK成功；不同tenant/app相同event ID不能互相去重。

**验证方法**

100次同源事件只创建1任务；不同app相同event_id不互相误去重；落盘前后崩溃结果一致。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第10、20页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-014

**实现任务状态与事件原子提交**

阶段 M1 · 优先级 P0 · 状态 VERIFIED · 能力域 Runtime · 规模 M

**需求** [RQ02](requirements_traceability.md#rq02)、[RQ03](requirements_traceability.md#rq03)

**前置依赖** OB-011、OB-012、OB-013

**先读设计** [03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[05_storage_api.md](../docs/05_storage_api.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。状态权威不清会造成虚假完成与重复执行。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** `sqlite3`

**复用边界（reuse_notes）**

- Task、状态版本CAS、event/outbox同事务保留自研；不得交给外部Agent状态机。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 将docs/03 Task跃迁表编码为domain规则与version CAS。
2. 实现状态+审计+outbox的原子application用例。
3. 实现只读审计回放与状态快照，验证非法跃迁拒绝。
4. 将WriterCommand稳定请求ID和幂等结果关联到既有持久记录；调用方timeout/断连后使用相同标识读取实际状态，不新增第二权威账本。

**目标输出路径**

- `services/core/src/openbot/application/state_machine.py`

**正向验收**

实现docs/03 Task合法跃迁与version CAS；权威task/operation、event、outbox同事务；Task使用QUEUED/RUNNING等定义，审计回放绝不执行历史工具。 caller取消不破坏状态/event/outbox原子性；只有确认实际commit才返回成功，重复请求先查原结果而不重新执行事务语义。

**反例与禁止行为**

- 模型final不得直接把Task标SUCCEEDED；事件回放不得执行副作用。
- HTTP断连或协程取消不能充当“事务未发生”的证据，也不能回ACK后让writer静默丢弃写命令。

**验证方法**

对每条合法/非法跃迁验证；崩溃后状态和event版本不分裂；重放不会启动executor。 commit完成前后断开调用者，重查同一请求ID的状态/event/outbox一致且无重复副作用。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第3、20页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-017

**实现动作意图与执行attempt日志**

阶段 M1 · 优先级 P0 · 状态 IN_PROGRESS · 能力域 Runtime · 规模 M

**需求** [RQ02](requirements_traceability.md#rq02)、[RQ03](requirements_traceability.md#rq03)

**前置依赖** OB-007、OB-011、OB-014

**先读设计** [03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[05_storage_api.md](../docs/05_storage_api.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)

**风险** CRITICAL。这是外部副作用可能重复的核心窗口。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** 无直接组件引用

**复用边界（reuse_notes）**

- 保持Operation级provider幂等键、Attempt级dispatch_id与CONSUMED不可逆；组件自动重试须映射到受控尝试而非绕开账本。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 实现不可变Operation与Attempt分表：provider_idempotency_key属于Operation，dispatch_id属于Attempt；同Attempt传输重试固定dispatch_id，新Attempt生成新dispatch_id。
2. 首次CLAIMED事务消费批准并建立Attempt；Approval一旦CONSUMED永不退APPROVED。CLAIMED到DISPATCHING使用第二个短事务再次检查取消、runtime_epoch与资源版本，再持久化后发包。
3. 保存接收ledger、receipt与UNKNOWN；同Operation安全重试只能由恢复器批准并沿用既有消费关系，仍复验原授权期限、policy、actor/identity、取消及resource，不二次消费或授权其他Operation。
4. 覆盖claim后取消、同Attempt重传、新Attempt重试、外部成功后本地崩溃；记录ID与grant关系作为故障证据。

**目标输出路径**

- `services/core/src/openbot/application/operations.py`

**正向验收**

Operation与Attempt严格分离；provider_idempotency_key在Operation内稳定，dispatch_id在同Attempt重传时不变、在新Attempt中重新生成。批准首次消费后永久保持CONSUMED历史关系，不退APPROVED。CLAIMED→DISPATCHING第二短事务复核取消、epoch与资源，成功提交后才能派发。安全重试仅由恢复器对同Operation复验原期限、policy、actor/identity、cancel与resource后允许，任一条件变化则新建Operation；结果不明进入UNKNOWN。

**反例与禁止行为**

- 禁止把CONSUMED改回APPROVED、二次消费或借给其他Operation；通用重试按钮/adapter不能自行判定已消费grant可重用。
- 禁止给同Attempt传输重试换dispatch_id，或让新Attempt沿用旧dispatch_id；不得在创建新Attempt时更换同Operation的provider幂等键。
- claim之后、DISPATCHING提交之前发生取消/epoch失效/resource变化必须阻止派发；仅claim时检查不满足验收。

**验证方法**

注入intent、CLAIMED、DISPATCHING前后、外部成功和结果提交故障；断言同Attempt重传只接受同dispatch_id，新Attempt用新dispatch_id且保留Operation的provider_idempotency_key；CONSUMED无逆向状态变化；claim后取消/epoch或资源变化没有任何worker接收。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。
- 提供Operation/Attempt/dispatch/provider幂等键/grant关联快照，证明CONSUMED单向性与两次短事务的检查点。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第3、21页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-018

**实现审批决定与一次性授权**

阶段 M1 · 优先级 P0 · 状态 IN_PROGRESS · 能力域 Security · 规模 M

**需求** [RQ04](requirements_traceability.md#rq04)

**前置依赖** OB-002、OB-014、OB-017、OB-090

**先读设计** [04_security_approvals.md](../docs/04_security_approvals.md)；[05_storage_api.md](../docs/05_storage_api.md)；[07_feishu.md](../docs/07_feishu.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。错误绑定会让旧批准授权新动作。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `rfc8785`、`pydantic-jsonschema`

**复用边界（reuse_notes）**

- Python为binding摘要权威，复用标准JCS与深层不可变字节；标准向量验证，不强制UI另写JCS。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 由Python权威端构造固定字段/版本的绑定对象，严格JSON校验后调用获准rfc8785生成并持久化canonical bytes与SHA-256。
2. 实现审批预览、nonce/actor/TTL/policy/identity CAS和READY跃迁；深层不可变或拷贝防止批准后嵌套参数被改变。
3. 记录决定与outbox，重复决定返回现状而不再授权；执行前核对同一规范字节/摘要与资源版本。
4. 使用OB-090标准向量验证UTF-16排序、数值/Unicode边界；UI展示服务端hash，不强制为不使用JCS的UI再实现哈希。

**目标输出路径**

- `services/core/src/openbot/policy/approvals.py`

**正向验收**

认证actor、profile、task、binding、nonce、TTL、identity_epoch及policy一起CAS；批准只将Operation改READY；Approval消费与执行结果分开；RFC8785 golden vectors验证binding hash。 Approval从APPROVED首次消费为CONSUMED后永不回退；同Operation是否可安全重试只能由恢复器复验既有消费关系，普通批准接口不能复活或再次消费授权。 RFC8785属性按UTF-16码元排序；非有限数、重复键、非法Unicode与超出合同数值域的输入拒绝。只有实际加入第二JCS实现时才要求跨实现字节一致。

**反例与禁止行为**

- action.value中的actor/role、过期nonce、旧policy和变化参数必须拒绝。
- 禁止通过重复批准callback、API或人工核对把CONSUMED记录改回APPROVED。
- 不得用json.dumps(sort_keys=True)模拟JCS或只依赖frozen=True防嵌套变更；客户端重算hash不替代服务端授权。

**验证方法**

同一PENDING/version的并发互斥决定最多一个成功；后续针对尚未消费授权的合法撤销可按新version独立成功，并阻止claim/dispatch；错主体、错设备、过期、变更参数全拒绝；授权状态可审计。 嵌套变异与标准向量通过，错误代码点排序会失败；ApprovalPreview与执行绑定指向同一不可变内容。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第7、21页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-021

**实现durable outbox及投递状态**

阶段 M1 · 优先级 P0 · 状态 IN_PROGRESS · 能力域 Integration · 规模 M

**需求** [RQ02](requirements_traceability.md#rq02)、[RQ08](requirements_traceability.md#rq08)

**前置依赖** OB-012、OB-014、OB-017

**先读设计** [05_storage_api.md](../docs/05_storage_api.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[07_feishu.md](../docs/07_feishu.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。外发乱序或重试会造成错误状态和重复消息。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** `tenacity`

**复用边界（reuse_notes）**

- outbox语义/调度自研；SDK退避仅在已审定投递类型内由一个所有者执行，计数可见，不能假称远端exactly-once。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 实现outbox语义键、revision、receipt、重试期限与dead letter。
2. 把远端发送移到DB事务外，按接口幂等能力处理IN_FLIGHT恢复。
3. 实现可合并进度和终态保护，提供后续gateway发送端口。
4. 对SDK/HTTP/应用退避选一个所有者，逐次记录投递attempt、预算/deadline和receipt；库异常不得让outbox消费者重放原业务动作。

**目标输出路径**

- `services/core/src/openbot/application/outbox.py`
- `services/core/src/openbot/storage/outbox.py`

**正向验收**

持久化语义键、revision、IN_FLIGHT、attempt/deadline及远端receipt；发送在事务外；状态更新可合并，旧版本不能覆盖终态；远端结果不明按能力核对。 重试次数真实可数，迟到或重复回执不覆写更高revision，未知远端效果继续按既定能力核对。

**反例与禁止行为**

- 通知重试不能重执行业务；没有远端幂等保证不得声称exactly-once通知。
- 通用tenacity装饰器不能无界重试所有异常或驱动未知副作用再次提交。

**验证方法**

断网重启后通知仍存在；重复重试不倒退卡片状态；不能声称无远端幂等支持时exactly-once。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第10、21页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-023

**实现任务预算和熔断**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Runtime · 规模 M

**需求** [RQ03](requirements_traceability.md#rq03)、[RQ07](requirements_traceability.md#rq07)

**前置依赖** OB-007、OB-014、OB-017

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。预算竞争可造成无限循环与不受控费用。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `tiktoken`、`tenacity`

**复用边界（reuse_notes）**

- 预算账本自研；tokenizer按模型选择、离线资源需预置与校验，不能把OpenAI词表当全模型精确计数；重试每次计费尝试都纳入预算。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 定义各预算与保守上限，调用前reserve并持久记录。
2. 响应后settle真实用量；超时未知费用留待核对。
3. 实现重复提案/连续错误/空转熔断与PAUSED恢复条件。
4. 将估算/预留/真实usage/未知费用分开；tokenizer与模型、离线词表固定映射，实际HTTP重试逐次预留/结算，取消后不再发新请求。

**目标输出路径**

- `services/core/src/openbot/application/budgets.py`

**正向验收**

steps、模型调用、时间、tokens、费用、重试、工具与artifact大小均有限额；模型/工具调用前reserve，结果后settle；未知费用保守保留；预算不足进入PAUSED。 只有一个请求重试策略所有者；SDK与transport不得产生账本外请求。tiktoken不充当所有Provider完整请求的精确计费器，未知用量保守保留。

**反例与禁止行为**

- 并发或重试不得超卖预算；预算耗尽不得静默继续调用付费服务。
- 不得给未知模型套统一精确token数、在断流后清零费用，或把SDK重试叠加tenacity扩大预算。

**验证方法**

runaway模型无法无限循环；并发预算不超卖；预算不足任务进入可解释暂停而非静默结束。 429/503/连接断开与首块后取消逐次计数，实际请求数等于预算attempt记录；空缓存禁网词表首用成功或明确不可用。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。
- 模型/编码器/词表hash、估算与usage偏差和每次请求的预留/结算证据。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第8、16、21–22页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-024

**实现上下文快照与摘要**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Runtime · 规模 M

**需求** [RQ06](requirements_traceability.md#rq06)、[RQ07](requirements_traceability.md#rq07)

**前置依赖** OB-007、OB-014、OB-017、OB-023

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。上下文压缩可能丢约束或洗白注入内容。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** `tiktoken`

**复用边界（reuse_notes）**

- 上下文裁剪/provenance/污点继承自有；复用tokenizer不替代上下文授权，也不额外引入Agent memory框架。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 建立有限上下文选择、消息与tool_call_id关联及来源标签。
2. 实现保留目标、授权范围、待办和source refs的摘要。
3. 验证长会话、跨重启和注入传播，输出用于模型的最小数据集。
4. 按已声明模型使用准入tokenizer并记录估算误差；裁剪或摘要不得让外部内容获得权威字段，且不引入独立Agent memory执行循环。

**目标输出路径**

- `services/core/src/openbot/application/context.py`

**正向验收**

上下文来自目标、约束、状态、已批准范围与必要证据；摘要保留source refs与未决动作；数据分类和provenance不被摘要洗白；不持久化隐藏推理。 额外消息包装、tool schema和多模态开销有预算策略，不以纯文本分词数冒充最终费用。

**反例与禁止行为**

- 摘要、memory或模型转述不得把外部文字升级为系统/用户授权。

**验证方法**

长会话截断后仍能恢复待办与工具关联；注入文本经摘要后不会获得更高信任。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第3、8–9页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-031

**实现确定性策略评估器**

阶段 M1 · 优先级 P0 · 状态 IN_PROGRESS · 能力域 Security · 规模 M

**需求** [RQ04](requirements_traceability.md#rq04)

**前置依赖** OB-002、OB-007、OB-008、OB-018

**先读设计** [04_security_approvals.md](../docs/04_security_approvals.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。策略是全部执行能力的强制边界。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** `opa-casbin`、`pathspec`

**复用边界（reuse_notes）**

- 不默认引入OPA/Casbin；pathspec只能辅助忽略/展示规则，不得作为安全路径白名单或授权判定。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 实现actor/resource/action/data/destination/backend组合规则。
2. 冻结决策与理由码，明确硬拒绝和本地设置权限。
3. 用表驱动输入和未知能力场景验证确定性。
4. 维持纯代码表驱动策略；OPA/Casbin不作默认runtime，pathspec只做忽略/展示辅助，不能承担路径授权。

**目标输出路径**

- `services/core/src/openbot/policy/evaluator.py`

**正向验收**

以actor/resource/action/data_class/destination/backend和有效授权做纯确定性判断；输出ALLOW、ASK、DENY、REQUIRE_LOCAL及原因码；未知能力默认拒绝，硬拒绝不能被远程批准覆盖。 SDK helper、源码模板与工具metadata不能产生额外权限；未知工具/网络目标/执行器仍按确定性规则拒绝。

**反例与禁止行为**

- 模型risk评分、MCP hint或远程批准不得覆盖DENY/REQUIRE_LOCAL。
- 不得以pathspec匹配成功、官方包身份或第三方readOnlyHint替代六维授权判断。

**验证方法**

同一输入重复判定一致；未知工具默认deny；策略单元用例覆盖强制deny优先级。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第3、8页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-032

**实现工作区路径与文件访问守卫**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Security · 规模 M

**需求** [RQ04](requirements_traceability.md#rq04)、[RQ05](requirements_traceability.md#rq05)

**前置依赖** OB-002、OB-008、OB-031

**先读设计** [04_security_approvals.md](../docs/04_security_approvals.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。路径绕过可能读取密钥或覆盖工作区外文件。

**复用职责（reuse_type）** `native_primitive` · 原生原语适配

**关联组件（component_refs）** `pathspec`、`git-worktree`

**复用边界（reuse_notes）**

- 路径/句柄守卫继续自有；Win32/OS库为原语，不能机械删除\?\前缀或仅字符串normalize后放行，保留拒绝与原生攻击语料。
- 实际OS、架构、backend和配置组合须独立提供证据；统一API、正常退出或进程组不能自动证明所有强杀与逃逸场景均可回收。

**实施步骤**

1. 定义受管工作区与真实路径/句柄策略，并列各OS不支持路径类型。
2. 实现读取/创建/替换前核验及执行时复验。
3. 跑symlink、junction、ADS、UNC、父目录变化等原生OS语料。
4. 审查快照构造和搜索适配器的实际路径/配置行为；git worktree准备须隔离或验证禁hooks/filter，不能因“创建快照”就视为无执行。

**目标输出路径**

- `services/core/src/openbot/tools/filesystem_guard.py`

**正向验收**

宿主ACI使用路径对象与可用OS句柄防护，拒绝根外、设备/UNC/ADS和不支持的reparse point；创建时验证父目录和旧hash；同用户恶意竞态边界明确，必要时只开放受管工作树。 pathspec/.gitignore仅筛选内容；Windows路径拒绝策略和真实句柄复核不能简化为去前缀或大小写归一。

**反例与禁止行为**

- 仅靠resolve或字符串prefix不能通过验收；根外与敏感路径必须拒绝。
- 不把rg、Git或dulwich绕过FileGuard；不可在未审查的仓库配置下执行post-checkout/filter等宿主代码。

**验证方法**

各目标OS原生攻击路径语料；替换链接竞态不能写到授权根外；没有承诺仅normalize即可彻底沙箱。 使用恶意Git hook/filter与rg配置canary，确认守卫/隔离先于任何潜在执行。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第12页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-036

**实现Artifact存储与可信元数据**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Runtime · 规模 M

**需求** [RQ02](requirements_traceability.md#rq02)、[RQ06](requirements_traceability.md#rq06)

**前置依赖** OB-011、OB-017、OB-032

**先读设计** [05_storage_api.md](../docs/05_storage_api.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。Artifact通道可绕过大小、权限和数据出口控制。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** 无直接组件引用

**复用边界（reuse_notes）**

- hashlib、平台原子文件原语可用；content-addressed对象、fsync/rename、分类/引用和限额自有，不无理由加MIME/对象存储框架。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 实现内容写入、hash、原子注册及artifact_refs。
2. 施加字节预算、classification、TTL与受限下载。
3. 实现孤立对象回收、缺失对象状态与引用保护。
4. 把审批所用确切新内容Artifact和backup GC pin纳入引用/保留合同；hashlib/平台原子文件原语不替代注册与分类一致性。

**目标输出路径**

- `services/core/src/openbot/artifacts`

**正向验收**

artifact对象不可变且有hash、MIME、bytes、classification、TTL与artifact_refs；临时文件→原子rename→注册；预览、单产物、单任务大小限额可配置，下载不暴露宿主路径。 已批准新内容hash变化必须失效，GC不能删除待审批或正在备份的引用对象。

**反例与禁止行为**

- 不得作为任意宿主路径文件服务器；HTML/脚本不得默认内联执行。
- MIME/检测库结果不能降低classification或让普通预览访问SECRET。

**验证方法**

注册前崩溃可回收孤立文件；登记后缺失文件明确标记；大输出不能无限耗尽磁盘。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第6、22–23页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-037

**实现统一数据外发策略**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Security · 规模 M

**需求** [RQ04](requirements_traceability.md#rq04)、[RQ06](requirements_traceability.md#rq06)

**前置依赖** OB-002、OB-008、OB-031、OB-036

**先读设计** [04_security_approvals.md](../docs/04_security_approvals.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。无统一出口会让安全文件工具仍把敏感内容发送远端。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** `httpx`、`model-runner`、`model-ollama`

**复用边界（reuse_notes）**

- 统一egress守卫仍覆盖SDK/网页/MCP及本地模型runner；审查HTTP客户端、DNS、代理、tokenizer缓存下载；localhost不能证明无云转发，脱敏不能替代出口限制。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 定义各数据类与目的地组合，并在所有出口前调用策略。
2. 将模型上下文、通知预览、文件上传和MCP参数统一标记。
3. 验证摘要/Artifact/流式输出仍保留限制，以及OFFLINE全出口拒绝。
4. 将SDK/HTTP环境代理、模型runner云路由、tokenizer/grammar下载、Scanner联网验证和浏览器子进程纳入受管出口；明确探针覆盖及不可证明部分。

**目标输出路径**

- `services/core/src/openbot/policy/egress.py`

**正向验收**

模型、飞书通知、Browser、MCP、上传和消息工具共享数据出口策略；PUBLIC/WORKSPACE/SENSITIVE/SECRET按目标和动作评估；敏感预览不能默默上传，OFFLINE禁外网。 允许loopback不等于允许其转发云请求；本地模型需选定model/禁云/真实egress证据，未确认时拒绝本地保证。HTTPX等客户端关闭隐式环境读取或只注入获准代理。

**反例与禁止行为**

- SENSITIVE不得因放进卡片或摘要而自动外发；只限制LLM不算OFFLINE。
- 任何Provider托管web search/remote MCP、扫描器网络验证、隐式price map/词表下载或未批准代理不得绕过出口。

**验证方法**

敏感文件经摘要/Artifact仍保持限制；OFFLINE阻断所有远端连接；允许域名不等于允许任意数据发送。 实际网络隔离/审计结合各transport fixture；仅mock httpx不作为所有requests/Rust/子进程零网络证据。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。
- 受管进程/runner/浏览器出口范围、代理配置及绕过反例。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第3、8、13页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-043

**实现本地消息草稿**

阶段 M1 · 优先级 P1 · 状态 TODO · 能力域 Runtime · 规模 S

**需求** [RQ04](requirements_traceability.md#rq04)、[RQ06](requirements_traceability.md#rq06)

**前置依赖** OB-007、OB-036、OB-037

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)

**风险** HIGH。收件人歧义会导致隐私发送给错误对象。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** 无直接组件引用

**复用边界（reuse_notes）**

- 本地不可变消息草稿、明确收件人与附件hash自有，不复用上游自动发送或首次sender当owner逻辑。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 要求稳定收件人ID和目标账户，无法解析时WAITING_INPUT。
2. 生成正文/附件不可变草稿artifact及digest。
3. 提供本地预览和修订版本，不进行网络发送。

**目标输出路径**

- `services/core/src/openbot/tools/messages/draft.py`

**正向验收**

message.draft仅生成本地不可变草稿artifact；稳定recipient ID、channel、正文与附件固定；名称歧义需WAITING_INPUT；未明确收件人不能生成可发送提案。

**反例与禁止行为**

- 仅有同名联系人或旧草稿hash不得进入可发送READY状态。

**验证方法**

草稿编辑产生新版本；旧approval不能批准新内容；没有网络调用。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第9–10页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-092

**建立组件副作用和重试取消故障契约**

阶段 M1 · 优先级 P0 · 状态 IN_PROGRESS · 能力域 QA · 规模 M

**需求** [RQ03](requirements_traceability.md#rq03)、[RQ06](requirements_traceability.md#rq06)、[RQ07](requirements_traceability.md#rq07)、[RQ08](requirements_traceability.md#rq08)、[RQ09](requirements_traceability.md#rq09)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-007、OB-008、OB-009、OB-010、OB-089、OB-090、OB-091

**先读设计** [03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)

**风险** HIGH。SDK隐藏重试/下载/网络/取消语义绕开预算与恢复账本。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `httpx`、`model-openai`、`model-ollama`、`model-anthropic`、`model-runner`、`detect-secrets`

**复用边界（reuse_notes）**

- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。
- component_refs表示相关组件或被审查边界，不表示自动安装或已准入；按catalog类别和当前阶段执行。

**实施步骤**

1. 建立有界子进程/网络探针和fake HTTP计数器，覆盖import、初始化、首次实际调用、DNS/代理/下载/线程、流/取消/关闭；分别说明respx与平台审计覆盖。
2. 默认SDK max_retries=0并关闭transport隐式重试，由OpenBot唯一管理次数/退避/deadline/预算；任何委托SDK例外须逐次可观测且不得叠加tenacity。
3. 限定SDK允许API，canary验证tool_runner/Agent Runner/Provider托管工具和remote MCP不执行；加入localhost转云、scanner联网验证/allowlist与取消后新请求反例。
4. 当前M1候选完成实际合同，后续每个SDK在自己的阶段填真实证据；提供可重用runner与失败样例，fake通过不自动认证后续组件。

**目标输出路径**

- `tests/components/contracts`
- `tests/components/probes`
- `docs/evidence/component-fault-contract.md`

**正向验收**

实际HTTP请求数与Gateway request-attempt/预算一致，取消或流中断终止当前调用后不会由隐藏层自动新发；应用主动新尝试必须走显式策略。导入/首用意外联网下载、自动工具执行、网络验证或外部allowlist旁路都能触发门禁；每个真实组件的结果独立记录。

**反例与禁止行为**

- 不能仅patch httpx就声称拦住requests/urllib/子进程全部网络；fake测试通过不代表lark、Playwright或MCP真实实现通过。
- 官方SDK来源、loopback地址、扫描阴性或单一httpx mock均不能自动证明没有隐藏执行/云外发。

**验证方法**

以fake server产生连接失败、429/503、退避取消、首块后中断/取消与未知usage；计数SDK/transport/Gateway层，对网络探针未覆盖路径显式记录限制。后续适配器逐个重用该合同。

**必须提交的证据**

- 探针覆盖范围/局限、attempt计数、fault traces、组件合同runner使用说明与反例。
- 记录精确来源/版本、OS/架构/配置、测试命令与限制；本包只定义门禁，真实结果未实施前保持NOT_RUN。

**来源与修订依据**

U3《OpenBot 开源组件复用评估》PDF物理第7–9、13–14、20–24页提出复用方向；本任务为v1.2工程补足与修正，以docs_refs中设计及官方证据为准。

### OB-038

**实现密钥存储与最小注入**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Security · 规模 M

**需求** [RQ06](requirements_traceability.md#rq06)、[RQ11](requirements_traceability.md#rq11)

**前置依赖** OB-008、OB-031、OB-092

**先读设计** [04_security_approvals.md](../docs/04_security_approvals.md)；[02_architecture.md](../docs/02_architecture.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。凭据泄漏会扩大到用户外部账户。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `keyring`、`crypto-storage`

**复用边界（reuse_notes）**

- keyring择已验证OS后端；缺服务/锁定/交互错误明确失败，不把任意插件或自制Fernet存储作为自动fallback。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 实现OS凭据引用与凭据不可用的明确错误。
2. 为gateway/模型/worker划分最小secret注入和短时IPC交接。
3. 实现轮换、撤销与测试key canary扫描。
4. 锁定keyring允许后端并验证锁定、无D-Bus/无图形会话/取消；不加载不明插件，不把缺独立主密钥设计的加密文件作为自动fallback。

**目标输出路径**

- `services/core/src/openbot/policy/secrets`
- `native/supervisor/src/credential_transport.rs`

**正向验收**

OS凭据存储或明确加密替代，配置仅secret_ref；gateway只有飞书secret，模型网关仅被选Provider key，worker用单用途secret handle；token不入argv或日志。 各OS凭据backend实际可用才启用能力；secret_ref失效可解释且不默默重新生成或扩大注入范围。

**反例与禁止行为**

- 不能继承全env、挂宿主HOME或把token写argv；钥匙串失败不能静默明文保存。
- 不得自动回退明文或未评审的cryptography/Fernet文件存储，也不得继承父进程全部env。

**验证方法**

测试凭据丢失/锁定；child env、日志、异常栈和诊断包均无测试密钥；无法调用钥匙串时不默默明文保存。 钥匙串不可用/权限撤销/用户取消/恢复旧引用后对应能力拒绝，输出保持无秘密。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第14、22–23页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-039

**实现敏感数据输出过滤**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Security · 规模 M

**需求** [RQ06](requirements_traceability.md#rq06)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-036、OB-037、OB-038、OB-092

**先读设计** [04_security_approvals.md](../docs/04_security_approvals.md)；[05_storage_api.md](../docs/05_storage_api.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。日志和诊断是常被遗漏的秘密出口。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `detect-secrets`、`structlog`

**复用边界（reuse_notes）**

- detect-secrets默认CI辅助，运行时只用离线已审查检测器；关闭网络验证/动态插件，外部allowlist不生效，不承诺128字节/100%。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 定义运行时redactor的已注册secret精确匹配、规则范围、最大长度/编码、跨任意chunk和flush策略，先过滤再持久化/外发。
2. detect-secrets默认仅开发/CI辅助；若复用运行时检测器，只用审核的离线插件，关闭网络验证和动态插件，不采外部文本/项目配置allowlist。
3. 将stdout/stderr、SDK debug、exception、header、UI事件、Artifact、诊断和模型入口接同一过滤链；不确定敏感内容拒绝外发。
4. 用不同切分点/编码/超长秘密/allowlist注释和检测器错误测试canary集合，记录范围与残余风险，不承诺100%识别。

**目标输出路径**

- `services/core/src/openbot/observability/redaction.py`

**正向验收**

secret过滤在模型、日志与artifact持久化之前，流式跨chunk处理；只保留必要诊断；合成canary覆盖所有出口；明确正则无法识别全部隐私，访问策略仍是首道边界。 网络验证关闭且有真实请求计数/拒绝证据；外部pragma allowlist secret等注释不能让测试secret通过。固定128字节窗口不构成通用保证，扫描阴性不降低SECRET/SENSITIVE分类。

**反例与禁止行为**

- 截断前后或分chunk的测试密钥不得出现在模型、普通日志和Artifact。
- 不得发送真实secret到第三方验证端点；不得让页面、日志或仓库allowlist控制出口，也不得以正则扫描通过替代egress。

**验证方法**

把密钥切成两chunk或嵌入JSON异常仍不泄漏；测试stdout、stderr、HTTP header、UI事件和导出。 构造任意分片、Unicode/编码、超过窗口长度、allowlist注入和联网验证canary，所声明规则均通过且探针无额外网络。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。
- redactor规则/长度/flush合同、网络验证禁用配置、canary矩阵及明确未覆盖风险。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第14、18–19、22–23页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-025

**实现首个云模型适配器**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Runtime · 规模 M

**需求** [RQ06](requirements_traceability.md#rq06)、[RQ07](requirements_traceability.md#rq07)

**前置依赖** OB-007、OB-008、OB-009、OB-023、OB-024、OB-037、OB-038、OB-039、OB-092

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。Provider格式差异可触发错误工具或泄漏上下文。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `model-openai`、`httpx`、`tiktoken`、`tenacity`、`litellm`、`model-runner`

**复用边界（reuse_notes）**

- 优先官方openai异步SDK+薄转换；显式关闭或统一管理SDK内建重试，禁止叠加tenacity；fake HTTP计数、流中断/取消/半包/usage缺失契约齐全。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 锁定首个云Provider与允许的SDK基础请求API/字段；首选官方openai薄适配，明确能力、错误和timeout映射。
2. 显式设置SDK max_retries=0并控制HTTP transport重试/环境代理，由OpenBot唯一管理有界重试；每次真实请求先reserve并通过egress。
3. 累积流到完整JSON/schema后仅返回ToolCall提案；禁自动runner、Provider托管执行工具、remote MCP与任意extra_body/extra_headers透传。
4. fake server验证429/503/中断/退避取消/首块后取消和usage不明，计数与预算一致后做受控真实smoke。

**目标输出路径**

- `services/core/src/openbot/providers/openai_compatible.py`

**正向验收**

首个真实云Provider通过统一模型网关，文本/工具/流式/usage/取消/超时有映射；完整JSON和schema通过前不派发；每次请求先经过出口策略与预算；compatible差异写能力表。 允许的SDK API白名单可检查；取消后新请求为0，半包丢弃不等于服务端未计费。固定版本支持的重试关闭项实测有效，不叠加tenacity。

**反例与禁止行为**

- 畸形/半包tool call不执行；Provider重试不能重放已执行工具。
- 官方SDK也不得自动执行函数、启用未纳管web search/remote MCP，或让外部内容覆盖endpoint/认证头；默认重试不能藏在Gateway账本外。

**验证方法**

fake server覆盖分片参数、畸形JSON、429、tool ID缺失、流中断；真实provider仅额外smoke。 可控服务器计数与SDK配置、Gateway attempt、预算三者一致；canary函数批准前调用为0；mock覆盖范围与真实smoke分别列出。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供至少一份实际声明平台/服务的受控集成证据及能力矩阵；mock结果单独列出，不能代替真实验证。
- SDK允许API/字段清单、显式重试/timeout/代理配置、实际HTTP尝试和usage记录。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第8–9、16、21–22页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-093

**验证首发OS的Supervisor与隔离后端能力**

阶段 M1 · 优先级 P0 · 状态 IN_PROGRESS · 能力域 Platform · 规模 M

**需求** [RQ01](requirements_traceability.md#rq01)、[RQ03](requirements_traceability.md#rq03)、[RQ05](requirements_traceability.md#rq05)、[RQ11](requirements_traceability.md#rq11)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-003、OB-004、OB-007、OB-008、OB-010、OB-089、OB-091

**先读设计** [02_architecture.md](../docs/02_architecture.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)

**风险** HIGH。wrapper名称掩盖原生能力差异、客户端退出后容器或子孙仍运行。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `profile-locks`、`windows-sys`、`processkit-process-wrap`、`ur-taking-me-with-you`、`service-manager`、`python-on-whales`、`command-group`

**复用边界（reuse_notes）**

- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。
- component_refs表示相关组件或被审查边界，不表示自动安装或已准入；按catalog类别和当前阶段执行。

**实施步骤**

1. 在首发OS选择一个原生进程实现和一个Docker隔离组合，记录实际版本/feature/权限；不新引command-group，不推断service-manager Windows具备User后端。
2. 确定profile唯一排他锁持有者并测试父子交接/独立启动，防父supervisor与daemon互相争锁自锁。
3. 测试实际进程创建/Job或对应OS控制、父/子孙/监督进程强杀、Job分配失败/逃逸与独立容器残留；记录归属id与清理证据。
4. 验证容器stop/wait→受限导出校验→remove，无法证实旧执行域失效则拒绝新dispatch；其他OS仍NOT_RUN，交OB-069—071完成资格。

**目标输出路径**

- `tests/components/native_poc`
- `native/supervisor/src/platform`
- `docs/evidence/backend-capabilities.md`

**正向验收**

首发OS原语成功与失败路径有可重复证据，profile锁无父子自锁；容器不依赖CLI存活，被登记的遗留执行域可核对与停止，无法确认时保持隔离。不支持的OS/backend路径明确CAPABILITY_UNAVAILABLE，不给通用crate全平台/100%保证。

**反例与禁止行为**

- 不得据processkit/service-manager等宣传宣称100%清理或三平台兼容；不能把杀掉docker客户端当成销毁容器，不能回退高权限或宿主执行。
- 禁止父子同时获取同一profile排他锁；service-manager不支持的Windows用户会话不得以系统服务代验。

**验证方法**

构造第二实例/父死/锁交接失败和多代子进程；Windows适用时核对挂起→入Job成功→恢复与失败不执行；kill容器CLI后单独核对容器最终状态和导出次序。

**必须提交的证据**

- OS/arch/版本、可重放命令、父子PID/容器id前后清单、失败样本与能力矩阵。
- 记录精确来源/版本、OS/架构/配置、测试命令与限制；本包只定义门禁，真实结果未实施前保持NOT_RUN。

**来源与修订依据**

U3《OpenBot 开源组件复用评估》PDF物理第4、12–14、18、23、25页提出复用方向；本任务为v1.2工程补足与修正，以docs_refs中设计及官方证据为准。

### OB-015

**实现单实例daemon和调度租约**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Runtime · 规模 M

**需求** [RQ01](requirements_traceability.md#rq01)、[RQ03](requirements_traceability.md#rq03)

**前置依赖** OB-003、OB-014、OB-093

**先读设计** [03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[02_architecture.md](../docs/02_architecture.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。双调度可重复执行已批准的危险动作。

**复用职责（reuse_type）** `native_primitive` · 原生原语适配

**关联组件（component_refs）** `profile-locks`、`windows-sys`

**复用边界（reuse_notes）**

- OS锁候选filelock/fd-lock等只能封装底层锁；profile唯一实例、epoch/fence/旧worker隔离自研。
- 实际OS、架构、backend和配置组合须独立提供证据；统一API、正常退出或进程组不能自动证明所有强杀与逃逸场景均可回收。

**实施步骤**

1. 由supervisor获取profile OS锁并生成runtime_epoch。
2. 实现单活动Task调度、claim租约、等待释放槽位和旧epoch拒绝。
3. 用双实例与失联worker场景验证唯一执行者边界。
4. 选定唯一profile排他锁拥有者及显式交接协议；父supervisor持锁时daemon验证受管身份而不重取同一锁，独立daemon启动路径另测。

**目标输出路径**

- `services/core/src/openbot/application/scheduler.py`
- `native/supervisor/src/instance_lock.rs`

**正向验收**

每profile默认一个活动Task和唯一daemon；runtime_epoch及fence拒绝陈旧提交；等待审批释放计算槽位；不能确认唯一实例或旧worker失效时不开始新执行。 OS锁原语只能证明持有关系，epoch与旧worker隔离仍自有；父子启动不会自锁。

**反例与禁止行为**

- 无法确认旧worker停止时不得凭租约超时开第二执行者。
- 禁止supervisor和daemon同时等待同一profile排他锁；租约到期不能单独证明旧进程已失效。

**验证方法**

两个daemon竞争只有一个获得实例锁；过期worker不能提交新状态；机器重启后可接管。 父子正常启动、第二实例、父死重启和锁交接失败均验证有界返回，不出现永久等待。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第14、21页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-016

**实现执行资源锁与会话排队**

阶段 M1 · 优先级 P0 · 状态 IN_PROGRESS · 能力域 Runtime · 规模 M

**需求** [RQ03](requirements_traceability.md#rq03)、[RQ05](requirements_traceability.md#rq05)、[RQ09](requirements_traceability.md#rq09)

**前置依赖** OB-015

**先读设计** [02_architecture.md](../docs/02_architecture.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)

**风险** HIGH。资源竞争会覆盖用户改动或操作错误页面。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** 无直接组件引用

**复用边界（reuse_notes）**

- 资源锁与UNKNOWN quarantine保持权威账本定义，库的进程内mutex不替代持久资源隔离。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 定义四类资源键、锁owner/epoch/fence和固定获取顺序。
2. 在单活动Task基线上实现等待、释放与重获后的版本核对。
3. 为人工审批和接管设计不长期持锁的释放点。

**目标输出路径**

- `services/core/src/openbot/application/resources.py`

**正向验收**

workspace、browser_profile、desktop_session与external_account资源键明确；MVP活动执行默认串行；锁不跨人工等待，恢复后重获并校验版本；未来并发需有序多锁。

**反例与禁止行为**

- 等待审批不得长期占DB事务或资源锁；同profile两个浏览器写动作不能并行。

**验证方法**

并发任务不互相覆盖文件或抢浏览器标签；取消/崩溃释放或安全回收锁；无无限饥饿。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第3、21页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-019

**实现执行前授权claim和再校验**

阶段 M1 · 优先级 P0 · 状态 IN_PROGRESS · 能力域 Security · 规模 M

**需求** [RQ03](requirements_traceability.md#rq03)、[RQ04](requirements_traceability.md#rq04)、[RQ05](requirements_traceability.md#rq05)

**前置依赖** OB-016、OB-017、OB-018、OB-031

**先读设计** [04_security_approvals.md](../docs/04_security_approvals.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)

**风险** CRITICAL。批准与派发之间的竞态可绕过用户决定。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** 无直接组件引用

**复用边界（reuse_notes）**

- claim及CLAIMED→DISPATCHING两短事务自研，取消/epoch/resource复核不变；任何库不得在第二事务提交前发外部请求。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. Broker首次执行检查未消费批准；恢复重试只有恢复器能发出同Operation的安全复用决定。两条路径均复验原授权期限、policy、actor/identity、cancel和resource，CONSUMED永不复活为APPROVED。
2. 首次claim短事务原子消费Approval、创建Attempt并进入CLAIMED；随后CLAIMED→DISPATCHING的第二短事务再次校验取消、runtime_epoch和resource，在持久化DISPATCHING后才允许发送。
3. dispatch token绑定本Attempt的固定dispatch_id、epoch、executor和资源；同Attempt重传保持ID，新Attempt生成新ID；Operation级provider_idempotency_key保持稳定，由worker ledger去重传输。
4. 通过并发claim、claim后取消/撤销、原授权到期和资源变化验证派发门禁，确保普通CLI/gateway/adapter不能冒充恢复器复用CONSUMED。

**目标输出路径**

- `services/core/src/openbot/application/dispatch.py`

**正向验收**

首次claim原子复验授权/任务/资源、消费Approval并创建Attempt，Operation进入CLAIMED；仅恢复器批准的同Operation安全重试可沿用匹配CONSUMED关系且不二次消费，仍复验期限、policy、actor/identity、cancel与resource。CLAIMED→DISPATCHING第二短事务再查取消、epoch和资源，提交成功才可派发。dispatch_id固定在Attempt，重传不变、新Attempt新ID；provider幂等键属于Operation。任何绑定条件变化都新建Operation重新审查。

**反例与禁止行为**

- 一个批准不得并发首次claim两次；CONSUMED不能退APPROVED、用于其他Operation或由普通客户端直接指定复用。
- 不能只在claim时检查取消/epoch/resource；DISPATCHING提交前已取消或资源失效必须零派发。
- 同Operation重试不能绕过原授权到期、身份撤销、policy变化或资源变化，不能通过刷新TTL延长原授权。

**验证方法**

对初次claim与恢复claim分别验证；在两事务之间插入取消、runtime_epoch变更和resource版本变化，断言无worker收到指令；并发首次claim最多一次消费；非法CONSUMED复用与原TTL/policy/actor/cancel/resource变化全部拒绝；检查Attempt级dispatch与Operation级provider幂等键。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。
- 保存claim与DISPATCHING两次事务的version/epoch/cancel/resource快照，以及恢复器判断来源和拒绝理由；不得以模型日志代替。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第3、21页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-020

**实现按副作用类型恢复**

阶段 M1 · 优先级 P0 · 状态 IN_PROGRESS · 能力域 Runtime · 规模 M

**需求** [RQ02](requirements_traceability.md#rq02)、[RQ03](requirements_traceability.md#rq03)

**前置依赖** OB-009、OB-015、OB-017、OB-019

**先读设计** [03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)

**风险** CRITICAL。错误恢复可能造成重复发送、覆盖或不可逆动作。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** 无直接组件引用

**复用边界（reuse_notes）**

- UNKNOWN/RECONCILING、证据核对、资源quarantine及唯一恢复器安全重试不变；人工文本success不能改账本，CONSUMED不退APPROVED。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 按docs/03检查唯一实例、schema和旧worker隔离，扫描权威Task/Operation/Attempt/Approval与dispatch ledger；未证明旧执行者失效就不接管派发。
2. 区分未派发CLAIMED与可能执行过的DISPATCHING，按retry_class查询receipt或进入UNKNOWN/RECONCILING；只有恢复器可以判断同Operation是否满足安全重试。
3. 安全重试沿用既有CONSUMED消费关系但永不退APPROVED、不二次消费；重新检查原期限、policy、actor/identity、cancel和resource。新Attempt使用新dispatch_id，保留operation_id与provider_idempotency_key；同Attempt重传才复用dispatch_id，派发前仍执行第二短事务检查。
4. 人工reconcile接口仅接收并保存带身份、来源、hash/ref的核对证据；由恢复器/OutcomeVerifier按证据规则作状态决定，不接受用户一句success或指定目标状态覆盖数据库。不能确认时继续UNKNOWN/RECONCILING。

**目标输出路径**

- `services/core/src/openbot/application/recovery.py`

**正向验收**

恢复扫描权威表并隔离旧epoch，区分CLAIMED与DISPATCHING/UNKNOWN，按retry_class核对。仅恢复器可允许同Operation复用已有CONSUMED grant，永不退APPROVED且每次复验原期限、policy、actor/identity、cancel及resource；条件变化需新Operation。新Attempt新dispatch_id、同Attempt重传ID不变，Operation级provider_idempotency_key保持不变；CLAIMED→DISPATCHING再次复验取消/epoch/resource。人工reconcile仅记录核对证据，状态变更由验证规则决定，不接受用户指定success覆盖账本；无充分证据继续UNKNOWN/RECONCILING。 未核对UNKNOWN持有相关资源quarantine，普通resume或新Task/Operation ID不得绕过；取消终态必须无在途或结果未知操作。

**反例与禁止行为**

- 未解决UNKNOWN不能被模型、用户一句“success”、HTTP目标状态参数或普通管理按钮直接改为SUCCEEDED/CANCELLED，也不能以“忽略”触发重发。
- CONSUMED不得退APPROVED、重复消费或供不同Operation使用；恢复器以外模块不得批准安全复用；原TTL/policy/actor/cancel/resource变化必须阻止复用。
- 同Attempt重传不能换dispatch_id，新Attempt不能复用旧dispatch_id，同Operation重试不能换provider幂等键；不具备核对语义的外部动作不得盲重发。

**验证方法**

逐崩溃点验证五类retry_class；测试原授权已到期、policy更新、actor撤销、取消、resource变化及无法隔离旧worker均拒绝安全重试。分别验证同Attempt重传与新Attempt ID关系、CONSUMED无回退。人工提交无证据success、伪造目标状态、重复证据或冲突receipt不得直接改账本；通过核验的证据保留审计来源。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。
- 提供恢复器安全重试决定、原grant全部复验字段、Attempt/dispatch/provider key关系，以及人工reconcile原始证据引用和验证决定；证明人工说明未直接覆盖权威状态。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第3、21页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-022

**实现取消和停止传播**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Runtime · 规模 M

**需求** [RQ03](requirements_traceability.md#rq03)、[RQ04](requirements_traceability.md#rq04)

**前置依赖** OB-014、OB-016、OB-019、OB-020

**先读设计** [03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。取消假成功会误导用户并继续产生外部效果。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** `sqlite3`、`aiosqlite`

**复用边界（reuse_notes）**

- 取消先落盘、派发前再查；库取消不等于效果撤回，仍可能UNKNOWN。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 持久化取消请求与revision，撤销未开始Operation及未消费批准。
2. 向运行worker传播取消并阻止所有后续dispatch。
3. 按剩余DISPATCHING/UNKNOWN进入核对或确定终态，保留已发生效果。
4. 取消写命令有稳定请求ID；caller超时/断连后先核对实际cancel_revision持久状态，不把等待取消当成撤销请求回滚。

**目标输出路径**

- `services/core/src/openbot/application/cancellation.py`

**正向验收**

cancel_requested_at和cancel_revision先持久化并阻止新dispatch；撤销未消费批准；有DISPATCHING/UNKNOWN时保持RECONCILING，仅完成核对后可标CANCELLED，过去效果不伪称回滚。 取消与CLAIMED→DISPATCHING第二短事务串行判定；该事务提交前已取消必须不发包，提交后只能如实核对并尽力停止在途动作。 commit已发生的取消继续阻断派发；未确认落盘不能谎报取消成功，重复API请求只核对/返回原幂等结果。

**反例与禁止行为**

- 运行中外部提交不能因为收到取消就显示已回滚；取消后的旧批准不能启动动作。
- claim之后尚未提交DISPATCHING的取消不能因“此前已claim”而被忽略。
- 不得因取消响应超时复活授权、重新发动作或宣称外部效果已经撤回。

**验证方法**

在规划、等审批、执行、结果提交同时取消；无新高风险动作启动；终态和残余效果明确。 在取消入队/commit前后断开客户端，重查取消版本并验证后续DISPATCHING复核一致。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第3、21页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-030

**实现数据库备份恢复与保留策略**

阶段 M1 · 优先级 P1 · 状态 TODO · 能力域 Runtime · 规模 M

**需求** [RQ02](requirements_traceability.md#rq02)、[RQ06](requirements_traceability.md#rq06)、[RQ11](requirements_traceability.md#rq11)

**前置依赖** OB-011、OB-012、OB-014、OB-020

**先读设计** [05_storage_api.md](../docs/05_storage_api.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。备份/清理错误会毁坏唯一任务与证据副本。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `sqlite3`

**复用边界（reuse_notes）**

- 使用SQLite backup接口；manifest/密钥排除/引用保留与恢复判定自研，不因库copy成功就宣称备份一致。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 使用SQLite backup或一致停写方案形成DB快照，取得并保持Artifact GC pin/retention保护，复制版本/配置和一致的引用manifest；不复制孤立db文件。
2. 校验Artifact实际hash/大小、备份范围、保留secret_ref但排除真实秘密的规则；完成验证后释放GC保护，失败备份保留可核对状态。
3. 恢复时先停止新dispatch，核验DB/Artifact、实例/授权/未决UNKNOWN及secret_ref可解析性；凭据失效进入显式重配置，不恢复秘密或重放未知动作。
4. 注入活跃写、并发GC、磁盘满、缺产物、失效secret_ref和迁移中断，验证恢复可查询、无悬空引用和无未批准效果。

**目标输出路径**

- `services/core/src/openbot/storage/maintenance.py`

**正向验收**

使用SQLite在线backup或一致停写备份；包含artifact manifest与版本，普通备份无凭据；磁盘配额/清理保护未完成任务和审批引用；M1完成基础恢复，M3跨平台实测。 在线backup不自动覆盖Artifact/凭据/外部效果；备份期间GC不能删除快照引用。失效秘密引用使对应能力不可用，UNKNOWN/DISPATCHING恢复仍需核对。

**反例与禁止行为**

- 不能漏WAL、把密钥写普通备份或清理被待审批Operation引用的产物。
- 不得仅凭backup API成功标记完整备份；恢复旧DB不得复活授权、忽略缺秘密或重复执行未知副作用。

**验证方法**

活跃写期间备份可恢复；磁盘满不会先执行再失败写intent；迁移失败可还原可用副本。 并发GC与备份交错、恢复缺失Artifact/钥匙串项以及含UNKNOWN库，核对manifest和实际执行次数。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。
- GC pin生命周期、快照/manifest校验、secret_ref失效与UNKNOWN恢复反例。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第7、20–21页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-033

**实现list read search文件工具**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Runtime · 规模 M

**需求** [RQ05](requirements_traceability.md#rq05)、[RQ06](requirements_traceability.md#rq06)

**前置依赖** OB-007、OB-019、OB-032、OB-092

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。读取与搜索既能泄漏数据也能耗尽资源。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `ripgrep`、`pathspec`、`encoding-detectors`

**复用边界（reuse_notes）**

- rg --json在受管快照/范围内受控调用，禁用户rg配置/危险链接与环境继承；UTF-8边界不因候选charset/binary包自动扩张；可不加ripgrepy。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 封装固定来源/摘要的rg二进制与结构化查询，显式--no-config、清理RIPGREP_CONFIG_PATH和代理/执行环境；不开放原始flags。
2. 用-e绑定pattern、--分隔受控路径，禁--pre及动态外部预处理；在受管快照和FileGuard范围内运行。
3. 分别限制深度、文件数、单文件、全局命中数/总字节/耗时；--max-count的按文件限制不代替全局上限。
4. 验证UTF-8、二进制/权限/无匹配/恶意配置和符号链接，输出路径/行/hash/provenance并经Artifact策略。

**目标输出路径**

- `services/core/src/openbot/tools/workspace/read.py`

**正向验收**

workspace.list/read/search有范围、深度、文件大小、时间和结果上限；UTF-8为MVP文本边界；返回路径/行号/hash/provenance，不把外部文件文字当指令。 MVP仍为UTF-8文本，不因encoding-detectors候选默认扩张或重写编码；ignore不授予根外权限。

**反例与禁止行为**

- 目录递归、regex或大文件不得无限占用资源；外部文件指令不得执行。
- --pre、用户rg配置和以--开头的查询不能导致任意参数或进程执行；不得自动装ripgrepy等不必要包装。

**验证方法**

大文件、二进制、权限错误、无匹配可解释；根外读取拒绝；结果上限不绕过Artifact策略。 恶意配置预处理器canary为0；海量小文件命中/超长行受全局限额约束，所有路径重新验证。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。
- 实际argv/最小env、二进制hash、全局限额与preprocessor拒绝证据。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第12、22页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-034

**实现补丁提议与受授权应用**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Runtime · 规模 M

**需求** [RQ04](requirements_traceability.md#rq04)、[RQ05](requirements_traceability.md#rq05)

**前置依赖** OB-007、OB-016、OB-019、OB-032、OB-033、OB-036、OB-092

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。编辑副作用可能造成用户数据丢失。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `unidiff`、`patch-ng`、`git-worktree`、`dulwich`

**复用边界（reuse_notes）**

- 解析库不写宿主；审批前冻结old/new hash和确切新字节Artifact，禁止审批后fuzz/换行修正，多文件依变更日志恢复。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 用unidiff解析或difflib生成展示Diff；patch-ng仅在通过支持子集PoC后可于受控暂存区变换，禁止直接充当宿主写入器。
2. 在审批前确定每个目标的旧hash、确切新字节Artifact/hash和变更manifest；解析后的路径、创建/删除/重命名支持范围均经FileGuard。
3. apply仅写入已绑定新字节并复验旧hash/资源/授权；审批后不再模糊匹配、纠正换行或重算新内容，保护用户已有修改。
4. 实现本任务自有最小提交journal及部分失败恢复，按文件受控原子替换，不依赖OB-035才能安全提交；OB-035后续复用和扩展。git worktree准备隔离或明确禁hooks/filter，绝不自动reset/commit/push。

**目标输出路径**

- `services/core/src/openbot/tools/workspace/patch.py`
- `services/core/src/openbot/tools/workspace/commit_journal.py`

**正向验收**

workspace.propose_patch只生成不可变Diff及确切新内容Artifact，不改用户原目录；workspace.apply_patch绑定旧文件hash、新内容hash、目标和工作树，批准后复验并按文件受控原子替换。默认受管快照/工作树，不自动commit/push；多文件可能部分提交，必须使用本任务自己的最小提交日志和部分恢复策略，OB-035复用并扩展语言验证/撤回策略，不能宣称跨文件原子性。

**反例与禁止行为**

- 多匹配或old hash变化必须拒绝；禁止git reset --hard、自动commit/push和覆盖用户改动。
- 不得将patch-ng apply返回true当安全提交证据，或批准后更改CRLF/fuzz匹配；多文件提交不能冒充单个文件系统原子事务。

**验证方法**

用户在审批间修改同文件时拒绝旧patch；多处匹配不猜；写中断恢复原文件或完整新文件。 旧hash变化、新Artifact变化、重复匹配、恶意路径、行尾改变和第二文件提交失败均检查实际文件与恢复记录；hook/filter canary不执行。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。
- 审批绑定的old/new hash、不可变新字节Artifact、逐文件提交/恢复manifest和具体解析库版本。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第12、17、22页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-040

**实现结构化进程执行协议**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Platform · 规模 M

**需求** [RQ03](requirements_traceability.md#rq03)、[RQ05](requirements_traceability.md#rq05)

**前置依赖** OB-007、OB-009、OB-019、OB-031、OB-038、OB-039

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。结构化argv不能阻止任意程序读写或触网。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** `ripgrep`、`git-worktree`

**复用边界（reuse_notes）**

- 容器/进程SDK不能增添未批准argv/env/mount/network；协议仍锁定输入、执行器、镜像与backend。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 定义不可变process执行计划和干净环境，不开放裸shell字符串。
2. 实现fake/受控worker通信、流式输出、timeout与取消结果映射。
3. 等待隔离后端通过后才启用真实代码执行，并记录快照和镜像digest。
4. 把rg --pre、Git worktree post-checkout、filters和其他配置驱动进程列为隐藏执行入口；适配器固定命令/参数/环境并经相同隔离策略。

**目标输出路径**

- `services/core/src/openbot/tools/executors/process.py`
- `contracts/schemas/dispatch.schema.json`

**正向验收**

process.run合同锁定可执行文件/argv、输入快照、backend、镜像digest、干净HOME/TMPDIR、env和资源限制；任意解释器、测试、构建和Git钩子均视为代码执行。 容器客户端与容器各有受管标识，停止前者不自动认定后者结束；实际镜像与网络/挂载能力纳入可查询结果。

**反例与禁止行为**

- pytest、python、npm或Git不能以“只读白名单”绕过隔离；失败不能自动加网或提权。
- 不得因动作名叫search/snapshot/lint就允许任意宿主程序或透传CLI参数。

**验证方法**

先用fake worker验证控制协议和输出洪泛；真实执行仅在OB-041隔离后端通过后开放；分别断言exit code、signal、timeout、取消与UNKNOWN。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第12–13、23页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-041

**实现worker隔离与资源上限**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Platform · 规模 M

**需求** [RQ04](requirements_traceability.md#rq04)、[RQ05](requirements_traceability.md#rq05)、[RQ06](requirements_traceability.md#rq06)

**前置依赖** OB-002、OB-016、OB-036、OB-040、OB-093

**先读设计** [04_security_approvals.md](../docs/04_security_approvals.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。隔离配置错误会把远程执行扩大为宿主权限。

**复用职责（reuse_type）** `native_primitive` · 原生原语适配

**关联组件（component_refs）** `python-on-whales`、`podman-nerdctl`、`bubblewrap`

**复用边界（reuse_notes）**

- 容器backend逐组合认证；容器归属独立于CLI，stop/wait→受限导出校验→remove，无自动host/引擎兜底。
- 实际OS、架构、backend和配置组合须独立提供证据；统一API、正常退出或进程组不能自动证明所有强杀与逃逸场景均可回收。

**实施步骤**

1. 通过OB-093先认证一个Docker后端，python-on-whales或受控CLI择一；固定引擎/镜像digest/挂载/网络/资源与非root/drop-capabilities配置。
2. Broker登记容器ID/标签与profile/Operation/Attempt/epoch归属，输入只读、独立输出；host端控制接口不进入不可信容器。
3. 完成或取消时先stop仍运行容器并wait确认，再经限额/类型/路径/链接/权限检查导出Artifact，最后remove；不让auto-remove先删证据。
4. 分别验证客户端死亡、容器存活、恶意导出和恢复清理；Podman/nerdctl/bubblewrap不自动兜底，缺已验证backend返回CAPABILITY_UNAVAILABLE。

**目标输出路径**

- `services/core/src/openbot/tools/executors/sandbox.py`
- `native/supervisor/src/worker_control.rs`

**正向验收**

默认受控容器以非root、drop capabilities、无privileged/宿主socket、只读输入快照、独立输出区、资源上限和默认禁网执行；无后端就返回CAPABILITY_UNAVAILABLE，不回退宿主机。 容器生命周期独立于CLI；导出在已停止/wait后进行，校验成功或按已记录失败处理后remove。POSIX权限和Windows ACL按平台验证，不能统一chmod替代。

**反例与禁止行为**

- 禁止privileged、Docker socket、宿主全HOME和无后端自动host回退。
- 不得仅kill docker CLI就标worker回收完成；不得导入符号链接/路径穿越/特殊文件或删除未登记用户容器。

**验证方法**

容器无secret/宿主socket；越界文件和非授权网络失败；无已验证隔离环境时相关动作返回CAPABILITY_UNAVAILABLE，不进入宿主执行模式。 kill客户端后检查容器仍否存活，随后按登记ID停止、wait、导出验证、remove；恶意tar/link/权限与缺backend反例可重复。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。
- backend能力记录、实际容器ID/标签及完整stop→wait→export校验→remove时序、恶意导出拒绝证据。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第12–13、17、23页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-035

**实现显式语言验证与修改事务**

阶段 M1 · 优先级 P1 · 状态 TODO · 能力域 Runtime · 规模 M

**需求** [RQ05](requirements_traceability.md#rq05)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-034、OB-041、OB-092

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。自动回滚或验证脚本可能破坏用户状态或执行任意代码。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `tree-sitter`、`tree-sitter-language-pack`、`git-worktree`

**复用边界（reuse_notes）**

- 只用固定grammar/原生资产，安装期预置、禁网首次parse；独立有界worker承受native解析风险。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 只选择明确支持语言的tree-sitter/grammar并锁定原生资产版本/hash；检查language-pack所选版本的按需下载，安装期预置、运行期禁止下载和任意workspace grammar。
2. 在受资源/时间/输入/输出限制的独立parser worker解析；native崩溃或深嵌套只影响worker，不破坏daemon/审批账本。
3. ruff/mypy/pytest/tsc及项目配置插件、Git hooks/filter均视为代码执行，走已准入隔离process.run；无backend不能宿主兜底。
4. 多文件变更用已批准新字节manifest与恢复记录，仅撤回本Operation变更；语法树无ERROR/lint通过不等于功能正确。

**目标输出路径**

- `services/core/src/openbot/tools/workspace/validation.py`

**正向验收**

仅对已支持语言做显式语法/静态验证；验证脚本也走隔离执行；多文件变更有manifest与本次变更撤回策略，不把lint成功等同于功能正确。 干净安装首次真实parse在禁网环境成功；未安装语言明确不可用，native parser资产可对应release清单。

**反例与禁止行为**

- lint通过不能标功能正确；验证失败不能无条件恢复整个仓库。
- 不得因为不执行目标语言就把任意native grammar放入可信daemon；不得在首次parse偷偷下载parser或加载工作区提供的二进制。

**验证方法**

两个文件中后一个验证失败时不会丢掉用户修改；验证命令自身走进程权限策略。 超大/深嵌套/畸形输入、native崩溃/超时、缺grammar及多文件第二项失败有实际隔离和恢复证据。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。
- 实际加载grammar文件hash、禁网首次parse、worker故障和多文件恢复记录。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第12、17、22页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-042

**实现worker进程树取消与回收**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Platform · 规模 M

**需求** [RQ01](requirements_traceability.md#rq01)、[RQ05](requirements_traceability.md#rq05)、[RQ11](requirements_traceability.md#rq11)

**前置依赖** OB-003、OB-022、OB-040、OB-041、OB-093

**先读设计** [02_architecture.md](../docs/02_architecture.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。孤儿worker可能继续未授权动作或占用资源。

**复用职责（reuse_type）** `native_primitive` · 原生原语适配

**关联组件（component_refs）** `windows-sys`、`processkit-process-wrap`、`ur-taking-me-with-you`、`command-group`、`python-on-whales`

**复用边界（reuse_notes）**

- 仅封装原生原语；command-group不新用。核验Job/进程组/容器最终状态，强杀与协作清理边界明确。
- 实际OS、架构、backend和配置组合须独立提供证据；统一API、正常退出或进程组不能自动证明所有强杀与逃逸场景均可回收。

**实施步骤**

1. 实现受管worker/容器归属和epoch/PID身份；选择一个获准process-wrap/processkit类封装或最小原生实现，command-group不新引入。
2. Windows用挂起创建→Job分配成功→恢复，禁止breakaway逃逸；Linux/macOS按实测cgroup/进程组/监督能力描述限制。
3. graceful后强制清理并核验子孙最终状态；容器按登记ID独立stop/wait、导出校验与remove，不能仅清理CLI。
4. 测试daemon/supervisor/worker强杀、子孙、容器残留、PID复用和UI退出；无法确认旧执行域失效时保持quarantine并拒绝新dispatch。

**目标输出路径**

- `native/supervisor/src/process_tree.rs`
- `services/core/src/openbot/tools/executors/supervision_port.py`
- `tests/integration/platform`

**正向验收**

用户级supervisor按实际OS能力监督worker；Windows Job、Linux可用cgroup/进程组、macOS相应受控进程组/监督逻辑均有边界说明；graceful后强制清理，UI退出不停止daemon。 每个清理对象有最终状态或无法确认的证据；pipe EOF/Drop只作为有限协作机制，不宣称100%清理。

**反例与禁止行为**

- 单纯Python finally/pipe EOF不能作为强制死亡后的唯一清理保证。
- 不得以统一crate API、父PID退出或lease到期替代真实OS隔离证据；不能误杀未登记进程/容器。

**验证方法**

派生子孙进程、daemon崩溃、worker挂死均有原生OS验证；UI关闭不杀daemon。 原生平台记录创建顺序、Job分配失败、进程组逃逸/强杀和独立容器残留，确认失败时不开新执行。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。
- OS/arch/原语版本，PID身份/Job/容器归属与前后进程树清单及清理失败决定。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第13–14、18、23页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-044

**实现消息发送用例与受控适配端口**

阶段 M1 · 优先级 P1 · 状态 TODO · 能力域 Security · 规模 M

**需求** [RQ03](requirements_traceability.md#rq03)、[RQ04](requirements_traceability.md#rq04)、[RQ06](requirements_traceability.md#rq06)

**前置依赖** OB-017、OB-018、OB-019、OB-020、OB-037、OB-043

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[07_feishu.md](../docs/07_feishu.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)

**风险** CRITICAL。外部发送通常不可撤回且可能泄露数据。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** `lark-oapi`

**复用边界（reuse_notes）**

- 发送用例仍由Broker批准并判UNKNOWN；SDK只实现transport，M1 fake/M2真实启用次序不变。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 实现发送用例与受控transport端口，绑定草稿和稳定目的地。
2. 接入审批、dispatch、receipt与RECONCILE_ONLY默认语义。
3. 先fake验证成功后断连，真实adapter通过M2验证再启用。

**目标输出路径**

- `services/core/src/openbot/tools/messages/send.py`

**正向验收**

message.send绑定草稿hash、destination account和稳定recipient；走独立外发审批；fake transport先证明receipt/UNKNOWN语义，真实平台发送到M2经对应适配器验证后才启用。

**反例与禁止行为**

- 未知发送结果不能自动重发；普通owner进度授权不能复用为第三方发送授权。

**验证方法**

fake服务覆盖错收件人、旧草稿、成功后断连和重复请求；无已验证发送适配器时CAPABILITY_UNAVAILABLE；owner进度通知不复用第三方发送授权。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第9–10页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-081

**在M1实现认证本地HTTP与SSE控制API**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Desktop · 规模 M

**需求** [RQ04](requirements_traceability.md#rq04)、[RQ06](requirements_traceability.md#rq06)、[RQ10](requirements_traceability.md#rq10)

**前置依赖** OB-006、OB-008、OB-014、OB-018、OB-020、OB-022、OB-031、OB-038、OB-039、OB-092

**先读设计** [02_architecture.md](../docs/02_architecture.md)；[05_storage_api.md](../docs/05_storage_api.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。该API是所有客户端入口，若后置会诱发各通道绕过内核。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `fastapi-stack`、`pydantic-jsonschema`

**复用边界（reuse_notes）**

- FastAPI/Uvicorn/sse-starlette按M1需求择准入；认证、scope、Host/Origin、API用途、SSE一致性/背压/取消仍自有，proxy头不能绕过loopback。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. M1先实现loopback HTTP、认证scope、Host/Origin/profile/体积限制及受保护token交接。
2. 按application端口提供health/tasks/approvals/cancel/resume/reconcile与SSE，gateway使用独立内部scope。
3. 验证幂等冲突、version CAS、跨源拒绝、事件断点与保留期410；CLI和gateway据此接入。 reconcile只接收证据而非受信结果状态；禁止客户端指定grant恢复许可。
4. FastAPI/Uvicorn和按需SSE库只提供传输原语；禁宽泛CORS/隐式proxy信任，限定body/速率/事件队列；测试断开连接时writer实际提交和SSE取消/背压。

**目标输出路径**

- `services/core/src/openbot/adapters/local_api`
- `contracts/openapi.yaml`
- `tests/contracts/local_api`
- `tests/security/local_api`

**正向验收**

M1提供loopback HTTP、Host/Origin校验、profile绑定、限额和受保护token交接；最小health/tasks/events/approvals/cancel/resume/reconcile供CLI和gateway使用；内部gateway接口scope独立。 审批查询使用独立ApprovalPreview，SECRET不在任何预览暴露；本地challenge端点仅限有效PENDING和owner范围，gateway不能获取；OperationSnapshot提供Operation.version；KEEP_UNKNOWN可无新增证据，确认结果需可追踪证据；证据导入只接收受限文件内容，不接受宿主路径。 Host/Origin/profile/scope由OpenBot判定；未知/远程refs与重复JSON键拒绝。after_seq与Last-Event-ID冲突拒绝，保留期外410后客户端取快照。

**反例与禁止行为**

- 不得匿名暴露任务/审批或允许WebView持广域token；不允许UI/CLI/gateway直开SQLite。
- reconcile API不得接受用户指定SUCCEEDED/CANCELLED覆盖Operation账本；仅保存证据并交恢复器/OutcomeVerifier判断，客户端不能授权CONSUMED复用。
- 不得让框架Dependency/客户端断连替代持久事务和授权结果；proxy头不能把非loopback请求伪装本地owner。

**验证方法**

跨源网页、非loopback网络、错误profile、失效token、越权scope、旧version、同幂等键不同payload均拒绝；CLI与gateway不得直连DB；SSE断点与410恢复可重复。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。
- 实际监听/Host/Origin/proxy与scope反例、writer断连重查、SSE游标/背压测试。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第6–7、22页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-028

**提供CLI任务和审批操作**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Platform · 规模 M

**需求** [RQ10](requirements_traceability.md#rq10)

**前置依赖** OB-008、OB-014、OB-018、OB-020、OB-022、OB-081、OB-092

**先读设计** [05_storage_api.md](../docs/05_storage_api.md)；[02_architecture.md](../docs/02_architecture.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。本地管理入口也可能成为授权绕过路径。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `cli-toolchain`、`httpx`

**复用边界（reuse_notes）**

- Typer/Rich/httpx可复用；命令语义和审批预览不变，只有认证API访问，无SQLite旁路，JSON输出可稳定测试。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 实现CLI配置与受保护本地API会话连接。
2. 提供task/approval/cancel/resume/reconcile与稳定JSON输出。
3. 覆盖无daemon、认证失败、版本冲突和等待核对的用户路径。
4. 用Typer/Rich/httpx薄适配；稳定JSON输出与人类视图分离，转义外部ANSI/富文本控制，受控代理/超时/取消不导致新动作或重复批准。

**目标输出路径**

- `apps/cli`
- `tests/integration/cli`

**正向验收**

CLI通过认证本地HTTP API创建/查看/取消/恢复任务、查看审批及提交决定、核对UNKNOWN；JSON与人类输出稳定；不直连SQLite或绕过application。 依赖仅负责命令解析、呈现和HTTP；外部日志/路径不能注入终端控制或被当作命令。

**反例与禁止行为**

- CLI不能打开SQLite绕过policy；没有证据不能提供ignore-and-rerun未知动作选项。
- reconcile命令只提交核对证据，不提供force-success或复活CONSUMED的客户端开关。
- 不得把富文本/ANSI输入直接渲染为可执行或伪造审批提示；CLI不得凭等待超时宣称动作未执行。

**验证方法**

无飞书和UI也能运行整条fake任务；错误返回码稳定；approve仅由本地受信用户接口可调用。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第14、22页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-029

**交付首条持久化垂直切片**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 QA · 规模 M

**需求** [RQ02](requirements_traceability.md#rq02)、[RQ03](requirements_traceability.md#rq03)、[RQ04](requirements_traceability.md#rq04)、[RQ10](requirements_traceability.md#rq10)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-010、OB-020、OB-021、OB-022、OB-023、OB-025、OB-028、OB-036、OB-041、OB-042

**先读设计** [03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[05_storage_api.md](../docs/05_storage_api.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。没有首个闭环证据会使后续适配器建立在未验证核心上。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `sqlite3`、`rfc8785`

**复用边界（reuse_notes）**

- 完整M1 API/权限/Artifact/真实受限执行集成不变；OB-091承担早期MockWorker协议PoC，演示仍可FakeProvider/OFFLINE。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 保留完整M1 CLI/认证API/application/权限/产物链路；演示使用FakeProvider和受控测试数据，默认OFFLINE且无需真实租户/模型密钥。
2. 在首发已验证backend执行真实受限文件/进程效果，另用fault executor制造外部成功但本地回执丢失；两类证据分开。
3. 演示审批、一次有效dispatch、结果/outbox、取消与资源隔离；在规定提交点崩溃重启并重查稳定请求ID。
4. 复用OB-091早期反例并提供真实本地端口/Artifact/隔离路径结果；不能用M0 PoC或全MockWorker代替完整M1门禁。

**目标输出路径**

- `tests/integration/scenarios/first_vertical_slice`
- `docs/demos/m1.md`

**正向验收**

CLI→认证API→持久Task→fake模型提案→policy/审批→fake可验证效果→结果/outbox构成可重启切片；默认OFFLINE，无真实租户或模型密钥也能演示。 OB-091只负责早期协议PoC；本任务必须同时给出实际本地API、Artifact、受控文件与隔离worker的集成证据。真实模型/飞书能力仍由对应适配任务另验。

**反例与禁止行为**

- 演示不得调用真实生产服务；fake通过不能声称真实飞书/模型/平台已验证。

**验证方法**

相同场景覆盖5个崩溃点与重复输入；人工演示给出命令、预期状态和验收证据。 记录真实本地效果和fault executor计数各自的证据，不混成生产服务成功；原有全部前置依赖保留。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。
- 真实本地受限效果、Artifact hash、worker/container归属与stop/wait/导出/回收证据。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第26页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-045

**交付安全工具威胁回归**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 QA · 规模 M

**需求** [RQ03](requirements_traceability.md#rq03)、[RQ04](requirements_traceability.md#rq04)、[RQ05](requirements_traceability.md#rq05)、[RQ06](requirements_traceability.md#rq06)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-029、OB-031、OB-032、OB-034、OB-037、OB-039、OB-041、OB-042

**先读设计** [04_security_approvals.md](../docs/04_security_approvals.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。未验证的强制边界不能进入远程运行。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `rfc8785`、`ripgrep`、`git-worktree`、`detect-secrets`

**复用边界（reuse_notes）**

- 在M1加入导入联网、嵌套修改、隐式重试、非法refs、rg/git配置、parser下载与后端清理失败的可验证用例。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 把M1每个安全/恢复不变量变成固定攻击与故障语料。
2. 断言实际文件、进程、网络、secret与副作用次数，而非模型文字。
3. 接入PR必跑门禁并保存失败复现方法。
4. 把组件引入的新边界反例加入相应M1必跑集合：深层变异/JCS、writer取消、隐藏SDK执行/重试、rg/Git配置、parser下载、scanner验证与backend残留。

**目标输出路径**

- `tests/security`
- `docs/demos/m2.md`

**正向验收**

M1即运行路径、注入、授权竞态、secret、输出洪泛、隔离与恢复回归；用真实文件/进程/网络效果断言；不把安全测试延后至M3发布。 以实际网络/进程/文件/请求计数证明门禁，不要求所有后期真实组件提前安装；后期SDK随接入复用同合同。

**反例与禁止行为**

- 安全用例失败不得通过放宽policy、删除断言或mock掉实际效果来解决。
- 不得把未安装的M2/M3组件伪报测试通过，或通过删除边界检查让复用库更易接入。

**验证方法**

所有必阻断case均无未授权副作用；不能以模型是否拒绝的文本作为通过证据。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第7–14、20–23页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-046

**发布最小本地Alpha边界说明**

阶段 M1 · 优先级 P0 · 状态 TODO · 能力域 Lead · 规模 S

**需求** [RQ01](requirements_traceability.md#rq01)、[RQ05](requirements_traceability.md#rq05)、[RQ10](requirements_traceability.md#rq10)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-029、OB-033、OB-034、OB-040、OB-041、OB-045

**先读设计** [00_scope.md](../docs/00_scope.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。阶段命名不准确会掩盖尚未验证的危险能力。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** 无直接组件引用

**复用边界（reuse_notes）**

- 本地Alpha报告列出启用的精确组件/资源、未支持backend与残余风险；不把候选列表当已实现能力。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 按M1范围准备本地原型演示和能力清单。
2. 从空配置用CLI和mock完成读/提案/审批/隔离测试与重启。
3. 记录未支持能力及下一阶段依赖，作为M2入口门禁。
4. Alpha验收列精确启用组件/资产/OS/backend、准入证据和未支持项；解释OB-091早期PoC与OB-029完整M1证据差异。

**目标输出路径**

- `docs/releases/local-prototype-acceptance.md`
- `tests/integration/scenarios/local_prototype`

**正向验收**

CLI可经认证API完成读文件、补丁提议、批准应用和隔离测试；mock/OFFLINE演示可运行；声明试点OS和未支持能力；完整MVP还需M2/M3。 任何NOT_RUN候选不列为已支持；复用收益只报告测量/范围，不写固定LOC/耗时/安全保证。

**反例与禁止行为**

- 未验证平台、真实飞书或完整MVP不得在原型说明中写成已完成。

**验证方法**

从空配置按文档跑通一次任务；生成版本化能力报告和已知限制清单。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第19–26页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。


## M2 飞书远程闭环

### OB-047

**核验飞书真实租户协议与权限**

阶段 M2 · 优先级 P0 · 状态 BLOCKED · 能力域 Integration · 规模 M

**需求** [RQ08](requirements_traceability.md#rq08)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-004、OB-006、OB-008、OB-092

**先读设计** [00_scope.md](../docs/00_scope.md)；[02_architecture.md](../docs/02_architecture.md)；[05_storage_api.md](../docs/05_storage_api.md)；[07_feishu.md](../docs/07_feishu.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。协议误读会导致授权回调失效和静默断连。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `lark-oapi`

**复用边界（reuse_notes）**

- 真实租户协议+锁定lark SDK的可重放样例；核验实际callback/传输/权限/时限，测冷启动与阻塞行为，不照抄24.27秒或固定超时。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 在专用测试自建应用确认所需权限与消息/callback字段。
2. 捕获脱敏样例、SDK版本、ACK方式和错误返回。
3. 用样例建立adapter contract，记录卡片与token真实限制。
4. 在独立进程对锁定lark SDK做导入/凭据/发现/握手/ready分段测量，核对当前版阻塞/timeout与回调形状；修复需基于所选版本证据。

**目标输出路径**

- `docs/integrations/feishu-contract.md`
- `tests/fixtures/feishu`

**正向验收**

真实自建应用核验消息事件、卡片callback、app/tenant/operator身份和最小权限；保存脱敏payload与SDK版本；该任务研究协议，授权权威仍在daemon。 不用固定24.27秒、固定模块数或历史Issue推导本机超时；普通卡/回调权限与实际更新时限有官方和真实租户依据。

**反例与禁止行为**

- 不得把HTTP响应样例直接当WebSocket回调合同，或把未经核实Issue当当前行为。
- 不得盲patch私有方法或强制线程预热作为万能修复；不得把WebSocket ACK与HTTP callback响应混同。

**验证方法**

样例脱敏可回放；不混淆HTTP响应和WebSocket SDK回调返回；不把未知Issue直接当需求事实。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供至少一份实际声明平台/服务的受控集成证据及能力矩阵；mock结果单独列出，不能代替真实验证。
- 所选SDK版本、脱敏真实payload、分段时序和当前缺陷/上游修复证据。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第9–10、16、23页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-048

**实现安全配对与owner撤销**

阶段 M2 · 优先级 P0 · 状态 TODO · 能力域 Security · 规模 M

**需求** [RQ04](requirements_traceability.md#rq04)、[RQ08](requirements_traceability.md#rq08)、[RQ10](requirements_traceability.md#rq10)

**前置依赖** OB-002、OB-008、OB-013、OB-018、OB-047、OB-081

**先读设计** [04_security_approvals.md](../docs/04_security_approvals.md)；[07_feishu.md](../docs/07_feishu.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)

**风险** CRITICAL。配对是远程执行权限的入口。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** `nanobot`

**复用边界（reuse_notes）**

- 只参考配对展示；本地challenge、待确认tenant/app/user与owner授权自有，不复制上游first-user/二维码自动授权。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 本地API/CLI生成短TTL限次挑战并绑定profile/app/tenant。
2. gateway转发远端claim，daemon仅保存待确认身份。
3. 本地确认后授权owner，实现撤销和epoch更新。

**目标输出路径**

- `services/core/src/openbot/policy/pairing.py`
- `services/feishu_gateway/src/openbot_feishu/pairing.py`
- `apps/cli`

**正向验收**

本地认证用户发起短时一次性随机挑战；飞书回传只形成待确认身份；本地展示tenant/app/user后确认owner；nonce限次、防重放、撤销提升identity_epoch。

**反例与禁止行为**

- 第一个远端消息人不得自动成为owner；旧二维码、跨租户claim和撤销身份须拒绝。

**验证方法**

偷看旧码、跨租户、重复claim、被撤销owner无法创建或批准任务；首次配对有本地确认。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第10、23页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-049

**实现飞书WebSocket入站适配**

阶段 M2 · 优先级 P0 · 状态 TODO · 能力域 Integration · 规模 M

**需求** [RQ02](requirements_traceability.md#rq02)、[RQ08](requirements_traceability.md#rq08)、[RQ10](requirements_traceability.md#rq10)

**前置依赖** OB-013、OB-047、OB-048、OB-081

**先读设计** [02_architecture.md](../docs/02_architecture.md)；[05_storage_api.md](../docs/05_storage_api.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[07_feishu.md](../docs/07_feishu.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。接入越权会直接暴露本地执行能力。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `lark-oapi`、`httpx`

**复用边界（reuse_notes）**

- 用lark-oapi协议能力；独立gateway、单消费者、受限HTTP/inbox ACK边界不变，SDK升级受契约fixture保护。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 实现单gateway SDK连接和消息规范化。
2. 通过内部scope调用daemon inbox用例，持久化成功后ACK。
3. 默认拒绝群聊执行、陌生身份与超限附件，并记录去重结果。
4. 以lark-oapi承担握手/帧解析/事件类型，转换到自有Port；实际子进程环境和scope最小化，阻塞回调不进入daemon主循环。

**目标输出路径**

- `services/feishu_gateway/src/openbot_feishu/inbound.py`

**正向验收**

单活动gateway转换协议并通过范围受限内部HTTP接口交daemon；owner权限由daemon校验；入站持久提交后才ACK；默认禁用群聊执行，不在SDK回调中调模型。 SDK内部消息队列不拥有Task/owner/去重权威，协议升级需要重放脱敏fixture。

**反例与禁止行为**

- gateway不能自己决定owner或直开SQLite；回调线程不能等待LLM。
- 不得重写不必要WebSocket协议或借SDK默认行为绕过inbox提交后的ACK规则。

**验证方法**

重复与乱序事件不重复创建任务；陌生sender、其他租户、附件超限被拒绝；ACK延迟单独记录。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第9–10、23页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-050

**实现飞书审批callback处理**

阶段 M2 · 优先级 P0 · 状态 TODO · 能力域 Integration · 规模 M

**需求** [RQ04](requirements_traceability.md#rq04)、[RQ08](requirements_traceability.md#rq08)

**前置依赖** OB-018、OB-019、OB-047、OB-048、OB-049

**先读设计** [04_security_approvals.md](../docs/04_security_approvals.md)；[05_storage_api.md](../docs/05_storage_api.md)；[07_feishu.md](../docs/07_feishu.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。审批callback是跨网络授权的关键边界。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `lark-oapi`

**复用边界（reuse_notes）**

- card callback适配到daemon CAS；所有拒绝/超时/异常返回合法且及时，禁止等待模型/工具或库内队列旁路批准。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 映射真实callback operator、app/tenant、卡片上下文和opaque approval ID。
2. 调用daemon审批用例并返回真实CAS结果的简短响应。
3. 验证重放、并发点击、数据库延迟和旧卡，持久唤醒不靠内存。
4. 为选定SDK的合法成功/拒绝/过期/数据库忙回调建立fixture，在剩余deadline内同步返回，不把未确认commit映射为批准成功。

**目标输出路径**

- `services/feishu_gateway/src/openbot_feishu/approval_callback.py`
- `services/core/src/openbot/application/approval_use_case.py`

**正向验收**

gateway转发真实operator和卡片上下文；daemon核验身份/nonce/binding并CAS、持久唤醒；同步回调仅回简短状态，不以内存queue或文本is_owner授权。 回调实际operator经daemon校验；未来SDK返回结构变化须先通过合同测试。

**反例与禁止行为**

- 提交失败不得回复已批准；action.value中伪造身份与已取消Task旧卡必须拒绝。
- 不得等待模型/worker或仅凭卡片payload中的owner字段放行。

**验证方法**

并发点击与超时再点安全；已取消任务旧卡无效；数据库阻塞时不谎报批准成功。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第9–10、23页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-054

**实现网关健康探测与重连**

阶段 M2 · 优先级 P0 · 状态 TODO · 能力域 Integration · 规模 M

**需求** [RQ01](requirements_traceability.md#rq01)、[RQ08](requirements_traceability.md#rq08)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-009、OB-021、OB-049

**先读设计** [02_architecture.md](../docs/02_architecture.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[07_feishu.md](../docs/07_feishu.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。静默断连会使远程助手不可用并隐藏任务状态。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `lark-oapi`、`httpx`、`tenacity`

**复用边界（reuse_notes）**

- 先检查选定SDK是否仍有问题；通过支持的timeout/session扩展或受控最小补丁处理；初始化与ready时限分开，独立进程watchdog能收回阻塞实例。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 分别限制SDK初始化/发现/连接/读取/业务ready，按所选版本优先采用上游修复；必要窄补丁记录commit/diff和退出条件。
2. 在可能阻塞的gateway进程之外运行hard-deadline监督，内部heartbeat只提供观测；空闲无业务消息不视作故障。
3. 按jitter有界退避重建，先确认旧实例退出再建立新消费者；SDK/HTTP层不得叠加不可见重试。
4. 注入DNS停滞/TCP半开/SDK阻塞/休眠，确认审批/取消不受阻、每次重建有记录且只有一个活动gateway。

**目标输出路径**

- `services/feishu_gateway/src/openbot_feishu/health.py`

**正向验收**

gateway独立健康、连接/读取deadline、heartbeat与带jitter退避可见；空闲无消息不算失联；daemon监督重启网关不产生第二消费者；阻塞SDK不拖慢审批/取消。 不同计时路径单独测量；同一个被阻塞的事件循环中的watchdog不能充当硬截止保证。

**反例与禁止行为**

- 空闲无消息不能自动判死；重连不得占住daemon writer或审批线程。
- 不得单靠asyncio.wait_for或线程预热声称能中断阻塞SDK；不能为更快恢复同时连接两个消费者。

**验证方法**

DNS停滞/TCP半开/断网/休眠恢复后可重连；不要求空闲消息出现；重连可观测。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。
- 外部监督时序、旧进程退出证据、SDK配置/补丁差异和实际重试次数。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第9、23页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-055

**实现死信检视与安全重投**

阶段 M2 · 优先级 P1 · 状态 TODO · 能力域 Integration · 规模 M

**需求** [RQ03](requirements_traceability.md#rq03)、[RQ08](requirements_traceability.md#rq08)、[RQ10](requirements_traceability.md#rq10)

**前置依赖** OB-013、OB-020、OB-021、OB-049、OB-054

**先读设计** [05_storage_api.md](../docs/05_storage_api.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[07_feishu.md](../docs/07_feishu.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)

**风险** HIGH。人工恢复入口可能绕过正常幂等保护。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** 无直接组件引用

**复用边界（reuse_notes）**

- 死信/通知重投通过application，不让SDK/tenacity重播UNKNOWN业务副作用。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 存dead-letter原因、attempt、任务关联及远端结果状态。
2. 通过受限API提供查看、丢弃和条件重投。
3. 将通知重投与业务Operation核对严格区分。

**目标输出路径**

- `services/feishu_gateway/src/openbot_feishu/dead_letter.py`

**正向验收**

dead letter有原因、attempt与关联Task；检查、丢弃和重投通过受限application/API；通知重投不重执行业务；UNKNOWN副作用必须先reconcile。

**反例与禁止行为**

- dead letter操作不能删除未核对副作用或把UNKNOWN作为普通重试。

**验证方法**

拒绝重放未知副作用动作；通知死信重发只影响通知；跨owner不可读取死信。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第3、9–10页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-094

**审查飞书模板的最小源码复用**

阶段 M2 · 优先级 P1 · 状态 TODO · 能力域 Integration · 规模 S

**需求** [RQ08](requirements_traceability.md#rq08)、[RQ11](requirements_traceability.md#rq11)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-004、OB-047、OB-089、OB-092

**先读设计** [07_feishu.md](../docs/07_feishu.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)

**风险** MEDIUM。模板夹带Agent/owner/消息队列执行逻辑，许可证或归属记录不完整。

**复用职责（reuse_type）** `source_review` · 源码参考/摘取审查

**关联组件（component_refs）** `nanobot`、`langbot`

**复用边界（reuse_notes）**

- 默认REFERENCE_ONLY；比较后可给出NO_COPY及理由。只有选择有限摘取时才要求固定commit/path/hash、LICENSE/NOTICE、差异和回归，禁止整仓导入。
- component_refs表示相关组件或被审查边界，不表示自动安装或已准入；按catalog类别和当前阶段执行。

**实施步骤**

1. 对候选nanobot/LangBot的具体目标文件作收益/维护/边界比较；若考虑摘取，核实精确commit、文件许可证、依赖和副作用。
2. 形成明确NO_COPY或有限摘取决定。NO_COPY只需比较依据与理由，不创建vendor目录或安装上游框架；普通卡实现仍由OB-051负责。
3. 只有选择摘取时才保留commit/path/hash、LICENSE/NOTICE、本地diff、维护人与回归；只复制纯构造/展示，不复制owner/消息执行循环。

**目标输出路径**

- `docs/evidence/source-reuse-feishu.md`
- `components/source-reuse/feishu.json`

**正向验收**

NO_COPY有明确比较与理由即可通过源码审查任务，不强制vendoring。若实际摘取，每片段可追溯来源/许可/变更并用离线fixture证明无发送、配对授权或Agent执行；两分支都不引入整个上游runtime。

**反例与禁止行为**

- 不得为了完成任务强行复制源码/安装nanobot或LangBot；不得移植first-owner、channel bus、Agent loop或隐藏发送。
- 未获项目准入的copyleft源码不可擅自混入；不把GPL/AGPL一般描述为违法。

**验证方法**

评审比较表与NO_COPY理由；只有摘取分支运行模板输出/副作用fixture并核对NOTICE与源码diff，NO_COPY分支将摘取专属验证标NOT_APPLICABLE。

**必须提交的证据**

- 明确的NO_COPY或有限摘取决定，所比较的候选/方案、收益与维护理由。
- 实际摘取时附精确commit/path/hash/许可证/NOTICE/diff及离线fixture；NO_COPY无需虚构这些已采用资产。

**来源与修订依据**

U3《OpenBot 开源组件复用评估》PDF物理第10、17、23页提出复用方向；本任务为v1.2工程补足与修正，以docs_refs中设计及官方证据为准。

### OB-051

**实现普通卡片与结果回执**

阶段 M2 · 优先级 P0 · 状态 TODO · 能力域 Integration · 规模 M

**需求** [RQ06](requirements_traceability.md#rq06)、[RQ08](requirements_traceability.md#rq08)

**前置依赖** OB-021、OB-037、OB-047、OB-049、OB-094

**先读设计** [04_security_approvals.md](../docs/04_security_approvals.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[05_storage_api.md](../docs/05_storage_api.md)；[07_feishu.md](../docs/07_feishu.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。卡片信息不足或泄漏会造成盲批和隐私外发。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `lark-oapi`、`nanobot`、`langbot`

**复用边界（reuse_notes）**

- 普通卡片先完成；只有OB-094审过的固定commit模板可移植，模板不得自带网络/Agent/owner逻辑。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 实现无CardKit依赖的普通任务/审批/结果卡。
2. 预览走数据策略，不能安全展示影响范围时要求本地审阅。
3. 按receipt/UNKNOWN/PARTIAL等真实状态更新展示。
4. 先用自有最小普通卡完成闭环；只有OB-094选择有限摘取时才使用固定commit模板，NO_COPY同样允许，不引入上游channel bus或Agent循环。

**目标输出路径**

- `services/feishu_gateway/src/openbot_feishu/cards.py`

**正向验收**

先普通卡片完成任务状态、脱敏提案、批准/拒绝和结果；无CardKit也可用；敏感影响范围无法安全展示时REQUIRE_LOCAL，不让用户盲批截断内容；UNKNOWN明确待核对。 卡片构造层离线无发送副作用，模板可替换；源码摘取有LICENSE/NOTICE/本地diff，否则记录NO_COPY及比较理由。

**反例与禁止行为**

- 不得外发敏感完整diff/截图或让用户批准被截断到看不出影响的动作。
- 模板不得携带owner授予、自动发送或隐藏SDK调用；不因上游许可宽松就整仓导入。

**验证方法**

无CardKit权限也可完成任务和审批；敏感diff默认不出本机；未知结果有明确提示。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第10、23页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-052

**实现进度卡节流与更新顺序**

阶段 M2 · 优先级 P1 · 状态 TODO · 能力域 Integration · 规模 M

**需求** [RQ02](requirements_traceability.md#rq02)、[RQ08](requirements_traceability.md#rq08)

**前置依赖** OB-021、OB-051

**先读设计** [05_storage_api.md](../docs/05_storage_api.md)；[07_feishu.md](../docs/07_feishu.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** MEDIUM。错误卡片状态会误导用户重复操作。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** `lark-oapi`

**复用边界（reuse_notes）**

- card_revision、限流、合并和终态保护继续自有；不能原封不动复制上游内存流式循环。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 为任务卡定义revision和可合并进度类型。
2. 节流中间更新并处理retry_after，终态优先。
3. 模拟乱序、重复、断网恢复，确保最新终态保留。
4. 复用纯卡片构造器，revision/节流/重试调度仍由outbox掌握；SDK/tenacity不能形成第二个更新循环。

**目标输出路径**

- `services/feishu_gateway/src/openbot_feishu/progress.py`

**正向验收**

任务进度版本递增；可合并中间更新；最终状态不被迟到进度覆盖；处理API限流retry_after。 每次实际API更新、retry_after和合并原因可观察，取消不会留下无主后台更新任务。

**反例与禁止行为**

- 迟到进度不得把SUCCEEDED/FAILED等终态覆盖回RUNNING。

**验证方法**

快速生成100次进度更新后卡片保持最新终态；断网恢复不发送100条过时卡。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第10、23页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-053

**实现CardKit与更新通道降级**

阶段 M2 · 优先级 P1 · 状态 TODO · 能力域 Integration · 规模 M

**需求** [RQ08](requirements_traceability.md#rq08)

**前置依赖** OB-047、OB-051、OB-052、OB-094

**先读设计** [00_scope.md](../docs/00_scope.md)；[05_storage_api.md](../docs/05_storage_api.md)；[07_feishu.md](../docs/07_feishu.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** MEDIUM。卡片增强失败不应使核心审批不可用。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `lark-oapi`、`nanobot`

**复用边界（reuse_notes）**

- 复用已核验的CardKit构造模式；有效期/次数/权限来自实际平台与协议版本，不照抄报告硬编码28分钟/14天等。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 基于真实协议记录实现权限探测与更新路径选择。
2. 从token生成时间跟踪期限和次数，而非从任务创建时间计算。
3. 用受控时钟测试权限不足、过期、耗尽和原卡失效的降级。
4. 以OB-094的采纳/NO_COPY结论决定模板来源，记录各卡通道实际协议版本/权限/生成时点；到期/次数/降级判断用可控时钟测试。

**目标输出路径**

- `services/feishu_gateway/src/openbot_feishu/cardkit.py`

**正向验收**

按实际权限和协议能力选择CardKit/同步/延迟/API更新；token期限自生成起计算；路径不可用可降级普通卡或受控重发；不把卡片寿命写死为未经核验常量。

**反例与禁止行为**

- 无CardKit权限不能阻断普通审批；45分钟后点击不能被误当已生成token过期。
- 不得照抄报告28分钟/14天等常量代替当前平台合同，也不能让上游流式循环直接支配outbox。

**验证方法**

无权限、token过期、次数耗尽、原消息不可更新均可降级；“45分钟后点击”不被误判token过期。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。
- 卡通道能力/时限依据、受控时钟反例与源码采纳或NO_COPY理由。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第10、23–24页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-056

**飞书端到端真实验收**

阶段 M2 · 优先级 P0 · 状态 TODO · 能力域 QA · 规模 M

**需求** [RQ08](requirements_traceability.md#rq08)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-025、OB-045、OB-048、OB-050、OB-051、OB-054

**先读设计** [00_scope.md](../docs/00_scope.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[07_feishu.md](../docs/07_feishu.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。远程真实协议必须在发布前得到独立证据。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `lark-oapi`

**复用边界（reuse_notes）**

- 保留真实租户闭环，新增所选SDK的启动、断线、取消与双消费者检测证据，分别报告各计时路径。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 用真实测试租户和M1一个Provider跑手机任务/审批/取消。
2. 断网、重启、重复callback、旧卡和撤销owner逐场景验证。
3. 记录冷启动、连接、ACK与callback分位及失败截图/日志的脱敏证据。
4. 真实租户验收固定SDK与协议组合，分别测冷/热启动、发现、握手、callback；补双消费者与SDK阻塞被外部watchdog回收反例。

**目标输出路径**

- `tests/integration/feishu`
- `docs/demos/m3.md`

**正向验收**

M2用一个已验证Provider在真实测试租户完成手机发任务、审批、取消、重启与断网恢复；记录独立延迟；第二Provider到M3验证，不反向阻塞远程闭环。 结果带版本、环境和样本数；普通卡可用不等于CardKit全部能力已验证。

**反例与禁止行为**

- mock通过不算真实飞书验收；第二Provider未到M3不阻塞本阶段但不得宣称完整MVP。

**验证方法**

完成主流程和6个失败场景；冷启动与3秒callback响应分别报告，不给未经测量延迟保证。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供至少一份实际声明平台/服务的受控集成证据及能力矩阵；mock结果单独列出，不能代替真实验证。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第9–10、23页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。


## M3 MVP与三平台CLI

### OB-026

**实现Ollama或第二Provider**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 Runtime · 规模 M

**需求** [RQ06](requirements_traceability.md#rq06)、[RQ07](requirements_traceability.md#rq07)

**前置依赖** OB-007、OB-008、OB-009、OB-023、OB-024、OB-037、OB-038、OB-039、OB-092

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[00_scope.md](../docs/00_scope.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。本地模式错误映射可隐式外发或产生能力误报。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `model-ollama`、`httpx`、`tiktoken`、`model-runner`

**复用边界（reuse_notes）**

- Ollama SDK或httpx择一；loopback可能转云，验证model/runner配置与实际出口，不以名称或地址推断本地。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 到M3锁定Ollama SDK或受控httpx及实际本地model/runner组合，记录模型来源、能力与启动配置。
2. 核验真实网络命名空间、关闭云功能并限制允许模型/服务工具；localhost、模型名或无云key均不单独证明本地推理。
3. 统一处理流、usage、取消与有界重试；禁止自动工具helper、Provider托管搜索/remote MCP和隐式云回退。
4. 在干净缓存/禁网环境执行首个真实模型请求，观测runner的实际egress并测试云模型/搜索/资产下载拒绝；再完成与云Provider相同合同场景。

**目标输出路径**

- `services/core/src/openbot/providers/ollama.py`

**正向验收**

M3补齐本地Provider，使MVP具备一个云Provider和一个本地Provider；LOCAL_MODEL/OFFLINE均不云回退；无tool能力时明确CAPABILITY_UNAVAILABLE。 本地能力需要model、runner配置及网络证据共同成立；缺少可核验证据时CAPABILITY_UNAVAILABLE而不宣称LOCAL_MODEL/OFFLINE。任务中不拉取模型或词表。

**反例与禁止行为**

- 模型不支持工具时不能伪造成功；容器localhost不能未经验证当宿主本地服务。
- 不得只检查127.0.0.1或cloud名称后放行；不能让本机服务转发云模型/web search，不能在本地失败后转云。

**验证方法**

同一固定任务两Provider都可完成或给出能力拒绝；OFFLINE网络审计通过。 针对所选版本主动构造localhost转云/搜索请求，确认被配置和网络边界拒绝；记录本地模型实际推理与无额外网络的观察范围。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供至少一份实际声明平台/服务的受控集成证据及能力矩阵；mock结果单独列出，不能代替真实验证。
- 模型资产/runner版本、禁云配置、真实首次请求网络证据与取消后的尝试计数。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第8、24页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-057

**实现专用浏览器profile与会话锁**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 Platform · 规模 M

**需求** [RQ06](requirements_traceability.md#rq06)、[RQ09](requirements_traceability.md#rq09)

**前置依赖** OB-007、OB-016、OB-031、OB-037、OB-039、OB-042、OB-092

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[02_architecture.md](../docs/02_architecture.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。浏览器登录态拥有用户账户权限。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `playwright`

**复用边界（reuse_notes）**

- 直接Playwright原语、专用profile；Chromium sandbox显式配置/验证，不能暗加--no-sandbox；外层隔离另证。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 使用直接Playwright异步原语，建立专用profile目录/锁和用户手动登录；固定驱动与浏览器build，清理继承环境。
2. 对所选Chromium后端显式配置并验证chromium_sandbox；检查实际启动参数及容器/OS边界，不依赖默认false或暗中--no-sandbox。
3. 浏览器纳入统一supervisor与资源归属，用户cookie/凭据不出profile；不复制默认Chrome目录或接任意CDP。
4. 验证并发/旧epoch/profile冲突/异常退出、sandbox不可用及登录态保护，按实际OS/engine/backend记录资格。

**目标输出路径**

- `services/core/src/openbot/tools/executors/browser/session.py`

**正向验收**

直接Playwright原语配OpenBot专用user-data目录和profile锁；用户手动登录；不复制日常Chrome profile、解密cookie或接管任意CDP端口；能力按OS报告。 Chromium自身sandbox与外层OS/容器隔离分别有证据；需要的边界不可启用时拒绝能力，不静默去掉sandbox启动。

**反例与禁止行为**

- 不得复制用户默认Chrome profile、解密cookies或附着任意CDP端口。
- 不得通过--no-sandbox消除启动报错后仍声称强隔离；专用profile不是OS沙箱证明。

**验证方法**

并发任务不相互抢上下文；敏感cookie不进Artifact；profile锁冲突提示且不损坏用户profile。 核对实际argv/配置与探针，故意破坏sandbox前提时可解释拒绝；浏览器关闭/崩溃后执行域能被Supervisor核对。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供至少一份实际声明平台/服务的受控集成证据及能力矩阵；mock结果单独列出，不能代替真实验证。
- Playwright/browser build与资产hash、sandbox配置/实际启动证据、OS/backend资格与profile锁记录。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第13、17–18、24页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-058

**实现浏览器网络与下载策略**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 Security · 规模 M

**需求** [RQ06](requirements_traceability.md#rq06)、[RQ09](requirements_traceability.md#rq09)

**前置依赖** OB-032、OB-036、OB-037、OB-057、OB-041

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。浏览器可通过子请求或上传绕过表面导航限制。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `playwright`

**复用边界（reuse_notes）**

- BrowserContext.route / Page.route仅一层，Service Worker默认阻止绕过或由已验证更强边界覆盖；真实出口与上传下载同验。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 把导航/重定向/popup/iframe/subrequest、WebSocket及上传下载共同纳入数据/网络策略，禁止file/内部/metadata地址。
2. 明确Service Worker策略：受控能力默认阻止其绕过route；若应用确需启用，必须由已验证更强网络边界覆盖并记录限制。
3. 需要强隔离的能力使用实际OS/容器网络边界；BrowserContext.route / Page.route只作应用层防线，代理/DNS/浏览器进程不得有策略旁路。
4. 验证SW发起请求、重定向/弹窗/下载路径穿越、未批上传与边界不可用的拒绝，不以路由handler覆盖率当隔离证明。

**目标输出路径**

- `services/core/src/openbot/tools/executors/browser/network_policy.py`

**正向验收**

导航、重定向、popup、iframe、subrequest、下载上传一起经过策略；禁止file/内部/元数据地址；需要强网络边界时用隔离后端，BrowserContext.route / Page.route不能当完整隔离证明。 BrowserContext.route / Page.route无法拦截的Service Worker等路径被明确禁用或受独立网络边界约束；缺少相应证据不标能力可用。

**反例与禁止行为**

- 仅BrowserContext.route / Page.route不能宣称完整隔离；无法强制必要边界就不得开放该任务。
- 不得静默启用Service Worker或增加代理来绕过拦截，也不得把route当整个浏览器网络沙箱。

**验证方法**

重定向到localhost/metadata、下载路径穿越、上传未批文件被阻断；运行模式能力不足时拒绝。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。
- Service Worker拒绝/独立边界策略、实际请求目标与下载/upload反例。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第13、18、24页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-062

**实现MCP版本协商与生命周期**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 Integration · 规模 M

**需求** [RQ09](requirements_traceability.md#rq09)

**前置依赖** OB-004、OB-007、OB-009、OB-038、OB-092

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。MCP进程协议故障可阻塞任务或引入未经审核代码。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `mcp-sdk`

**复用边界（reuse_notes）**

- 采用锁定官方MCP SDK/stdio协议；适配到自有有界进程与流，不默认升级transport或自动安装包。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 固定stdio server与SDK兼容版本，完成initialize和能力协商。
2. 实现bounded请求、取消、断连和process退出映射。
3. 对不支持版本/transport给出明确错误，HTTP能力单独开关。
4. 使用所选官方MCP SDK最低所需API与固定stdio协议组合；初始化/取消/close和实际派生进程均受统一deadline/监督，默认SDK行为须实测。

**目标输出路径**

- `services/core/src/openbot/tools/mcp/client.py`

**正向验收**

MVP先实现固定版本stdio MCP、SDK协商与compatibility manifest；初始化、取消、断连和输出有界；Streamable HTTP另立能力开关，不以旧SSE假设为唯一协议。 SDK选定版本而不是报告mcp>=范围是兼容性证据；早期trusted fixture不等于允许任意server未隔离启动。

**反例与禁止行为**

- 不能自动以uvx/npx latest启动server，或遇到版本不匹配无限等待。
- 不得任意切旧SSE/新transport以掩盖协议不匹配，或在任务中npx/uvx latest补安装。

**验证方法**

使用受控MCP服务器测试初始化、异常、取消与版本不匹配；无无限等待或secret日志。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供至少一份实际声明平台/服务的受控集成证据及能力矩阵；mock结果单独列出，不能代替真实验证。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第13、18、24–25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-063

**实现MCP注册与工具元数据锁定**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 Security · 规模 M

**需求** [RQ04](requirements_traceability.md#rq04)、[RQ09](requirements_traceability.md#rq09)

**前置依赖** OB-002、OB-031、OB-037、OB-062、OB-090

**先读设计** [04_security_approvals.md](../docs/04_security_approvals.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。工具动态变更会在用户批准后改变实际行为。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `mcp-sdk`、`rfc8785`、`pydantic-jsonschema`

**复用边界（reuse_notes）**

- JCS hash覆盖完整manifest、package、命令/env/transport；refs本地化与Draft2020-12校验；list_changed隔离，annotations仅外部数据。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 为server包、启动命令、环境和完整工具定义生成manifest digest。
2. 启动及list_changed先隔离相关工具，再产生差异审阅。
3. 将批准绑定tool manifest版本，更新后撤销不兼容旧提案。
4. manifest由Python权威规范化，使用OB-090向量与本地schema registry；固定完整定义并对schema大小/引用/递归/时间设限。

**目标输出路径**

- `services/core/src/openbot/tools/mcp/registry.py`

**正向验收**

pinning覆盖包digest、命令、环境、transport、完整tool definition与input/output schema/annotations；启动与list_changed隔离重审；元数据固定不等于server可信。 未经允许的远程/未知ref不联网解析，format要求显式校验；完整元数据变更冻结相关能力并使旧绑定重新审查。

**反例与禁止行为**

- schema hash一致不能作为server代码安全证明；工具名不得覆盖内建名称。
- 工具description/inputSchema/outputSchema/annotations的任何关键变化不能沿用旧批准；JCS hash不证明server实现安全。

**验证方法**

描述或schema改变后无法沿用旧批准；不能以schema hash证明server代码可信。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第7、13、24–25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-064

**实现MCP进程和网络权限**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 Security · 规模 M

**需求** [RQ04](requirements_traceability.md#rq04)、[RQ05](requirements_traceability.md#rq05)、[RQ06](requirements_traceability.md#rq06)、[RQ09](requirements_traceability.md#rq09)

**前置依赖** OB-019、OB-037、OB-038、OB-041、OB-062、OB-063、OB-042

**先读设计** [04_security_approvals.md](../docs/04_security_approvals.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。MCP服务拥有代码执行能力，客户端校验不能替代隔离。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `mcp-sdk`、`python-on-whales`

**复用边界（reuse_notes）**

- stdio server必须经已验证隔离后端与Supervisor；SDK派生子进程不准继承全部env，也不能自行触发sampling/Agent loop。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 在隔离后端运行已安装stdio server并注入最小secret。
2. 把每个调用包为普通Operation/dispatch，使用本地reviewed manifest。
3. 禁用sampling、隐式提权和运行中安装，测试越权读取与网络。
4. 显式构造stdio子进程env/HOME/TMP/PATH和固定启动命令，实测真实进程而不假设SDK默认全继承或全过滤；接入统一容器/进程监督。

**目标输出路径**

- `services/core/src/openbot/tools/mcp/executor.py`

**正向验收**

stdio server作为不可信程序隔离，无父进程全部env；MCP调用必须经过同一Broker和短期dispatch；本地reviewed manifest决定retry_class；MVP禁sampling与自动安装latest。 关闭采样与自动工具/Provider远端MCP旁路；server安装、来源审查与任务调用分离。

**反例与禁止行为**

- 第三方readOnlyHint/idempotentHint不得直接决定授权或重试；未知server不执行。
- 不得因MCP SDK自带spawn就绕过OB-041/042，或让annotations决定免审批/重试。

**验证方法**

恶意server读宿主secret或额外网络请求被隔离层拦截；缺少沙箱不宣称工具安全。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第13、18、24–25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-065

**建立MCP恶意与故障服务器测试**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 QA · 规模 M

**需求** [RQ09](requirements_traceability.md#rq09)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-062、OB-063、OB-064

**先读设计** [04_security_approvals.md](../docs/04_security_approvals.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。协议边界测试不足会让第三方工具绕过通用安全。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `mcp-sdk`、`model-runner`

**复用边界（reuse_notes）**

- 覆盖SDK取消语义、服务端断连、schema/refs洪泛与变更；独立计数请求/效果，执行后断连不自动再执行。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 实现恶意/故障MCP fixture，包括变更、洪泛、重复ID和执行后断连。
2. 检查工具注册、输出过滤、timeout和UNKNOWN语义。
3. 保存可复现案例并接入对应PR回归。
4. 增加实际SDK取消/断连、恶意远程ref/格式、主动sampling、重复ID和server-side执行诱导；失败状态与真实副作用计数一致。

**目标输出路径**

- `tests/integration/mcp`

**正向验收**

模拟工具表更新、超长输出、schema洪泛、请求ID重复、server退出和未知结果；输出通过统一过滤。 所选MCP SDK与server组合有独立fault证据，模型托管remote MCP不充当本地受控MCP实现。

**反例与禁止行为**

- server断连后的未知副作用不能无条件重试；大输出不得耗尽内存。

**验证方法**

全部客户端超时有界；工具名碰撞不会覆盖内建工具；执行后断连不无条件重试。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第13、24–25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-066

**实现只读技能指令加载**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 Runtime · 规模 M

**需求** [RQ04](requirements_traceability.md#rq04)、[RQ07](requirements_traceability.md#rq07)

**前置依赖** OB-002、OB-008、OB-024、OB-031

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。技能文字是常见持久化注入入口。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** 无直接组件引用

**复用边界（reuse_notes）**

- 技能来源/版本/license与组件来源台账格式协调，但技能文本不获得依赖准入或权限修改权。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 实现只读技能manifest与来源/版本/license/capabilities字段。
2. 把说明作为受限上下文载入，不开放内部管理工具。
3. 验证恶意README/技能文本、自动生成draft和权限声明变化。
4. 技能与组件来源台账关联但互不授予权限；技能不能安装未准入依赖、加载workspace原生插件或改变运行模式。

**目标输出路径**

- `services/core/src/openbot/application/skills.py`
- `contracts/schemas/skill_manifest.schema.json`

**正向验收**

技能保留来源/版本/license和capabilities，MVP只读说明加载；文字不能改policy、扩大workspace或调内部管理工具；自动生成只留draft，不自动安装。

**反例与禁止行为**

- 技能不能增加workspace、关闭policy或自动安装执行生成代码。
- 源码注释/AGENTS/README不能把REFERENCE_ONLY候选升级成默认runtime。

**验证方法**

仓库AGENTS/README中恶意指令不能改系统策略；用户安装技能有来源和权限展示。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第3、26页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-068

**实现用户级daemon安装与卸载**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 Platform · 规模 M

**需求** [RQ01](requirements_traceability.md#rq01)、[RQ11](requirements_traceability.md#rq11)

**前置依赖** OB-003、OB-005、OB-008、OB-028、OB-042、OB-093

**先读设计** [02_architecture.md](../docs/02_architecture.md)；[00_scope.md](../docs/00_scope.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[10_project_plan.md](../docs/10_project_plan.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。安装生命周期错误会扩大权限或破坏用户数据。

**复用职责（reuse_type）** `native_primitive` · 原生原语适配

**关联组件（component_refs）** `service-manager`、`profile-locks`、`windows-sys`

**复用边界（reuse_notes）**

- service-manager仅在已验证launchd/systemd用户级场景复用；Windows用户登录会话独立实现，不用系统服务替代。
- 实际OS、架构、backend和配置组合须独立提供证据；统一API、正常退出或进程组不能自动证明所有强杀与逃逸场景均可回收。

**实施步骤**

1. 按OS实现用户级安装/start/stop/status/uninstall；macOS LaunchAgent和Linux systemd --user可用已验证service-manager封装。
2. Windows独立实现登录用户会话机制，验证交互用户令牌/最低权限；所选service-manager的sc.exe/WinSW后端不支持User级能力，不能直接替代。
3. 明确唯一自启/锁所有者、登录/登出/重启/显式stop规则；UI退出不停止daemon，重复安装不创建第二实例。
4. 在原生环境验证服务描述、权限/目录、卸载保留数据与失败恢复；干净发行安装继续由OB-072证明。

**目标输出路径**

- `native/supervisor/packaging`
- `apps/cli`
- `docs/install`

**正向验收**

实现每目标OS用户级常驻服务的安装/启动/停止/自启/卸载；不以高权限system service运行用户桌面会话；基础服务验证后由OB-072补全打包安装证据。 组件跨平台API不等于跨平台用户会话语义；Windows不使用LocalSystem/root等高权限绕过缺能力。

**反例与禁止行为**

- 不得使用高权限system服务控制用户桌面；卸载不得误删工作区。
- 不得用service-manager Windows系统服务能力伪装用户会话支持，或让Tauri与原生服务各自启动一个daemon。

**验证方法**

全新用户环境安装后重启可恢复；卸载不误删工作区；UI退出不影响daemon。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。
- 每OS实际服务/登录任务描述、用户令牌/权限/锁归属与启停卸载证据。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第14、25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-069

**建立macOS原生运行门禁**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 Platform · 规模 M

**需求** [RQ05](requirements_traceability.md#rq05)、[RQ11](requirements_traceability.md#rq11)

**前置依赖** OB-032、OB-042、OB-068

**先读设计** [02_architecture.md](../docs/02_architecture.md)；[00_scope.md](../docs/00_scope.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。平台差异可能使安全与生命周期假设失效。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `keyring`、`service-manager`、`playwright`

**复用边界（reuse_notes）**

- macOS实际arch/OS/钥匙串/原生轮子/浏览器/worker残余均记录；UI不需要的屏幕权限不提前索取。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 选择macOS ARM64原生测试环境并记录版本/权限。
2. 验证路径、凭据、daemon与worker、Browser/MCP声明能力。
3. 输出supported/experimental/unsupported矩阵并交打包任务。
4. 对选定macOS/arch核验Keychain、LaunchAgent、原生wheel/grammar、浏览器sandbox及清理边界；不预先要求MVP无GUI能力的录屏/辅助权限。

**目标输出路径**

- `.github/workflows/platform-macos.yml`
- `tests/integration/platform/macos`

**正向验收**

原生macOS受控开发环境验证路径、凭据、daemon、浏览器与worker清理；ARM64为试点，Intel是否支持据实记录；无GUI版本不要求录屏授权。 库发布平台声明不替代本机实际能力；Intel是否支持仍据证据判断。

**反例与禁止行为**

- 未测Intel不得标支持；无GUI版本不能要求录屏权限或宣称已有桌面控制。

**验证方法**

原生macOS集成测试与能力报告；此任务可用固定开发运行时，完全无开发环境的安装证明由OB-072补足。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供至少一份实际声明平台/服务的受控集成证据及能力矩阵；mock结果单独列出，不能代替真实验证。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第14–15、25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-070

**建立Windows原生运行门禁**

阶段 M3 · 优先级 P1 · 状态 BLOCKED · 能力域 Platform · 规模 M

**需求** [RQ05](requirements_traceability.md#rq05)、[RQ11](requirements_traceability.md#rq11)

**前置依赖** OB-032、OB-042、OB-068

**先读设计** [02_architecture.md](../docs/02_architecture.md)；[00_scope.md](../docs/00_scope.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。Windows路径和进程归属是关键安全边界。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `windows-sys`、`keyring`、`service-manager`、`playwright`

**复用边界（reuse_notes）**

- Windows原生验证Job创建序列、嵌套/拒绝、中文路径与依赖资产；不用WSL或crate宣传替代证据。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 选择原生Windows x64测试环境，不用WSL代替。
2. 覆盖长路径/junction/中文空格、Job与凭据/用户会话。
3. 输出能力与失败限制，供CLI安装验证使用。
4. 验证挂起创建→Job分配→恢复顺序、Job失败/嵌套/PID复用、用户登录任务与Credential Manager；记录实际Windows wheel/CLI/浏览器资产。

**目标输出路径**

- `.github/workflows/platform-windows.yml`
- `tests/integration/platform/windows`

**正向验收**

原生Windows x64验证长路径/junction/Job Object/凭据与用户会话；不用WSL代验；路径含中文空格可用；未支持的原生命令不伪装成容器能力。

**反例与禁止行为**

- 容器里Linux命令不能被写成Windows原生PowerShell/Win32支持。
- service-manager缺User后端不能自动切LocalSystem；不得以WSL完成Windows资格。

**验证方法**

原生Windows受控环境跑平台测试与能力报告；干净安装由OB-072验证；检测worker脱离Job和PID复用风险。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供至少一份实际声明平台/服务的受控集成证据及能力矩阵；mock结果单独列出，不能代替真实验证。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第14、18、25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-071

**建立Linux原生运行门禁**

阶段 M3 · 优先级 P1 · 状态 BLOCKED · 能力域 Platform · 规模 M

**需求** [RQ05](requirements_traceability.md#rq05)、[RQ11](requirements_traceability.md#rq11)

**前置依赖** OB-032、OB-042、OB-068

**先读设计** [02_architecture.md](../docs/02_architecture.md)；[00_scope.md](../docs/00_scope.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。发行版与运行会话差异会破坏守护和隔离行为。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `keyring`、`service-manager`、`python-on-whales`

**复用边界（reuse_notes）**

- Linux发行版/服务管理/rootless容器/cgroup与keyring不可用路径明确，其他backend不能因接口相似自动标supported。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 冻结Linux x64发行版和systemd user基线。
2. 检查凭据、路径、cgroup/进程组、隔离后端和浏览器依赖。
3. 记录无systemd或桌面会话差异，生成能力报告。
4. 记录已测发行版、systemd user、可用cgroup/rootless引擎与Secret Service；缺组件/权限时能力拒绝，非systemd和其他引擎另给支持边界。

**目标输出路径**

- `.github/workflows/platform-linux.yml`
- `tests/integration/platform/linux`

**正向验收**

明确受支持Linux x64发行版、systemd user与可选无systemd边界；验证文件/浏览器/隔离能力；X11/Wayland GUI不计入本MVP完成条件。

**反例与禁止行为**

- X11测试不能代表Wayland桌面自动化，未支持能力不得静默失败。
- 不得把Docker/Podman/nerdctl统一API当等价保证，或无D-Bus时回退明文keyring。

**验证方法**

原生Linux固定运行时测试与能力报告；干净安装由OB-072验证；容器缺失、资源权限不足给CAPABILITY_UNAVAILABLE。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供至少一份实际声明平台/服务的受控集成证据及能力矩阵；mock结果单独列出，不能代替真实验证。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第13–14、25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-072

**建立可复现打包与运行资源清单**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 Platform · 规模 M

**需求** [RQ11](requirements_traceability.md#rq11)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-004、OB-005、OB-069、OB-070、OB-071、OB-089

**先读设计** [00_scope.md](../docs/00_scope.md)；[02_architecture.md](../docs/02_architecture.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。开发机可运行不能证明用户能安装使用。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `pyinstaller`、`cli-toolchain`、`playwright`、`tree-sitter-language-pack`、`tiktoken`

**复用边界（reuse_notes）**

- PyInstaller onedir是候选打包路线；每OS干净安装、首次离线运行、完整资源清单；可复现性按实测说明，不承诺bitwise一致。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 按各OS锁定工具链，优先评估PyInstaller onedir；列Python/Rust/前端包与rg、浏览器、grammar、词表、镜像和源码片段等完整资产。
2. 在安装/构建准备阶段取得固定资产并校验，运行期不自动下载；缺后端/资产明确报错，默认环境不包含未来P2功能。
3. 每OS干净机器安装、首次离线version/API/词表/支持grammar/浏览器smoke，观察网络、权限与secret/profile排除。
4. 保存重建命令、输入/产物hash、平台差异和可复现范围；把完整资产交OB-096核验，不以“可重复构建”承诺未经证明bitwise一致。

**目标输出路径**

- `scripts/build`
- `packaging`
- `docs/runtime-dependencies.md`

**正向验收**

三平台CLI安装包构建可复现、附hash/版本/依赖清单；Python/浏览器/隔离后端如何提供或预检说明完整；M3可采用明确标注的未签名试点包，不能假称桌面签名Beta。 Python包锁之外的非包资产有精确版本/hash与来源；安装准备联网与OFFLINE首用明确分开。

**反例与禁止行为**

- 产物不得包含secret/profile/cache；不完整CLI安装不能把MVP标完成。
- 不得首次使用时暗中补浏览器/grammar/词表；未签名试点包仍按既有M3说明，不冒称M4认证。

**验证方法**

每OS干净机器安装smoke；runtime资源缺失明确报错；产物不含测试密钥/缓存profile。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供至少一份实际声明平台/服务的受控集成证据及能力矩阵；mock结果单独列出，不能代替真实验证。
- 三OS实际安装资源清单、禁网首次调用、可再建差异说明与全部产物hash。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第14、25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-075

**实现统一可观测性与诊断**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 Runtime · 规模 M

**需求** [RQ06](requirements_traceability.md#rq06)、[RQ10](requirements_traceability.md#rq10)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-009、OB-015、OB-021、OB-023、OB-039、OB-054

**先读设计** [02_architecture.md](../docs/02_architecture.md)；[05_storage_api.md](../docs/05_storage_api.md)；[00_scope.md](../docs/00_scope.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。诊断泄漏和健康误报会掩盖运行风险。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `structlog`、`opentelemetry`

**复用边界（reuse_notes）**

- structlog是格式/上下文管道，跨任务contextvars绑定/清理与脱敏自有；OpenTelemetry按需单独准入，不默认远程exporter。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 汇总M1结构日志、trace和ledger，增加跨进程关联。
2. 提供队列、UNKNOWN、预算、连接和资源健康指标。
3. 实现显式本地诊断导出并验证脱敏和容量。
4. structlog负责结构化管道；显式绑定/清除并发contextvars，前置过滤与异常处理统一。OpenTelemetry按需准入，默认无远程exporter。

**目标输出路径**

- `services/core/src/openbot/observability`
- `docs/operations`

**正向验收**

汇总M1已有结构日志和审计，关联Task/Operation/Attempt/event；增加inbox lag、outbox age、UNKNOWN、writer queue、预算和网关指标；默认不远程上报，不收集隐藏思维。 高基数Task/Operation等只用于有界日志/trace，不作为无界metrics标签；SDK调试日志同样受最小化/脱敏。

**反例与禁止行为**

- 不采集模型隐藏思维、secret或默认远传诊断；UI在线不等于系统健康。
- 不得声称装structlog即自动全链路安全，或通过默认exporter外发秘密/运行数据。

**验证方法**

每个主失败场景可由日志定位；诊断包需显式导出且脱敏；不收集隐藏推理内容。 并发任务上下文不串线，异常与SDK debug经过同一过滤；诊断包仍显式导出。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第14页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-078

**建立断网休眠与崩溃浸泡**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 QA · 规模 M

**需求** [RQ03](requirements_traceability.md#rq03)、[RQ11](requirements_traceability.md#rq11)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-020、OB-022、OB-030、OB-042、OB-054、OB-075

**先读设计** [03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[00_scope.md](../docs/00_scope.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。长时故障会暴露竞态与资源泄漏。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `lark-oapi`、`python-on-whales`、`model-runner`

**复用边界（reuse_notes）**

- 覆盖SDK阻塞、DNS半开、daemon/客户端/容器各类死亡与遗留资源；报告样本和清理边界，不用100%表述。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 把规定故障点扩展为三平台有界浸泡场景。
2. 注入DNS/TCP半开、睡眠、磁盘满和进程死亡，记录恢复决定。
3. 输出样本时间、环境、首故障和残余UNKNOWN报告。
4. 补SDK真实取消/阻塞、runner本地转云、客户端死而容器存活、scanner联网验证、空缓存资产首用与native parser故障，按实际启用能力组合运行。

**目标输出路径**

- `tests/chaos/soak`
- `docs/soak-report-template.md`

**正向验收**

扩展M1已覆盖的崩溃点为三平台长时网络/休眠/磁盘故障浸泡；记录版本、时间、硬件、未知效果与恢复决定；不把样本通过写成绝对无损保证。 强杀、休眠、普通异常和真实断电分别记录，不能把任一类通过当全部耐久性证明。

**反例与禁止行为**

- 有限样本不能宣称100%无损；恢复不能为了完成率盲重试危险动作。

**验证方法**

至少覆盖每OS已支持能力；恢复时不重复危险操作；报告时间/样本/硬件/版本。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第9、13–14页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-095

**审查DOM提取脚本的最小源码复用**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 Platform · 规模 M

**需求** [RQ06](requirements_traceability.md#rq06)、[RQ09](requirements_traceability.md#rq09)、[RQ11](requirements_traceability.md#rq11)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-057、OB-058、OB-089、OB-092

**先读设计** [04_security_approvals.md](../docs/04_security_approvals.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)

**风险** HIGH。被抽出的脚本仍依赖浏览器Agent执行网络/动作或包含过量隐私。

**复用职责（reuse_type）** `source_review` · 源码参考/摘取审查

**关联组件（component_refs）** `browser-use`、`playwright`

**复用边界（reuse_notes）**

- 默认REFERENCE_ONLY；比较后可给出NO_COPY及理由。只有选择有限摘取时才要求固定commit/path/hash、LICENSE/NOTICE、差异和回归，禁止整仓导入。
- component_refs表示相关组件或被审查边界，不表示自动安装或已准入；按catalog类别和当前阶段执行。

**实施步骤**

1. 比较browser-use候选只读DOM片段与最小自有提取器的范围、依赖、维护成本；拟摘取时检查精确commit/文件许可与隐藏执行。
2. 记录NO_COPY或有限摘取决定；NO_COPY只需有明确比较和理由，后续最小DOM实现交OB-059，不强制vendor或引入browser-use包。
3. 若选择摘取，保留来源/NOTICE/diff并裁剪为限量只读脚本，移除模型/Agent/自动点击/主动fetch；在DOM/iframe/导航/恶意页面fixture验边界。

**目标输出路径**

- `docs/evidence/source-reuse-browser-dom.md`
- `components/source-reuse/browser-dom.json`

**正向验收**

NO_COPY分支有比较与理由即可完成审查；实际摘取分支才要求独立脚本fixture、确定来源hash、额外动作/主动请求为0、输出时间/大小有界及TAINTED_EXTERNAL/page/frame/revision。任何决定都不采用自治Agent.run。

**反例与禁止行为**

- 不得为关闭任务而整仓导入或强制复制；不得使用browser-use自治循环、自行请求模型或自动执行动作。
- DOM脚本来源不会使页面文本变可信，也不能赋予owner/策略/授权。

**验证方法**

复核NO_COPY理由及与自有方案的比较；实际摘取才执行只读DOM、隐式请求/动作canary、超限与导航fixture，并核对源文件/NOTICE/hash。

**必须提交的证据**

- NO_COPY或有限摘取决定与方案比较；NO_COPY的提取代码/fixture项明确NOT_APPLICABLE。
- 实际摘取时提供commit/path/license/hash/diff、维护人与只读/限额/副作用计数证据。

**来源与修订依据**

U3《OpenBot 开源组件复用评估》PDF物理第13、18、24页提出复用方向；本任务为v1.2工程补足与修正，以docs_refs中设计及官方证据为准。

### OB-059

**实现结构化浏览器读工具**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 Runtime · 规模 M

**需求** [RQ07](requirements_traceability.md#rq07)、[RQ09](requirements_traceability.md#rq09)

**前置依赖** OB-007、OB-019、OB-057、OB-058、OB-095

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。不稳定页面引用会让后续动作指向错误目标。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `playwright`、`browser-use`

**复用边界（reuse_notes）**

- 只采用OB-095核验的DOM只读片段或最小自有提取器；结果带page/frame/revision/provenance，独立预算与输出限额。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 实现open/extract的稳定page/frame/revision引用。
2. 把结构化正文/表格与外部provenance、URL证据返回。
3. 验证导航变化、超量DOM、恶意文本和fixture表格。
4. 按OB-095决定使用有限摘取或NO_COPY后自有最小DOM提取器；执行脚本只读、无模型/自动点击/主动fetch且有输出/时间界限。

**目标输出路径**

- `services/core/src/openbot/tools/browser/read.py`

**正向验收**

browser.open/extract返回page/frame/snapshot revision、最终origin与结构化证据；页面文本外部不可信；限时限量；旧元素引用跨导航无效。 DOM脚本只产生带TAINTED_EXTERNAL和page/frame/revision的证据，代码来源不改变页面内容不可信性。

**反例与禁止行为**

- 旧element index不能跨页面使用；页面文字不能改变工具权限。
- 不得调用browser-use Agent.run或从页面文字生成权威身份、策略、授权字段。

**验证方法**

fixture站点读表正确；恶意页面不能改变策略；导航变化使旧元素引用无效。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。
- DOM来源决定、只读脚本fixture和隐式动作/网络canary计数。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第13、18、24页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-060

**实现浏览器写动作提案与确认**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 Security · 规模 M

**需求** [RQ03](requirements_traceability.md#rq03)、[RQ04](requirements_traceability.md#rq04)、[RQ09](requirements_traceability.md#rq09)

**前置依赖** OB-017、OB-018、OB-019、OB-059

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。浏览器写通常直接影响外部账户。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** `playwright`、`browser-use`、`model-runner`

**复用边界（reuse_notes）**

- 每个浏览器写动作都经Broker、revision复验与OutcomeVerifier；不采用browser-use Agent.run()或多动作批量越权。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 构造带目标、输入、origin和revision的不可变browser.act提案。
2. 审批后重获资源、重新定位与核对页面条件。
3. 执行后验证目标效果，提交超时转UNKNOWN并提供核对信息。
4. 浏览器SDK只执行单次已批准原语，禁browser-use自治loop和推测多动作；第三方成功返回仍需OutcomeVerifier证据。

**目标输出路径**

- `services/core/src/openbot/tools/browser/actions.py`

**正向验收**

browser.act绑定page/frame/locator/action/input/revision及origin；写操作批准后重新定位/复验；超时不能当作提交失败，可能已执行时Operation UNKNOWN、Task RECONCILING。

**反例与禁止行为**

- 金额、目标按钮、页面或frame变化时旧批准必须失效；禁止盲点第二次提交。
- 不允许页面中的“已成功”文字或库返回无异常直接解除UNKNOWN/quarantine，不能因timeout再点击。

**验证方法**

页面换按钮、变金额、跨站跳转后旧批准拒绝；外部提交timeout进入UNKNOWN。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第13、18、24页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-061

**建立浏览器结果验证回归**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 QA · 规模 M

**需求** [RQ09](requirements_traceability.md#rq09)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-020、OB-059、OB-060

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。只测点击成功会漏掉实际提交错误。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `playwright`

**复用边界（reuse_notes）**

- DOM污染/导航/权限变化/点击已成功回执丢失按真实效果计数，驱动返回无异常不能代表用户目标成功。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 建立受控登录、表单、下载、重定向与页面变化fixture。
2. 记录外部效果计数、DOM/receipt和有限截图证据。
3. 将读、写、未知结果和用户介入场景接入回归。
4. 增加Service Worker/重定向出口、sandbox拒绝、DOM脚本隐式动作和提交成功后断流；按真实页面结果、请求和副作用计数判定。

**目标输出路径**

- `tests/integration/browser`

**正向验收**

测试目标是页面结果和外部副作用计数；失败不能仅靠模型说完成；提供截图/DOM证据限制。 fixture覆盖仅应用层route与更强网络模式的差异，未满足边界的场景明确拒绝。

**反例与禁止行为**

- 模型说完成或点击API返回成功不能代替业务效果验证。

**验证方法**

fixture购物/表单/下载/重定向/登录过期场景可复现；对不可确认结果明确unknown。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供至少一份实际声明平台/服务的受控集成证据及能力矩阵；mock结果单独列出，不能代替真实验证。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第13、24页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-067

**交付全MVP能力集回归**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 QA · 规模 M

**需求** [RQ07](requirements_traceability.md#rq07)、[RQ08](requirements_traceability.md#rq08)、[RQ09](requirements_traceability.md#rq09)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-026、OB-056、OB-061、OB-065、OB-066

**先读设计** [00_scope.md](../docs/00_scope.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[07_feishu.md](../docs/07_feishu.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。功能清单通过但未真正集成会产生虚假完成。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** 无直接组件引用

**复用边界（reuse_notes）**

- 已选组件的合同/副作用门禁随能力集验证；记录确切组合，不把各库独立通过拼成整系统安全结论。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 逐项映射U1完整MVP到已有模块和证据。
2. 组合两Provider、Feishu、ACI、隔离、Browser和MCP的受控场景。
3. 安全关键失败阻断功能集签核；安装证据交OB-072/080合并。
4. 把已启用组件版本/资产/配置组合与Q门禁关联，核对先前单库合格是否仍满足组合后的预算、egress和恢复语义。

**目标输出路径**

- `docs/demos/mvp.md`
- `tests/integration/scenarios/mvp`

**正向验收**

M3功能回归覆盖云加本地两Provider、飞书、ACI/隔离进程/Browser/MCP、恢复；每项原研究MVP能力有证据；三OS安装发布在OB-072/080联合完成，不以单环境演示代替。 云+本地Provider、Browser/MCP/飞书真实证据与mock反例分列；未启用的REFERENCE_ONLY/DEFERRED不冒充能力。

**反例与禁止行为**

- 本地/飞书Alpha不能替代完整MVP；不支持能力不能返回空成功。

**验证方法**

每项原研究第14页MVP都有证据和任务映射；任一安全关键失败阻止发布。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。
- 启用组件组合清单、关联Q/任务证据与每项能力的真实/模拟区分。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第19–26页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-076

**建立真实任务质量基准集**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 QA · 规模 M

**需求** [RQ07](requirements_traceability.md#rq07)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-067、OB-075

**先读设计** [03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[00_scope.md](../docs/00_scope.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。错误质量指标会掩盖产品做不成任务。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** 无直接组件引用

**复用边界（reuse_notes）**

- 记录选定组件、模型、原生资源及样本n；性能、LOC、成本、工期以本机测量和范围为准，不继承报告保证。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 定义受控任务、产物验证器和分项rubric。
2. 多次真实模型运行并记录n、模型/prompt/tool版本、成本和结果状态。
3. 建立baseline后再冻结质量目标，保留失败案例与回归阈值。
4. 同时记录组件/SDK/model/browser/grammar/镜像版本与配置，测量启动、安装体积、常驻资源、请求/恢复耗时，报告样本与失败。

**目标输出路径**

- `evals/scenarios`
- `evals/rubrics`
- `evals/run.py`

**正向验收**

真实Provider受控基准区分协议/安全/能力，记录SUCCEEDED/PARTIAL/FAILED/RECONCILING结果与n、版本、成本、延迟；模型final只有请求完成权，OutcomeVerifier核对产物和未知动作。

**反例与禁止行为**

- mock测试或模型final不能作为真实任务成功证据；未知动作未解决不能算成功。
- 不得把报告Stars、5k–15k行、400行、固定倍数收益或工期作为验收承诺。

**验证方法**

mock不作为智能效果证据；真实模型至少多次运行记录n和失败样例；模型/提示/工具版本可追踪。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供至少一份实际声明平台/服务的受控集成证据及能力矩阵；mock结果单独列出，不能代替真实验证。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第1、8、12、14、26页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-079

**完成上手与故障处置文档**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 Docs · 规模 M

**需求** [RQ10](requirements_traceability.md#rq10)、[RQ11](requirements_traceability.md#rq11)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-056、OB-067、OB-068、OB-072、OB-075

**先读设计** [00_scope.md](../docs/00_scope.md)；[05_storage_api.md](../docs/05_storage_api.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[07_feishu.md](../docs/07_feishu.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** MEDIUM。可操作性不足会导致用户错误恢复或扩大权限。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** 无直接组件引用

**复用边界（reuse_notes）**

- 列依赖组、安装期资产下载/批准、首次离线启动、缺backend拒绝、组件升级和NOTICE；未验证候选对用户不宣称已支持。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 编写从空环境安装、doctor、配对和首个任务的步骤。
2. 补取消/撤销、UNKNOWN核对、备份恢复、密钥轮换与脱敏报障。
3. 让未参与开发者按文档独立完成，记录阻塞点后修订。
4. 写清依赖组、组件准入、安装期资产准备、首次离线运行、NO_COPY或来源维护、缺backend拒绝、SDK升级与许可证清单阅读路径。

**目标输出路径**

- `README.md`
- `docs/getting-started.md`
- `docs/troubleshooting.md`
- `SECURITY.md`

**正向验收**

M3完成CLI/飞书配对、权限、停止、UNKNOWN核对、密钥轮换、备份恢复和诊断文档；MVP安装路径完整；M4自动升级/桌面步骤由OB-073/074补充。 用户可从能力清单知道哪些已验证、未验证或延期；恢复手册不建议ignore UNKNOWN后重做。

**反例与禁止行为**

- 不要求用户查源码才能处理常见失败；未完成M4功能不能写成可用。

**验证方法**

从未使用项目的人按说明独立完成主场景；失败路径无需查源码才能恢复。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第19–26页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-096

**验收全量交付资产来源与供应链**

阶段 M3 · 优先级 P0 · 状态 TODO · 能力域 QA · 规模 M

**需求** [RQ05](requirements_traceability.md#rq05)、[RQ07](requirements_traceability.md#rq07)、[RQ09](requirements_traceability.md#rq09)、[RQ11](requirements_traceability.md#rq11)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-004、OB-067、OB-072、OB-089、OB-094、OB-095

**先读设计** [08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)

**风险** HIGH。锁文件覆盖Python包却漏浏览器/grammar/tokenizer/rg/镜像及vendored源码。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `sbom-tools`、`pyinstaller`、`playwright`、`tree-sitter-language-pack`、`tiktoken`

**复用边界（reuse_notes）**

- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。
- component_refs表示相关组件或被审查边界，不表示自动安装或已准入；按catalog类别和当前阶段执行。

**实施步骤**

1. 按构建输入与实际包枚举全部Python/Rust/前端依赖及CLI、浏览器build、grammar、tokenizer、镜像和实际摘取代码，匹配catalog/各生态锁/来源/NOTICE。
2. 生成明确格式的SPDX或CycloneDX SBOM及校验、checksums和平台资产清单；NO_COPY决定无需虚构vendor资产，条件候选未启用不冒称安装。
3. 在三OS发行环境验证安装期准备与首次禁网使用，缺资产拒绝；检查受管容器/浏览器/parser实际加载配置与构建清单一致。
4. 以篡改/来源或许可缺失/摘要漂移和过期风险例外阻断release，记录可再建范围与差异；M4桌面签名独立，M3不延后来源核验。

**目标输出路径**

- `scripts/check_release_components.py`
- `docs/releases/component-supply-chain.md`
- `release/SBOM`
- `release/THIRD_PARTY_NOTICES.md`
- `release/checksums.json`

**正向验收**

交付内容与资产清单逐项匹配；SBOM标明实际使用SPDX或CycloneDX且通过相应schema；被篡改资产被拒绝；原生三OS安装证据可关联精确hash。

**反例与禁止行为**

- 不能把锁定版本当无漏洞保证；不能把CycloneDX输出冒称SPDX；不能以M4签名未做为由跳过M3源/许可证/摘要核验。
- 不能把仅Python包SBOM当完整供应链，也不能因所有来源已锁就声称没有漏洞。

**验证方法**

从OB-072三OS实际产物导出内容清单，与catalog/锁/SBOM/NOTICE/checksums逐项比较；校验所选SBOM schema，篡改一项资产必须失败，重建/离线首用记录可追溯。

**必须提交的证据**

- 三OS包/资源清单、选定格式SBOM及校验、NOTICE、构建输入hash、禁网首用记录、篡改反例和有限期风险例外。
- 记录精确来源/版本、OS/架构/配置、测试命令与限制；本包只定义门禁，真实结果未实施前保持NOT_RUN。

**来源与修订依据**

U3《OpenBot 开源组件复用评估》PDF物理第15–19、25–26页提出复用方向；本任务为v1.2工程补足与修正，以docs_refs中设计及官方证据为准。

### OB-077

**建立分层CI门禁**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 QA · 规模 M

**需求** [RQ11](requirements_traceability.md#rq11)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-010、OB-045、OB-067、OB-069、OB-070、OB-071、OB-072、OB-096

**先读设计** [00_scope.md](../docs/00_scope.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。门禁虚设会把已知安全缺陷带入发布。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `cli-toolchain`、`sbom-tools`

**复用边界（reuse_notes）**

- 早期已执行registry/锁/合同门禁，本任务整合阶段矩阵、上游升级fixture、供应链与release gate；不存在M3才加安全测试。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 盘点M0/M1已存在门禁并按风险归入PR层。
2. 新增真实Provider/租户nightly和三OS安装release层。
3. 注入一次已知失败证明门禁会阻断，并隔离测试凭据。
4. 整合M0准入/合同、M1组件故障和M3全资产门禁；上游版本/来源变更触发对应fixture，锁/来源/SBOM漂移阻断release。

**目标输出路径**

- `.github/workflows/pull_request`
- `.github/workflows/nightly`
- `.github/workflows/release`

**正向验收**

将M0/M1已有契约、安全、迁移和故障门禁整合成PR/nightly/release层级；M3才补真实租户和三OS发行验证；不是等到本任务才写安全测试。 新增OB-089—096按阶段验收，PR不因全局列表就安装所有组件；文档改动只跑必要一致性检查。

**反例与禁止行为**

- 不能等M3才开启安全测试；不得通过跳过失败测试放行。

**验证方法**

一次故障注入证明门禁能阻断；不要求每小改跑12h或所有付费测试；测试用秘密隔离。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。
- 至少一例组件版本/来源/资产不匹配导致门禁失败的复现，另附受影响测试选择规则。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第19–26页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-080

**完成MVP发布验收与风险登记**

阶段 M3 · 优先级 P1 · 状态 TODO · 能力域 Lead · 规模 S

**需求** [RQ01](requirements_traceability.md#rq01)、[RQ11](requirements_traceability.md#rq11)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-067、OB-072、OB-076、OB-077、OB-078、OB-079、OB-096

**先读设计** [00_scope.md](../docs/00_scope.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。发布声明必须与实际验证边界一致。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `sbom-tools`

**复用边界（reuse_notes）**

- M3基础供应链/离线首用/真实OS支持证据为发布前置；M4签名桌面和P2组件仍后置，不逆向阻塞。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 汇总功能、原生平台、安装、安全和真实质量证据。
2. 逐项签核RQ/S场景并登记剩余风险、owner与降级。
3. 在候选版本重新安装演示，发布明确能力矩阵和限制。
4. 将OB-096全量资产供应链与已启用组件资格作为M3退出条件；核对真实能力矩阵、有限期风险例外和未验证项，不等待M4签名替代。

**目标输出路径**

- `docs/releases/mvp-acceptance.md`
- `docs/risks.md`

**正向验收**

M3逐条签核原MVP范围、三平台CLI和受支持能力；安全关键失败阻断；无真实证据不标supported；M4桌面签名与自动升级不作为本gate的逆向依赖。

**反例与禁止行为**

- 安全关键失败或无三平台CLI证据不能放行MVP；M4签名不是反向前置依赖。
- NOT_RUN候选、缺资产或未证实本地/隔离能力不得标MVP通过；安全关键失败不能靠白名单扩大权限。

**验证方法**

重新安装候选版本演示；安全必阻断失败为零；质量基准与已知限制公开记录。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供至少一份实际声明平台/服务的受控集成证据及能力矩阵；mock结果单独列出，不能代替真实验证。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第25–26页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。


## M4 Tauri桌面Beta与签名升级

### OB-073

**实现版本升级和迁移恢复**

阶段 M4 · 优先级 P1 · 状态 TODO · 能力域 Platform · 规模 M

**需求** [RQ02](requirements_traceability.md#rq02)、[RQ03](requirements_traceability.md#rq03)、[RQ11](requirements_traceability.md#rq11)

**前置依赖** OB-011、OB-020、OB-030、OB-072、OB-080

**先读设计** [05_storage_api.md](../docs/05_storage_api.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[02_architecture.md](../docs/02_architecture.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。升级失败可能破坏唯一数据库或重复任务。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `tauri`

**复用边界（reuse_notes）**

- Tauri updater只做传输/签名校验，Drain/UNKNOWN处理/DB备份迁移/失败恢复自有；签名升级属M4。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 实现更新前drain、运行中操作核对和一致备份。
2. 校验包与schema兼容，执行可恢复替换和迁移。
3. 在下载/替换/迁移/重启失败点验证恢复及旧授权失效。
4. 更新器只负责经验证的传输/签名等原语；OpenBot负责Drain、UNKNOWN核对、GC受保护备份、兼容迁移和失败恢复，组件升级改变工具语义需重新审查旧授权。

**目标输出路径**

- `services/core/src/openbot/update`
- `docs/upgrade.md`

**正向验收**

M4更新先drain新任务、核对运行中操作、备份DB/manifest再迁移；签名校验与版本兼容明确；不兼容DB不能直接运行旧binary；可恢复安装状态不等于逆转外部效果。

**反例与禁止行为**

- DB升级不兼容时不能直接降级binary；回滚安装不表示撤回外部动作。
- 不得由updater插件自动跳过在途效果核对，或新旧资源混装后继续使用旧Operation批准。

**验证方法**

在下载、替换、迁移、重启各点失败可恢复；待审批动作遇策略/工具变化重新审议。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第15、25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-082

**实现Tauri任务与审批UI**

阶段 M4 · 优先级 P1 · 状态 TODO · 能力域 Desktop · 规模 M

**需求** [RQ01](requirements_traceability.md#rq01)、[RQ06](requirements_traceability.md#rq06)、[RQ10](requirements_traceability.md#rq10)

**前置依赖** OB-003、OB-081、OB-089

**先读设计** [02_architecture.md](../docs/02_architecture.md)；[05_storage_api.md](../docs/05_storage_api.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。桌面壳可能成为高权限token泄漏和执行绕过入口。

**复用职责（reuse_type）** `dependency_adapter` · 依赖薄适配

**关联组件（component_refs）** `tauri`、`macos-permissions`

**复用边界（reuse_notes）**

- Tauri v2受限Rust IPC复用，插件逐个准入；WebView无广域token/任意shell，窗口退出不停止daemon；不默认安装所有桌面插件。
- 在所属阶段通过组件准入后经Port/Adapter使用；第三方类型、隐式联网、重试与自动执行不能穿透到领域或事务层。

**实施步骤**

1. 在Tauri Rust层实现固定白名单command调用本地API。
2. 展示服务端快照、提案/影响范围、状态与取消/审批入口。
3. 验证关闭重开、过期页面和token不进入WebView资源。
4. 到M4锁定Tauri和实际使用插件，Rust只暴露白名单command；autostart只协调既有用户级生命周期，不启动第二daemon，也不为非GUI功能先索取屏幕权限。

**目标输出路径**

- `apps/desktop`
- `docs/desktop`

**正向验收**

Tauri通过Rust受限command代理连接既有API；任务/审批/配置展示服务端状态；不把广域token放WebView或开放任意shell；只展示计划摘要和执行证据。

**反例与禁止行为**

- 不得暴露任意shell command；关闭窗口不得停daemon；不展示隐藏推理。
- 未审查的shell/fs插件capability不能进入WebView；不能因插件存在就把sidecar当已沙箱化。

**验证方法**

关闭/重开UI任务持续；旧页面审批会被版本校验拒绝；无命令字符串直达shell。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第15、19、25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-083

**实现桌面接管与事件回放**

阶段 M4 · 优先级 P1 · 状态 TODO · 能力域 Desktop · 规模 M

**需求** [RQ03](requirements_traceability.md#rq03)、[RQ10](requirements_traceability.md#rq10)

**前置依赖** OB-016、OB-022、OB-075、OB-082

**先读设计** [05_storage_api.md](../docs/05_storage_api.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[02_architecture.md](../docs/02_architecture.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。接管与回放竞态可能重复或误执行动作。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** `tauri`

**复用边界（reuse_notes）**

- SSE快照重取/只读回放/接管锁仍遵守daemon语义；插件事件不是权威状态。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 实现snapshot加SSE续订以及410后的快照重取。
2. 实现接管pause和资源互斥，人工修改提升版本。
3. 验证掉线、重放、旧页面批准和human/agent冲突。
4. Tauri/SSE客户端只呈现权威快照与只读事件，插件事件不改账本；SDK断线重试不能重复批准、接管或派发。

**目标输出路径**

- `apps/desktop/src/features/timeline`
- `apps/desktop/src/features/takeover`

**正向验收**

使用snapshot加after_seq/Last-Event-ID恢复事件，过保留期410后重取；接管先暂停自动执行并获取资源锁，人工修改使旧proposal失效；回放只读。 UI关闭不改变daemon的资源归属，接管退出后须重取状态再决定恢复。

**反例与禁止行为**

- 事件回放不得重新执行工具；人工接管期间Agent不得继续点击或改写。

**验证方法**

掉线重连无漏终态；接管时自动任务不再点击/改写；回放只读不重做副作用。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第15、25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-074

**完成桌面安装签名与发布供应链**

阶段 M4 · 优先级 P1 · 状态 TODO · 能力域 Platform · 规模 M

**需求** [RQ11](requirements_traceability.md#rq11)、[RQ12](requirements_traceability.md#rq12)

**前置依赖** OB-004、OB-072、OB-073、OB-082、OB-083

**先读设计** [00_scope.md](../docs/00_scope.md)；[02_architecture.md](../docs/02_architecture.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。分发与更新链可成为代码注入入口。

**复用职责（reuse_type）** `qualification` · 准入与验证

**关联组件（component_refs）** `tauri`、`sbom-tools`、`pyinstaller`

**复用边界（reuse_notes）**

- 保留M4桌面签名、公证、更新信任根/通道；M3基础SBOM/来源与摘要前移到OB-096，不等桌面阶段。
- 本任务产生准入、反例或组合验证证据，不凭示例/import成功标记产品能力可用；未实测的真实能力继续NOT_RUN或不可用。

**实施步骤**

1. 打包Tauri、daemon与supervisor并整理许可证/SBOM。
2. 按目标OS完成签名/公证和更新签名校验，保管发布密钥。
3. 验证篡改拒绝、测试通道隔离与显式stable发布步骤。
4. 复用OB-096已完成的M3来源/SBOM/NOTICE基线，增加M4桌面签名、公证、更新信任根与通道；SBOM格式须与生成器真实输出一致。

**目标输出路径**

- `.github/workflows/release`
- `dist/sbom.spdx.json`
- `dist/SHA256SUMS`
- `docs/releases`

**正向验收**

M4交付Tauri与daemon/supervisor整体安装产物，按目标OS签名/公证或明确实验状态；SBOM/许可证/checksum随版本；更新校验签名，stable promotion显式。 CycloneDX与SPDX明确标识，签名本身不替代漏洞/许可/资产核验。

**反例与禁止行为**

- 未签名或未公证产物不得冒充已认证；测试release不能自动晋升stable。
- 不得等本任务才首次核验MVP来源，或称cyclonedx-bom输出为SPDX。

**验证方法**

篡改包/错误签名更新失败；测试release不可自动进入stable通道；不会宣称已获认证。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供至少一份实际声明平台/服务的受控集成证据及能力矩阵；mock结果单独列出，不能代替真实验证。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。


## P2 后续独立能力

### OB-027

**补充Anthropic原生Provider**

阶段 P2 · 优先级 P2 · 状态 TODO · 能力域 Runtime · 规模 M

**需求** [RQ07](requirements_traceability.md#rq07)

**前置依赖** OB-025、OB-026、OB-092

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** MEDIUM。新增适配器可能破坏已有消息与费用语义。

**复用职责（reuse_type）** `deferred` · 后续阶段适配

**关联组件（component_refs）** `model-anthropic`、`httpx`、`model-runner`

**复用边界（reuse_notes）**

- Anthropic仅P2基础请求API；禁止tool_runner及未经纳管的Provider托管工具、remote MCP和隐藏重试。
- 只在P2对应能力被实施时准入依赖；不得进入MVP默认runtime，也不得借组件自带循环扩大执行范围。

**实施步骤**

1. 记录原生Anthropic API实际版本与能力差异。
2. 适配ToolResult、停止原因、流和usage到统一Provider合同。
3. 完成合约回归与受控真实模型证据，再标supported。
4. 只允许审查过的基础messages.create/stream等请求API；禁tool_runner、托管工具和remote MCP，关闭SDK内建重试并通过统一预算/egress。

**目标输出路径**

- `services/core/src/openbot/providers/anthropic.py`

**正向验收**

后续单独支持Anthropic原生Provider，映射ToolResult、usage、stop reason与stream，不把未测试API兼容性当作已支持。 P2才安装原生Anthropic组；官方SDK自动工具helper不能因官方来源被放行。

**反例与禁止行为**

- 不得用字符串拼接模拟结构消息或未经测试承诺兼容全部模型。
- 不得调用beta.messages.tool_runner或将可执行Python函数交给SDK自动循环；外部内容不能透传任意服务端工具配置。

**验证方法**

Provider合约全通过；真实smoke记录模型版本与成本；无默认额外回退。 fake HTTP验证实际请求数、取消后新请求为0与未知usage保留；canary函数审批前为0。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供至少一份实际声明平台/服务的受控集成证据及能力矩阵；mock结果单独列出，不能代替真实验证。
- 允许SDK API表与工具helper拒绝用例、请求/预算对应记录。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第8、25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-084

**为一个OS实现原生桌面观察**

阶段 P2 · 优先级 P2 · 状态 TODO · 能力域 Platform · 规模 L

**需求** [RQ06](requirements_traceability.md#rq06)、[RQ09](requirements_traceability.md#rq09)、[RQ11](requirements_traceability.md#rq11)

**前置依赖** OB-002、OB-016、OB-037、OB-039、OB-042、OB-082、OB-089

**先读设计** [00_scope.md](../docs/00_scope.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。桌面观察含大量敏感信息且坐标不稳定。

**复用职责（reuse_type）** `deferred` · 后续阶段适配

**关联组件（component_refs）** `native-gui`、`macos-permissions`

**复用边界（reuse_notes）**

- pywinauto/PyObjC/Portal等单OS选择；权限必须运行时检查并处理撤销，不依据报告声称固定每30天行为，不强绑Tauri。
- 只在P2对应能力被实施时准入依赖；不得进入MVP默认runtime，也不得借组件自带循环扩大执行范围。

**实施步骤**

1. 只选一个OS实现控件树观察和必要截图权限检测。
2. 统一window/display/frame/scale与观察版本，分类过滤截图数据。
3. 测试多屏、DPI、锁屏、RDP及权限撤销，报告能力边界。
4. P2只选一个OS原生UIA/AX/Portal实现，按需审查pywinauto/PyObjC/权限插件；权限运行时可撤销，探测不依赖Tauri窗口存活。

**目标输出路径**

- `services/core/src/openbot/tools/desktop/observe`
- `docs/desktop-capabilities`

**正向验收**

P2先单OS实现UIA/accessibility观察与必要截图，带display/window/frame/scale/有效期；权限撤销、锁屏或RDP状态明确不可用；数据按classification处理。 不用固定“每30天”规则推断权限有效；能力状态由实际API/会话/锁屏/远程桌面环境判定。

**反例与禁止行为**

- 截图可用不等于GUI控制可用；权限不足不能黑屏死循环或自动外发截图。
- 不得自动提前安装全部OS GUI库、复用UFO自治loop，或缺权限后持续黑屏重试。

**验证方法**

缩放/多屏/焦点变化可识别；权限不足不会黑屏死循环；截图不会默认发送云或飞书。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供至少一份实际声明平台/服务的受控集成证据及能力矩阵；mock结果单独列出，不能代替真实验证。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第15、25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-085

**实现受限桌面写动作**

阶段 P2 · 优先级 P2 · 状态 TODO · 能力域 Security · 规模 L

**需求** [RQ03](requirements_traceability.md#rq03)、[RQ04](requirements_traceability.md#rq04)、[RQ09](requirements_traceability.md#rq09)

**前置依赖** OB-017、OB-018、OB-019、OB-084

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** CRITICAL。GUI写动作难以可靠幂等且可影响任意用户账户。

**复用职责（reuse_type）** `deferred` · 后续阶段适配

**关联组件（component_refs）** `native-gui`、`model-runner`

**复用边界（reuse_notes）**

- 只复用UIA/AX动作原语，逐动作审批/观察版本/互斥/UNKNOWN不变，不复用UFO推测性多动作自动提交。
- 只在P2对应能力被实施时准入依赖；不得进入MVP默认runtime，也不得借组件自带循环扩大执行范围。

**实施步骤**

1. 定义绑定观察快照与目标窗口的桌面动作。
2. 审批后复验焦点、坐标空间、目标语义和资源锁。
3. 验证真实效果或转UNKNOWN，处理人类输入和页面漂移。
4. 第三方UIA/AX库仅执行一次已批准原语；禁推测性多动作批处理和自治loop，helper不得在同一批准下继续下一步。

**目标输出路径**

- `services/core/src/openbot/tools/desktop/action`

**正向验收**

P2桌面写绑定目标应用窗口、观察版本和坐标空间；执行前复验、一次一审；不能确认效果则UNKNOWN；human/agent互斥，不以截图坐标稳定为默认假设。

**反例与禁止行为**

- 窗口/缩放/目标变化必须拒绝旧动作；不可确认提交不能再点击一次。
- 不能以库返回成功、坐标未变或视觉文本代替效果核对，未知结果不得再次提交。

**验证方法**

窗口移动、DPI变化、焦点抢占、金额变化使旧动作失败；并发human与agent动作有互斥。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第15、25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-086

**实现可验证记忆与删除**

阶段 P2 · 优先级 P2 · 状态 TODO · 能力域 Runtime · 规模 M

**需求** [RQ04](requirements_traceability.md#rq04)、[RQ06](requirements_traceability.md#rq06)、[RQ07](requirements_traceability.md#rq07)

**前置依赖** OB-024、OB-030、OB-037、OB-066

**先读设计** [06_tools_providers.md](../docs/06_tools_providers.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[05_storage_api.md](../docs/05_storage_api.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)

**风险** HIGH。长期记忆可持久化隐私或攻击指令。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** 无直接组件引用

**复用边界（reuse_notes）**

- 未新增memory框架或向量库默认依赖；证据、删除、owner/workspace隔离自研。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 实现带owner/workspace/source/有效期的非向量记忆。
2. 提供用户确认、更正、撤销和删除传播。
3. 验证跨workspace隔离、注入内容和摘要事实的不确定性。

**目标输出路径**

- `services/core/src/openbot/application/memory`
- `docs/privacy.md`

**正向验收**

P2记忆存owner/workspace/source/有效期/删除状态；仅可核对事实和确认偏好；不生成权限规则；删除后不召回，embedding另立ADR。

**反例与禁止行为**

- 记忆不能成为授权或跨workspace默认召回SENSITIVE；删除后不得继续召回旧事实。

**验证方法**

用户删除/更正后不再召回旧事实；跨workspace权限不泄漏；未证实摘要不当作用户授权。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-087

**实现持久定时触发器**

阶段 P2 · 优先级 P2 · 状态 TODO · 能力域 Runtime · 规模 M

**需求** [RQ03](requirements_traceability.md#rq03)、[RQ04](requirements_traceability.md#rq04)

**前置依赖** OB-013、OB-014、OB-015、OB-023、OB-056、OB-089

**先读设计** [00_scope.md](../docs/00_scope.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)

**风险** HIGH。自动触发增加用户不在场时的执行风险。

**复用职责（reuse_type）** `deferred` · 后续阶段适配

**关联组件（component_refs）** `scheduling-libs`

**复用边界（reuse_notes）**

- croniter/触发器仅计算时间，zoneinfo/DST/misfire/occurrence唯一性自有；不启APScheduler自动executor，首次使用不下载时区等资源。
- 只在P2对应能力被实施时准入依赖；不得进入MVP默认runtime，也不得借组件自带循环扩大执行范围。

**实施步骤**

1. 定义timezone/DST/misfire/catch-up与唯一occurrence合同。
2. 定时器仅创建普通Task，继承预算/权限/审批和取消。
3. 测试休眠、时钟变化、重启与停用schedule的未开始任务。
4. 仅复用croniter或经过审查的触发器计算模块，固定时区资源；禁APScheduler后台executor，next_time与misfire决定由OpenBot生成持久occurrence。

**目标输出路径**

- `services/core/src/openbot/application/schedules`

**正向验收**

P2持久schedule明确时区、DST、misfire、catch-up与唯一occurrence；生成普通Task且走同一policy/审批；离线错过任务不会批量执行危险动作。 计算库不获得运行函数/调用Broker的权力；首次运行缺时区资源明确失败而非下载。

**反例与禁止行为**

- 错过触发不能批量执行危险动作；时钟回拨不能重复同一occurrence。
- 不得把调度库job store变为第二Task权威，或唤醒后自动补做所有高风险积压动作。

**验证方法**

休眠错过任务不突然批量执行危险动作；时钟变化不重复执行；停用schedule撤销未开始任务。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 保留关键故障注入或并发反例的状态快照、event/operation/attempt关联与实际副作用计数；证明没有盲目重执行。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第15、25页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

### OB-088

**评估第二设备和团队扩展边界**

阶段 P2 · 优先级 P2 · 状态 TODO · 能力域 Lead · 规模 M

**需求** [RQ01](requirements_traceability.md#rq01)、[RQ04](requirements_traceability.md#rq04)、[RQ08](requirements_traceability.md#rq08)、[RQ11](requirements_traceability.md#rq11)

**前置依赖** OB-080、OB-083

**先读设计** [00_scope.md](../docs/00_scope.md)；[02_architecture.md](../docs/02_architecture.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[10_project_plan.md](../docs/10_project_plan.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)

**风险** HIGH。扩展会改变授权、队列和持久化的基本假设。

**复用职责（reuse_type）** `control_owned` · 自研控制面

**关联组件（component_refs）** 无直接组件引用

**复用边界（reuse_notes）**

- 第二设备/团队仍仅ADR实验，不为组件复用新增中央服务、共享gateway或权限模型。
- 权威状态、权限和副作用规则由OpenBot掌握；相关组件只能处理边界原语，不得取得直接派发或修改账本的权力。

**实施步骤**

1. 以单设备基线为前提列第二设备/团队场景和身份边界。
2. 验证显式设备路由、任务归属和审批绑定的小型实验。
3. 形成是否引入中央队列/共享数据库的ADR，不默认启用。

**目标输出路径**

- `docs/adr/future-multi-device.md`
- `docs/adr/future-team.md`

**正向验收**

P2仅做第二设备/团队路由ADR与隔离实验；审批绑定设备与owner；多gateway竞争消费不等于广播；通过归属/队列证据后再决定中央服务。

**反例与禁止行为**

- 多个gateway竞争消费不能当广播；一个设备的批准不能授权另一个设备的新动作。

**验证方法**

只有设计与实验，无默认启用；证明任务归属后再决定是否需要中央队列或Postgres。

**必须提交的证据**

- 提交本任务限定范围的文件变更清单；说明新增/修改的接口、状态与数据迁移。
- 提供验收与反例的可复现命令、环境/依赖版本、预期和实际结果；隐藏全部凭据。
- 提供可重复的正向用例和负向边界用例，记录任何未实现或受环境限制的能力。

**来源与修订依据**

U1《深度研究报告》PDF第13–15页MVP与CI；U2《架构设计与任务规划》PDF第26–33页WBS；本任务细化及修正以docs_refs所列本设计包基线为准。 U3《OpenBot 开源组件复用评估》PDF物理第1、26页为候选建议；本轮采纳/修正及官方证据以docs/12–14为准，不照搬未验证版本、性能或安全保证。

## 本任务包结构核验

生成时检查96个唯一ID、全部TODO、每项2—4步、至少一个反例、完整证据字段、RQ01—RQ12覆盖、已有设计引用、52项catalog ID范围、依赖和DAG。阶段分布为M0=13、M1=37、M2=11、M3=25、M4=4、P2=6；原88项ID/阶段/依赖保留。

这些结果证明任务包结构一致，真实产品行为和组件资格仍需实施任务后提交证据。详细字段差异及哈希见revision_delta.json。
