# OB-011—014、OB-016、OB-021、OB-023、OB-024、OB-030、OB-036：持久化、资源锁、Durable Outbox、预算熔断、上下文摘要、Artifact 存储与备份恢复验收范围 / Persistence, Resource Leases, Durable Outbox, Budget Circuit-Breaker, Context Summary, Artifact Store, and Backup/Restore Verification Scope

## 中文说明

实际命令：`PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/integration/storage -q --tb=short`；当前含状态机终态、OutcomeVerifier、取消/恢复守卫、四类资源锁/会话排队、提案/审批/派发/恢复、durable outbox、取消传播、预算熔断、上下文摘要、Artifact 存储与数据库备份恢复共 83 passed，原始输出在 evidence/implementation/m1-storage-tests.log。Python 3.12 / macOS ARM64；SQLite 版本与连接选项由测试实际读取。

OB-011：校验顺序 checksum 的迁移器；实际新建 23 表、显式升级前 backup、未知/不连续/被改历史拒绝、FK 与 integrity 检查、WAL/FULL/FK/recursive_triggers 读回。真实子进程在 DDL 后退出，重启未留下半迁移。旧 11 表没有获准迁移，明确拒绝。仅使用标准库 sqlite3，不引入 aiosqlite 或 yoyo。

OB-012：唯一 writer 线程独占完整短事务，稳定 request_id 与既有权威记录关联；有界队列分 lane 保留容量与轮询公平性；总 deadline 约束锁等待和 SQL。接受后的 Future 不能取消已提交工作；commit/rollback 双 I/O 故障使 writer 拒绝新写。反例包含队列满、嵌套调用、并发取消、致命异常不遗留悬挂 Future。没有第二业务账本。

OB-013：source_scope 包含 channel/tenant/app/profile，100 次同事件仅一个 Task；不同 app 不互相去重，同 key 改 payload 拒绝。Task/budget/inbox/event/outbox 同事务，outbox 失败全部回滚。真实子进程分别在提交前与提交后 ACK 前 os._exit，重试后五表各一条；未提交不 ACK。模型/入站 body 不得赋 owner 或扩展网络权限。附件入口等待 OB-036，明确不可用。

OB-014：完整覆盖 docs/03 的 11×11 Task 跃迁矩阵与 version CAS、source_scope 请求去重、只读无副作用审计回放与快照；实现 OutcomeVerifier（complete 用例核对 DIAGNOSIS/PATCH/TEST 产物、AVAILABLE 状态、零未决 Operation/Approval/BudgetReservation 及 PARTIAL 缺失项披露）、cancel 用例（无 UNKNOWN/DISPATCHING 时直接 CANCELLED 并撤销待决审批/未派发动作；存在 UNKNOWN/DISPATCHING 时递增 cancel_revision 并驻留 RECONCILING）以及 resume_reconciled 用例（核对未知结果证据与工作区 quarantine 后才允许 RECONCILING -> QUEUED）。真实子进程在 complete 提交前和提交后 ACK 前 os._exit，重查同一 request_id 结果一致且无重复事件/outbox。

OB-016（持久化资源锁与会话排队子集，保持 IN_PROGRESS）：实现 WORKSPACE、BROWSER_PROFILE、DESKTOP_SESSION、EXTERNAL_ACCOUNT 四类资源键及固定加锁顺序（按类型优先级与字典序排序防死锁），fencing_token 由 profile_config 单调递增分配；实现单活动 Task 串行槽位与会话内 FIFO 排队（claim_next_task）、人工审批/输入等待时的原子释锁点（park_for_wait，禁止在途 DISPATCHING/UNKNOWN 释锁）、重获锁时的工作区 generation/version 校验，以及租约过期不等于可抢占（仅旧 runtime_epoch=STOPPED 且未派发 attempt 可回收）与 UNKNOWN/DISPATCHING 资源 quarantine 阻断。因上游 OB-015 / OB-093 正式 Supervisor 代际交接尚未闭合，OB-016 记为 IN_PROGRESS。

