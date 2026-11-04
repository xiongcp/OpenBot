# OB-017—020 / OB-022 / OB-028—029 / OB-031—035 / OB-037—039 / OB-043—046 / OB-081：M1 提案、审批、六维策略、派发、恢复、取消、工具、外发、密钥、输出过滤、认证本地控制 API、CLI、垂直切片、安全威胁回归与本地 Alpha 边界说明 / M1 Proposals, Approvals, 6D Policy, Dispatch, Recovery, Cancellation, Tools, Egress, Secrets, Redaction, Local Control API, CLI, Vertical Slice, Threat Regression, and Local Alpha Boundary

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

实现（OB-034）：新增 `services/core/src/openbot/tools/workspace/patch.py`（`WorkspacePatchTool`、`FileEditSpec`、`FrozenFilePatchPlan`、`PatchProposalBundle`、`PatchApplyReport`）与 `services/core/src/openbot/tools/workspace/commit_journal.py`（`PatchCommitJournal`）：
1. 审批前冻结精确新旧哈希与新字节 Artifact（`propose_patch`）：使用 `WorkspaceFileGuard.observe` 观测目标文件而不改动工作区；拒绝重复匹配（`AMBIGUOUS_MULTIPLE_MATCHES`，多处匹配绝不猜测）；使用标准库 `difflib.unified_diff` 生成展示 Diff，并将确切新文件字节写入 `ArtifactStore` 固化 `old_sha256`、`new_artifact_id` 与 `new_sha256`。
2. 批准后精确字节替换与零 fuzz/零换行改写（`apply_patch`）：不调用 `patch-ng` 直接写宿主，也不在批准后做模糊匹配、CRLF/LF 修正或重算新内容；写入前逐文件复验 `ArtifactStore.verify_approved_digest`、目标文件当前 `old_sha256` 与父目录 inode（若用户在审批期间修改文件或改变行尾则立即拒绝）。
3. 逐文件提交日志与多文件部分失败恢复（`PatchCommitJournal`）：显式声明 `claims_cross_file_atomicity=False`（不冒充跨文件单文件系统事务）；写入前落盘 `journal.json` 及原文件备份字节，按文件调用 `WorkspaceFileGuard.write_atomic`；当第二文件提交失败时，自动按日志回滚已写入的第一文件至原字节并记录 `RESTORED_ORIGINAL` / `FAILED_NOT_APPLIED`，绝不调用 `git reset --hard`、自动 commit 或 push。

实现（OB-035）：新增 `services/core/src/openbot/tools/workspace/validation.py`（`PinnedGrammarRegistry`、`IsolatedParserWorker`、`WorkspaceValidationCoordinator`）：
1. 固定离线 Grammar 资产与禁工作区加载（`PinnedGrammarRegistry`）：校验已声明语言离线 grammar 资产存在性与 SHA-256（未安装语言立即返回 `CAPABILITY_UNAVAILABLE` 且禁运行期下载）；拒绝加载位于不可信工作区内的任何二进制/grammar 文件。
2. 独立有界子进程解析（`IsolatedParserWorker`）：在受输入大小（`max_input_bytes`）、括号嵌套深度（`max_nesting_depth`）与超时（`timeout_ms`）限制的独立子进程（`python -I`）中执行语法解析；模拟 native 崩溃（exit 139）或超时仅使单次解析返回 `PARSER_WORKER_CRASHED`/`PARSER_WORKER_TIMEOUT`，绝不破坏主 daemon 或审批账本。
3. 多文件按操作范围撤回与非功能正确声明（`WorkspaceValidationCoordinator`）：复用 `WorkspacePatchTool` 与 `PatchCommitJournal`，当多文件补丁中后一个文件语法验证失败时，仅撤回本次 Operation 修改的文件，完全保留工作区内用户原有的未提交修改；所有返回均显式标记 `functional_correctness_proven=False`（语法/lint 通过不等于功能正确）。

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

实现（OB-043）：新增 `services/core/src/openbot/tools/messages/draft.py`（`MessageDraftService`、`ContactCandidate`、`MessageDraftOutcome`）：
1. 稳定收件人解析与同名歧义阻断：当 `recipient_candidates` 缺失或存在多个同名候选人时，原子将 Task 转入 `WAITING_INPUT` 并返回 `sendable=False`、`draft_artifact_id=None`，绝不在收件人未唯一确认时生成可发送草稿。
2. 本地不可变草稿 Artifact 与修订版本绑定：校验全部附件 Artifact 的存在性与 SHA-256，将通道、账户、稳定 `recipient_id`、版本号（`revision`）、正文与附件摘要序列化为 canonical JSON 存入 `ArtifactStore`；每次修订生成新 `revision` 与新 `draft_sha256`，旧版本摘要在 `verify_latest_draft_binding` 中自动失效，且全过程零网络请求（`network_calls_made=0`）。

实现（OB-044）：新增 `services/core/src/openbot/tools/messages/send.py`（`MessageSendService`、`MessageSendTransportPort`、`MessageSendEnvelope`、`MessageSendResult`）：
1. 绑定草稿哈希与稳定收件人提案（`propose_send`）：在生成 `message.send` 提案前强制调用 `MessageDraftService.verify_latest_draft_binding` 核验最新不可变草稿 `draft_artifact_id` 与 `draft_sha256`，并将 `destination` 固定为 `MESSAGE_RECIPIENT`（绑定 `account_id` 与稳定 `recipient_id`），默认采用 `RECONCILE_ONLY` 重试类别。
2. 独立外发授权与适配门禁（`execute_approved_send`）：拒绝将普通 `owner_progress` 通知授权复用为第三方发送授权；在 M2 真实平台适配器通过验证前（`transport.qualified=False`）直接拒绝并返回 `CAPABILITY_UNAVAILABLE`；派发前再次核验 `caller_recipient_id`、最新草稿哈希与 `EgressGuard`。
3. 成功后断连进入 `UNKNOWN` 与禁止自动重发：经 `claim` -> `begin_dispatch` 两次短事务后在事务外调用 `transport.send_message`；若发送中断连或回执丢失，将 `operation_attempts` 与 `operations` 置为 `UNKNOWN`、关联 Task 置为 `RECONCILING` 并保留资源 quarantine；后续恢复（`RecoveryService.recover_operation`）对 `RECONCILE_ONLY` 绝不签发重试凭据，防止重复发送外部消息。

