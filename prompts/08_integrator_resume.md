# Integrator：整合 Claude 工作并继续 M1 → M3

中文与英文任选一版。Choose one equivalent language version.

## 中文提示词（可直接复制）

继续 OpenBot v1.2，实现目标仍为 M3；先完成当前 M1 门禁，不把已提交代码当作任务 DONE。读取 README、AGENTS、CLAUDE、docs/handoff/2026-11-04-checkpoint.md、prompts/05_autonomous_project.md、当前代码、backlog 和组件目录；当前机器结果以重新执行为准。

如果 Claude 已交付 OB-093 工作分支/commit，先获取其确切本地分支和 hash，核对文件归属、ADR、真实轨迹与限制；未知 hash 不要猜。审查共享边界后整合本地提交，解决冲突并在实际合并树复验，不把分支各自测试通过当作集成通过。没有 Claude 结果时继续不重叠的核心工作，不在其独占目录并行改动。

工作顺序：

1. 保持 OB-001—096；逐卡检查 depends_on、component_refs、reuse_type、reuse_notes 与正负验收。已有 M0 合同/PoC 和 OB-011—013 本机证据应复用，不从头重生成设计包。
2. 完成 OB-014 的终态/OutcomeVerifier 边界，审查 OB-093 真正可证明的 Supervisor 与旧域隔离范围，之后推进 OB-015/016。依赖未闭合时只做明确可独立验收的子任务，不假称整项 READY/DONE。
3. 补 OB-017/018/031 的正式权限/生命周期，再实现 OB-019 两次短事务 claim→DISPATCHING、OB-020 恢复、OB-021 outbox、OB-022 取消、OB-023 持久预算。当前 proposal/approval 只有内部 local 子集，nonce store/安全预览/认证 API 并未实现。
4. 按 DAG 补文件/Artifact、外发/密钥/过滤、受控执行、认证 API/CLI，使用实际隔离执行与可控 FakeProvider 通过 OB-029；不能用 M0 MockWorker 代替隔离。
5. 再进入 M2/M3；真实飞书租户、模型资产/凭据、Windows/Linux 环境缺失只阻塞对应实际验收，工程待办与环境阻塞分别报告。不得宣称现有 150/169 测试或 Docker PoC 证明 M3 已完成。

共享 schema、migration 编号、Python 锁、policy/状态机、backlog/TASKS 与组件准入由你作为唯一 Integrator 更新。跨公共合同/锁/安全策略先写 ADR/合同，再做最小实现。库/SDK/CLI/平台用法先查 Context7，证据注明来源与限制。常规可逆本地实现/修复/测试连续执行，无须逐步确认。

所有副作用经 Broker；身份与权限由服务器可信上下文派生；短事务内不等待网络/工具/人工；批准只 READY；CONSUMED 不复活；dispatch 属 Attempt、provider key 属 Operation；未知结果进入 UNKNOWN/RECONCILING 并持资源 quarantine；取消阻止后续派发但不谎称回滚外部效果；无隔离拒绝执行；不自动云回退或下载资产；秘密不进源码、模型、普通日志或产物。

先失败反例，再最小实现，再验收、diff/秘密检查、证据与状态同步，再选择下一就绪项。运行 `.venv/bin/python scripts/verify.py` 与适用的 `.venv-m1/bin/python scripts/verify.py --phase M1`；增加原生/真实服务门禁时单独记录实际命令、版本、退出码与局限。所有提交使用中英双语标题/说明；本地提交可在验证后执行，不推送/部署/发布/发信/安装系统服务。最终输出任务 ID、变更理由、实际验证、未验证内容、风险、下一依赖与 commit hash，中英双语报告。

## English prompt (ready to copy)

Continue OpenBot v1.2 toward M3, completing current M1 gates first. A commit does not make a task DONE. Read README, AGENTS, CLAUDE, docs/handoff/2026-11-04-checkpoint.md, prompts/05_autonomous_project.md, current code, backlog and component catalog. Rerun checks for current-machine claims.

If Claude has delivered an OB-093 branch/commit, obtain its exact local branch and hash; do not guess. Review exclusive-file ownership, ADRs, real traces and limitations before integrating locally. Resolve conflicts and rerun gates on the actual merged tree; separate branch successes are not integration evidence. If no Claude result exists, continue nonoverlapping core work and do not concurrently edit its exclusive directories.

Work in this order:

1. Preserve OB-001–096. Read dependencies, component_refs/reuse_type/reuse_notes and positive/negative acceptance for every card. Reuse current M0 contracts/PoC and OB-011–013 local evidence; do not regenerate the project from scratch.
2. Complete OB-014 terminal/OutcomeVerifier boundaries, review exactly what OB-093 proves about Supervisor and old-domain isolation, then advance OB-015/016. With incomplete dependencies, work only on explicitly independent subtasks; do not claim full READY/DONE.
3. Complete OB-017/018/031 permissions/lifecycle, then OB-019 two-transaction claim→DISPATCHING, OB-020 recovery, OB-021 outbox, OB-022 cancellation and OB-023 durable budgets. Current proposal/approval services are internal-local subsets; the protected nonce store, safe preview and authenticated API are not implemented.
4. Follow the DAG through file/artifact, egress/secrets/filtering, controlled execution and authenticated API/CLI gates. Pass OB-029 using actual qualified isolation and a controlled FakeProvider where appropriate. An M0 MockWorker cannot substitute for isolation.
5. Advance to M2/M3 only afterward. Missing Feishu tenants, model assets/credentials or native Windows/Linux environments block their specific real acceptance. Report engineering TODOs separately from environment blockers. Existing 150/169 test counts or Docker primitives do not establish M3 completion.

As the sole Integrator, own shared schemas, migration numbering, Python locks, policies/state machines, backlog/TASKS and component admissions. Update ADR/contracts before changing shared contracts, locks or security policy, then implement minimally. Use Context7 for library/SDK/CLI/platform usage and record sources/limitations. Continue routine reversible local implementation, fixes and tests without repeated confirmation.

All effects go through the Broker. Identity/permissions come from trusted server context. Short transactions do not wait on networks/tools/humans. Approval only yields READY; CONSUMED never revives. Dispatch IDs belong to Attempts; provider keys to Operations. Unknown effects retain UNKNOWN/RECONCILING and resource quarantine. Cancellation stops new dispatch without pretending to undo past effects. Fail closed without isolation, never auto-fallback to cloud or download assets at runtime, and keep secrets out of source/model context/ordinary logs/artifacts.

Write failing cases, implement minimally, verify, review diff/secrets, update evidence/status, then select the next ready item. Run `.venv/bin/python scripts/verify.py` and the applicable `.venv-m1/bin/python scripts/verify.py --phase M1`. Record native/real-service commands, versions, actual exit codes and limits separately. Use bilingual commit titles/descriptions. Make validated local commits, but do not push, deploy, publish, message third parties or install system services. Report task IDs, rationale, actual verification, unverified scope, risks, next dependencies and commit hashes in Chinese and English.
