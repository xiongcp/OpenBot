# OpenBot 需求与任务追踪矩阵

版本 1.2 · 2026年11月4日 · 12类需求 · 96项待实施任务

RQ01—RQ12继续沿用v1.1分类；既有AC-RQxx-01—03保留，新增AC-RQxx-04描述组件复用的验收增量。组件是实现选择，不据此增加用户产品功能或扩张23表/14API。任务全部TODO，真实组件资格初始NOT_RUN。

每个任务的完整字段、反例与证据见 [TASKS.md](TASKS.md) 和 [backlog.json](backlog.json)；每次字段变化见 [revision_delta.json](revision_delta.json)。Q01—Q16的权威定义见 [13_component_qualification.md](../docs/13_component_qualification.md)，下表把它们连接到新旧任务。

## 用户场景到需求

| 场景 | 关联需求 | 主要证据 |
|---|---|---|
| S01 代码诊断 | RQ02、RQ04、RQ05、RQ06、RQ07、RQ08、RQ10、RQ12 | 来源路径/hash、诊断、不可变diff及未自动commit/push的证据。 |
| S02 隔离验证 | RQ03、RQ04、RQ05、RQ06、RQ08、RQ12 | 审批binding、输入快照、argv/镜像/权限、退出码与日志。 |
| S03 长任务恢复 | RQ01、RQ02、RQ03、RQ04、RQ08、RQ11、RQ12 | 崩溃点、持久状态、原审批版本、重启决定和副作用次数。 |
| S04 取消与接管 | RQ03、RQ04、RQ08、RQ10 | cancel_revision、停止新dispatch、核对中的效果及资源锁。 |
| S05 浏览器查阅 | RQ04、RQ06、RQ09、RQ12 | profile与page revision、origin/网络策略、结构数据和写动作receipt。 |
| S06 离线工作 | RQ03、RQ05、RQ06、RQ07、RQ10 | 模式/依赖组合同、真实model/runner禁云与受管出口证据；M0 fake验证与M3实际本地模型分列。 |

## 需求总览

| 需求ID | 名称 | 关联任务数 | 首要阶段 | 新增门禁任务 |
|---|---|---:|---|---|
| RQ01 | 产品范围与生命周期 | 14 | M0 | OB-093 |
| RQ02 | 持久化与数据一致性 | 16 | M0 | OB-090、OB-091 |
| RQ03 | 调度恢复与预算 | 25 | M0 | OB-091、OB-092、OB-093 |
| RQ04 | 身份策略与审批 | 26 | M0 | OB-090、OB-091 |
| RQ05 | 工作区与隔离执行 | 19 | M0 | OB-093、OB-096 |
| RQ06 | 隐私密钥与数据出口 | 26 | M0 | OB-092、OB-095 |
| RQ07 | 模型上下文与技能 | 15 | M0 | OB-089、OB-090、OB-092、OB-096 |
| RQ08 | 飞书远程闭环 | 16 | M1 | OB-092、OB-094 |
| RQ09 | 浏览器与MCP受控接入 | 18 | M0 | OB-090、OB-092、OB-095、OB-096 |
| RQ10 | 本地接口与用户控制 | 13 | M0 | 原任务补强 |
| RQ11 | 跨平台安装与更新 | 24 | M0 | OB-089、OB-093、OB-094、OB-095、OB-096 |
| RQ12 | 可观测评测与工程交付 | 31 | M0 | OB-089、OB-090、OB-091、OB-092、OB-093、OB-094、OB-095、OB-096 |

## RQ01

**产品范围与生命周期**

设计基线：[00_scope.md](../docs/00_scope.md)；[02_architecture.md](../docs/02_architecture.md)；[10_project_plan.md](../docs/10_project_plan.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)。

**验收条款**

1. **AC-RQ01-01** 单owner、单profile、单设备与单活动gateway的默认范围明确；UI和网络连接不拥有任务权威状态。
2. **AC-RQ01-02** 用户级supervisor负责常驻生命周期与唯一实例；关闭UI不终止daemon，显式stop停止后续派发并清理workers。
3. **AC-RQ01-03** 模块依赖、能力边界和未支持平台有版本化合同；scope变更通过ADR同步任务和验收。
4. **AC-RQ01-04** 组件只能提供锁/进程/服务原语；profile排他锁有唯一持有者且父子不自锁；Windows用户登录会话单独验证，UI不拥有daemon生命周期。

**必须阻断的反例**

UI关闭不得停止常驻daemon；多gateway竞争消费不能被描述为广播；未测能力不得标supported。 父supervisor和daemon不得同时争抢同一profile排他锁；service-manager系统服务不能替代Windows用户会话。

**阶段门槛与证据**

M0范围与ADR评审；M1 OB-015/042/046生命周期证据；M4 OB-082关闭重开UI验证。 OB-093首发OS原语PoC先于生产锁/worker；其余OS由OB-069—071证明。

**关联任务**