OB-021（Durable Outbox 及投递状态，保持 IN_PROGRESS）：先读取 `component_refs`（`tenacity`）、`reuse_type`（`control_owned`）与 `reuse_notes`，采用纯自研有界退避与单重试所有者模型，不引入通用 `tenacity` 装饰器。新增 `services/core/src/openbot/storage/outbox.py`（`OutboxStore`、`enqueue_outbox_tx`）与 `services/core/src/openbot/application/outbox.py`（`OutboxService`、`OutboxGatewayPort`、`OutboxEnvelope`、`GatewaySendResult`）：
1. 持久化语义键（`target_key` + `semantic_key`）、单调 `revision`、可合并进度（`UPSERT_REVISION` 新版本入队自动将同键旧 `PENDING` 置为 `SUPERSEDED`）与终态保护（拒绝非终态进度覆盖已存在的终态通知；迟到或重复回执在存在更高 `revision` 时记为 `SUPERSEDED`，绝不倒退更高已投递版本）。
2. 远端发送严格移出 SQLite 短事务：`dispatch_next` 先经第一短事务 `claim_due`（`PENDING -> IN_FLIGHT`，递增真实可数 `attempt_count`，绑定 `claim_runtime_epoch` 与 `lease_token`），事务外调用 `gateway.send`，再经第二短事务 `complete_delivery` 落盘 `SENT / PENDING / DEAD / EXPIRED / UNKNOWN / SUPERSEDED` 与 `provider_receipt_json`。
3. 唯一重试所有者与异常隔离：强制校验 `gateway.sdk_max_retries == 0`（拒绝叠加 SDK 内部自动重试）；捕获传输/库异常并收敛为 outbox 投递状态，绝不触发原业务 `Operation` 或 `operation_attempts` 重执行；仅当 `delivery_class == 'PROVIDER_IDEMPOTENT'` 且网关明确支持幂等时记录 `exact_once_guaranteed=True`，无远端幂等支持时禁止声称 `exactly-once`。
4. 断网重启后的 `IN_FLIGHT` 恢复与核对：`recover_in_flight` 要求原 `claim_runtime_epoch` 已证明 `STOPPED`，按 `UPSERT_REVISION` / `PROVIDER_IDEMPOTENT` / `RECONCILE_ONLY` 分流（无幂等能力转 `UNKNOWN` 核对，不盲目重发）；`reconcile_unknown` 凭核实回执解决 `UNKNOWN -> SENT / SUPERSEDED / PENDING / DEAD / EXPIRED`。因上游 `OB-017` 仍为 `IN_PROGRESS`，`OB-021` 记为 `IN_PROGRESS`。

OB-023（实现任务预算和熔断，保持 IN_PROGRESS）：先读取 `component_refs`（`tiktoken`、`tenacity`）、`reuse_type`（`dependency_adapter`）与 `reuse_notes`。新增 `services/core/src/openbot/application/budgets.py`（`BudgetService`、`TaskBudgetPolicy`、`OfflineVocabularyEstimator`、`TokenEstimate`）：
1. 全维度保守上限与调用前预留（`reserve`）：覆盖 `max_steps`、`max_model_calls`、`max_tool_calls`、`max_retries_per_call`、`max_duration_ms`、`max_single_artifact_bytes`、`max_total_artifact_bytes` 以及金额/Token 余额（`limit - spent - reserved`）；取消后（`cancel_revision > 0`）拒绝任何新预留；任一预算不足时原子将 Task 转入 `PAUSED` 并记录明确 `paused_reason`，绝不超卖或静默继续调用。
2. 结算（`settle`）与未知费用保守保留（`mark_unknown`）：响应完成后扣减预留并记入 `amount_spent_micros`/`tokens_spent`，同时记录预估与真实 usage 偏差（`usage_delta_tokens`）；断流、超时或 usage 缺失时将 `budget_reservations` 置为 `UNKNOWN`，并在 `budgets` 表中保守保留预留额度，绝不在断流后清零费用。
3. 离线词表校验与非通用计费声明（`OfflineVocabularyEstimator`）：对已声明模型校验本地预置词表文件存在性与 SHA-256 摘要（缺失或篡改时立即 `CAPABILITY_UNAVAILABLE` 失败，禁止运行期联网下载）；对未知模型使用保守 UTF-8 上界，从不把 OpenAI 分词器当作全 Provider 精确计费器（`exact_billing_guaranteed=False`）。
4. 重复提案/连续错误/空转熔断（`record_turn_activity`）与恢复（`resume_paused`）：触发阈值时自动将 Task 置为 `PAUSED`，仅在显式重置熔断/补充额度且未取消时恢复为 `QUEUED`。因上游 `OB-017` 及真实模型离线词表资产打包尚待闭合，`OB-023` 记为 `IN_PROGRESS`。

