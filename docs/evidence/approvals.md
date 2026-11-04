# OB-017—020 / OB-022 / OB-031—033 / OB-037—039：提案、审批、六维策略、派发、恢复、取消、文件守卫/只读工具、统一外发、密钥与输出过滤 / Proposals, Approvals, 6D Policy, Dispatch, Recovery, Cancellation, File Guard/Read Tools, Egress, Secrets, and Redaction

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

实现（OB-032）：新增 `services/core/src/openbot/tools/filesystem_guard.py`（`WorkspaceFileGuard`、`ObservedFileSnapshot`、`validate_relative_workspace_path`、`build_safe_git_worktree_env_and_argv`、`build_safe_ripgrep_argv`）：
1. 攻击路径语料拒绝（`validate_relative_workspace_path`）：拒绝空路径、控制字符/NUL、绝对路径、`..` 越界、Windows 盘符/UNC（`\\server\share`）/Win32 设备前缀（`\\?\`、`\\.\`）/ADS 数据流（`:`）/保留设备名（`CON`、`NUL`、`COM1` 等）、尾随点或空格，以及工作区内 `.git`、`.env`、私钥（`id_rsa`、`id_ed25519`、`*.pem`、`*.key`）等敏感路径。
2. OS 目录句柄与 `O_NOFOLLOW` 逐步核验（`WorkspaceFileGuard`）：从工作区根 `dir_fd` 逐段执行 `os.lstat(..., dir_fd=cur_fd)` 与 `os.open(..., O_DIRECTORY | O_NOFOLLOW, dir_fd=cur_fd)` 校验 `st_dev` 与 `st_ino`，任何中间或末端 symlink、跨设备挂载、非普通文件或多硬链接写覆盖均立即拒绝；`observe` 记录父目录 inode、文件 inode 与 SHA-256，`write_atomic` 在同父目录句柄内复验父目录 inode 与旧文件 SHA-256 后经同目录临时文件 `fsync` + `os.replace(..., src_dir_fd=parent_fd, dst_dir_fd=parent_fd)` 原子替换，阻断观测后父目录被替换为外部符号链接的竞态。
3. Git worktree 与 ripgrep 安全隔离（`build_safe_git_worktree_env_and_argv`、`build_safe_ripgrep_argv`）：在调用 Git 前审计 `.git/config` 与 `.gitattributes`，拒绝 `fsmonitor`、`hooksPath`、`sshCommand`、`filter.*` 等可执行指令，并强制 `-c core.hooksPath=/dev/null -c core.fsmonitor=false -c protocol.allow=never` 与 `GIT_CONFIG_NOSYSTEM=1`；ripgrep 构建器剥离 `RIPGREP_CONFIG_PATH` 并强制 `--no-config --no-pre --no-follow --`，确保模式串不注入 `--pre` 预处理器。

实现（OB-033）：新增 `services/core/src/openbot/tools/workspace/read.py`（`WorkspaceReadTools`、`WorkspaceReadLimits`、`build_pinned_ripgrep_command`）：
1. 固定摘要 `rg` 命令构建（`build_pinned_ripgrep_command`）：核验 `rg` 二进制真实文件与 SHA-256 摘要，清理 `RIPGREP_CONFIG_PATH` 与代理环境变量，固定生成 `--json --no-config --no-pre --no-follow -e <pattern> -- <subpath>`（不开放原始 flags，防止以 `--pre=` 开头的查询串注入预处理器），且不引入不必要的 `ripgrepy` 包装。
2. 有界 `list_entries`、`read` 与 `search`（`WorkspaceReadTools`）：全部路径经 `WorkspaceFileGuard` 逐步句柄核验；MVP 严格以 UTF-8 为文本边界（拒绝含 NUL 字节的二进制文件 `BINARY_FILE_UNSUPPORTED` 与非 UTF-8 文件 `NON_UTF8_TEXT_UNSUPPORTED`，不因候选编码检测库自动扩张编码）；分别施加目录深度（`max_depth`）、扫描文件数（`max_files_scanned`）、单文件字节（`max_single_file_bytes`）、全局命中数（`max_global_matches`）、全局输出总字节（`max_global_output_bytes`）、单行字符（`max_line_chars`）与耗时（`timeout_ms`）上限；所有结果均携带 `sha256`、`provenance_kind='UNTRUSTED_WORKSPACE_FILE'` 与 `executable_instructions=False`。

实现（OB-037）：新增 `services/core/src/openbot/policy/egress.py`（`EgressGuard`、`EgressRequest`、`EgressDecision`、`LocalModelRunnerAttestation`、`ControlledHttpConfig`、`build_controlled_http_config`）：
1. 全出口统一评估：共享覆盖 `MODEL_GATEWAY`、`LOCAL_MODEL_RUNNER`、`FEISHU_NOTIFICATION`、`BROWSER`、`MCP`、`FILE_UPLOAD` 与 `MESSAGE_TOOL`；`OFFLINE` 模式阻断所有出口的全部远端连接（不只限制 LLM）；`SECRET` 数据在任何出口（含 `redacted=True`）均硬拒绝（`SECRET_EGRESS_FORBIDDEN`）。
2. 敏感预览/摘要保护与隐式出口阻断：`SENSITIVE` 数据不会因放进通知卡片（返回 `REQUIRE_LOCAL`）、上下文摘要（`from_summary=True`）或 Artifact（`from_artifact=True`）而自动放行，发送到允许域名的模型也必须经过显式一次一审 `ASK`；任何 Provider 托管 `web_search`/`remote_mcp`、价格表/词表/语法包运行期下载或扫描器在线验证均直接 `DENY`。
3. 本地模型 Runner 核验与受控 HTTP 代理配置：允许 loopback 地址不等于允许云转发，必须通过 `LocalModelRunnerAttestation` 证明本地模型来源、禁用 `:cloud` 路由、禁用 web search 且出口隔离已验证；`build_controlled_http_config` 强制 `trust_env=False`、`follow_redirects=False`、`max_retries=0`，清理环境 `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` 并仅允许白名单内代理，同时显式声明 Python 审计探针覆盖范围与需要 OS/容器隔离证明的边界。

实现（OB-038）：新增 `services/core/src/openbot/policy/secrets/broker.py`（`SecretBroker`、`SecretUnavailableError`、`SingleUseSecretHandle`、`build_minimal_child_spawn_spec`）与 `native/supervisor/src/credential_transport.rs`：
1. 锁定 OS 凭据后端白名单（`APPROVED_KEYRING_BACKENDS`）：仅允许 `macos.Keychain`、`windows.WinVaultKeyring`、`linux.SecretService`，拒绝明文文件、未知插件或无独立主密钥的 `Fernet` 文件自动回退；钥匙串锁定（`KEYCHAIN_LOCKED`）、无 D-Bus（`DBUS_UNAVAILABLE`）、无图形会话（`HEADLESS_NO_SESSION`）或用户取消（`USER_CANCELLED`）时抛出不含任何秘密字节的 `SecretUnavailableError`。
2. 按组件最小权限隔离注入：飞书网关仅可解析 `keychain:feishu:*`；模型网关仅可解析匹配 `selected_provider` 的 `keychain:provider:<selected_provider>:*`（禁止跨 Provider 读取或读取飞书密钥）；Worker 仅获得绑定 `attempt_id` 与有效期的单用途短时 IPC 句柄 `SingleUseSecretHandle`（一次消费即销毁，撤销或轮换 `secret_ref` 立即使全部在途句柄失效）。
3. 子进程环境净化与 Canary 扫描（`build_minimal_child_spawn_spec`）：不继承父进程 `os.environ`，拒绝挂载宿主 `HOME` 目录，扫描并拒绝任何包含测试/已注册密钥 canary 的 `argv`，确保 child env、argv、异常栈与诊断中零密钥泄漏。

实现（OB-039）：新增 `services/core/src/openbot/observability/redaction.py`（`StreamingSecretRedactor`、`RedactionPipeline`、`RedactionContract`、`RedactionResult`）：
1. 跨任意分片与超长秘密的流式过滤（`StreamingSecretRedactor`）：根据已注册秘密及其 Base64/URL/JSON 转义变体的最大长度动态扩展 `holdback_window_chars`（不依赖固定 128 字节窗口），支持在任意字符边界切分的流式 `feed()` + `flush()`，并结合离线审查过的模式规则（Bearer、`sk-*`、`fs_sec_*`、`cli_*`、PEM 私钥等）先过滤再持久化或外发。
2. 忽略外部 Allowlist 与永久禁用在线验证：外部 `# pragma: allowlist secret` 等注释完全不生效；`network_verification_enabled=False` 且 `verify_secret_online_forbidden` 硬拒绝任何向第三方验证端点发送秘密的行为。
3. 全出口统一接入与分类保护（`RedactionPipeline`）：统一覆盖 `stdout`、`stderr`、`sdk_debug`、`exception`、`http_header`、`ui_event`、`artifact`、`diagnostic` 与 `model_input` 九类出口；显式声明 `guarantees_100_percent_detection=False` 与 `negative_scan_downgrades_classification=False`（扫描阴性绝不降低 `SECRET`/`SENSITIVE` 分类，不确定敏感内容 `uncertain_sensitivity=True` 直接阻断远端外发）。

