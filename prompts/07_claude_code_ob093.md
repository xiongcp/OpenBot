# Claude Code：OB-093 macOS Supervisor 资格子任务

下面中文与英文等价，任选一版执行，不要当作两份任务重复运行。

The Chinese and English versions below are equivalent. Execute one version, not both.

## 中文提示词（可直接复制）

你负责 OpenBot v1.2 的 **OB-093 / Darwin arm64 Supervisor 资格子任务**。目标是补实际原生进程/锁/接管证据，不接入正式 Broker、数据库或调度器，不实施整个 M3。

先读 README.md、AGENTS.md、CLAUDE.md、docs/handoff/2026-11-04-checkpoint.md、docs/02_architecture.md、docs/03_runtime_recovery.md、docs/12_component_reuse.md、docs/13_component_qualification.md、docs/adr/0003-daemon-lifecycle.md、docs/adr/0005-sdk-and-isolation-gates.md、docs/adr/0007-native-container-poc.md、docs/evidence/backend-capabilities.md，以及 backlog 中 OB-093 的完整任务卡。逐项读 component_refs/reuse_type/reuse_notes，并核对 catalog。检查实际代码和当前 Git 状态，历史测试数字不是当前通过证据。

当前 OB-093 只包含 flock 与 Docker 合成原语，正式 Supervisor 尚未实现。多项上游仍 VERIFIED，OB-005 缺三 OS 实跑；ADR-0005 允许继续独立本机资格子任务，不允许跳过正式门禁或将整个 OB-093/015/042/029 标 DONE。

从本轮已提交检查点创建独立分支 `codex/ob093-macos-supervisor-qualification` 与独立 worktree。保留原工作树；按 AGENTS 准备工作树并防止 hooks/filter 隐式执行，不清理他人 worktree。普通本地可逆实现与测试可持续推进，无须逐小步请求确认。

你的写入范围仅为：

- `tests/components/native_poc/supervisor/**`：真实受控进程 harness 与失败反例。
- `native/supervisor/**`：仅在有真实可运行行为时创建，禁止空壳；不得提前接入生产派发。
- `docs/adr/ob093-supervisor-qualification.md`：在新增原生内部协议或依赖前记录选择、权衡与失败语义。
- `docs/evidence/ob093-supervisor.md` 与 `evidence/implementation/ob093-supervisor/**`：中英双语结论、合成轨迹与可重放证据。

不要修改根 pyproject/uv.lock、公共 contracts、DB/migrations、现有 state/operations/approvals、tasks/backlog.json、TASKS.md、catalog/admissions、总 backend-capabilities 或 CI。需要跨越这些边界时，在专属证据文档写出具体变更提案，交 Integrator 处理；继续不受影响的工作。若选择新依赖，先完成组件来源/精确版本/许可/资格选择；根共享锁由 Integrator 修改。默认可以从已有 stdlib fcntl/POSIX harness 开始，不必为用 Rust 而安装整套候选。

库、SDK、CLI 或平台 API 用法先通过 Context7 resolve-library-id/query-docs 核对；工具不可用时明确记录，使用官方原始资料补充，不伪称已查询。未经授权不读取真实秘密、不装系统服务、不发第三方消息、不部署/推送。

先补有意义的失败反例，再实现最小行为，实际验证：

1. 唯一 supervisor 持 profile 排他锁；daemon 不再争同一把锁。第二实例拒绝；父子交接失败有界退出，无互锁。
2. 通过受保护父子启动通道确认 runtime 身份；独立 daemon 启动不能绕过 owner。关闭测试客户端不结束 daemon。
3. 对 supervisor、daemon、worker 强杀分别留证；覆盖多代子孙和 setsid 逃逸。不要把进程组、Drop、EOF 或父死当作 100% 回收证明。
4. 仅按登记身份清理本轮合成进程，不碰旁观进程；记录 PID/PPID/PGID/SID、归属、前后清单和真实退出码，处理 PID 复用风险。
5. 旧执行域无法证实失效时，PoC 内模拟 dispatch 计数必须为 0，返回明确不可用/隔离状态；这不等于正式 Broker 已实现该守卫。
6. 若重跑容器，只用已准备的 digest、--pull=never 和专属合成资源；kill CLI 不等于容器停止，按登记 ID stop/wait→校验受限导出→remove。

Windows/Linux、logout/sleep、用户服务安装、生产回收、完整容器供应链均保持未验证。记录可以证明什么、不能证明什么；不扩大能力、不放宽守卫、不伪造日志。

按实际环境补充专属测试命令，并运行根 `scripts/verify.py` 对应组检查（依赖缺失先按锁在 worktree 安装当前必要组；不要复制其他工作树 venv）。脚本或日志名不能冒充执行结果。证据目录中的文本轨迹优先用可提交的 `.txt`/`.json`，普通日志遵循仓库忽略规则。