OB-024（实现上下文快照与摘要，保持 IN_PROGRESS）：先读取 `component_refs`（`tiktoken`）、`reuse_type`（`control_owned`）与 `reuse_notes`。新增 `services/core/src/openbot/application/context.py`（`ContextService`、`ContextMessage`、`ContextSummary`、`ModelContextSnapshot`）：
1. 消息追加、工具关联与脱敏限制（`append_message`）：拒绝持久化 `SECRET` 数据与 `hidden_reasoning` 内部推理字段；强制 `TOOL` 消息必须携带匹配同任务既有 `ASSISTANT` 消息的 `tool_call_id` 且来源保持 `UNTRUSTED_TOOL_OUTPUT`/`UNTRUSTED_EXTERNAL`。
2. 保留污点、来源引用与未决动作的窗口摘要（`summarize_window`）：跨被压缩消息继承最高敏感数据分类（`PUBLIC < WORKSPACE < SENSITIVE`）与最不可信来源（如 `UNTRUSTED_EXTERNAL`），合并保留全部 `source_refs` 以及来自数据库权威表的 `pending_operation_ids` / `approved_operation_ids`；显式标记 `authoritative_grants=False`，绝不因摘要洗白污点或把外部注入文字升级为系统/用户授权。
3. 长会话成对截断与开销核算（`build_model_context`）：跨重启恢复目标、未决动作、摘要与最近消息；按完整 `ASSISTANT+TOOL` 配对单元截断旧消息（不拆散 `tool_call_id` 关联）；显式将消息包装（`framing_overhead_tokens`）、工具 Schema（`tool_schema_overhead_tokens`）与多模态（`multimodal_overhead_tokens`）计入保守 Token 总额，不以纯文本分词数冒充最终费用（`exact_billing_guaranteed=False`）。因上游 `OB-017`/`OB-023` 仍为 `IN_PROGRESS`，`OB-024` 记为 `IN_PROGRESS`。

OB-036（实现 Artifact 存储与可信元数据，保持 IN_PROGRESS）：先读取 `component_refs`（空）、`reuse_type`（`control_owned`）与 `reuse_notes`。新增 `services/core/src/openbot/artifacts/store.py`（`ArtifactStore`、`ArtifactLimits`、`ArtifactRecord`、`ArtifactDownload`）：
1. 临时文件 `staging` -> `fsync` -> 原子 `os.replace` -> 数据库注册（`put`）：记录不可变 `sha256`、`mime`、`bytes`、`classification`（`PUBLIC`/`WORKSPACE`/`SENSITIVE`/`SECRET`，MIME 绝不降低分类）、`expires_at` 与 `artifact_refs`（`PRINCIPAL`/`SESSION`/`TASK`/`OPERATION`）；施加单产物（`max_single_artifact_bytes`）与单任务总额（`max_task_artifact_bytes`）字节配额。
2. 受控下载与预览守卫（`download`、`preview`、`verify_approved_digest`）：不接收或暴露任何宿主文件路径；强制返回 `Content-Disposition: attachment`、`Content-Security-Policy: default-src 'none'; sandbox` 与 `X-Content-Type-Options: nosniff`（防止 HTML/脚本内联执行）；拒绝通过 `preview` 访问 `SECRET` 产物；登记后若底层文件缺失或哈希不符，自动将数据库状态标为 `QUARANTINED`；审批绑定内容摘要变化（`verify_approved_digest`）立即拒绝。
3. 孤立文件回收与待审批/备份 GC 保护（`collect_garbage`、`pin_for_backup`、`unpin_backup`）：清理注册前崩溃遗留的 `staging/` 与未登记 `objects/` 孤立文件；即使 TTL 到期，仍拒绝回收任何被非终态 Task、待审批/在途/UNKNOWN Operation 或活跃备份 pin（`pin_for_backup`）引用的对象。因上游 `OB-017`/`OB-032` 仍为 `IN_PROGRESS`，`OB-036` 记为 `IN_PROGRESS`。

