# OB-011—014：持久化验收范围

实际命令：`PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/integration/storage -q --tb=short`；当前含状态机终态、OutcomeVerifier、取消/恢复守卫及提案/审批回归共 54 passed，原始输出在 evidence/implementation/m1-storage-tests.log。Python 3.12.12 / macOS ARM64；SQLite 版本与连接选项由测试实际读取。

OB-011：校验顺序 checksum 的迁移器；实际新建 23 表、显式升级前 backup、未知/不连续/被改历史拒绝、FK 与 integrity 检查、WAL/FULL/FK/recursive_triggers 读回。真实子进程在 DDL 后退出，重启未留下半迁移。旧 11 表没有获准迁移，明确拒绝。仅使用标准库 sqlite3，不引入 aiosqlite 或 yoyo。

OB-012：唯一 writer 线程独占完整短事务，稳定 request_id 与既有权威记录关联；有界队列分 lane 保留容量与轮询公平性；总 deadline 约束锁等待和 SQL。接受后的 Future 不能取消已提交工作；commit/rollback 双 I/O 故障使 writer 拒绝新写。反例包含队列满、嵌套调用、并发取消、致命异常不遗留悬挂 Future。没有第二业务账本。

OB-013：source_scope 包含 channel/tenant/app/profile，100 次同事件仅一个 Task；不同 app 不互相去重，同 key 改 payload 拒绝。Task/budget/inbox/event/outbox 同事务，outbox 失败全部回滚。真实子进程分别在提交前与提交后 ACK 前 os._exit，重试后五表各一条；未提交不 ACK。模型/入站 body 不得赋 owner 或扩展网络权限。附件入口等待 OB-036，明确不可用。

OB-014：完整覆盖 docs/03 的 11×11 Task 跃迁矩阵与 version CAS、source_scope 请求去重、只读无副作用审计回放与快照；实现 OutcomeVerifier（complete 用例核对 DIAGNOSIS/PATCH/TEST 产物、AVAILABLE 状态、零未决 Operation/Approval/BudgetReservation 及 PARTIAL 缺失项披露）、cancel 用例（无 UNKNOWN/DISPATCHING 时直接 CANCELLED 并撤销待决审批/未派发动作；存在 UNKNOWN/DISPATCHING 时递增 cancel_revision 并驻留 RECONCILING）以及 resume_reconciled 用例（核对未知结果证据与工作区 quarantine 后才允许 RECONCILING -> QUEUED）。真实子进程在 complete 提交前和提交后 ACK 前 os._exit，重查同一 request_id 结果一致且无重复事件/outbox。

OB-011—014 本机验收均记 VERIFIED；上游 OB-005 三 OS bootstrap 尚缺 Windows x64/Linux x64 实际执行，不以配置代替证据，不将其依赖链改为全部 DONE。当前无 daemon/API/Broker 可运行闭环，OB-029 未通过。
