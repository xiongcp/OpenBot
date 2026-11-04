# OB-017 / OB-018 / OB-019 / OB-020 / OB-022 / OB-031：不可变提案、审批决定、确定性策略评估器、两次短事务派发、恢复与取消传播 / Immutable Proposals, Approvals, 6D Policy, Two-Phase Dispatch, Recovery, and Cancellation Propagation

## 中文说明

先读取各项 component_refs/reuse_type/reuse_notes：复用已通过本机标准向量的 rfc8785/jsonschema；SQLite 标准库经唯一 writer 使用。OB-031 保持纯代码表驱动评估器，不引入 OPA/Casbin，也不以 pathspec 匹配结果充当安全路径白名单或授权判定。OB-019 两次短事务 claim→DISPATCHING、OB-020 恢复器/核对证据校验与 OB-022 取消传播完全自研。没有引入新 SDK、ORM、自动 runner 或第二账本。

实现（OB-017/018）：Operation 从本地 ACTIVE manifest、可信上下文、固定 TTL/nonce 和工具 args schema 构造；完整 JCS 字节保存到原 operations 表新增列，索引投影逐项复核。新增 migration 0002，原 0001/23 表设计基线未改。批准只使 Operation READY；本子集不创建 Attempt、不派发工具。审批状态、Task、脱敏 event/outbox 在同一事务提交；稳定 request_id 包含认证来源作用域。

实现（OB-031）：新增 `services/core/src/openbot/policy/evaluator.py`，从 SQLite `profile_config`、`policy_revisions`（复核 canonical SHA-256 digest）与 `tool_registry`（仅 ACTIVE 工具）构造不可变 `PolicySnapshot`；按 `actor / resource / action / data_class / destination / execution_backend` 六维输入做纯确定性评估，输出 `ALLOW / ASK / DENY / REQUIRE_LOCAL`、理由码、有效网络模式与允许域名交集（`profile & workspace & request`，任何扩权尝试直接 `DENY`）。`LOCAL_MODEL` 强制校验 `verified_local_model` 而非仅凭 `localhost` 字面量；`TRUSTED_HOST_EXECUTION`、`SECRET` 读取、`NON_RETRYABLE` 工具、未资格化 `CODE_EXECUTION` 后端均硬拒绝；控制设置、远端 `SENSITIVE` 与截断预览返回 `REQUIRE_LOCAL`；模型风险评分、MCP `readOnlyHint`/`idempotentHint`、`pathspec` 命中或远程授权永远无法覆盖 `DENY` 或 `REQUIRE_LOCAL`，且 `CODE_EXECUTION`/`EXTERNAL_WRITE` 始终保持一次一审 `ASK`。

实现（OB-019）：新增 `services/core/src/openbot/application/dispatch.py`（`DispatchService`、`RecoveryTicket` 与 `mint_recovery_ticket`）：
1. 第一短事务 `claim`（`READY -> CLAIMED`）：重新校验 Task `RUNNING` 且未取消、当前激活 `runtime_epoch`、原提案 canonical 绑定、`identity_epoch`、`policy_version`、工作区 `generation`、工具 `manifest_digest`、授权时钟与 TTL；首次 claim 原子消费 `APPROVED -> CONSUMED`、分配单调 `fencing_token` 与有序资源租约、创建新 `Attempt` 及 Attempt 级 `dispatch_id`（保留 Operation 级 `provider_idempotency_key`）。
2. 安全重试门禁：普通调用者无法复用 `CONSUMED` 授权；仅持有恢复器签发 `RecoveryTicket`（绑定同一 `operation_id`、`prior_attempt_id` 与 `runtime_epoch`）的恢复路径可在不回退 `CONSUMED` 状态、不二次消费的前提下创建新 `Attempt` 与新 `dispatch_id`，且仍逐项复验原期限、时钟权威、policy、identity、cancel 与资源版本。
3. 第二短事务 `begin_dispatch`（`CLAIMED -> DISPATCHING`）：向执行器发送指令前再次在独立短事务中复验取消、`runtime_epoch`、policy、identity、工作区版本、授权有效期及 `resource_leases` 持有状态；同 Attempt 重传保持原 `dispatch_id`。

实现（OB-020）：新增 `services/core/src/openbot/application/recovery.py`（`RecoveryService`）：
1. `recover_epoch`：扫描在途 `DISPATCHING` 操作并转为 `UNKNOWN`（关联 Task 转 `RECONCILING`）；若旧执行域未证明隔离（`old_epoch_isolated=False`），旧实例记 `LOST` 且拒绝切换激活 `active_runtime_epoch`；已证明隔离时旧实例记 `STOPPED` 并激活新 `runtime_epoch`。
2. `recover_operation`：要求旧 `runtime_epoch='STOPPED'` 并复核原提案期限、policy、identity、cancel 与工作区版本；未派发 `CLAIMED` 动作释放租约、旧 attempt 记 `ABANDONED`、Operation 回到 `READY` 并签发 `RecoveryTicket`；`DISPATCHING/UNKNOWN` 按 `retry_class` 分流（`SAFE_READ`、`IDEMPOTENT_WRITE(NOT_APPLIED)`、有效窗口内 `PROVIDER_IDEMPOTENT(CONFIRMED_NOT_EXECUTED)` 记录证据后释放租约回 `READY` 并签发 `RecoveryTicket`；`RECONCILE_ONLY`/`NON_RETRYABLE`/未知探针保持 `UNKNOWN` 与资源 quarantine，绝不签发重试凭据）。
3. `reconcile_unknown`：严格校验 `reconciliation.schema.json` 与 `expected_version`，仅接受 `PROVIDER_VERIFIED` 或 `USER_ATTESTED` 来源（拒绝 `MODEL_OUTPUT` 或无 `AVAILABLE` 产物引用的纯文本 `success`），核验关联 `artifacts` 与 `artifact_refs` 后解决 `UNKNOWN -> SUCCEEDED/FAILED` 并释放资源 quarantine。