OB-030（实现数据库备份恢复与保留策略，保持 IN_PROGRESS）：先读取 `component_refs`（`sqlite3`）、`reuse_type`（`dependency_adapter`）与 `reuse_notes`。新增 `services/core/src/openbot/storage/maintenance.py`（`DatabaseMaintenanceService`、`BackupManifest`、`RestoreVerificationReport`）：
1. 在线一致备份与 GC Pin 联动（`create_backup`）：先获取全部 `AVAILABLE` 产物的 `pin_for_backup` 保护，防止备份期间并发 GC 删除快照引用；调用 SQLite `backup()` 接口生成一致快照（含 WAL 已提交状态，非裸文件拷贝）并校验 `PRAGMA integrity_check` 与 `foreign_key_check`；逐个核对磁盘上 Artifact 文件的实际字节数与 SHA-256；manifest 仅记录不透明 `secret_ref` 且排除 `SECRET` 产物与任何真实密钥（`contains_secret_values=False`）；完成后在 `finally` 释放 GC pin，失败备份写入 `status='FAILED'`。
2. 安全恢复与防复活/防重放守卫（`restore_backup`）：先核验 `manifest.json`（`status=='VERIFIED'`）、数据库 SHA-256 与全部引用 Artifact 文件哈希后再启用恢复库；恢复后在同一事务内将旧 `runtime_instances` 置为 `STOPPED`，将未消费的 `PENDING`/`APPROVED` 授权撤销为 `REVOKED`（`CONSUMED` 绝不回退或复活），将在途 `DISPATCHING` 操作转为 `UNKNOWN`（关联 Task 转 `RECONCILING`），杜绝恢复旧备份导致复活旧批准或盲目重放未知副作用；逐项核对 `secret_ref` 可解析性，缺失钥匙串引用时将对应 `channel_accounts` 置为 `DISABLED` 并标记 `reconfiguration_required=True`。因上游 `OB-020` 仍为 `IN_PROGRESS` 且 M3 跨平台恢复实测待对应环境执行，`OB-030` 记为 `IN_PROGRESS`。

OB-011—014 本机验收均记 VERIFIED；上游 OB-005 三 OS bootstrap 尚缺 Windows x64/Linux x64 实际执行，不以配置代替证据，不将其依赖链改为全部 DONE。当前无 daemon/API/Broker 可运行闭环，OB-029 未通过。

## English Summary

Command: `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/integration/storage -q --tb=short` (83 passed, logged in `evidence/implementation/m1-storage-tests.log` on Python 3.12 / macOS ARM64).

- **OB-011**: Checksum-locked ordered SQLite migrator creating all 23 baseline tables, pre-upgrade backup, foreign-key and integrity checks, and WAL/FULL/FK/recursive_triggers verification using stdlib `sqlite3`.
- **OB-012**: Single writer thread owning short transactions with bounded per-lane queues, round-robin fairness, total deadline enforcement, and fail-closed fatal writer state on commit/rollback I/O errors.
- **OB-013**: Source-scoped durable inbox deduplication (`channel/tenant/app/profile`) committing Task, budget, inbox, event, and outbox atomically in one transaction.
- **OB-014**: Complete 11×11 Task state transition matrix with version CAS, `OutcomeVerifier` (DIAGNOSIS/PATCH/TEST artifact and unresolved operation/approval/budget checks), cancellation guard (`RECONCILING` when `UNKNOWN`/`DISPATCHING` operations exist), and `resume_reconciled` quarantine verification.
- **OB-016 (`IN_PROGRESS`)**: Durable resource leases (`WORKSPACE`, `BROWSER_PROFILE`, `DESKTOP_SESSION`, `EXTERNAL_ACCOUNT`) with deterministic lock ordering, monotonic `fencing_token`, single active Task FIFO session queueing, atomic release on `WAITING_APPROVAL`, workspace generation re-verification, and `UNKNOWN` quarantine enforcement.
- **OB-021 (`IN_PROGRESS`)**: Control-owned durable outbox (`services/core/src/openbot/storage/outbox.py` and `services/core/src/openbot/application/outbox.py`) without `tenacity` decorators:
  1. Monotonic `revision` per `(target_key, semantic_key)`, progress coalescing (`UPSERT_REVISION` marks older `PENDING` rows `SUPERSEDED`), and terminal state protection (rejecting non-terminal progress after terminal state and preventing late/duplicate receipts from regressing higher revisions).
  2. Transaction-external delivery (`PENDING -> IN_FLIGHT -> SENT/PENDING/DEAD/EXPIRED/UNKNOWN/SUPERSEDED`) with countable `attempt_count`, bounded backoff, deadline expiration, and dead-letter transition.
  3. Single retry owner (`gateway.sdk_max_retries == 0` enforced), exception containment (transport/library errors never re-execute business `Operation`/`Attempt`), and truthful delivery guarantees (`exact_once_guaranteed` is `False` unless `PROVIDER_IDEMPOTENT` is supported by the gateway).
  4. Crash recovery (`recover_in_flight` requiring `STOPPED` old runtime epoch and routing `RECONCILE_ONLY` to `UNKNOWN`) and `reconcile_unknown`. Kept `IN_PROGRESS` pending upstream `OB-017` closure.