实现（OB-081）：新增 `services/core/src/openbot/adapters/local_api/server.py`（`LocalControlApiServer`、`ScopedTokenStore`、`ApiRequest`、`ApiResponse`）与 `tests/contracts/local_api/test_local_api_contracts.py`、`tests/security/local_api/test_local_api_security.py`：
1. Loopback、Host/Origin、Proxy 头拦截、Profile 绑定与分域 Token：强制 `client_ip in {'127.0.0.1', '::1'}`，任何携带 `X-Forwarded-For`、`X-Real-IP`、`Forwarded` 的代理伪造请求直接返回 `403 PROXY_HEADER_FORBIDDEN`；强制校验本地 `Host` 与受控 `Origin`（阻断跨源网页与 DNS rebinding）；划分 `owner_cli`、`feishu_gateway`（内部网关独立 scope，调用本地 challenge 端点返回 `403 CHALLENGE_OWNER_SCOPE_ONLY`）与 `webview_readonly`（写请求返回 `403 READONLY_SCOPE_FORBIDDEN`）三类 Token。
2. 完整控制端点与安全预览/核对规则：提供 `/v1/health`、`/v1/tasks`（含 `Idempotency-Key` 冲突 `409`）、`/v1/tasks/{id}/cancel`、`/v1/tasks/{id}/resume`、`/v1/approvals/{id}/preview`（永不暴露 `SECRET` 或原始 `nonce`）、`/v1/approvals/{id}/challenge`（仅限有效 `PENDING` 且 `owner_cli`）、`/v1/approvals/{id}/decide`、`/v1/operations/{id}`（含 `Operation.version`）、`/v1/operations/{id}/evidence`（只接收内联受限字节，拒绝 `host_path`）与 `/v1/operations/{id}/reconcile`（拒绝客户端指定 `target_state` 或 `revive_consumed_grant`）。
3. SSE 事件流游标与保留期校验（`/v1/tasks/{id}/events`）：当 `after_seq` 与 `Last-Event-ID` 同时存在且冲突时返回 `400 SSE_CURSOR_CONFLICT`；当游标早于保留期下界（`after_seq < min_retained_event_seq`）时返回 `410 CURSOR_EXPIRED_FETCH_SNAPSHOT`。

实现（OB-028）：更新 `services/core/src/openbot/cli.py`（`CliApiSession`、`run_cli_command`、`sanitize_terminal_text`）并新增 `tests/integration/cli/test_cli_workflow.py`：
1. 纯本地认证 API 会话与零 SQLite 旁路：`task create|show|cancel|resume`、`approval preview|decide`（`APPROVE` 自动通过 `owner_cli` token 申请一次性 challenge nonce，`feishu_gateway` 调用返回码 `3`）、`operation reconcile`（上传内联证据生成 `OPERATION` artifact 后提交核对）全经 `/v1/*` 完成。
2. 反旁路、ANSI 转义与超时未知语义：拦截 `--ignore-and-rerun`、`--force-success`、`--revive-consumed`（返回码 `6`）；`sanitize_terminal_text` 剥离 ANSI CSI/OSC 控制字符与富文本标签；无 daemon 返回码 `2`，等待超时返回码 `5` 且强制声明 `action_guaranteed_not_executed=false`、`requery_required=true`。

实现（OB-029）：新增 `services/core/src/openbot/application/vertical_slice.py`（`M1VerticalSliceHarness`）、`tests/integration/scenarios/first_vertical_slice/test_first_vertical_slice.py` 与中英双语 `docs/demos/m1.md`：
1. 真实本地受限效果闭环（`run_local_restricted_effect_slice`）：在 `OFFLINE` 模式下串联 CLI → 认证本地控制 API → 持久 Task → 工作区文件补丁提案（`WorkspacePatchTool` + `ArtifactStore` SHA-256 冻结）→ CLI 审批（`CONSUMED` 一次性消费）→ `claim`/`begin_dispatch` → 真实工作区文件修改、受监管子进程回收（`ProcessSupervisorService`）与持久 Outbox 投递（`OutboxService`）。
2. 五个崩溃点与重复输入验证（`run_fault_crash_scenario`）：覆盖 `before_claim`、`after_claim_before_dispatch`（一次性 `RecoveryTicket` 恢复）、`after_dispatch_before_effect`、`after_effect_before_receipt`（`UNKNOWN`/`RECONCILING` 零盲目重放 + CLI 核对恢复）与 `after_complete_before_outbox_ack`，并校验重复 CLI 请求 ID 幂等稳定。