完成后检查 diff 与秘密，在你的分支做本地提交，使用中英双语提交说明，不推送、不合并。只提交你的独占文件；将新增 ADR、任务建议状态、真实命令与退出码、未验证范围、残余风险、commit hash 用中英双语交给 Integrator。由 Integrator 更新共享任务状态并在实际集成树重验。

## English prompt (ready to copy)

Own the **OB-093 / Darwin arm64 Supervisor qualification subtask** for OpenBot v1.2. Produce real native process/lock/takeover evidence. Do not integrate the production Broker, database or scheduler, and do not attempt all of M3.

First read README.md, AGENTS.md, CLAUDE.md, docs/handoff/2026-11-04-checkpoint.md, docs/02_architecture.md, docs/03_runtime_recovery.md, docs/12_component_reuse.md, docs/13_component_qualification.md, ADRs 0003/0005/0007, docs/evidence/backend-capabilities.md, and the complete OB-093 backlog card. Read its component_refs/reuse_type/reuse_notes and check the catalog. Inspect real code and Git state; historical test counts are not current verification.

OB-093 currently has flock and synthetic Docker primitives, not a production Supervisor. Several upstream tasks remain VERIFIED; OB-005 lacks actual three-OS runs. ADR-0005 permits an independent native qualification subtask, not bypassing gates or marking all of OB-093/015/042/029 DONE.

Create branch `codex/ob093-macos-supervisor-qualification` and a separate worktree from the committed checkpoint. Preserve the original worktree. Follow AGENTS when preparing Git worktrees and prevent implicit hooks/filters; do not clean other people's worktrees. Continue routine reversible local implementation/tests without repeated confirmation.

Your exclusive write scope is:

- `tests/components/native_poc/supervisor/**`: controlled real-process harness and negative cases.
- `native/supervisor/**`: create only runnable behavior, never empty scaffolding; no production dispatch integration.
- `docs/adr/ob093-supervisor-qualification.md`: record choices, tradeoffs and failure semantics before adding native internal protocols or dependencies.
- `docs/evidence/ob093-supervisor.md` and `evidence/implementation/ob093-supervisor/**`: bilingual conclusions, synthetic traces and reproducible evidence.

Do not change root pyproject/uv.lock, public contracts, DB/migrations, existing state/operations/approvals, backlog/TASKS, catalog/admissions, the shared backend-capability matrix or CI. Propose necessary shared changes in your exclusive evidence document for the Integrator, and continue unaffected work. Qualify source, exact version, license and necessary dependency scope first; the Integrator owns shared root lock changes. You can start from the existing stdlib fcntl/POSIX harness instead of installing every Rust/native candidate.

Check library, SDK, CLI and platform API usage with Context7 resolve-library-id/query-docs first. If unavailable, record that limitation and supplement with official primary documentation; do not pretend a tool was used. Do not read real secrets, install system services, message third parties, deploy or push.

Write meaningful failing cases before minimal implementation. Verify:

1. Only the supervisor owns the profile lock; the daemon does not reacquire it. Reject a second instance; bound handoff failures without deadlock.
2. Authenticate runtime identity through a protected parent/child startup channel. Independent daemon startup cannot bypass the owner. Disconnecting a test client leaves the daemon running.
3. Record supervisor/daemon/worker kills separately, including multigeneration descendants and setsid escape. Process groups, Drop, EOF or parent death are not universal cleanup guarantees.
4. Clean only registered identities belonging to this synthetic run; leave bystanders untouched. Record PID/PPID/PGID/SID, ownership, before/after inventories and actual exit codes; address PID reuse.
5. If the old execution domain cannot be proven inactive, the PoC simulated dispatch counter stays zero and returns explicit unavailability/quarantine. This does not prove a production Broker guard exists.
6. If rerunning containers, use the prepared digest, --pull=never and owned synthetic resources. Killing a client is not container cleanup: stop/wait, validate bounded exports, then remove registered IDs.

Native Windows/Linux, logout/sleep, user-service installation, production cleanup and full image supply-chain qualification remain unverified. State precisely what is and is not proven. Do not expand capabilities, relax guards or fabricate evidence.

Provide actual dedicated test commands and run the applicable root scripts/verify.py group. Install only necessary locked groups in your worktree if absent; never copy another worktree's venv. A script or log name is not proof it ran. Prefer committable .txt/.json traces under your evidence directory; ordinary logs must follow repository ignore rules.

Review your diff and secrets, then make a local commit on your branch with a bilingual message. Do not push or merge. Commit only exclusive files. Return the ADR, proposed task status, actual commands/exit codes, unverified scope, residual risks and commit hash in Chinese and English. The Integrator updates shared task state and revalidates the integrated tree.
