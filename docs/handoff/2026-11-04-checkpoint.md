# 实施检查点与分工 / Implementation checkpoint and work split

日期 / Date: 2026-11-04。当前事实源为仓库代码、`tasks/backlog.json` 和实际验证记录；本文是交接导航，不是第二份任务账本。

The code, `tasks/backlog.json`, and actual verification records are authoritative. This document is handoff navigation, not a second task ledger.

## 当前状态 / Current state

- OB-001—004 DONE；OB-006—010、089—091 与 OB-011—013 为 VERIFIED，保留各自范围与上游门禁限制。
- OB-014/017/018/092/093 IN_PROGRESS。已有内部状态/提案/审批和资格子集，未实现正式执行闭环。
- OB-005/047/070/071 BLOCKED：三 OS bootstrap、真实飞书测试租户与原生 Windows/Linux 环境缺口分别见 `docs/evidence/external-environments.md`。
- OB-029 尚未通过；M2/M3 尚未验收。现有 Docker 证据不能替代 Supervisor 或原生 Linux/Windows 资格。

OB-001–004 are DONE. OB-006–010, OB-089–091 and OB-011–013 are VERIFIED within their recorded scope and upstream gate limitations. OB-014/017/018/092/093 remain IN_PROGRESS. OB-005/047/070/071 are BLOCKED by their documented environment conditions. OB-029 has not passed; M2/M3 are not accepted. Docker primitives do not qualify the Supervisor or native Linux/Windows.

已有实现 / Implemented subsets:

1. 严格 JSON、Draft 2020-12、本地 ref、RFC 8785、可信 DTO 与时钟/错误合同。
2. 23 表显式迁移、单 writer/背压、持久 inbox、Task/event/outbox 原子提交子集。
3. canonical 提案与审批决定：批准只 READY；nonce 不进普通审计；完整 claim/dispatch/recovery 仍缺。
4. OpenAI/httpx 合成回环故障合同；macOS ARM64 flock 与固定 digest 容器原语。

Implemented subsets cover strict contracts, explicit SQLite migrations and writer/inbox semantics, partial Task/event/outbox use cases, canonical proposals and approval decisions, synthetic OpenAI/httpx fault contracts, and macOS ARM64 lock/container primitives. Approval only produces READY; it does not dispatch work.

## 验证 / Verification

在仓库根目录运行 / Run from the repository root:

```sh
.venv/bin/python scripts/verify.py
.venv-m1/bin/python scripts/verify.py --phase M1
```

本次已有基线为 M0 150 passed / 3 skipped、M1 169 passed / 1 skipped；实际本轮提交前以新生成的 verification.json / m1-verification.json 为准。容器 8 passed 是独立历史资格记录，只有显式重跑才算新鲜原生证据。

The recorded baseline is M0: 150 passed / 3 skipped; M1: 169 passed / 1 skipped. Use freshly generated verification JSON for the pre-commit result. The separate 8-pass container record is earlier native evidence; only an explicit rerun creates fresh native evidence.

SDK 测试仅使用合成 loopback 服务；容器测试只用已准备的 digest 和合成临时资源。普通 verify 不运行容器。真实模型、飞书、Windows/Linux、logout/sleep 和长时间浸泡均未通过。

SDK tests use synthetic loopback services. Native container tests require the prepared digest and owned synthetic resources; normal verification does not run them. Real models/Feishu, native Windows/Linux, logout/sleep and long soak tests are not qualified.

## 建议分工 / Recommended ownership

| 工作流 / Lane | 范围 / Scope | 文件归属 / Ownership |
|---|---|---|
| Claude Code | OB-093 的 macOS Supervisor 资格子任务 / macOS Supervisor qualification subtask | 新的 native PoC、专属测试/ADR/证据 / new exclusive PoC, tests, ADR and evidence |
| Codex / Integrator | OB-014/017/018 的核心门禁与后续依赖；整合并重验 / core gates, dependent work, integration and revalidation | 公共 schema、迁移、Python 锁、policy/状态账本、backlog/TASKS、总能力矩阵 / shared contracts, migrations, Python locks, policies/state, task ledger and capability matrix |

先将首个提交保存为共同起点。Claude 使用独立分支和 worktree；不要让两个助手在同一工作树改同一批文件。首发平台仍为本机 Darwin arm64，现有 fcntl 与 Docker 测试可以复用，不必先安装全部 Rust/原生候选。

Use the initial checkpoint commit as the common base. Claude must use a separate branch/worktree with exclusive files. Darwin arm64 is the current first platform. Existing fcntl and Docker probes can be reused; installing every native/Rust candidate is unnecessary.

复制使用 / Copy into the relevant assistant:

- [Claude Code 专项提示词 / Scoped Claude assignment](../../prompts/07_claude_code_ob093.md)
- [Integrator 续做提示词 / Integrator continuation](../../prompts/08_integrator_resume.md)

Claude 完成后交付 commit hash、实际测试命令/退出码、PID/归属轨迹、未验证条件和建议状态；Integrator 审查后更新共享任务账本与能力矩阵，并在合并后的真实树重跑门禁。代码提交不等于任务 DONE。

Claude should return its commit hash, real commands/exit codes, process ownership traces, limitations and proposed task status. The Integrator reviews the result, updates shared ledgers/capabilities, and reruns gates on the actual integrated tree. A commit does not mean the task is DONE.

## 边界 / Boundaries

原始设计与现有实现都保存到本地 Git 检查点。此次提交不授权远程推送、部署、发布、第三方发信、系统服务安装或读取真实凭据。常规可逆本地实现与合成验收可连续进行；受影响工作遇缺环境时如实留证，继续独立就绪项。

This checkpoint preserves the original design and current implementation in local Git. It does not authorize a remote push, deployment, publication, third-party messages, system-service installation or access to real credentials. Continue routine reversible local work and synthetic validation autonomously; record environment gaps and continue independent ready work.
