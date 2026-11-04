# OpenBot 数据库基线与参考事务

本目录交付可执行的数据库设计基线。它与 `docs/03_runtime_recovery.md`、`docs/04_security_approvals.md`、`docs/05_storage_api.md` 配套，供后续编码实施使用。这里的 SQL 与验证脚本没有实现 OpenBot daemon、飞书接入、真实执行器或隔离后端。

## 文件与运行

| 文件 | 用途 |
|---|---|
| `001_baseline.sql` | 新 profile 数据库的 23 张核心表、索引、检查约束和触发器 |
| `../validation/verify_database.py` | 仅依赖 Python 标准库的 DDL 与参考事务验收；在临时目录建库 |
| `../validation/database_report.json` | 最近一次离线验收结果、实际 SQLite 版本、SQL 文件摘要和未验证范围 |

从工程包根目录运行：

```bash
python3 validation/verify_database.py --report validation/database_report.json
```

脚本不访问网络，不启动进程执行器，不打开真实 profile，不保存真实凭据。运行时创建临时 SQLite 文件并在结束时清理。当前脚本包含 **33 个场景**；以生成报告的 `success`、`tests_run` 与失败详情为准，不把用例数量当作覆盖率。

项目基线要求 SQLite ≥ 3.38，并探测 JSON 与 STRICT 支持。Python 版本不等于它链接的 SQLite 版本；启动时必须读取实际 SQLite 版本。STRICT 用于加强存储类型约束，不负责验证 JSON Schema 或业务语义。[D1]

## 连接初始化与迁移边界

每个 profile 使用独立数据库。`profile_config.singleton = 1` 阻止在同一库中创建第二个 profile。其余表的 profile 范围由数据库归属确定；服务仍须验证当前请求所绑定的 profile，不能把知道一个对象 ID 当作权限。