实现（OB-045）：新增 `services/core/src/openbot/policy/threat_regression.py`（`M1ThreatRegressionSuite`）、`tests/security/test_m1_threat_regression.py` 与中英双语 `docs/demos/m2.md`：
1. 7 类安全与恢复威胁回归语料直接针对真实守卫断言 `total_unauthorized_side_effects == 0`：JCS 深层变异与重复键拒绝、路径穿越与符号链接逃逸阻断、ripgrep/Git 危险配置与预处理器剥离、工作区内 grammar 二进制与运行期下载阻断、跨分域密钥读取与命令行参数泄露阻断、`/bin/sh -c` 宿主 shell 包装拒绝与输出洪泛截断、残留子进程 PID 强制触发 `quarantine_required=True` 与 `new_dispatch_allowed=False`。

实现（OB-046）：新增 `services/core/src/openbot/application/local_prototype.py`（`LocalAlphaPrototypeRunner`、`LocalAlphaCapabilityReport`）、`tests/integration/scenarios/local_prototype/test_local_prototype.py` 与中英双语 `docs/releases/local-prototype-acceptance.md`：
1. 从空白配置目录一键跑通 `workspace.read` → `workspace.propose_patch` → CLI 审批 → `workspace.apply_patch` 与隔离进程回收 → 崩溃重启核对恢复，生成结构化能力报告并诚实声明试点 OS（`Darwin-arm64`）、未实测平台（`Windows-native`、`Linux-native`）及未接入外部能力（`real_feishu_tenant`、`claims_full_mvp_complete=False`）。

实现（OB-048）：新增 `services/core/src/openbot/policy/pairing.py`（`PairingService`、`PairingChallenge`、`PendingPairingCandidate`）、`services/feishu_gateway/src/openbot_feishu/pairing.py`（`FeishuPairingForwarder`）与 `tests/integration/feishu/test_pairing.py`：
1. 本地挑战与待确认候选分离：由本地生成绑定 `profile_id`、`expected_tenant_key`、`expected_app_id` 的短 TTL 限次挑战，远端飞书回传仅生成 `PENDING_LOCAL_CONFIRMATION` 候选；首个陌生远端发信人绝不自动成为 owner（`auto_paired=False`）；本地确认（`confirm_candidate_locally`）才写入 `channel_accounts` 与 `channel_identities`。
2. Owner 撤销与 `identity_epoch` 递增：`revoke_owner` 原子将 `channel_identities` 置为 `REVOKED` 并将 `profile_config.identity_epoch` 加 1，使旧 `InboundContext` 立即被 `authorize()` 拒绝。

实现（OB-049）：新增 `services/feishu_gateway/src/openbot_feishu/inbound.py`（`FeishuInboundAdapter`、`FeishuInboundConfig`、`InboundEventOutcome`）与 `tests/integration/feishu/test_inbound.py`：
1. 持久化提交后才 ACK：通过内部受限 API 提交 `/v1/tasks`，仅当 daemon `Inbox` 返回 200/201 时 `ws_ack=True`；持久化失败时 `ws_ack=False`（`INBOX_PERSIST_FAILED`），且回调线程从不阻塞等待 LLM（`llm_waited_in_callback=False`）。
2. 群聊、陌生发信人、跨租户与超限附件拦截：默认禁用群聊（`GROUP_CHAT_DISABLED`），拒绝未配对/已撤销发信人（`UNPAIRED_SENDER`）与超限附件（`ATTACHMENT_TOO_LARGE`），重复事件幂等返回相同 `task_id`。

实现（OB-050）：新增 `services/core/src/openbot/application/approval_use_case.py`（`RemoteApprovalUseCase`、`RemoteApprovalResult`）、`services/feishu_gateway/src/openbot_feishu/approval_callback.py`（`FeishuApprovalCallbackHandler`）与 `tests/integration/feishu/test_approval_callback.py`：
1. 真实 operator 校验与拒绝伪造载荷：从飞书卡片回调顶层 `event.operator.open_id` 提取操作人并经 `PairingService.is_active_owner` 校验，完全忽略 `action.value` 中伪造的 `is_owner` 或 `principal_id`。
2. 旧卡拦截与未确认提交诚实响应：已取消/已终结 Task 的旧审批卡直接返回 `APPROVAL_REJECTED_OR_STALE`；数据库超时或提交未确认时返回 `COMMIT_UNCONFIRMED`（`approved=False`），绝不谎称已批准或阻塞等待模型/worker。

实现（OB-051）：新增 `services/feishu_gateway/src/openbot_feishu/cards.py`（`FeishuPlainCardBuilder`、`RenderedApprovalCard`、`RenderedResultCard`）与 `tests/unit/test_feishu_cards.py`：
1. 零 CardKit 依赖的纯函数普通卡片：支持任务审批卡与结果回执卡离线构造，无隐式发送或 owner 赋权副作用。
2. 敏感或截断影响强制 `REQUIRE_LOCAL`：当 `data_class` 为 `SENSITIVE`/`SECRET` 或预览被截断（`truncated=True`）时，自动隐藏敏感摘要并禁用远端一键批准按钮（`mode='REQUIRE_LOCAL'`，`remote_approve_enabled=False`）；结果卡对 `UNKNOWN` 明确标记 `RECONCILIATION_REQUIRED`。

实现（OB-052）：新增 `services/feishu_gateway/src/openbot_feishu/progress.py`（`FeishuProgressCardCoordinator`、`CoalescedProgressUpdate`）与 `tests/unit/test_feishu_progress.py`：
1. 版本递增与高频进度合并节流：节流窗口内的 100 次中间进度更新自动合并为 1 条待投递快照（`coalesced_count=99`），处理 `retry_after` 限流退避；终态（`SUCCEEDED`/`PARTIAL`/`FAILED`/`CANCELLED`）锁定后绝不被迟到的 `RUNNING` 进度回写覆盖。

