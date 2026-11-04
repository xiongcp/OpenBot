# OB-017 / OB-018 / OB-019 / OB-031：不可变提案、审批决定、确定性策略评估器与两次短事务派发门禁

先读取各项 component_refs/reuse_type/reuse_notes：复用已通过本机标准向量的 rfc8785/jsonschema；SQLite 标准库经唯一 writer 使用。OB-031 保持纯代码表驱动评估器，不引入 OPA/Casbin，也不以 pathspec 匹配结果充当安全路径白名单或授权判定。OB-019 两次短事务 claim→DISPATCHING 与恢复凭据校验完全自研。没有引入新 SDK、ORM、自动 runner 或第二账本。

实现（OB-017/018）：Operation 从本地 ACTIVE manifest、可信上下文、固定 TTL/nonce 和工具 args schema 构造；完整 JCS 字节保存到原 operations 表新增列，索引投影逐项复核。新增 migration 0002，原 0001/23 表设计基线未改。批准只使 Operation READY；本子集不创建 Attempt、不派发工具。审批状态、Task、脱敏 event/outbox 在同一事务提交；稳定 request_id 包含认证来源作用域。

实现（OB-031）：新增 `services/core/src/openbot/policy/evaluator.py`，从 SQLite `profile_config`、`policy_revisions`（复核 canonical SHA-256 digest）与 `tool_registry`（仅 ACTIVE 工具）构造不可变 `PolicySnapshot`；按 `actor / resource / action / data_class / destination / execution_backend` 六维输入做纯确定性评估，输出 `ALLOW / ASK / DENY / REQUIRE_LOCAL`、理由码、有效网络模式与允许域名交集（`profile & workspace & request`，任何扩权尝试直接 `DENY`）。`LOCAL_MODEL` 强制校验 `verified_local_model` 而非仅凭 `localhost` 字面量；`TRUSTED_HOST_EXECUTION`、`SECRET` 读取、`NON_RETRYABLE` 工具、未资格化 `CODE_EXECUTION` 后端均硬拒绝；控制设置、远端 `SENSITIVE` 与截断预览返回 `REQUIRE_LOCAL`；模型风险评分、MCP `readOnlyHint`/`idempotentHint`、`pathspec` 命中或远程授权永远无法覆盖 `DENY` 或 `REQUIRE_LOCAL`，且 `CODE_EXECUTION`/`EXTERNAL_WRITE` 始终保持一次一审 `ASK`。

实现（OB-019）：新增 `services/core/src/openbot/application/dispatch.py`（`DispatchService`、`RecoveryTicket` 与 `mint_recovery_ticket`）：
1. 第一短事务 `claim`（`READY -> CLAIMED`）：重新校验 Task `RUNNING` 且未取消、当前激活 `runtime_epoch`、原提案 canonical 绑定、`identity_epoch`、`policy_version`、工作区 `generation`、工具 `manifest_digest`、授权时钟与 TTL；首次 claim 原子消费 `APPROVED -> CONSUMED`、分配单调 `fencing_token` 与有序资源租约、创建新 `Attempt` 及 Attempt 级 `dispatch_id`（保留 Operation 级 `provider_idempotency_key`）。
2. 安全重试门禁：普通调用者无法复用 `CONSUMED` 授权；仅持有恢复器签发 `RecoveryTicket`（绑定同一 `operation_id`、`prior_attempt_id` 与 `runtime_epoch`）的恢复路径可在不回退 `CONSUMED` 状态、不二次消费的前提下创建新 `Attempt` 与新 `dispatch_id`，且仍逐项复验原期限、时钟权威、policy、identity、cancel 与资源版本。
3. 第二短事务 `begin_dispatch`（`CLAIMED -> DISPATCHING`）：向执行器发送指令前再次在独立短事务中复验取消、`runtime_epoch`、policy、identity、工作区版本、授权有效期及 `resource_leases` 持有状态；同 Attempt 重传保持原 `dispatch_id`。两事务之间发生取消、epoch 切换、工作区修改或策略升级时，第二事务立即拒绝，`dispatch_started_at` 保持 `NULL`，实现零派发。

实际命令：
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_policy_evaluator.py -q --tb=short`（20 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/integration/storage -q --tb=short`（65 passed，含 `test_dispatch.py` 6 passed，见 evidence/implementation/m1-storage-tests.log）
- 完整验证命令为 `.venv/bin/python scripts/verify.py` 与 `.venv-m1/bin/python scripts/verify.py --phase M1`，各自真实退出码/日志 hash 位于 verification.json、m1-verification.json；容器需单独显式资格命令，验证脚本不继承启用容器的环境变量。

当前限制：提案与审批仍仅 local/internal 用例，未接认证 API、飞书、安全 ApprovalPreview 或真实持久 challenge store；上游 OB-015/093 尚未闭合。因此 OB-017/018/019/031 均保持 IN_PROGRESS，不凭该子集关闭 OB-029。