writer 在事务开始前设置并读回以下配置：

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA recursive_triggers = ON;
PRAGMA busy_timeout = 250;
```

`250` 毫秒是示例连接起点。实际等待上限由调用剩余 deadline 决定；回调不能因数据库等待超过平台响应期限。外键应在每个新连接上启用，不能依赖另一个连接的设置，也不能在事务中才尝试启用。[D2] `FULL` 是本项目对关键控制库采用的设置，断电、磁盘控制器和文件系统的实际耐久性仍需目标平台测试；本脚本中的关闭再打开不是断电测试。[D3]

DDL 不包含 `BEGIN`、`COMMIT` 或自己的 migration checksum。迁移 runner 必须把以下内容放进同一个事务：全部 DDL、`schema_migrations` 的版本和 SHA-256 记录。验证脚本的 `install_baseline()` 提供这一做法的标准库示例。它在 `executescript` 的脚本开头开启事务，再用参数化 SQL 插入 checksum，最后提交，避免 schema 已创建而 migration 记录未提交。

此文件只能用于空库初始化，不能覆盖原型已有数据库。没有使用 `IF NOT EXISTS` 来掩盖结构漂移。实际迁移 runner 还须实现版本顺序检查、已应用 checksum 比较、升级前备份、失败恢复、降级兼容门禁与单实例锁。已发布的 migration 不得原地修改；后续变更新建 migration。

## 表的职责

| 数据域 | 表 | 说明 |
|---|---|---|
| 配置与身份 | `schema_migrations`、`policy_revisions`、`profile_config`、`principals`、`channel_accounts`、`channel_identities` | 单 profile；最多一个活动 owner；飞书身份经 account 间接绑定 tenant/app；只存 `secret_ref` |
| 目标与上下文 | `workspaces`、`sessions`、`tasks`、`messages` | 会话归属不依赖连接；工作区 generation；Task 的 11 个状态；工具结果与逻辑 call ID |
| 执行与授权 | `tool_registry`、`operations`、`approvals`、`operation_attempts` | 工具版本固定；提案不可变；一次审批消费；每次尝试单独保留 |
| 生命周期与并发 | `runtime_instances`、`resource_leases` | 当前 epoch、全局递增 fence 与资源租约；不是外部系统的锁 |
| 持久交付 | `inbox`、`outbox`、`events` | 入站去重、版本化通知、追加审计与 SSE 序列 |
| 产物与预算 | `artifacts`、`artifact_refs`、`budgets`、`budget_reservations` | 不可变对象元数据、作用域引用、调用前预留与实际费用记录 |

时间使用 UTC 毫秒整数，运行中超时仍由单调时钟负责。金额使用指定币种的整数百万分之一单位，避免浮点费用比较。对象 ID 由应用生成不可预测值；`events.seq` 才是数据库内事件顺序，不按 UUID 排序。

长期记忆、embedding、schedule、多设备路由、配对挑战临时状态与企业 capability grants 未提前加入本基线；对应功能必须通过后续 migration 和独立合同实现。

## 已冻结的四个关键关系

### 1. Operation 与 Attempt

`operation_id` 表示一个具体、不可变的提案。工具和版本、参数 JSON、资源快照、目的地、数据分类、policy、identity epoch、授权期限、binding hash 与 provider 幂等键都不能原地修改。参数或授权条件改变时创建新的 Operation。

`attempt_id` 表示一次执行尝试。`attempt_no` 在同一 Operation 内递增；`dispatch_id` 属于 Attempt，并具有数据库唯一性。同一次 Attempt 的传输重发使用相同 dispatch ID；恢复器批准的新 Attempt 使用新 dispatch ID。`provider_idempotency_key` 属于 Operation，在供应商允许的幂等窗口内保持不变；它不等于本地 dispatch ID。

`operations.current_attempt_id` 与 `operation_attempts.operation_id` 使用复合外键，避免把另一个 Operation 的 Attempt 指为当前尝试。Attempt 的身份、epoch、fence、dispatch ID 和原始 claim 条件不能变更；已经有明确终态的历史 Attempt 不覆盖。

### 2. Approval 消费

一个 Operation 最多对应一个 Approval。审批的绑定 hash、允许批准者、nonce hash 与 Operation 关联；首次 claim 将 `APPROVED` 改成 `CONSUMED`，同时记录 `consumed_at` 和 `consumed_attempt_id`。消费记录与首次 Attempt 有外键关系，必要的循环引用使用延迟外键，事务提交时必须完整。

`CONSUMED` 永不变回 `APPROVED`，也不通过写成 `REVOKED` 覆盖历史消费事实。后续撤销通过新的 policy/identity epoch、Task 取消、Operation 状态等阻止新派发，并留下事件。已消费并不表示远端成功。

同一 Operation 的安全重试沿用已消费记录，不再次消费。参考脚本仅实现“已确认未进入 DISPATCHING、原 worker 已隔离”的恢复分支。每次 claim 和首次 dispatch 都重新检查原授权期限、actor、policy、identity、取消和资源。UNKNOWN 的供应商幂等重试与远端核对留给真实 reconciler，脚本不会把 UNKNOWN 自动改回 READY。

本基线的审批表只保存 `nonce_hash`。原 nonce 必须保存在受保护的 challenge store，并以 approval ID 对应的受保护记录查找；随机 opaque `nonce_ref` 列尚未加入 DDL，若正式实现采用独立引用，应通过 migration 增加它，不能把原 nonce 填入普通 JSON、日志或事件。不可变 binding 纳入 nonce hash。重启后原值无法恢复时撤销旧审批并创建新 Operation，不改写旧 hash。

公开 `ApprovalPreview` 与内部提案分开；普通 GET/SSE 不返回 nonce。当前有效 nonce 仅经本地 owner 的受限 `POST /v1/approvals/{approval_id}/challenge` 获取，要求正确 scope、PENDING、未过期和所属身份；gateway token 不能调用它。取得 challenge 不等于批准。脚本使用固定假 nonce 验证 hash 匹配，没有实现这个安全存储或 HTTP 端点。

### 3. 取消与首次派发

claim 和首次 dispatch 是两个短事务。claim 创建 Attempt 并消费批准；`CLAIMED → DISPATCHING` 的事务再次检查 Task 的 `cancel_requested_at/cancel_revision`、当前 epoch、资源版本、lease 和原授权期限。

取消先提交时，参考事务不能完成首次 dispatch。DISPATCHING 先提交时，即使尚未收到真实执行结果，也必须按可能已开始处理；之后的取消尽力停止，并把上层 Task 放进 RECONCILING。数据库事务不能与任意网络副作用组成原子事务，因此不能承诺“任何时间点击取消都能撤销”。

`operation_attempts` 是核心侧的派发记录。worker 的身份校验、dispatch token 一次兑换、重复接收时返回已有执行记录、真实进程的隔离与回收，仍须实际 Broker/worker 实现。不要把核心侧 `UNIQUE(dispatch_id)` 单独解释为外部恰好执行一次。

### 4. UNKNOWN 与核对

发出指令后没有得到可验证结果，Operation 进入 UNKNOWN，Task 进入 RECONCILING。不能用 timeout 推断失败，也不能直接重发。已有 UNKNOWN/DISPATCHING 的 Task 在更新时不能直接变成 SUCCEEDED 或 CANCELLED。

所有进入 CANCELLED 的路径都须满足没有 DISPATCHING/UNKNOWN 的全局条件。普通 resume 不能让 RECONCILING 绕过核对进入 QUEUED；只有恢复器按工具语义解决相关不确定结果后才能调度。DDL 没有自动实现这一完整恢复门禁，参考事务也没有提供通用 resume。

UNKNOWN 期间必须保留相关资源的持久 quarantine。当前表没有额外 `QUARANTINED` 枚举：基线用 `resource_leases.state = HELD` 且 holder 的 Attempt 为 UNKNOWN 表达不得接管的资源；即使 `expires_at` 已过，状态也不自动释放。Broker 按规范化 workspace/browser profile/external account 资源键查锁，更换 Task 或 Operation ID 仍受同一锁约束。脚本验证了 workspace 分支；多资源集合与按读写类别允许无关只读工作仍待实际实现。

Operation 从 UNKNOWN 转出需要 `resolution_evidence_ref`；数据库只验证证据引用存在，不验证证据真实有效。供应商回执、目标状态、用户核对和隔离证明必须由 reconciler 按工具合同检查，追加对应审计。单个文本字符串或模型声明不能构成证据。

核对请求使用 `OperationSnapshot.version`，不能误用 Task.version。通过 artifact/import 输入的文件默认不受信；证据可读并不等于证据有效。正式实现核对调用方、artifact 的 owner/task/operation 归属、来源与所证明的外部动作，记录 PROVIDER_VERIFIED 或 USER_ATTESTED，不能把人工声明标成供应商验证。这些证据级别与来源映射需在受验证的 result/event 合同或后续表中实现，不能靠一条任意字符串引用直接改变状态。

## 数据库强制项与应用责任

| 项目 | DDL 强制 | 应用和实际系统必须完成 |
|---|---|---|
| 数据结构 | STRICT、NOT NULL、非空 ID、状态枚举、JSON 合法且具有指定根类型、hash 形状、外键 | API schema、长度上限、数据分类、完整 binding、RFC 8785 和 SHA-256 一致性 |
| 审批 | 绑定复合外键、唯一 Operation/nonce、允许的审批转换、消费不可复活 | 真实 actor 认证、卡片上下文、nonce 校验、当前权限与展示内容完整性 |
| 并发写 | 核心状态表 version 增量检查、唯一活动 Attempt、fence 不倒退 | 每个写命令的 `expected_version` 条件、受影响行数检查、有界 writer 队列、单实例 OS 锁 |
| 执行 | Attempt/Operation 引用和 dispatch 唯一性 | preflight、实际资源观察、token 兑换、worker 接收去重、已失效 worker 无法执行 |
| 预算 | 非负整数、预留记录引用与 call 去重 | 预留和计数同事务、真实用量结算、UNKNOWN 计费核对、版本化价格与 token 估算 |
| 审计 | events 禁止 UPDATE/DELETE/REPLACE | 每个业务修改同事务追加正确事件、事件 schema、脱敏、授权 SSE 可见性 |
| 通知 | target/semantic key/revision 唯一、payload 不可变 | 同目标串行发送、合并旧版本、远端回执核对、provider 幂等有效期与重试 |
| 产物 | 对象元数据不可变、引用存在 | 写 staging、fsync/rename、DB 注册与崩溃对账；真实访问控制和清理保护 |

DDL 没有自动实现全部 Task/Operation 状态图，也不会自动生成业务事件和 outbox。参考事务展示其中的关键路径，实际 application 层仍须完整实现 `docs/03` 的转换表和 OutcomeVerifier。脚本的成功回执和单 Operation 目标完成是 fixture 假设。

预算限额是调用准入条件。DDL 不强制“实际花费永不超过上限”，因为供应商实际计费超出预估时仍必须记录真实账单；应用应标记超支、停止新预留并核对差异，不能为满足 CHECK 而丢弃费用证据。

## 只追加、REPLACE 与清理

运行时不得使用 `INSERT OR REPLACE` 更新状态或授权记录。SQLite 的 REPLACE 可能删除冲突旧行，不能当成普通 UPDATE；触发器是否收到这种删除还与 recursive triggers 设置有关。[D4] 本基线对审计、提案、批准、Attempt、lease counter、工具定义、产物和通知版本添加了显式防覆盖保护。

所有 FK 都没有 `ON DELETE CASCADE`。删除 Task 不能悄悄抹除批准与执行证据。普通运行时不能物理删除 operations、approvals、attempts、events、policy/migration 证据或 lease counter。清理需要未来显式维护流程：暂停写入与派发、验证没有活动引用、记录 purge/tombstone、形成一致备份，执行受审查的迁移/维护事务，再检查完整性。

这些触发器用来防应用误写。数据库文件的同用户拥有者仍可修改 schema、删除触发器或替换文件；它们不是针对恶意本机管理员的防篡改边界。

## 验收场景对照

| 测试 | 验证内容 |
|---|---|
| 01–02 | 实际连接配置、schema checksum、完整参考事务闭环 |
| 03–06 | inbox 重复/冲突/source scope、重复审批/nonce、错误 actor/nonce/TTL |
| 07–12 | 提案不变、FK、状态与 JSON 类型、审计追加、无级联删除、消费不可复活 |
| 13–14 | 安全重试不二次消费、新 dispatch ID、同 Operation 幂等键、原授权过期检查 |
| 15–17 | 取消发生在 claim 前、claim 后 dispatch 前、dispatch 后三个顺序 |
| 18–21 | epoch、真实资源观察替身、policy、identity、工具隔离状态变化 |
| 22–24 | stale version、outbox 写失败导致全事务回滚、UNKNOWN 禁止盲目重试和成功 |
| 25–28 | fence 不重置、Attempt/dispatch 不复用、单 profile/owner/runtime、通知旧版本合并 |
| 29–32 | 预算并发准入的参考谓词、工具/产物/工作区保护、批准落盘后重开连接、lease 到期不是接管许可 |
| 33 | UNKNOWN 的资源 quarantine 对新 Task/Operation ID 仍有效，RECONCILING 不能直接启动新动作 |

测试 28 中“把旧通知标为 SUPERSEDED”是参考发送器 SQL，不是数据库自动触发的网络排序保证。测试 32 中租约到期仍不接管，必须补充可信 supervisor 证据。所有 fake actor、account、时间、资源观察和回执只用于确定性验证。

## 编码阶段剩余工作

1. 把参考事务整理成正式 repository/unit-of-work 和用例层，所有 CAS 检查受影响行数，异常统一回滚。`RAISE(ABORT)` 终止当前语句，不替调用方撤销之前已执行的整个事务；本脚本的 transaction context 会显式 rollback。[D4]
2. 实现完整 Task/Operation 转换、OutcomeVerifier、取消传播、worker token 兑换、接收 ledger、旧 epoch/fence 拒绝及恢复器；按真实 OS 和供应商做故障注入。
3. 完成经过验证的 RFC 8785 binding 实现。脚本 `j()` 只用于无浮点的简单 fixture，不能复制为通用规范化算法。
4. 将 actor、account/source scope、工作区观察、secret handle 与核对证据接到真实可信边界；这些字段均不得由模型或任意请求 body 自证。
5. 实现多资源锁的固定顺序、lease 续约和 supervisor 失联核对；资源 expiry 本身不授权第二个 worker 启动外部动作。
6. 完成 provider 幂等窗口、UNKNOWN reconciliation、Outbox 单目标发送顺序与远端版本/回执检查；不能把所有超时都作为可重试。
7. 实现 artifact 文件与数据库对账、额度结算、保留清理、在线一致备份、实际迁移升级、恢复旧备份时不重放副作用。
8. 补充真实多进程竞争、磁盘满/BUSY、进程强杀、断电平台测试、三平台运行验证与安全测试。当前 33 项均不能替代这些门禁。

## 官方依据

- [D1 SQLite STRICT Tables](https://www.sqlite.org/stricttables.html)：严格类型和相应完整性检查。
- [D2 SQLite Foreign Key Support](https://www.sqlite.org/foreignkeys.html)：每连接启用、复合和延迟外键。
- [D3 SQLite PRAGMA](https://www.sqlite.org/pragma.html#pragma_synchronous)：运行配置与 synchronous 语义。
- [D4 SQLite ON CONFLICT](https://www.sqlite.org/lang_conflict.html)：ABORT、REPLACE 与递归触发器相关行为。

来源核对日期：2026-11-04。这里的具体表、状态、事务与产品限制是本工程包的设计决定。