实现（OB-053）：新增 `services/feishu_gateway/src/openbot_feishu/cardkit.py`（`FeishuCardChannelSelector`、`CardChannelPolicy`、`ChannelSelection`）与 `tests/unit/test_feishu_cardkit.py`：
1. 回调 token 寿命从生成时刻（`token_minted_ms`）起算：任务创建 45 分钟后用户点击生成回调 token 时，不会因以任务创建时刻起算而误判 token 过期；当无 CardKit 权限、token 过期、使用次数耗尽或原消息不可更新时，平滑降级至 `MESSAGE_PATCH_API` 或 `PLAIN_RESEND`。

实现（OB-054）：新增 `services/feishu_gateway/src/openbot_feishu/health.py`（`ExternalGatewaySupervisor`、`GatewayStageDeadlines`、`compute_jittered_backoff_ms`）与 `tests/unit/test_feishu_health.py`：
1. 外部进程级监督与空闲不误判：独立于 SDK 事件循环监督初始化/发现/握手与传输心跳（`in_loop_wait_for_claimed_as_hard_kill=False`），无业务消息但心跳正常时判定为 `IDLE_BUT_HEARTBEAT_FRESH`。
2. 单消费者硬门禁与带 jitter 有界退避：在旧消费者进程未确认退出前拒绝启动第二消费者（`OLD_CONSUMER_NOT_CONFIRMED_EXITED`），且重连退避绝不占用 daemon writer（`blocks_daemon_writer=False`）。

实现（OB-055）：新增 `services/feishu_gateway/src/openbot_feishu/dead_letter.py`（`DeadLetterInspectorService`、`DeadLetterRecord`）与 `tests/integration/feishu/test_dead_letter.py`：
1. 死信检视、丢弃与安全重投分离：仅允许已授权 owner 查看 `DEAD`/`EXPIRED` 通知记录并重置通知为 `PENDING`（`business_operation_reexecuted=False`）；对 `UNKNOWN` 状态或 `APPEND_MESSAGE` 非幂等副作用记录直接拒绝并要求先执行 reconcile（`UNKNOWN_REQUIRES_RECONCILE`）。

实现（OB-056）：新增 `services/feishu_gateway/src/openbot_feishu/e2e_harness.py`（`FeishuM2EndToEndHarness`、`FeishuM2VerificationReport`）、`tests/integration/feishu/test_feishu_e2e_harness.py` 与中英双语 `docs/demos/m3.md`：
1. 受控飞书端到端主流程与 6 故障场景验证：闭环串联安全配对、WebSocket 入站持久化后 ACK、普通审批卡构造与真实 operator 审批 callback CAS，并验证断网重连、daemon 重启、重复 callback、已取消任务旧卡、撤销 owner 与双消费者阻断；诚实标记 `real_feishu_tenant_verified=False`。

实现（OB-057）：新增 `services/core/src/openbot/tools/executors/browser/session.py`（`BrowserProfileSessionManager`、`BrowserSessionSpec`、`BrowserIsolationAttestation`）与 `tests/unit/test_browser_session.py`：
1. OpenBot 专用 profile 目录与独占锁：拒绝使用用户日常 Chrome 目录、拒绝解密系统 cookies、拒绝连接任意 CDP 端口；同一 profile 并发申请抛出 `BROWSER_PROFILE_LOCKED`。
2. Chromium 沙箱与外层隔离双重门禁：拦截 `--no-sandbox`、`--disable-setuid-sandbox`、`--disable-web-security` 等降级参数；导出 Artifact 元数据时仅保留 cookie 名称并剥离全部 cookie 敏感值。

实现（OB-058）：新增 `services/core/src/openbot/tools/executors/browser/network_policy.py`（`BrowserNetworkPolicyEnforcer`、`BrowserNetworkBoundaryConfig`）与 `tests/unit/test_browser_network_policy.py`：
1. 导航/重定向/iframe/subrequest 与 Service Worker 防旁路：阻断 `file://`、内网/loopback 与云元数据地址（`169.254.169.254`）；明确声明 `page_route_alone_is_complete_isolation=False`，未禁用 Service Worker 且无外层网络隔离时直接拒绝启动（`SERVICE_WORKER_BYPASS_RISK`）。
2. 下载路径净化与受批上传门禁：下载文件名剥离路径穿越并限制在隔离检疫目录内，未获批准的本地文件上传直接抛出 `UNAPPROVED_UPLOAD_FILE`。

实现（OB-059）：新增 `services/core/src/openbot/tools/browser/read.py`（`BrowserReadTool`、`BrowserPageSnapshot`、`BoundElementRef`）与 `tests/unit/test_browser_read.py`：
1. 有界结构化快照与不可信标注：每次快照返回单调递增 `snapshot_revision`、`page_id`、`frame_id`、`final_origin`，并强制标记 `provenance_kind='TAINTED_EXTERNAL'` 与 `grants_policy_or_owner_authority=False`；页面发生导航或 revision 变化后旧 `BoundElementRef` 立即失效（`STALE_BROWSER_ELEMENT_REF`）。

实现（OB-060）：新增 `services/core/src/openbot/tools/browser/actions.py`（`BrowserActionCoordinator`、`BrowserActionProposal`、`BrowserActionExecutionResult`）与 `tests/unit/test_browser_actions.py`：
1. 派发前复验与超时转 `UNKNOWN`：绑定 `element_ref`、`expected_label` 与 `expected_amount`，若执行前页面发生跨站跳转、按钮文本变化或金额篡改，立即拒绝旧批准（`BROWSER_PRECONDITION_DRIFT`）；点击后超时统一转入 `UNKNOWN`/`RECONCILING`，严禁盲目二次点击或仅凭页面内“已成功”文字自动解除隔离（`second_click_permitted=False`，`page_text_can_clear_unknown=False`）。