实际命令：
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_policy_evaluator.py -q --tb=short`（20 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_filesystem_guard.py -q --tb=short`（22 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_workspace_read_tools.py -q --tb=short`（2 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_egress_policy.py -q --tb=short`（3 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_secrets_broker.py -q --tb=short`（3 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_redaction.py -q --tb=short`（2 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/integration/storage -q --tb=short`（75 passed，含 `test_dispatch.py` 6 passed、`test_recovery.py` 3 passed、`test_outbox.py` 4 passed 与 `test_cancellation.py` 3 passed，见 evidence/implementation/m1-storage-tests.log）
- 完整验证命令为 `.venv/bin/python scripts/verify.py` 与 `.venv-m1/bin/python scripts/verify.py --phase M1`，各自真实退出码/日志 hash 位于 verification.json、m1-verification.json。

当前限制：提案与审批仍仅 local/internal 用例，未接认证 API、飞书、安全 ApprovalPreview 或真实持久 challenge store；上游 OB-015/093 及三平台真实 OS Keychain 实测尚未闭合。因此 OB-017/018/019/020/022/031/032/033/037/038/039 均保持 IN_PROGRESS，不凭该子集关闭 OB-029。

## English Summary

- **OB-017 / OB-018 (`IN_PROGRESS`)**: Authoritative RFC 8785 canonical proposal bytes stored in `operations.proposal_canonical_json` (migration 0002) and one-time approval decisions (`PENDING -> APPROVED/DENIED`). Approval only moves an Operation to `READY`; `CONSUMED` grants never revive.
- **OB-031 (`IN_PROGRESS`)**: Deterministic 6D table-driven `PolicyEvaluator` (`actor`, `resource`, `action`, `data_class`, `destination`, `execution_backend`) verifying `policy_revisions` SHA-256 digests, domain intersections, and `verified_local_model` for `LOCAL_MODEL`. Model risk scores, MCP hints, and `pathspec` never grant permissions.
- **OB-019 (`IN_PROGRESS`)**: Two-phase pre-dispatch gate (`DispatchService.claim` for `READY -> CLAIMED` consuming `APPROVED -> CONSUMED` and assigning attempt-scoped `dispatch_id`; `DispatchService.begin_dispatch` for `CLAIMED -> DISPATCHING` re-verifying cancellation, `runtime_epoch`, policy, identity, workspace generation, and held leases).
- **OB-020 (`IN_PROGRESS`)**: Side-effect aware crash recovery (`RecoveryService.recover_epoch`, `recover_operation` across 5 `retry_class` values issuing `RecoveryTicket` only when safe, and `reconcile_unknown` requiring `PROVIDER_VERIFIED` or `USER_ATTESTED` provenance with `AVAILABLE` artifacts).
- **OB-022 (`IN_PROGRESS`)**: Durable cancellation and stop propagation (`CancellationService` in `services/core/src/openbot/application/cancellation.py`):
  1. `request_cancel`: Persists `cancel_revision` and `cancel_requested_at` first, releases undispatched `CLAIMED` leases, revokes `PENDING/APPROVED` approvals (`CONSUMED` untouched), and cancels `PROPOSED/AWAITING_APPROVAL/READY/CLAIMED` operations so `begin_dispatch` is blocked.
  2. `propagate_cancel`: Commits DB state before propagating stop signals via `WorkerStopPort` outside the transaction; always reports `effects_rolled_back=False` and `preserved_succeeded_operations`, keeping the task in `RECONCILING` when `DISPATCHING`/`UNKNOWN` operations exist.
  3. `finalize_cancelled` & `inspect_cancel_status`: Transitions `RECONCILING -> CANCELLED` only after all unknown effects are reconciled, and allows disconnected callers to inspect durable `cancel_revision` without rolling back committed cancellations.
- **OB-032 (`IN_PROGRESS`)**: OS handle-backed workspace file guard (`services/core/src/openbot/tools/filesystem_guard.py`):
  1. `validate_relative_workspace_path`: Rejects traversal, absolute paths, UNC/Win32 device prefixes (`\\?\`, `\\.\`), ADS (`:`), reserved Windows device names (`CON`, `NUL`, `COM1`, etc.), trailing dots/spaces, and `.git`/`.env`/private key paths.
  2. `WorkspaceFileGuard`: Walks directory descriptors step-by-step with `O_NOFOLLOW` and `dir_fd`, verifying `st_dev` and `st_ino` at every hop; `observe` and `write_atomic` re-verify parent directory inode and old SHA-256 before writing via `fsync` + `os.replace(..., src_dir_fd=parent_fd, dst_dir_fd=parent_fd)` to defeat symlink swap races.
  3. `build_safe_git_worktree_env_and_argv` & `build_safe_ripgrep_argv`: Rejects `.git/config` hooks/filters/fsmonitor and enforces `-c core.hooksPath=/dev/null`; strips `RIPGREP_CONFIG_PATH` and forces `--no-config --no-pre --no-follow --`.
- **OB-033 (`IN_PROGRESS`)**: Bounded workspace `list`/`read`/`search` tools (`services/core/src/openbot/tools/workspace/read.py`):
  1. `build_pinned_ripgrep_command`: Verifies pinned `rg` binary SHA-256, strips `RIPGREP_CONFIG_PATH` and proxy variables, and binds patterns with `-e` and paths after `--` alongside `--json --no-config --no-pre --no-follow`.
  2. `WorkspaceReadTools`: Enforces `WorkspaceFileGuard` on every path, strict UTF-8 text boundary (rejecting binary NUL bytes and non-UTF-8 encodings), and separate limits on depth, files scanned, single-file size, global match count, global output bytes, line length, and timeout, tagging all outputs with `provenance_kind='UNTRUSTED_WORKSPACE_FILE'` and `executable_instructions=False`.
- **OB-037 (`IN_PROGRESS`)**: Unified data egress policy (`services/core/src/openbot/policy/egress.py`):
  1. `EgressGuard`: Evaluates `PUBLIC`/`WORKSPACE`/`SENSITIVE`/`SECRET` across `MODEL_GATEWAY`, `LOCAL_MODEL_RUNNER`, `FEISHU_NOTIFICATION`, `BROWSER`, `MCP`, `FILE_UPLOAD`, and `MESSAGE_TOOL`; `OFFLINE` blocks remote egress across all surfaces; `SECRET` is always denied.
  2. Taint & implicit-feature protection: `SENSITIVE` data in notification cards returns `REQUIRE_LOCAL` and in summaries/artifacts to allowed model domains requires `ASK`; provider-hosted `web_search`/`remote_mcp`, asset downloads, and online secret verification are denied.
  3. `LocalModelRunnerAttestation` & `build_controlled_http_config`: Requires verified local model source, disabled cloud routing, and isolated egress rather than trusting `localhost`; strips ambient proxy variables and enforces `trust_env=False`, `follow_redirects=False`, `max_retries=0` while documenting Python probe boundaries.
- **OB-038 (`IN_PROGRESS`)**: OS credential storage contract and minimal compartmentalized secret injection (`services/core/src/openbot/policy/secrets/broker.py` and `native/supervisor/src/credential_transport.rs`):
  1. `APPROVED_KEYRING_BACKENDS` & `SecretUnavailableError`: Rejects plaintext or ad-hoc Fernet file fallbacks and unapproved plugins; fails closed on locked keychain, missing D-Bus, headless session, or user cancellation without leaking secret bytes in exceptions.
  2. `SecretBroker`: Compartmentalizes secrets so the Feishu gateway only accesses `keychain:feishu:*`, model gateways only access `keychain:provider:<selected_provider>:*`, and workers only receive attempt-bound single-use IPC handles (`SingleUseSecretHandle`) invalidated on consumption, rotation, or revocation.
  3. `build_minimal_child_spawn_spec`: Prevents inheriting ambient `os.environ`, blocks mounting host `HOME`, and rejects `argv` containing any registered secret canary.
- **OB-039 (`IN_PROGRESS`)**: Streaming offline secret redaction across all output sinks (`services/core/src/openbot/observability/redaction.py`):
  1. `StreamingSecretRedactor`: Dynamically sizes its holdback window to the longest registered secret (including Base64, URL-encoded, and JSON-escaped variants) rather than relying on a fixed 128-byte window; redacts secrets split across arbitrary chunk boundaries.
  2. No allowlist or network bypass: Ignores `# pragma: allowlist secret` comments and permanently disables online secret verification (`network_verification_enabled=False`).
  3. `RedactionPipeline`: Filters `stdout`, `stderr`, `sdk_debug`, `exception`, `http_header`, `ui_event`, `artifact`, `diagnostic`, and `model_input` without downgrading `SECRET`/`SENSITIVE` classifications on negative scans (`guarantees_100_percent_detection=False`).