- **OB-023 (`IN_PROGRESS`)**: Durable task budgets, offline vocabulary verification, and circuit breakers (`services/core/src/openbot/application/budgets.py`):
  1. Pre-call `reserve` enforcing caps on steps, model calls, tool calls, per-call retries, duration, single/total artifact bytes, and available amount/tokens; transitions Task `RUNNING -> PAUSED` with an explicit `paused_reason` on exhaustion and refuses new reservations after cancellation.
  2. Post-call `settle` (recording `usage_delta_tokens` between estimated and actual tokens) and `mark_unknown` (retaining reserved amount/tokens on stream cuts or ambiguous failures instead of zeroing cost).
  3. `OfflineVocabularyEstimator`: verifies pinned offline vocabulary file SHA-256 without network downloads (failing closed when missing) and never claims OpenAI encodings provide exact billing for arbitrary models (`exact_billing_guaranteed=False`).
  4. Circuit breaker (`record_turn_activity`) tripping to `PAUSED` on repeated proposals, consecutive errors, or idle turns, with explicit `resume_paused` recovery.
- **OB-024 (`IN_PROGRESS`)**: Bounded model context snapshots and taint-inheriting summarization (`services/core/src/openbot/application/context.py`):
  1. `append_message`: Rejects `SECRET` payloads and `hidden_reasoning` fields; enforces that `TOOL` messages match a prior `ASSISTANT` `tool_call_id` in the same task and retain untrusted provenance.
  2. `summarize_window`: Inherits the strictest `data_class` (`SENSITIVE` over `WORKSPACE`/`PUBLIC`) and least-trusted `provenance_kind` (`UNTRUSTED_EXTERNAL`), preserves all `source_refs` and authoritative `pending_operation_ids`/`approved_operation_ids`, and enforces `authoritative_grants=False` so summaries never launder taint or elevate prompt-injection text into permissions.
  3. `build_model_context`: Reconstructs context across restarts, truncates older turns without splitting `ASSISTANT`+`TOOL` `tool_call_id` pairs, and explicitly accounts for message framing, tool schema, and multimodal token overhead (`exact_billing_guaranteed=False`).
- **OB-036 (`IN_PROGRESS`)**: Content-addressed artifact storage and trusted metadata (`services/core/src/openbot/artifacts/store.py`):
  1. `put`: Writes to `staging/`, `fsync`s, atomically `os.replace`s into `objects/`, and registers immutable `artifacts` and `artifact_refs` while enforcing single-artifact and per-task byte quotas.
  2. `download`, `preview` & `verify_approved_digest`: Never exposes host paths; enforces `attachment`, sandbox CSP, and `nosniff` headers so HTML/scripts never execute inline; blocks `SECRET` preview; marks missing/corrupted blobs `QUARANTINED`; invalidates tampered approval digests.
  3. `collect_garbage` & `pin_for_backup`: Cleans up pre-registration orphan files while protecting artifacts referenced by active tasks, pending/approved/in-flight/unknown operations, or active backup pins.
- **OB-030 (`IN_PROGRESS`)**: Online SQLite backup, artifact manifest verification, and safe restore (`services/core/src/openbot/storage/maintenance.py`):
  1. `create_backup`: Pins referenced `AVAILABLE` artifacts against concurrent GC via `pin_for_backup`, runs SQLite `backup()` with `integrity_check` and `foreign_key_check`, verifies on-disk artifact sizes and SHA-256 digests, and records only opaque `secret_ref` identifiers (`contains_secret_values=False`).
  2. `restore_backup`: Verifies `manifest.json` and all artifact digests before restoring; stops old `runtime_instances`, revokes unconsumed `PENDING`/`APPROVED` grants (`CONSUMED` untouched), transitions `DISPATCHING` operations to `UNKNOWN` (`RECONCILING` task state) to prevent replaying ambiguous side effects, and disables `channel_accounts` with missing `secret_ref` (`reconfiguration_required=True`).