实现（OB-061）：新增 `services/core/src/openbot/tools/browser/verifier.py`（`BrowserOutcomeRegressionHarness`、`BrowserRegressionReport`）与 `tests/integration/browser/test_browser_outcome_regression.py`：
1. 浏览器结果验证回归：覆盖结账金额篡改拦截、表单提交回执丢失转 `UNKNOWN`、下载路径检疫净化、重定向至云元数据拦截、以及登录会话过期跳转拒绝 5 类夹具场景，绝不凭模型自称完成或驱动无异常代替业务效果验证。

实现（OB-062）：新增 `services/core/src/openbot/tools/mcp/client.py`（`McpStdioLifecycleClient`、`McpCompatibilityManifest`）与 `tests/unit/test_mcp_client.py`：
1. 固定版本 stdio MCP 协商与禁止动态拉包：强制要求 `sha256:` 包摘要，拦截 `npx`/`uvx`/`pipx` 与 `@latest` 动态启动（`DYNAMIC_MCP_PACKAGE_RUNNER_FORBIDDEN`）；协议版本不匹配时立即拒绝（`MCP_PROTOCOL_VERSION_MISMATCH`），不静默降级 transport 且对响应字节实施有界截断。

实现（OB-063）：新增 `services/core/src/openbot/tools/mcp/registry.py`（`McpToolPinRegistry`、`McpToolSnapshot`、`PinnedMcpToolRecord`）与 `tests/unit/test_mcp_registry.py`：
1. 全量元数据 JCS 锁定与漂移隔离：对 `server_id`、`package_digest`、`command_argv`、`env_keys`、`transport`、`tool_name`、`description`、`input_schema`、`output_schema`、`annotations` 计算完整 JCS SHA-256（同时声明 `jcs_hash_proves_server_code_safe=False`）；禁止覆盖内建工具名称（`BUILTIN_TOOL_SHADOWING_FORBIDDEN`），阻断远程 `$ref`（`REMOTE_SCHEMA_REF_FORBIDDEN`），且任何描述/Schema/注释变化立即将工具转入 `QUARANTINED_ON_DRIFT` 并使旧批准失效。

实现（OB-064）：新增 `services/core/src/openbot/tools/mcp/executor.py`（`McpIsolatedExecutor`、`ReviewedLocalMcpManifest`、`McpDispatchPlan`）与 `tests/unit/test_mcp_executor.py`：
1. 隔离后端强制、环境剥离与忽略第三方注释：stdio MCP server 必须运行于已验证隔离后端（未验证直接返回 `CAPABILITY_UNAVAILABLE`），子进程仅保留 `allowed_env_keys`（剥离 `HOME` 与父进程密钥）；完全忽略第三方 `readOnlyHint`/`idempotentHint` 注释，仅由本地已审查 manifest 决定 `effective_retry_class` 与审批要求，并硬拒绝 MCP sampling（`MCP_SAMPLING_FORBIDDEN_IN_MVP`）。

实际命令：
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_policy_evaluator.py -q --tb=short`（20 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_filesystem_guard.py -q --tb=short`（22 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_workspace_read_tools.py -q --tb=short`（2 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_egress_policy.py -q --tb=short`（3 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_secrets_broker.py -q --tb=short`（3 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_redaction.py -q --tb=short`（2 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/contracts/local_api tests/security/local_api -q --tb=short`（2 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/integration/cli/test_cli_workflow.py -q --tb=short`（2 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/integration/scenarios/first_vertical_slice/test_first_vertical_slice.py -q --tb=short`（6 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/security/test_m1_threat_regression.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/integration/scenarios/local_prototype/test_local_prototype.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src:services/feishu_gateway/src .venv/bin/python -m pytest tests/integration/feishu/test_pairing.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src:services/feishu_gateway/src .venv/bin/python -m pytest tests/integration/feishu/test_inbound.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src:services/feishu_gateway/src .venv/bin/python -m pytest tests/integration/feishu/test_approval_callback.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src:services/feishu_gateway/src .venv/bin/python -m pytest tests/unit/test_feishu_cards.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src:services/feishu_gateway/src .venv/bin/python -m pytest tests/unit/test_feishu_progress.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src:services/feishu_gateway/src .venv/bin/python -m pytest tests/unit/test_feishu_cardkit.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src:services/feishu_gateway/src .venv/bin/python -m pytest tests/unit/test_feishu_health.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src:services/feishu_gateway/src .venv/bin/python -m pytest tests/integration/feishu/test_dead_letter.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src:services/feishu_gateway/src .venv/bin/python -m pytest tests/integration/feishu/test_feishu_e2e_harness.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_browser_session.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_browser_network_policy.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_browser_read.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_browser_actions.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/integration/browser/test_browser_outcome_regression.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_mcp_client.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_mcp_registry.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/unit/test_mcp_executor.py -q --tb=short`（1 passed）
- `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/integration/storage -q --tb=short`（89 passed，含 `test_workspace_patch.py` 2 passed、`test_workspace_validation.py` 2 passed、`test_message_draft.py` 1 passed 与 `test_message_send.py` 1 passed，见 evidence/implementation/m1-storage-tests.log）
- 完整验证命令为 `.venv/bin/python scripts/verify.py` 与 `.venv-m1/bin/python scripts/verify.py --phase M1`，各自真实退出码/日志 hash 位于 verification.json、m1-verification.json。