| ID | 任务 | 阶段 | 复用职责 |
|---|---|---|---|
| [OB-001](TASKS.md#ob-001) | 冻结用户场景与MVP边界 | M0 | 自研控制面 |
| [OB-003](TASKS.md#ob-003) | 冻结daemon与客户端生命周期 | M0 | 原生原语适配 |
| [OB-004](TASKS.md#ob-004) | 核验依赖和许可证 | M0 | 准入与验证 |
| [OB-005](TASKS.md#ob-005) | 建立最小仓库和工具链 | M0 | 准入与验证 |
| [OB-008](TASKS.md#ob-008) | 定义配置与网络模式 | M0 | 依赖薄适配 |
| [OB-015](TASKS.md#ob-015) | 实现单实例daemon和调度租约 | M1 | 原生原语适配 |
| [OB-042](TASKS.md#ob-042) | 实现worker进程树取消与回收 | M1 | 原生原语适配 |
| [OB-046](TASKS.md#ob-046) | 发布最小本地Alpha边界说明 | M1 | 准入与验证 |
| [OB-054](TASKS.md#ob-054) | 实现网关健康探测与重连 | M2 | 依赖薄适配 |
| [OB-068](TASKS.md#ob-068) | 实现用户级daemon安装与卸载 | M3 | 原生原语适配 |
| [OB-080](TASKS.md#ob-080) | 完成MVP发布验收与风险登记 | M3 | 准入与验证 |
| [OB-082](TASKS.md#ob-082) | 实现Tauri任务与审批UI | M4 | 依赖薄适配 |
| [OB-088](TASKS.md#ob-088) | 评估第二设备和团队扩展边界 | P2 | 自研控制面 |
| [OB-093](TASKS.md#ob-093) | 验证首发OS的Supervisor与隔离后端能力 | M1 | 准入与验证 |

## RQ02

**持久化与数据一致性**

设计基线：[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[05_storage_api.md](../docs/05_storage_api.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)。

**验收条款**

1. **AC-RQ02-01** inbox、权威状态、事件和outbox按规定事务提交；已提交任务可在进程崩溃后查询。
2. **AC-RQ02-02** 版本迁移、WAL与FULL配置、有限writer队列和磁盘故障处理可验证；不在数据库事务内等待网络或人工。
3. **AC-RQ02-03** 备份包含一致的数据库与Artifact清单；保留/清理不抹去未完成任务及仍被引用的授权证据。
4. **AC-RQ02-04** 严格JSON/JCS与深层不可变有标准向量；WriterCommand稳定request_id可关联持久结果，caller等待取消不等于事务回滚；备份期间Artifact有GC保护。

**必须阻断的反例**

提交失败不能ACK成功或继续派发；不得只复制.db遗漏WAL；事件回放不得重新运行工具。 aiosqlite await取消不证明rollback；备份不能删secret_ref或遗漏Artifact GC竞态。

**阶段门槛与证据**

M1 OB-011–014、OB-017/020/021/030；M3 OB-078/080汇总实际平台恢复与备份证明。 M0 OB-090/091先验证合同与故障；M1 writer真实提交和GC pin由OB-012/014/022/030验收。

**关联任务**

| ID | 任务 | 阶段 | 复用职责 |
|---|---|---|---|
| [OB-006](TASKS.md#ob-006) | 定义事件与命令协议 | M0 | 依赖薄适配 |
| [OB-011](TASKS.md#ob-011) | 实现带版本的数据库迁移 | M1 | 依赖薄适配 |
| [OB-012](TASKS.md#ob-012) | 实现串行写事务与数据库背压 | M1 | 依赖薄适配 |
| [OB-013](TASKS.md#ob-013) | 实现持久inbox与作用域去重 | M1 | 自研控制面 |
| [OB-014](TASKS.md#ob-014) | 实现任务状态与事件原子提交 | M1 | 自研控制面 |
| [OB-017](TASKS.md#ob-017) | 实现动作意图与执行attempt日志 | M1 | 自研控制面 |
| [OB-020](TASKS.md#ob-020) | 实现按副作用类型恢复 | M1 | 自研控制面 |
| [OB-021](TASKS.md#ob-021) | 实现durable outbox及投递状态 | M1 | 自研控制面 |
| [OB-029](TASKS.md#ob-029) | 交付首条持久化垂直切片 | M1 | 准入与验证 |
| [OB-030](TASKS.md#ob-030) | 实现数据库备份恢复与保留策略 | M1 | 依赖薄适配 |
| [OB-036](TASKS.md#ob-036) | 实现Artifact存储与可信元数据 | M1 | 自研控制面 |
| [OB-049](TASKS.md#ob-049) | 实现飞书WebSocket入站适配 | M2 | 依赖薄适配 |
| [OB-052](TASKS.md#ob-052) | 实现进度卡节流与更新顺序 | M2 | 自研控制面 |
| [OB-073](TASKS.md#ob-073) | 实现版本升级和迁移恢复 | M4 | 依赖薄适配 |
| [OB-090](TASKS.md#ob-090) | 验证Schema与JCS标准合同向量 | M0 | 准入与验证 |
| [OB-091](TASKS.md#ob-091) | 交付最小claim/dispatch崩溃协议PoC | M0 | 准入与验证 |

## RQ03

**调度恢复与预算**

设计基线：[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[02_architecture.md](../docs/02_architecture.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)。

**验收条款**

1. **AC-RQ03-01** Task、Operation、Attempt分离；CLAIMED、DISPATCHING、UNKNOWN与Task RECONCILING语义确定；dispatch_id属于Attempt，provider_idempotency_key属于Operation。
2. **AC-RQ03-02** 重试按retry_class与证据决定；仅恢复器可复用同Operation的CONSUMED关系且复验原期限、policy、actor、cancel、resource；UNKNOWN外部动作不盲重发，人工说明不能直接改成success。
3. **AC-RQ03-03** CLAIMED到DISPATCHING第二短事务复验取消、epoch与resource；同Attempt重传ID不变、新Attempt新dispatch ID；预算仍采用预留后结算，旧worker不能继续派发。
4. **AC-RQ03-04** 模型/SDK/HTTP transport只有一个重试策略负责人，每次实际请求与预算可对应；M0协议PoC与M1完整切片分开，未知外部效果不以组件成功返回推断。

**必须阻断的反例**

UNKNOWN外部动作不得盲重试或由人工一句success覆盖；CONSUMED不得退APPROVED；同Attempt重传不能换dispatch ID，新Attempt不能复用旧dispatch ID；取消/epoch/resource必须在DISPATCHING事务再次检查。 SDK与tenacity不能叠加隐式请求；cancel后的隐藏新请求必须为0。

**阶段门槛与证据**

M1 OB-015–023/029/045；M3 OB-078长时故障；后续OB-087定时触发独立验收。 OB-091早期PoC；OB-092共享故障合同；SDK实际证据随OB-025/026/027及其他适配任务产生。

**关联任务**

| ID | 任务 | 阶段 | 复用职责 |
|---|---|---|---|
| [OB-009](TASKS.md#ob-009) | 统一错误与时钟语义 | M0 | 自研控制面 |
| [OB-010](TASKS.md#ob-010) | 建立确定性系统测试夹具 | M0 | 准入与验证 |
| [OB-012](TASKS.md#ob-012) | 实现串行写事务与数据库背压 | M1 | 依赖薄适配 |
| [OB-014](TASKS.md#ob-014) | 实现任务状态与事件原子提交 | M1 | 自研控制面 |
| [OB-015](TASKS.md#ob-015) | 实现单实例daemon和调度租约 | M1 | 原生原语适配 |
| [OB-016](TASKS.md#ob-016) | 实现执行资源锁与会话排队 | M1 | 自研控制面 |
| [OB-017](TASKS.md#ob-017) | 实现动作意图与执行attempt日志 | M1 | 自研控制面 |
| [OB-019](TASKS.md#ob-019) | 实现执行前授权claim和再校验 | M1 | 自研控制面 |
| [OB-020](TASKS.md#ob-020) | 实现按副作用类型恢复 | M1 | 自研控制面 |
| [OB-022](TASKS.md#ob-022) | 实现取消和停止传播 | M1 | 自研控制面 |
| [OB-023](TASKS.md#ob-023) | 实现任务预算和熔断 | M1 | 依赖薄适配 |
| [OB-029](TASKS.md#ob-029) | 交付首条持久化垂直切片 | M1 | 准入与验证 |
| [OB-040](TASKS.md#ob-040) | 实现结构化进程执行协议 | M1 | 自研控制面 |
| [OB-044](TASKS.md#ob-044) | 实现消息发送用例与受控适配端口 | M1 | 自研控制面 |
| [OB-045](TASKS.md#ob-045) | 交付安全工具威胁回归 | M1 | 准入与验证 |
| [OB-055](TASKS.md#ob-055) | 实现死信检视与安全重投 | M2 | 自研控制面 |
| [OB-060](TASKS.md#ob-060) | 实现浏览器写动作提案与确认 | M3 | 自研控制面 |
| [OB-073](TASKS.md#ob-073) | 实现版本升级和迁移恢复 | M4 | 依赖薄适配 |
| [OB-078](TASKS.md#ob-078) | 建立断网休眠与崩溃浸泡 | M3 | 准入与验证 |
| [OB-083](TASKS.md#ob-083) | 实现桌面接管与事件回放 | M4 | 自研控制面 |
| [OB-085](TASKS.md#ob-085) | 实现受限桌面写动作 | P2 | 后续阶段适配 |
| [OB-087](TASKS.md#ob-087) | 实现持久定时触发器 | P2 | 后续阶段适配 |
| [OB-091](TASKS.md#ob-091) | 交付最小claim/dispatch崩溃协议PoC | M0 | 准入与验证 |
| [OB-092](TASKS.md#ob-092) | 建立组件副作用和重试取消故障契约 | M1 | 准入与验证 |
| [OB-093](TASKS.md#ob-093) | 验证首发OS的Supervisor与隔离后端能力 | M1 | 准入与验证 |

## RQ04

**身份策略与审批**

设计基线：[04_security_approvals.md](../docs/04_security_approvals.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[07_feishu.md](../docs/07_feishu.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)。

**验收条款**

1. **AC-RQ04-01** 身份由可信接入校验产生；配对需本地发起与最终确认；撤销后旧owner与旧卡不能继续授权。
2. **AC-RQ04-02** 提案binding覆盖身份、任务、工具、参数、资源、策略、TTL与nonce；批准、首次消费和执行结果分开；CONSUMED永不退APPROVED，安全重试只能由恢复器按原条件复验。
3. **AC-RQ04-03** ALLOW、ASK、DENY、REQUIRE_LOCAL由确定性代码判断；模型、外部文档及工具提示不能赋权或覆盖硬拒绝。
4. **AC-RQ04-04** Python构造权威canonical bytes，frozen不替代嵌套防护；同PENDING/version互斥决定最多一个成功，后续合法撤销仍能阻止未消费授权的claim/dispatch。

**必须阻断的反例**

外部is_owner/role、过期nonce、旧binding和变化参数必须拒绝；硬拒绝不能靠远程批准覆盖；CONSUMED不能二次消费、用于其他Operation或由客户端自行决定重用。 重复键、非法数值/Unicode、嵌套变异不得改变已批准内容；不提供客户端force-success。

**阶段门槛与证据**

M1 OB-018/019/031/045/081；M2 OB-048/050/056真实身份与审批；后续新工具继续复用。 OB-090标准合同向量，OB-091审批/派发反例；既有审批/恢复任务仍为生产权威。

**关联任务**

| ID | 任务 | 阶段 | 复用职责 |
|---|---|---|---|
| [OB-002](TASKS.md#ob-002) | 定义信任边界和动作副作用类别 | M0 | 自研控制面 |
| [OB-018](TASKS.md#ob-018) | 实现审批决定与一次性授权 | M1 | 依赖薄适配 |
| [OB-019](TASKS.md#ob-019) | 实现执行前授权claim和再校验 | M1 | 自研控制面 |
| [OB-022](TASKS.md#ob-022) | 实现取消和停止传播 | M1 | 自研控制面 |
| [OB-029](TASKS.md#ob-029) | 交付首条持久化垂直切片 | M1 | 准入与验证 |
| [OB-031](TASKS.md#ob-031) | 实现确定性策略评估器 | M1 | 自研控制面 |
| [OB-032](TASKS.md#ob-032) | 实现工作区路径与文件访问守卫 | M1 | 原生原语适配 |
| [OB-034](TASKS.md#ob-034) | 实现补丁提议与受授权应用 | M1 | 依赖薄适配 |
| [OB-037](TASKS.md#ob-037) | 实现统一数据外发策略 | M1 | 自研控制面 |
| [OB-041](TASKS.md#ob-041) | 实现worker隔离与资源上限 | M1 | 原生原语适配 |
| [OB-043](TASKS.md#ob-043) | 实现本地消息草稿 | M1 | 自研控制面 |
| [OB-044](TASKS.md#ob-044) | 实现消息发送用例与受控适配端口 | M1 | 自研控制面 |
| [OB-045](TASKS.md#ob-045) | 交付安全工具威胁回归 | M1 | 准入与验证 |
| [OB-048](TASKS.md#ob-048) | 实现安全配对与owner撤销 | M2 | 自研控制面 |
| [OB-050](TASKS.md#ob-050) | 实现飞书审批callback处理 | M2 | 依赖薄适配 |
| [OB-060](TASKS.md#ob-060) | 实现浏览器写动作提案与确认 | M3 | 自研控制面 |
| [OB-063](TASKS.md#ob-063) | 实现MCP注册与工具元数据锁定 | M3 | 依赖薄适配 |
| [OB-064](TASKS.md#ob-064) | 实现MCP进程和网络权限 | M3 | 依赖薄适配 |
| [OB-066](TASKS.md#ob-066) | 实现只读技能指令加载 | M3 | 自研控制面 |
| [OB-081](TASKS.md#ob-081) | 在M1实现认证本地HTTP与SSE控制API | M1 | 依赖薄适配 |
| [OB-085](TASKS.md#ob-085) | 实现受限桌面写动作 | P2 | 后续阶段适配 |
| [OB-086](TASKS.md#ob-086) | 实现可验证记忆与删除 | P2 | 自研控制面 |
| [OB-087](TASKS.md#ob-087) | 实现持久定时触发器 | P2 | 后续阶段适配 |
| [OB-088](TASKS.md#ob-088) | 评估第二设备和团队扩展边界 | P2 | 自研控制面 |
| [OB-090](TASKS.md#ob-090) | 验证Schema与JCS标准合同向量 | M0 | 准入与验证 |
| [OB-091](TASKS.md#ob-091) | 交付最小claim/dispatch崩溃协议PoC | M0 | 准入与验证 |

## RQ05

**工作区与隔离执行**

设计基线：[06_tools_providers.md](../docs/06_tools_providers.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)。

**验收条款**

1. **AC-RQ05-01** 文件读取有范围和大小上限；propose_patch只产出草稿，apply_patch核对旧hash并保护用户已有改动。
2. **AC-RQ05-02** 任意解释器/测试/构建都视为代码执行；默认只在明确受控隔离后端执行，不静默回退宿主机。
3. **AC-RQ05-03** worker只得到一次dispatch的文件/网络/凭据能力；超时、取消和崩溃由supervisor回收并保留结果证据。
4. **AC-RQ05-04** rg/Git配置和hook、native grammar与容器独立生命周期纳入执行边界；stop/wait后校验导出再remove，多文件提交使用自身journal/partial恢复而非假定跨文件原子性。

**必须阻断的反例**

不得自动host回退、挂Docker socket/全HOME或覆盖用户脏改动；测试命令不天然只读。 禁止rg --pre、未审查Git hooks/filter、运行时下载grammar和仅kill容器CLI后宣布回收。

**阶段门槛与证据**

M1 OB-032–035/040–042/045/046；M3 OB-069–072原生平台与干净安装，能力边界据实标记。 OB-093先认证首发backend；OB-096核对实际执行资产，后期原生OS分别通过。

**关联任务**

| ID | 任务 | 阶段 | 复用职责 |
|---|---|---|---|
| [OB-002](TASKS.md#ob-002) | 定义信任边界和动作副作用类别 | M0 | 自研控制面 |
| [OB-007](TASKS.md#ob-007) | 定义工具和模型Provider契约 | M0 | 自研控制面 |
| [OB-016](TASKS.md#ob-016) | 实现执行资源锁与会话排队 | M1 | 自研控制面 |
| [OB-019](TASKS.md#ob-019) | 实现执行前授权claim和再校验 | M1 | 自研控制面 |
| [OB-032](TASKS.md#ob-032) | 实现工作区路径与文件访问守卫 | M1 | 原生原语适配 |
| [OB-033](TASKS.md#ob-033) | 实现list read search文件工具 | M1 | 依赖薄适配 |
| [OB-034](TASKS.md#ob-034) | 实现补丁提议与受授权应用 | M1 | 依赖薄适配 |
| [OB-035](TASKS.md#ob-035) | 实现显式语言验证与修改事务 | M1 | 依赖薄适配 |
| [OB-040](TASKS.md#ob-040) | 实现结构化进程执行协议 | M1 | 自研控制面 |
| [OB-041](TASKS.md#ob-041) | 实现worker隔离与资源上限 | M1 | 原生原语适配 |
| [OB-042](TASKS.md#ob-042) | 实现worker进程树取消与回收 | M1 | 原生原语适配 |
| [OB-045](TASKS.md#ob-045) | 交付安全工具威胁回归 | M1 | 准入与验证 |
| [OB-046](TASKS.md#ob-046) | 发布最小本地Alpha边界说明 | M1 | 准入与验证 |
| [OB-064](TASKS.md#ob-064) | 实现MCP进程和网络权限 | M3 | 依赖薄适配 |
| [OB-069](TASKS.md#ob-069) | 建立macOS原生运行门禁 | M3 | 准入与验证 |
| [OB-070](TASKS.md#ob-070) | 建立Windows原生运行门禁 | M3 | 准入与验证 |
| [OB-071](TASKS.md#ob-071) | 建立Linux原生运行门禁 | M3 | 准入与验证 |
| [OB-093](TASKS.md#ob-093) | 验证首发OS的Supervisor与隔离后端能力 | M1 | 准入与验证 |
| [OB-096](TASKS.md#ob-096) | 验收全量交付资产来源与供应链 | M3 | 准入与验证 |

## RQ06

**隐私密钥与数据出口**

设计基线：[04_security_approvals.md](../docs/04_security_approvals.md)；[05_storage_api.md](../docs/05_storage_api.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[07_feishu.md](../docs/07_feishu.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)。

**验收条款**

1. **AC-RQ06-01** CONNECTED、LOCAL_MODEL、OFFLINE分别控制模型、飞书和工具网络；OFFLINE禁止外部连接。
2. **AC-RQ06-02** SECRET不进入模型或普通日志；SENSITIVE不自动发送云端或飞书；数据经过摘要、Artifact和通知仍保留限制。
3. **AC-RQ06-03** 凭据按用途最小注入；Artifact有hash、权限、大小与保留策略，诊断/导出经过脱敏和显式授权。
4. **AC-RQ06-04** 本地runner需model/禁云配置/实际egress证据，localhost不单独证明本地；扫描器运行时无网络验证，外部allowlist无效，扫描阴性不降低classification。

**必须阻断的反例**

OFFLINE不得连飞书或外部模型；SECRET不得进入模型/普通日志/默认诊断；摘要不能洗白数据分类。 禁止localhost转云、scanner在线验证和来自外部内容的allowlist；固定窗口不构成全面保密证明。

**阶段门槛与证据**

M1 OB-008/024/030/036–039/045/081；M2卡片与M3 Browser/MCP出口分别补真实证据。 M0 OB-008做配置/fake边界，M3 OB-026真实本地runner；OB-092/095分别验证组件/DOM出口。

**关联任务**

| ID | 任务 | 阶段 | 复用职责 |
|---|---|---|---|
| [OB-002](TASKS.md#ob-002) | 定义信任边界和动作副作用类别 | M0 | 自研控制面 |
| [OB-008](TASKS.md#ob-008) | 定义配置与网络模式 | M0 | 依赖薄适配 |
| [OB-024](TASKS.md#ob-024) | 实现上下文快照与摘要 | M1 | 自研控制面 |
| [OB-025](TASKS.md#ob-025) | 实现首个云模型适配器 | M1 | 依赖薄适配 |
| [OB-026](TASKS.md#ob-026) | 实现Ollama或第二Provider | M3 | 依赖薄适配 |
| [OB-030](TASKS.md#ob-030) | 实现数据库备份恢复与保留策略 | M1 | 依赖薄适配 |
| [OB-033](TASKS.md#ob-033) | 实现list read search文件工具 | M1 | 依赖薄适配 |
| [OB-036](TASKS.md#ob-036) | 实现Artifact存储与可信元数据 | M1 | 自研控制面 |
| [OB-037](TASKS.md#ob-037) | 实现统一数据外发策略 | M1 | 自研控制面 |
| [OB-038](TASKS.md#ob-038) | 实现密钥存储与最小注入 | M1 | 依赖薄适配 |
| [OB-039](TASKS.md#ob-039) | 实现敏感数据输出过滤 | M1 | 依赖薄适配 |
| [OB-041](TASKS.md#ob-041) | 实现worker隔离与资源上限 | M1 | 原生原语适配 |
| [OB-043](TASKS.md#ob-043) | 实现本地消息草稿 | M1 | 自研控制面 |
| [OB-044](TASKS.md#ob-044) | 实现消息发送用例与受控适配端口 | M1 | 自研控制面 |
| [OB-045](TASKS.md#ob-045) | 交付安全工具威胁回归 | M1 | 准入与验证 |
| [OB-051](TASKS.md#ob-051) | 实现普通卡片与结果回执 | M2 | 依赖薄适配 |
| [OB-057](TASKS.md#ob-057) | 实现专用浏览器profile与会话锁 | M3 | 依赖薄适配 |
| [OB-058](TASKS.md#ob-058) | 实现浏览器网络与下载策略 | M3 | 依赖薄适配 |
| [OB-064](TASKS.md#ob-064) | 实现MCP进程和网络权限 | M3 | 依赖薄适配 |
| [OB-075](TASKS.md#ob-075) | 实现统一可观测性与诊断 | M3 | 依赖薄适配 |
| [OB-081](TASKS.md#ob-081) | 在M1实现认证本地HTTP与SSE控制API | M1 | 依赖薄适配 |
| [OB-082](TASKS.md#ob-082) | 实现Tauri任务与审批UI | M4 | 依赖薄适配 |
| [OB-084](TASKS.md#ob-084) | 为一个OS实现原生桌面观察 | P2 | 后续阶段适配 |
| [OB-086](TASKS.md#ob-086) | 实现可验证记忆与删除 | P2 | 自研控制面 |
| [OB-092](TASKS.md#ob-092) | 建立组件副作用和重试取消故障契约 | M1 | 准入与验证 |
| [OB-095](TASKS.md#ob-095) | 审查DOM提取脚本的最小源码复用 | M3 | 源码参考/摘取审查 |

## RQ07

**模型上下文与技能**

设计基线：[06_tools_providers.md](../docs/06_tools_providers.md)；[00_scope.md](../docs/00_scope.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)。

**验收条款**

1. **AC-RQ07-01** M1具备一个Provider适配合同；完整MVP至少一个云Provider与一个本地Provider，能力差异明确。
2. **AC-RQ07-02** 半包或畸形tool call不执行；调用用量与错误可追踪；模型重试不会触发重复工具效果或隐式云回退。
3. **AC-RQ07-03** 上下文、摘要和技能保留来源与用户约束；模型文字和学习到的偏好不能变成授权。
4. **AC-RQ07-04** SDK只用获准基础请求API；禁止tool_runner、未纳管Provider托管工具/remote MCP；tokenizer按模型预估并预置资产，未知usage保守保留。

**必须阻断的反例**

半包/畸形工具调用不能执行；Provider重试不能重放工具；未知能力不能伪装成功。 官方SDK自动helper、任意extra_body/extra_headers和Provider托管执行不得穿透Broker。

**阶段门槛与证据**

M1 OB-007/023–025；M3 OB-026/066/067/076；OB-027第三Provider后续独立验收。 OB-089分组准入、OB-090完整Schema、OB-092唯一重试/自动执行反例，OB-096发布tokenizer等资产。

**关联任务**

| ID | 任务 | 阶段 | 复用职责 |
|---|---|---|---|
| [OB-007](TASKS.md#ob-007) | 定义工具和模型Provider契约 | M0 | 自研控制面 |
| [OB-023](TASKS.md#ob-023) | 实现任务预算和熔断 | M1 | 依赖薄适配 |
| [OB-024](TASKS.md#ob-024) | 实现上下文快照与摘要 | M1 | 自研控制面 |
| [OB-025](TASKS.md#ob-025) | 实现首个云模型适配器 | M1 | 依赖薄适配 |
| [OB-026](TASKS.md#ob-026) | 实现Ollama或第二Provider | M3 | 依赖薄适配 |
| [OB-027](TASKS.md#ob-027) | 补充Anthropic原生Provider | P2 | 后续阶段适配 |
| [OB-059](TASKS.md#ob-059) | 实现结构化浏览器读工具 | M3 | 依赖薄适配 |
| [OB-066](TASKS.md#ob-066) | 实现只读技能指令加载 | M3 | 自研控制面 |
| [OB-067](TASKS.md#ob-067) | 交付全MVP能力集回归 | M3 | 准入与验证 |
| [OB-076](TASKS.md#ob-076) | 建立真实任务质量基准集 | M3 | 准入与验证 |
| [OB-086](TASKS.md#ob-086) | 实现可验证记忆与删除 | P2 | 自研控制面 |
| [OB-089](TASKS.md#ob-089) | 建立组件准入目录和分阶段依赖门禁 | M0 | 准入与验证 |
| [OB-090](TASKS.md#ob-090) | 验证Schema与JCS标准合同向量 | M0 | 准入与验证 |
| [OB-092](TASKS.md#ob-092) | 建立组件副作用和重试取消故障契约 | M1 | 准入与验证 |
| [OB-096](TASKS.md#ob-096) | 验收全量交付资产来源与供应链 | M3 | 准入与验证 |

## RQ08

**飞书远程闭环**

设计基线：[00_scope.md](../docs/00_scope.md)；[02_architecture.md](../docs/02_architecture.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[05_storage_api.md](../docs/05_storage_api.md)；[07_feishu.md](../docs/07_feishu.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)。

**验收条款**

1. **AC-RQ08-01** 单gateway将经过校验的入站交给daemon，提交成功后才确认；重复/乱序事件只产生一个逻辑任务。
2. **AC-RQ08-02** 消息事件与审批callback分开处理；同步响应不等待模型；普通卡片基线可用，更新具有顺序、节流与降级。
3. **AC-RQ08-03** 重连、网络半开、休眠、死信和外发结果不明均可诊断；冷启动、WS连接与callback响应分别度量。
4. **AC-RQ08-04** 锁定SDK真实协议与分段启动/回调证据；hard deadline位于可能阻塞进程之外；模板NO_COPY或有限摘取不改变owner、CAS、outbox权威。

**必须阻断的反例**

gateway不能自定owner或直连DB；数据库提交失败不能回复已批准；迟到进度不能覆盖终态。 不能套用固定冷启动数字/所有卡片通用时限，也不能在旧gateway未退出时重建第二消费者。

**阶段门槛与证据**

M1 inbox/outbox端口；M2 OB-047–056真实租户整体验证；M3 OB-078浸泡。 OB-094明确NO_COPY或有限摘取；OB-047/054分别核对版本事实和进程外监督。

**关联任务**

| ID | 任务 | 阶段 | 复用职责 |
|---|---|---|---|
| [OB-013](TASKS.md#ob-013) | 实现持久inbox与作用域去重 | M1 | 自研控制面 |
| [OB-021](TASKS.md#ob-021) | 实现durable outbox及投递状态 | M1 | 自研控制面 |
| [OB-047](TASKS.md#ob-047) | 核验飞书真实租户协议与权限 | M2 | 准入与验证 |
| [OB-048](TASKS.md#ob-048) | 实现安全配对与owner撤销 | M2 | 自研控制面 |
| [OB-049](TASKS.md#ob-049) | 实现飞书WebSocket入站适配 | M2 | 依赖薄适配 |
| [OB-050](TASKS.md#ob-050) | 实现飞书审批callback处理 | M2 | 依赖薄适配 |
| [OB-051](TASKS.md#ob-051) | 实现普通卡片与结果回执 | M2 | 依赖薄适配 |
| [OB-052](TASKS.md#ob-052) | 实现进度卡节流与更新顺序 | M2 | 自研控制面 |
| [OB-053](TASKS.md#ob-053) | 实现CardKit与更新通道降级 | M2 | 依赖薄适配 |
| [OB-054](TASKS.md#ob-054) | 实现网关健康探测与重连 | M2 | 依赖薄适配 |
| [OB-055](TASKS.md#ob-055) | 实现死信检视与安全重投 | M2 | 自研控制面 |
| [OB-056](TASKS.md#ob-056) | 飞书端到端真实验收 | M2 | 准入与验证 |
| [OB-067](TASKS.md#ob-067) | 交付全MVP能力集回归 | M3 | 准入与验证 |
| [OB-088](TASKS.md#ob-088) | 评估第二设备和团队扩展边界 | P2 | 自研控制面 |
| [OB-092](TASKS.md#ob-092) | 建立组件副作用和重试取消故障契约 | M1 | 准入与验证 |
| [OB-094](TASKS.md#ob-094) | 审查飞书模板的最小源码复用 | M2 | 源码参考/摘取审查 |

## RQ09

**浏览器与MCP受控接入**

设计基线：[06_tools_providers.md](../docs/06_tools_providers.md)；[04_security_approvals.md](../docs/04_security_approvals.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)。

**验收条款**

1. **AC-RQ09-01** 专用浏览器profile与page revision控制会话和动作；写操作绑定目标、输入与页面版本，外部结果需要证据。
2. **AC-RQ09-02** 导航、重定向、上传下载和子请求遵守网络/数据策略；无法强制所需边界时能力不可用。
3. **AC-RQ09-03** MVP先支持固定版本stdio MCP；安装与运行分离，工具元数据变化隔离；外部annotations不直接决定权限或重试。
4. **AC-RQ09-04** Chromium sandbox显式配置并验证，Service Worker绕过路由须阻断或由独立网络边界覆盖；完整MCP manifest、受限stdio与本地Schema refs不因SDK默认值放宽。

**必须阻断的反例**

不得复制默认浏览器profile、沿用变化页面的旧批准或在任务运行中安装MCP latest；未知效果不能再提交。 不得暗加--no-sandbox或仅靠BrowserContext.route / Page.route声称强隔离；DOM源码参考不能引入自治循环。

**阶段门槛与证据**

M3 OB-057–065/067；原生GUI在P2 OB-084/085独立验收，不能计入MVP已实现能力。 OB-095源码比较决定，OB-090/092共享合同，OB-096核对浏览器/MCP及grammar资产。

**关联任务**

| ID | 任务 | 阶段 | 复用职责 |
|---|---|---|---|
| [OB-007](TASKS.md#ob-007) | 定义工具和模型Provider契约 | M0 | 自研控制面 |
| [OB-016](TASKS.md#ob-016) | 实现执行资源锁与会话排队 | M1 | 自研控制面 |
| [OB-057](TASKS.md#ob-057) | 实现专用浏览器profile与会话锁 | M3 | 依赖薄适配 |
| [OB-058](TASKS.md#ob-058) | 实现浏览器网络与下载策略 | M3 | 依赖薄适配 |
| [OB-059](TASKS.md#ob-059) | 实现结构化浏览器读工具 | M3 | 依赖薄适配 |
| [OB-060](TASKS.md#ob-060) | 实现浏览器写动作提案与确认 | M3 | 自研控制面 |
| [OB-061](TASKS.md#ob-061) | 建立浏览器结果验证回归 | M3 | 准入与验证 |
| [OB-062](TASKS.md#ob-062) | 实现MCP版本协商与生命周期 | M3 | 依赖薄适配 |
| [OB-063](TASKS.md#ob-063) | 实现MCP注册与工具元数据锁定 | M3 | 依赖薄适配 |
| [OB-064](TASKS.md#ob-064) | 实现MCP进程和网络权限 | M3 | 依赖薄适配 |
| [OB-065](TASKS.md#ob-065) | 建立MCP恶意与故障服务器测试 | M3 | 准入与验证 |
| [OB-067](TASKS.md#ob-067) | 交付全MVP能力集回归 | M3 | 准入与验证 |
| [OB-084](TASKS.md#ob-084) | 为一个OS实现原生桌面观察 | P2 | 后续阶段适配 |
| [OB-085](TASKS.md#ob-085) | 实现受限桌面写动作 | P2 | 后续阶段适配 |
| [OB-090](TASKS.md#ob-090) | 验证Schema与JCS标准合同向量 | M0 | 准入与验证 |
| [OB-092](TASKS.md#ob-092) | 建立组件副作用和重试取消故障契约 | M1 | 准入与验证 |
| [OB-095](TASKS.md#ob-095) | 审查DOM提取脚本的最小源码复用 | M3 | 源码参考/摘取审查 |
| [OB-096](TASKS.md#ob-096) | 验收全量交付资产来源与供应链 | M3 | 准入与验证 |

## RQ10

**本地接口与用户控制**

设计基线：[02_architecture.md](../docs/02_architecture.md)；[05_storage_api.md](../docs/05_storage_api.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[10_project_plan.md](../docs/10_project_plan.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)。

**验收条款**

1. **AC-RQ10-01** M1即提供认证loopback HTTP与SSE；Host、Origin、profile范围、大小限制和受保护token传递得到验证。
2. **AC-RQ10-02** CLI/gateway调用application/API，不直连DB；用户可查看、批准、取消、恢复并提交核对证据，不能以指定success覆盖账本或自行允许CONSUMED复用。
3. **AC-RQ10-03** M4 Tauri通过受限接口展示计划摘要、提案、策略和执行证据；重连与接管不重放工具或显示隐藏推理。
4. **AC-RQ10-04** API/CLI/UI组件只提供传输和呈现；严格输入、Host/Origin/proxy/scope、SSE游标/背压和writer断连后持久结果均能核对；不要求UI重复实现权威JCS。

**必须阻断的反例**

跨源/非loopback/错profile请求必须拒绝；WebView不持广域token；客户端不得绕过application，reconcile不得接收force-success或grant恢复许可。 框架默认CORS/proxy/Schema处理不得扩大owner权限；终端输出不能注入控制序列或伪造审批。

**阶段门槛与证据**

M1 OB-081先于OB-028/029；M2 gateway接入；M4 OB-082/083桌面观察与接管。 OB-081复用标准校验和API框架，OB-090以Python权威端验证；窗口退出不改daemon。

**关联任务**

| ID | 任务 | 阶段 | 复用职责 |
|---|---|---|---|
| [OB-006](TASKS.md#ob-006) | 定义事件与命令协议 | M0 | 依赖薄适配 |
| [OB-009](TASKS.md#ob-009) | 统一错误与时钟语义 | M0 | 自研控制面 |
| [OB-028](TASKS.md#ob-028) | 提供CLI任务和审批操作 | M1 | 依赖薄适配 |
| [OB-029](TASKS.md#ob-029) | 交付首条持久化垂直切片 | M1 | 准入与验证 |
| [OB-046](TASKS.md#ob-046) | 发布最小本地Alpha边界说明 | M1 | 准入与验证 |
| [OB-048](TASKS.md#ob-048) | 实现安全配对与owner撤销 | M2 | 自研控制面 |
| [OB-049](TASKS.md#ob-049) | 实现飞书WebSocket入站适配 | M2 | 依赖薄适配 |
| [OB-055](TASKS.md#ob-055) | 实现死信检视与安全重投 | M2 | 自研控制面 |
| [OB-075](TASKS.md#ob-075) | 实现统一可观测性与诊断 | M3 | 依赖薄适配 |
| [OB-079](TASKS.md#ob-079) | 完成上手与故障处置文档 | M3 | 准入与验证 |
| [OB-081](TASKS.md#ob-081) | 在M1实现认证本地HTTP与SSE控制API | M1 | 依赖薄适配 |
| [OB-082](TASKS.md#ob-082) | 实现Tauri任务与审批UI | M4 | 依赖薄适配 |
| [OB-083](TASKS.md#ob-083) | 实现桌面接管与事件回放 | M4 | 自研控制面 |

## RQ11

**跨平台安装与更新**

设计基线：[00_scope.md](../docs/00_scope.md)；[02_architecture.md](../docs/02_architecture.md)；[05_storage_api.md](../docs/05_storage_api.md)；[08_desktop_release.md](../docs/08_desktop_release.md)；[10_project_plan.md](../docs/10_project_plan.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)。

**验收条款**

1. **AC-RQ11-01** 基础合同从M0运行三OS CI；M3在macOS、原生Windows、Linux分别验证CLI和所声明能力，未通过不标supported。
2. **AC-RQ11-02** 安装器声明Python/浏览器/隔离后端依赖，用户级服务可启停/卸载，不能误删工作区或秘密数据。
3. **AC-RQ11-03** M4签名与升级流程校验产物、先drain和备份再迁移；数据库不兼容时不能盲降级旧程序。
4. **AC-RQ11-04** 按阶段准入并锁定包与非包资产，M3全量SBOM/NOTICE/hash/离线首用已经完成；M4桌面签名独立，不借SDK或安装器的跨平台名称冒称原生资格。

**必须阻断的反例**

WSL不能替代Windows原生资格；未签名产物不能称已签名；不兼容DB不能直接降级旧binary。 M0不得整包安装后续候选；不能混淆SPDX/CycloneDX、漏非Python资产或把未签名包称签名Beta。

**阶段门槛与证据**

M0 OB-005基础矩阵；M3 OB-068–072与OB-080完整CLI安装；M4 OB-073/074更新签名。 M0 OB-089、M1 OB-093、M2 OB-094、M3 OB-095/096随阶段落地，禁止M0一次预装全部候选。

**关联任务**

| ID | 任务 | 阶段 | 复用职责 |
|---|---|---|---|
| [OB-003](TASKS.md#ob-003) | 冻结daemon与客户端生命周期 | M0 | 原生原语适配 |
| [OB-004](TASKS.md#ob-004) | 核验依赖和许可证 | M0 | 准入与验证 |
| [OB-005](TASKS.md#ob-005) | 建立最小仓库和工具链 | M0 | 准入与验证 |
| [OB-030](TASKS.md#ob-030) | 实现数据库备份恢复与保留策略 | M1 | 依赖薄适配 |
| [OB-038](TASKS.md#ob-038) | 实现密钥存储与最小注入 | M1 | 依赖薄适配 |
| [OB-042](TASKS.md#ob-042) | 实现worker进程树取消与回收 | M1 | 原生原语适配 |
| [OB-068](TASKS.md#ob-068) | 实现用户级daemon安装与卸载 | M3 | 原生原语适配 |
| [OB-069](TASKS.md#ob-069) | 建立macOS原生运行门禁 | M3 | 准入与验证 |
| [OB-070](TASKS.md#ob-070) | 建立Windows原生运行门禁 | M3 | 准入与验证 |
| [OB-071](TASKS.md#ob-071) | 建立Linux原生运行门禁 | M3 | 准入与验证 |
| [OB-072](TASKS.md#ob-072) | 建立可复现打包与运行资源清单 | M3 | 准入与验证 |
| [OB-073](TASKS.md#ob-073) | 实现版本升级和迁移恢复 | M4 | 依赖薄适配 |
| [OB-074](TASKS.md#ob-074) | 完成桌面安装签名与发布供应链 | M4 | 准入与验证 |
| [OB-077](TASKS.md#ob-077) | 建立分层CI门禁 | M3 | 准入与验证 |
| [OB-078](TASKS.md#ob-078) | 建立断网休眠与崩溃浸泡 | M3 | 准入与验证 |
| [OB-079](TASKS.md#ob-079) | 完成上手与故障处置文档 | M3 | 准入与验证 |
| [OB-080](TASKS.md#ob-080) | 完成MVP发布验收与风险登记 | M3 | 准入与验证 |
| [OB-084](TASKS.md#ob-084) | 为一个OS实现原生桌面观察 | P2 | 后续阶段适配 |
| [OB-088](TASKS.md#ob-088) | 评估第二设备和团队扩展边界 | P2 | 自研控制面 |
| [OB-089](TASKS.md#ob-089) | 建立组件准入目录和分阶段依赖门禁 | M0 | 准入与验证 |
| [OB-093](TASKS.md#ob-093) | 验证首发OS的Supervisor与隔离后端能力 | M1 | 准入与验证 |
| [OB-094](TASKS.md#ob-094) | 审查飞书模板的最小源码复用 | M2 | 源码参考/摘取审查 |
| [OB-095](TASKS.md#ob-095) | 审查DOM提取脚本的最小源码复用 | M3 | 源码参考/摘取审查 |
| [OB-096](TASKS.md#ob-096) | 验收全量交付资产来源与供应链 | M3 | 准入与验证 |

## RQ12

**可观测评测与工程交付**

设计基线：[00_scope.md](../docs/00_scope.md)；[01_gap_review.md](../docs/01_gap_review.md)；[03_runtime_recovery.md](../docs/03_runtime_recovery.md)；[05_storage_api.md](../docs/05_storage_api.md)；[06_tools_providers.md](../docs/06_tools_providers.md)；[09_testing_operations.md](../docs/09_testing_operations.md)；[10_project_plan.md](../docs/10_project_plan.md)；[11_decisions_evidence.md](../docs/11_decisions_evidence.md)；[12_component_reuse.md](../docs/12_component_reuse.md)；[13_component_qualification.md](../docs/13_component_qualification.md)；[14_revision_v1_2.md](../docs/14_revision_v1_2.md)。

**验收条款**

1. **AC-RQ12-01** 关键边界在M1/M2随功能测试，不拖至发布前；PR、nightly和release门禁按风险分层。
2. **AC-RQ12-02** 真实任务基准区分安全、协议和模型能力；记录样本、版本、成功/部分/失败/待核对结果、成本和延迟。
3. **AC-RQ12-03** 任务具备依赖、反例和证据；仓库接口与迁移有owner，交接文件、运行手册和风险登记可以独立复现。
4. **AC-RQ12-04** 组件选择、当前真实资格NOT_RUN/证据、复用边界与变更delta可追踪；只重跑受影响门禁，不以LOC、Stars、固定倍数或工期承诺代替测量。

**必须阻断的反例**

mock不代表真实能力；模型final不代表效果完成；不得删除门禁或扩大权限换取“通过”。 审阅源码不等于真实环境测试；NOT_RUN不能被文档完成、import成功或fake通过自动改成资格通过。

**阶段门槛与证据**

各阶段随任务提交证据；M1 OB-029/045、M2 OB-056、M3 OB-076–080组成集成与发布门槛。 OB-089—096提供独立门禁；每次变更记录受影响Q项，NO_COPY无须虚构vendor测试。

**关联任务**

| ID | 任务 | 阶段 | 复用职责 |
|---|---|---|---|
| [OB-001](TASKS.md#ob-001) | 冻结用户场景与MVP边界 | M0 | 自研控制面 |
| [OB-004](TASKS.md#ob-004) | 核验依赖和许可证 | M0 | 准入与验证 |
| [OB-005](TASKS.md#ob-005) | 建立最小仓库和工具链 | M0 | 准入与验证 |
| [OB-010](TASKS.md#ob-010) | 建立确定性系统测试夹具 | M0 | 准入与验证 |
| [OB-029](TASKS.md#ob-029) | 交付首条持久化垂直切片 | M1 | 准入与验证 |
| [OB-035](TASKS.md#ob-035) | 实现显式语言验证与修改事务 | M1 | 依赖薄适配 |
| [OB-039](TASKS.md#ob-039) | 实现敏感数据输出过滤 | M1 | 依赖薄适配 |
| [OB-045](TASKS.md#ob-045) | 交付安全工具威胁回归 | M1 | 准入与验证 |
| [OB-046](TASKS.md#ob-046) | 发布最小本地Alpha边界说明 | M1 | 准入与验证 |
| [OB-047](TASKS.md#ob-047) | 核验飞书真实租户协议与权限 | M2 | 准入与验证 |
| [OB-054](TASKS.md#ob-054) | 实现网关健康探测与重连 | M2 | 依赖薄适配 |
| [OB-056](TASKS.md#ob-056) | 飞书端到端真实验收 | M2 | 准入与验证 |
| [OB-061](TASKS.md#ob-061) | 建立浏览器结果验证回归 | M3 | 准入与验证 |
| [OB-065](TASKS.md#ob-065) | 建立MCP恶意与故障服务器测试 | M3 | 准入与验证 |
| [OB-067](TASKS.md#ob-067) | 交付全MVP能力集回归 | M3 | 准入与验证 |
| [OB-072](TASKS.md#ob-072) | 建立可复现打包与运行资源清单 | M3 | 准入与验证 |
| [OB-074](TASKS.md#ob-074) | 完成桌面安装签名与发布供应链 | M4 | 准入与验证 |
| [OB-075](TASKS.md#ob-075) | 实现统一可观测性与诊断 | M3 | 依赖薄适配 |
| [OB-076](TASKS.md#ob-076) | 建立真实任务质量基准集 | M3 | 准入与验证 |
| [OB-077](TASKS.md#ob-077) | 建立分层CI门禁 | M3 | 准入与验证 |
| [OB-078](TASKS.md#ob-078) | 建立断网休眠与崩溃浸泡 | M3 | 准入与验证 |
| [OB-079](TASKS.md#ob-079) | 完成上手与故障处置文档 | M3 | 准入与验证 |
| [OB-080](TASKS.md#ob-080) | 完成MVP发布验收与风险登记 | M3 | 准入与验证 |
| [OB-089](TASKS.md#ob-089) | 建立组件准入目录和分阶段依赖门禁 | M0 | 准入与验证 |
| [OB-090](TASKS.md#ob-090) | 验证Schema与JCS标准合同向量 | M0 | 准入与验证 |
| [OB-091](TASKS.md#ob-091) | 交付最小claim/dispatch崩溃协议PoC | M0 | 准入与验证 |
| [OB-092](TASKS.md#ob-092) | 建立组件副作用和重试取消故障契约 | M1 | 准入与验证 |
| [OB-093](TASKS.md#ob-093) | 验证首发OS的Supervisor与隔离后端能力 | M1 | 准入与验证 |
| [OB-094](TASKS.md#ob-094) | 审查飞书模板的最小源码复用 | M2 | 源码参考/摘取审查 |
| [OB-095](TASKS.md#ob-095) | 审查DOM提取脚本的最小源码复用 | M3 | 源码参考/摘取审查 |
| [OB-096](TASKS.md#ob-096) | 验收全量交付资产来源与供应链 | M3 | 准入与验证 |

## 组件资格场景到任务

Q场景按所在阶段运行实际实现，M0的合同/夹具不会提前安装后续组件。NO_COPY只需明确比较与理由；摘取专属测试只有选择实际摘取时适用。

| Q ID | 验证主题 | 时点 | 任务 |
|---|---|---|---|
| Q01 | 最小依赖、导入/首次使用与离线资产 | M0合同；后续实际组件随阶段 | [OB-005](TASKS.md#ob-005)、[OB-008](TASKS.md#ob-008)、[OB-072](TASKS.md#ob-072)、[OB-089](TASKS.md#ob-089)、[OB-092](TASKS.md#ob-092) |
| Q02 | 严格JSON与标准JCS向量 | M0；生产binding随M1/M3 | [OB-006](TASKS.md#ob-006)、[OB-007](TASKS.md#ob-007)、[OB-018](TASKS.md#ob-018)、[OB-063](TASKS.md#ob-063)、[OB-090](TASKS.md#ob-090) |
| Q03 | 深层不可变、完整Schema/format/refs | M0；API和MCP接入时复验 | [OB-006](TASKS.md#ob-006)、[OB-007](TASKS.md#ob-007)、[OB-081](TASKS.md#ob-081)、[OB-090](TASKS.md#ob-090) |
| Q04 | 模型请求重试、预算、本地runner转云 | M1云；M3本地；P2原生Anthropic | [OB-023](TASKS.md#ob-023)、[OB-025](TASKS.md#ob-025)、[OB-026](TASKS.md#ob-026)、[OB-027](TASKS.md#ob-027)、[OB-092](TASKS.md#ob-092) |
| Q05 | writer、caller取消、迁移/备份/GC pin | M0协议；M1生产 | [OB-011](TASKS.md#ob-011)、[OB-012](TASKS.md#ob-012)、[OB-013](TASKS.md#ob-013)、[OB-014](TASKS.md#ob-014)、[OB-018](TASKS.md#ob-018)、[OB-019](TASKS.md#ob-019)、[OB-020](TASKS.md#ob-020)、[OB-022](TASKS.md#ob-022)、[OB-030](TASKS.md#ob-030)、[OB-091](TASKS.md#ob-091) |
| Q06 | 路径、rg/Git配置、补丁、partial提交 | M1 | [OB-032](TASKS.md#ob-032)、[OB-033](TASKS.md#ob-033)、[OB-034](TASKS.md#ob-034)、[OB-035](TASKS.md#ob-035) |
| Q07 | native parser、资产与有界worker | M1；M3三OS发行 | [OB-035](TASKS.md#ob-035)、[OB-041](TASKS.md#ob-041)、[OB-093](TASKS.md#ob-093)、[OB-096](TASKS.md#ob-096) |
| Q08 | 容器隔离、独立归属、导出与清理 | M1 | [OB-040](TASKS.md#ob-040)、[OB-041](TASKS.md#ob-041)、[OB-042](TASKS.md#ob-042)、[OB-093](TASKS.md#ob-093) |
| Q09 | 原生锁/Job/进程树/用户会话 | M1首发；M3三OS | [OB-015](TASKS.md#ob-015)、[OB-042](TASKS.md#ob-042)、[OB-068](TASKS.md#ob-068)、[OB-069](TASKS.md#ob-069)、[OB-070](TASKS.md#ob-070)、[OB-071](TASKS.md#ob-071)、[OB-093](TASKS.md#ob-093) |
| Q10 | 飞书SDK/外部watchdog/真实回调 | M2 | [OB-047](TASKS.md#ob-047)、[OB-049](TASKS.md#ob-049)、[OB-050](TASKS.md#ob-050)、[OB-051](TASKS.md#ob-051)、[OB-052](TASKS.md#ob-052)、[OB-053](TASKS.md#ob-053)、[OB-054](TASKS.md#ob-054)、[OB-055](TASKS.md#ob-055)、[OB-056](TASKS.md#ob-056) |
| Q11 | Browser sandbox/SW/页面绑定/UNKNOWN | M3 | [OB-057](TASKS.md#ob-057)、[OB-058](TASKS.md#ob-058)、[OB-059](TASKS.md#ob-059)、[OB-060](TASKS.md#ob-060)、[OB-061](TASKS.md#ob-061)、[OB-095](TASKS.md#ob-095) |
| Q12 | MCP协议/环境/定义固定/恶意server | M3 | [OB-062](TASKS.md#ob-062)、[OB-063](TASKS.md#ob-063)、[OB-064](TASKS.md#ob-064)、[OB-065](TASKS.md#ob-065)、[OB-092](TASKS.md#ob-092) |
| Q13 | 跨chunk、scanner离线/allowlist、日志 | M1；M3观测汇总 | [OB-037](TASKS.md#ob-037)、[OB-038](TASKS.md#ob-038)、[OB-039](TASKS.md#ob-039)、[OB-075](TASKS.md#ob-075)、[OB-092](TASKS.md#ob-092) |
| Q14 | 来源比较、NO_COPY或有限摘取 | M0规则；M2/M3来源决定 | [OB-004](TASKS.md#ob-004)、[OB-051](TASKS.md#ob-051)、[OB-059](TASKS.md#ob-059)、[OB-089](TASKS.md#ob-089)、[OB-094](TASKS.md#ob-094)、[OB-095](TASKS.md#ob-095) |
| Q15 | 全生态锁、非包资产、SBOM/NOTICE | M0记录；M3发布；M4签名增量 | [OB-066](TASKS.md#ob-066)、[OB-072](TASKS.md#ob-072)、[OB-073](TASKS.md#ob-073)、[OB-074](TASKS.md#ob-074)、[OB-089](TASKS.md#ob-089)、[OB-096](TASKS.md#ob-096) |
| Q16 | 早期claim/dispatch协议PoC与M1切片 | M0 PoC；M1完整集成 | [OB-010](TASKS.md#ob-010)、[OB-017](TASKS.md#ob-017)、[OB-018](TASKS.md#ob-018)、[OB-019](TASKS.md#ob-019)、[OB-020](TASKS.md#ob-020)、[OB-029](TASKS.md#ob-029)、[OB-090](TASKS.md#ob-090)、[OB-091](TASKS.md#ob-091) |

## 新报告到工程验收的增量

页码为U3《OpenBot 开源组件复用评估》PDF物理页码。下表将候选建议、修订及可检查证据分开，具体官方来源和事实核验见docs/12—14。

| U3位置与主题 | 修订 | 任务及证据 |
|---|---|---|
| p1—3、21、26：自研控制面 | 保留四对象/两事务/UNKNOWN/egress，增最早协议PoC | OB-017—022、091；持久状态与效果计数 |
| p7、20—21：Pydantic/JCS/Schema | UTF-16标准向量、深层不可变、重复键/完整Schema/format/本地refs；Python权威 | OB-006/007/018/063/090；规范字节与拒绝用例 |
| p7、20—21：异步SQLite与backup | 完整WriterCommand独占、稳定请求ID、取消后持久重查、Artifact GC pin和secret_ref有效性 | OB-011/012/014/022/030；并发/提交/GC反例 |
| p8—9、16、21—22：官方SDK与重试 | API白名单、SDK/transport重试关闭、统一预算、禁tool_runner/托管工具；本地runner另验云路由 | OB-008/023/025—027/037/092；HTTP尝试计数与实际egress |
| p12、17、22：ACI与grammar | rg --no-config/禁--pre；Git hooks/filter；确切新字节hash；有界native parser和安装期资产 | OB-032—035/040/045/096；canary、journal与禁网首parse |
| p9—10、23：飞书SDK/社区模板 | 真实版本/分段计时/外部watchdog；模板NO_COPY或有限摘取 | OB-047—056/094；真实payload、回调和来源决定 |
| p12—14、18、23、25：进程/容器/服务 | 原语逐OS验证、唯一锁所有者、容器独立stop/wait→导出校验→remove、Windows用户会话单独设计 | OB-015/041/042/068—072/093；进程/容器归属证据 |
| p13、18、24：Browser/MCP | Chromium sandbox、Service Worker边界、完整manifest/受限stdio；DOM允许NO_COPY | OB-057—065/095；实际网络/页面效果和恶意server |
| p14、18—19、22—23：脱敏/观测 | 禁scanner网络验证、外部allowlist；跨chunk和最小出口，拒绝100%保证 | OB-037—039/075/092；合成canary与观察范围 |
| p19、25—26：全量M0安装/供应链 | 阶段分组，完整资产锁/NOTICE，M3 SBOM区分格式；桌面签名仍M4 | OB-004/005/072/074/089/096；包/非包资产对应 |

## v1.1原缺口继续保持的闭环

| 原材料问题 | 持续保留的修正 | 任务 |
|---|---|---|
| U2 p27 把状态机/预算/Provider合成大工作包 | 分别合同、权威状态、预算、上下文与适配器，逐项失败证据 | OB-007/014/023—027 |
| U2 p28 Browser/MCP共用验收 | 浏览器页面效果与MCP恶意server独立；接同一Broker | OB-057—065 |
| U2 p29—30 审批CAS与执行一次混淆 | CONSUMED不可逆、Attempt/Operation键分离、第二事务复验、UNKNOWN证据核对 | OB-017—022/029/045 |
| U1长期daemon与U2 p24/31 UI退出杀全树矛盾 | 用户级supervisor托管，UI退出不停止daemon；真实原生清理 | OB-003/015/042/068/082 |
| 原WBS未安排最早认证本地API | M1 OB-081作为CLI/gateway前置，不拖到桌面阶段 | OB-081→OB-028/049 |
| 原打包未覆盖完整安装/数据恢复 | M3三OS CLI与备份，M4桌面签名升级单独验证 | OB-030/068—074/080 |

## 一致性核验

96项任务全部关联至少一类RQ，RQ01—RQ12无空项；48条命名AC包含原36条及12条组件增量。Q01—Q16均有明确任务和证据入口。M0=13、M1=37、M2=11、M3=25、M4=4、P2=6。

原88个ID和阶段保留、原依赖未删除；拓扑排序96/96，无环、无缺失依赖或跨阶段逆向边。OB-034拥有自己的最小安全提交journal，不依赖其后续OB-035才能完成；OB-008不要求M0实测M3模型；OB-096不依赖M4。

这些是设计结构检查，不能代替真实源码、OS、租户、模型、隔离或签名资格。