实现（OB-022）：新增 `services/core/src/openbot/application/cancellation.py`（`CancellationService`、`WorkerStopPort`、`WorkerStopAck`）：
1. `request_cancel`：在单 writer 短事务内先持久化 `cancel_revision` 与首次 `cancel_requested_at`，释放未派发 `CLAIMED` attempt 的资源租约，将待决/已批准未消费的 `PENDING/APPROVED` 审批撤销为 `REVOKED`（`CONSUMED` 绝不回退或复活），并将 `PROPOSED/AWAITING_APPROVAL/READY/CLAIMED` 操作与未派发 attempt 置为 `CANCELLED`；使后续 `CLAIMED -> DISPATCHING` 第二短事务必然拒绝发包。
2. `propagate_cancel` 与终态保护：先等待短事务落盘确认（未确认落盘绝不谎报取消成功），再在事务外通过 `WorkerStopPort` 向所有在途 `DISPATCHING` 执行器发送停止信号；任何停止回执均显式标记 `effect_rolled_back=False`，并保留已成功操作列表 `preserved_succeeded_operations`（绝不伪称已发生的外部副作用已回滚）；存在 `DISPATCHING` 或 `UNKNOWN` 时任务保持 `RECONCILING`。
3. `finalize_cancelled` 与 `inspect_cancel_status`：仅当所有在途/未知操作均已核对闭合后才允许 `RECONCILING -> CANCELLED`；客户端超时/断连后可通过稳定 `request_id` 幂等重查或调用 `inspect_cancel_status` 读取真实 `cancel_revision` 持久状态，绝不把客户端等待取消当作撤销已提交取消请求。

实际命令：
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_policy_evaluator.py -q --tb=short`（20 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/integration/storage -q --tb=short`（75 passed，含 `test_dispatch.py` 6 passed、`test_recovery.py` 3 passed、`test_outbox.py` 4 passed 与 `test_cancellation.py` 3 passed，见 evidence/implementation/m1-storage-tests.log）
- 完整验证命令为 `.venv/bin/python scripts/verify.py` 与 `.venv-m1/bin/python scripts/verify.py --phase M1`，各自真实退出码/日志 hash 位于 verification.json、m1-verification.json。

当前限制：提案与审批仍仅 local/internal 用例，未接认证 API、飞书、安全 ApprovalPreview 或真实持久 challenge store；上游 OB-015/093 尚未闭合。因此 OB-017/018/019/020/022/031 均保持 IN_PROGRESS，不凭该子集关闭 OB-029。

## English Summary

- **OB-017 / OB-018 (`IN_PROGRESS`)**: Authoritative RFC 8785 canonical proposal bytes stored in `operations.proposal_canonical_json` (migration 0002) and one-time approval decisions (`PENDING -> APPROVED/DENIED`). Approval only moves an Operation to `READY`; `CONSUMED` grants never revive.
- **OB-031 (`IN_PROGRESS`)**: Deterministic 6D table-driven `PolicyEvaluator` (`actor`, `resource`, `action`, `data_class`, `destination`, `execution_backend`) verifying `policy_revisions` SHA-256 digests, domain intersections, and `verified_local_model` for `LOCAL_MODEL`. Model risk scores, MCP hints, and `pathspec` never grant permissions.
- **OB-019 (`IN_PROGRESS`)**: Two-phase pre-dispatch gate (`DispatchService.claim` for `READY -> CLAIMED` consuming `APPROVED -> CONSUMED` and assigning attempt-scoped `dispatch_id`; `DispatchService.begin_dispatch` for `CLAIMED -> DISPATCHING` re-verifying cancellation, `runtime_epoch`, policy, identity, workspace generation, and held leases).
- **OB-020 (`IN_PROGRESS`)**: Side-effect aware crash recovery (`RecoveryService.recover_epoch`, `recover_operation` across 5 `retry_class` values issuing `RecoveryTicket` only when safe, and `reconcile_unknown` requiring `PROVIDER_VERIFIED` or `USER_ATTESTED` provenance with `AVAILABLE` artifacts).
- **OB-022 (`IN_PROGRESS`)**: Durable cancellation and stop propagation (`CancellationService` in `services/core/src/openbot/application/cancellation.py`):
  1. `request_cancel`: Persists `cancel_revision` and `cancel_requested_at` first, releases undispatched `CLAIMED` leases, revokes `PENDING/APPROVED` approvals (`CONSUMED` untouched), and cancels `PROPOSED/AWAITING_APPROVAL/READY/CLAIMED` operations so `begin_dispatch` is blocked.
  2. `propagate_cancel`: Commits DB state before propagating stop signals via `WorkerStopPort` outside the transaction; always reports `effects_rolled_back=False` and `preserved_succeeded_operations`, keeping the task in `RECONCILING` when `DISPATCHING`/`UNKNOWN` operations exist.
  3. `finalize_cancelled` & `inspect_cancel_status`: Transitions `RECONCILING -> CANCELLED` only after all unknown effects are reconciled, and allows disconnected callers to inspect durable `cancel_revision` without rolling back committed cancellations.