当前限制：上游三平台原生隔离/Keychain 实测尚未闭合。因此 OB-017/018/019/020/022/028/029/031/032/033/034/035/037/038/039/043/044/045/046/081 均保持 IN_PROGRESS，不伪称跨平台或真实云/飞书服务已验证。

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
- **OB-034 (`IN_PROGRESS`)**: Workspace patch proposal, frozen-byte application, and per-file commit journal (`services/core/src/openbot/tools/workspace/patch.py` and `commit_journal.py`):
  1. `propose_patch`: Freezes `old_sha256`, exact new bytes in `ArtifactStore` (`new_artifact_id`, `new_sha256`), and `difflib` display diff without modifying the workspace; rejects duplicate hunk matches (`AMBIGUOUS_MULTIPLE_MATCHES`).
  2. `apply_patch` & `PatchCommitJournal`: Re-verifies `old_sha256`, parent directory inode, and approved artifact digest before writing exact frozen bytes via `WorkspaceFileGuard.write_atomic` (zero post-approval fuzz or CRLF normalization); uses `PatchCommitJournal` (`claims_cross_file_atomicity=False`) to roll back already-written files if a subsequent file fails, without `git reset --hard` or auto-commit/push.
- **OB-035 (`IN_PROGRESS`)**: Explicit syntax/static validation and operation-scoped revert (`services/core/src/openbot/tools/workspace/validation.py` and `tests/integration/storage/test_workspace_validation.py`, 2 passed):
  1. `PinnedGrammarRegistry` & `IsolatedParserWorker`: Verifies pinned offline grammar SHA-256 without runtime downloads, rejects grammar binaries located inside the workspace, and executes syntax parsing in a bounded out-of-process worker (`max_input_bytes`, `max_nesting_depth`, `timeout_ms`) so parser crashes never affect the daemon.
  2. `WorkspaceValidationCoordinator`: Reverts only the files modified by the current operation via `PatchCommitJournal` when validation fails on a multi-file edit, preserving unrelated user changes and always reporting `functional_correctness_proven=False`.
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
- **OB-043 (`IN_PROGRESS`)**: Local immutable message draft service (`services/core/src/openbot/tools/messages/draft.py` and `tests/integration/storage/test_message_draft.py`, 1 passed):
  1. `create_or_revise_draft`: Transitions the task to `WAITING_INPUT` (`sendable=False`) when recipient candidates are missing or ambiguous; stores canonical JSON drafts with stable `recipient_id`, `channel`, `account_id`, `revision`, and attachment SHA-256 digests in `ArtifactStore` with zero network calls (`network_calls_made=0`).
  2. `verify_latest_draft_binding`: Ensures edits create a new `revision` and `draft_sha256`, invalidating stale draft hashes so old approvals cannot authorize modified message content.
- **OB-044 (`IN_PROGRESS`)**: Controlled `message.send` use case and transport port (`services/core/src/openbot/tools/messages/send.py` and `tests/integration/storage/test_message_send.py`, 1 passed):
  1. `propose_send` & `execute_approved_send`: Binds `draft_artifact_id`, `draft_sha256`, `account_id`, and stable `recipient_id` (`RECONCILE_ONLY`); rejects reusing ordinary `owner_progress` notification grants for third-party sends, rejects recipient or draft-hash drift, and fails closed with `CAPABILITY_UNAVAILABLE` when the real channel adapter is not yet qualified (`transport.qualified=False`).
  2. Disconnect handling: Runs two-phase `claim -> begin_dispatch` before calling `transport.send_message` outside the transaction; connection drops after send transition the Operation to `UNKNOWN` and Task to `RECONCILING` while retaining resource quarantine and refusing automatic re-send.
- **OB-081 (`IN_PROGRESS`)**: Authenticated loopback HTTP and SSE control API (`services/core/src/openbot/adapters/local_api/server.py`, `tests/contracts/local_api/`, and `tests/security/local_api/`, 2 passed):
  1. Loopback, Host/Origin, proxy header, profile, and scoped token enforcement: Rejects non-loopback IPs, `X-Forwarded-For` proxy headers, external `Origin`/`Host` headers, wrong `X-OpenBot-Profile`, `feishu_gateway` access to `/challenge`, and `webview_readonly` mutations.
  2. Control endpoints & SSE cursors: Implements `/v1/health`, `/v1/tasks`, `/v1/tasks/{id}/cancel`, `/v1/tasks/{id}/resume`, `/v1/approvals/{id}/preview` (never exposing `SECRET` or `nonce`), `/v1/approvals/{id}/challenge`, `/v1/approvals/{id}/decide`, `/v1/operations/{id}` (with `version`), `/v1/operations/{id}/evidence` (inline content only, rejecting `host_path`), `/v1/operations/{id}/reconcile` (rejecting client-supplied `target_state` or `revive_consumed_grant`), and `/v1/tasks/{id}/events` (`400` on `after_seq`/`Last-Event-ID` conflict, `410` on expired cursor).
- **OB-028 (`IN_PROGRESS`)**: Authenticated CLI task, approval, and reconciliation commands (`services/core/src/openbot/cli.py` and `tests/integration/cli/test_cli_workflow.py`, 2 passed):
  1. Loopback API session without SQLite bypass: Supports `task create|show|cancel|resume`, `approval preview|decide` (requesting owner-scoped challenge nonce before `APPROVE`), and `operation reconcile` (uploading inline evidence before reconciliation).
  2. Anti-bypass, ANSI stripping, and timeout honesty: Rejects `--ignore-and-rerun`, `--force-success`, and `--revive-consumed` (exit code `6`); strips ANSI CSI/OSC and rich-text tags via `sanitize_terminal_text`; returns exit code `2` when daemon is down and exit code `5` on wait timeout with `action_guaranteed_not_executed=false` and `requery_required=true`.
- **OB-029 (`IN_PROGRESS`)**: First persistent vertical slice (`services/core/src/openbot/application/vertical_slice.py`, `tests/integration/scenarios/first_vertical_slice/test_first_vertical_slice.py`, and `docs/demos/m1.md`, 6 passed):
  1. Real local restricted workspace patch, Artifact SHA-256 verification, supervised worker reclaim, and durable Outbox delivery closed loop in `OFFLINE` mode via CLI and authenticated Local Control API.
  2. Five crash injection points (`before_claim`, `after_claim_before_dispatch`, `after_dispatch_before_effect`, `after_effect_before_receipt`, `after_complete_before_outbox_ack`) and duplicate CLI idempotency verification with zero blind replay.
- **OB-045 (`IN_PROGRESS`)**: M1 security tool threat regression corpus (`services/core/src/openbot/policy/threat_regression.py`, `tests/security/test_m1_threat_regression.py`, and `docs/demos/m2.md`, 1 passed):
  1. Verifies 7 threat families (JCS deep mutation/duplicate keys, path traversal/symlink escape, ripgrep/Git config injection, parser workspace binary/runtime download rejection, secret compartment/argv leak blocking and offline redaction, shell wrapper rejection and output flood truncation, and residual worker PID quarantine) with `total_unauthorized_side_effects == 0`.
- **OB-046 (`IN_PROGRESS`)**: Minimal local Alpha prototype runner and capability boundary report (`services/core/src/openbot/application/local_prototype.py`, `tests/integration/scenarios/local_prototype/test_local_prototype.py`, and `docs/releases/local-prototype-acceptance.md`, 1 passed):
  1. Runs the M1 local Alpha workflow from an empty directory (`workspace.read`, `workspace.propose_patch`, CLI approval, `workspace.apply_patch`, supervised worker reclaim, and crash recovery) and emits an honest capability report (`pilot_os='Darwin-arm64'`, `claims_full_mvp_complete=False`).
- **OB-048 (`IN_PROGRESS`)**: Control-owned pairing and owner revocation (`services/core/src/openbot/policy/pairing.py`, `services/feishu_gateway/src/openbot_feishu/pairing.py`, and `tests/integration/feishu/test_pairing.py`, 1 passed):
  1. Local short-TTL limited-attempt challenge bound to `profile_id`/`tenant_key`/`app_id`; remote claim only produces `PENDING_LOCAL_CONFIRMATION`; first sender never auto-pairs; `revoke_owner` increments `profile_config.identity_epoch` to invalidate stale contexts.
- **OB-049 (`IN_PROGRESS`)**: Feishu WebSocket inbound adapter (`services/feishu_gateway/src/openbot_feishu/inbound.py` and `tests/integration/feishu/test_inbound.py`, 1 passed):
  1. Enforces persist-before-ACK via the daemon's `/v1/tasks` endpoint (`ws_ack=False` on persistence failure), rejects group chats (`GROUP_CHAT_DISABLED`), unpaired senders (`UNPAIRED_SENDER`), cross-tenant events, and oversized attachments (`ATTACHMENT_TOO_LARGE`), and never waits on LLMs inside callbacks.
- **OB-050 (`IN_PROGRESS`)**: Feishu approval callback handler and daemon use case (`services/feishu_gateway/src/openbot_feishu/approval_callback.py`, `services/core/src/openbot/application/approval_use_case.py`, and `tests/integration/feishu/test_approval_callback.py`, 1 passed):
  1. Extracts the real `event.operator.open_id` and verifies active owner pairing while ignoring forged `action.value.is_owner` fields; rejects stale cards on cancelled tasks (`APPROVAL_REJECTED_OR_STALE`) and never claims approval on unconfirmed database commits (`COMMIT_UNCONFIRMED`).
- **OB-051 (`IN_PROGRESS`)**: Pure Feishu plain card builders (`services/feishu_gateway/src/openbot_feishu/cards.py` and `tests/unit/test_feishu_cards.py`, 1 passed):
  1. Builds plain approval and result cards without CardKit; enforces `REQUIRE_LOCAL` (disabling remote approve and omitting sensitive text) when `data_class` is `SENSITIVE`/`SECRET` or `truncated=True`, and flags `UNKNOWN` outcomes with `RECONCILIATION_REQUIRED`.
- **OB-052 (`IN_PROGRESS`)**: Feishu progress card throttling and terminal ordering (`services/feishu_gateway/src/openbot_feishu/progress.py` and `tests/unit/test_feishu_progress.py`, 1 passed):
  1. Coalesces rapid intermediate progress updates (100 updates merged into 1 emission), respects `retry_after` rate-limit backoff, and prevents late `RUNNING` updates from overwriting terminal states (`SUCCEEDED`/`PARTIAL`/`FAILED`/`CANCELLED`).
- **OB-053 (`IN_PROGRESS`)**: CardKit capability selector and channel fallback (`services/feishu_gateway/src/openbot_feishu/cardkit.py` and `tests/unit/test_feishu_cardkit.py`, 1 passed):
  1. Tracks callback token TTL strictly from `token_minted_ms` (so clicking 45 minutes after task creation does not falsely expire the newly minted token) and degrades to `MESSAGE_PATCH_API` or `PLAIN_RESEND` when permissions, TTL, use count, or message updatability are unavailable.
- **OB-054 (`IN_PROGRESS`)**: External gateway health watchdog and jittered reconnect (`services/feishu_gateway/src/openbot_feishu/health.py` and `tests/unit/test_feishu_health.py`, 1 passed):
  1. Evaluates transport heartbeat outside the SDK event loop (`in_loop_wait_for_claimed_as_hard_kill=False`), treats idle business traffic with fresh heartbeat as healthy (`IDLE_BUT_HEARTBEAT_FRESH`), forbids spawning a second consumer before confirming old exit (`OLD_CONSUMER_NOT_CONFIRMED_EXITED`), and computes bounded jittered backoff without blocking the daemon writer.
- **OB-055 (`IN_PROGRESS`)**: Dead-letter inspection and safe notification redelivery (`services/feishu_gateway/src/openbot_feishu/dead_letter.py` and `tests/integration/feishu/test_dead_letter.py`, 1 passed):
  1. Restricts dead-letter listing to the active owner, redelivers `DEAD`/`EXPIRED` notifications without re-running business operations (`business_operation_reexecuted=False`), and refuses to discard or blindly retry `UNKNOWN` side effects (`UNKNOWN_REQUIRES_RECONCILE`).
- **OB-056 (`IN_PROGRESS`)**: Controlled M2 Feishu end-to-end harness (`services/feishu_gateway/src/openbot_feishu/e2e_harness.py`, `tests/integration/feishu/test_feishu_e2e_harness.py`, and `docs/demos/m3.md`, 1 passed):
  1. Verifies the M2 Feishu main flow and 6 failure scenarios (`disconnect_and_jittered_reconnect`, `daemon_restart_recovery`, `duplicate_approval_callback`, `stale_card_on_cancelled_task`, `revoked_owner_rejected`, `dual_consumer_spawn_blocked`) while honestly reporting `real_feishu_tenant_verified=False` pending a live test tenant.
- **OB-057 (`IN_PROGRESS`)**: Dedicated browser profile and session lock manager (`services/core/src/openbot/tools/executors/browser/session.py` and `tests/unit/test_browser_session.py`, 1 passed):
  1. Enforces OpenBot-dedicated `user_data_dir`, profile mutex locks (`BROWSER_PROFILE_LOCKED`), and both Chromium sandbox and outer isolation (`--no-sandbox`, CDP attach, and system cookie decryption forbidden); strips cookie values from Artifact exports.
- **OB-058 (`IN_PROGRESS`)**: Browser network, Service Worker, download, and upload policy (`services/core/src/openbot/tools/executors/browser/network_policy.py` and `tests/unit/test_browser_network_policy.py`, 1 passed):
  1. Blocks `file://`, loopback, private-IP, and cloud metadata (`169.254.169.254`) navigation/redirects/subrequests, requires Service Worker blocking or verified outer network isolation (`page_route_alone_is_complete_isolation=False`), sanitizes download paths into quarantine, and blocks unapproved file uploads.
- **OB-059 (`IN_PROGRESS`)**: Structured browser read tool (`services/core/src/openbot/tools/browser/read.py` and `tests/unit/test_browser_read.py`, 1 passed):
  1. Extracts bounded snapshots tagged `TAINTED_EXTERNAL` (`grants_policy_or_owner_authority=False`) bound to `(page_id, frame_id, snapshot_revision, final_origin)`, invalidating stale element references across navigations (`STALE_BROWSER_ELEMENT_REF`).
- **OB-060 (`IN_PROGRESS`)**: Browser write action proposal and re-verification (`services/core/src/openbot/tools/browser/actions.py` and `tests/unit/test_browser_actions.py`, 1 passed):
  1. Re-verifies `BoundElementRef`, button label, and amount before execution (`BROWSER_PRECONDITION_DRIFT`), transitions post-click timeouts to `UNKNOWN`/`RECONCILING`, and forbids automatic second clicks or trusting in-page text to clear `UNKNOWN`.
- **OB-061 (`IN_PROGRESS`)**: Browser outcome verification regression (`services/core/src/openbot/tools/browser/verifier.py` and `tests/integration/browser/test_browser_outcome_regression.py`, 1 passed):
  1. Verifies 5 fixture scenarios (checkout amount drift, form submit lost receipt -> `UNKNOWN`, download quarantine, metadata redirect blocking, and expired login session rejection) without accepting model self-claims or driver no-error returns as proof.
- **OB-062 (`IN_PROGRESS`)**: MCP version negotiation and lifecycle client (`services/core/src/openbot/tools/mcp/client.py` and `tests/unit/test_mcp_client.py`, 1 passed):
  1. Enforces pinned `sha256` package digests and explicit stdio protocol versions, blocks `npx`/`uvx`/`@latest` dynamic package runners (`DYNAMIC_MCP_PACKAGE_RUNNER_FORBIDDEN`), rejects protocol mismatches without silent transport downgrade, and bounds output bytes.
- **OB-063 (`IN_PROGRESS`)**: MCP tool registration and JCS metadata pinning (`services/core/src/openbot/tools/mcp/registry.py` and `tests/unit/test_mcp_registry.py`, 1 passed):
  1. Pins full MCP tool metadata via JCS SHA-256 (`jcs_hash_proves_server_code_safe=False`), blocks builtin tool name shadowing and remote `$ref` URIs, and quarantines tools (`MCP_METADATA_DRIFT_QUARANTINED`) if description, schema, or annotations change.
- **OB-064 (`IN_PROGRESS`)**: MCP process and network isolation executor (`services/core/src/openbot/tools/mcp/executor.py` and `tests/unit/test_mcp_executor.py`, 1 passed):
  1. Requires a qualified isolation backend (`CAPABILITY_UNAVAILABLE` otherwise), strips parent environment variables outside `allowed_env_keys`, ignores third-party `readOnlyHint`/`idempotentHint` annotations in favor of `ReviewedLocalMcpManifest`, and forbids MCP sampling (`MCP_SAMPLING_FORBIDDEN_IN_MVP`).
