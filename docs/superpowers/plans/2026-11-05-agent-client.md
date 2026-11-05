# Agent Client Implementation Plan / Agent 客户端实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver the approved macOS client, configuration activation, factual execution graph and shared Feishu entry point. / 交付已确认的 macOS 客户端、配置生效流程、事实执行图与飞书统一入口。

**Architecture:** Reuse the scoped local API, Writer, events and task checkpoints. Add bounded runtime orchestration and an isolated fixture MCP; Tauri proxies allowlisted commands and owns no execution lifecycle. / 复用既有 API、writer、events 和 checkpoint；Tauri 仅代理受限命令。

**Tech Stack:** Python 3.12, SQLite, existing OpenAI adapter, stdlib JSON-RPC container transport, Tauri 2, static ES modules/CSS/SVG. / 前端用静态 ES modules 避免额外打包依赖，保留既定交互与 IPC 边界。

**Spec:** `docs/superpowers/specs/2026-11-05-agent-client-design.md` (approved by user).

## Global Constraints / 全局约束

- Keep OB-001—096 and their acceptance gates; use existing component refs; no inferred runtime admission.
- No secrets in Git, logs, UI payloads or artifacts; credentials enter through protected CLI, live in memory.
- Every tool effect passes Broker authorization, claim and dispatch rechecks; no host-shell fallback.
- No hidden reasoning collection; no effect re-execution during replay; UNKNOWN remains unresolved.
- One profile/owner/active run; all configuration and event writes use the existing bounded Writer.
- Work on the already confirmed `codex/agent-client-observability` branch, in the clean current checkout; no parallel code edits/worktrees.
- Explicit staging, atomic commit, push, remote SHA and CI verification per independent slice. No merge, publish or deployment.
- 界面与交付文档双语；真实/合成/未验证分开报告。

## Review Focus / 审查重点

- Invalid/duplicate-key config and concurrent stale previews must leave previous active config intact (Task 1).
- Revocation while a model is in flight must prevent the next tool dispatch (Task 2).
- A process restart with an unfinished run must not silently re-execute model/tool requests (Task 2).
- Untrusted event text and markup must remain inert and redacted in both UI languages (Task 4).
- UI closure and reconnect/cursor gaps must preserve daemon ownership and display incomplete evidence honestly (Tasks 3–4).

### Task 1: Durable settings and trace foundation / 持久配置与事件基础（OB-008/075）

Files: create `application/client_state.py`, `contracts/client-control.md`, `contracts/client-settings.schema.json`, `docs/adr/0009-client-control.md`, `tests/integration/test_client_state.py`.

Interfaces: `ClientState(writer, context, redactor)`, `settings()`, `preview(raw)`, `apply(raw, request_id)`, `start_run(task_id)`, `record(task_id, kind, data, parent_event_id=None)`, `trace(task_id, after_seq=0)`; JSON DTOs only. Reuse events aggregate metadata and checkpoint; no migration required.

- [ ] Write tests for atomic invalid config/CAS, revision persistence, run config pinning, parent validation, canary redaction and zero dispatch on replay.
- [ ] Run `.venv/bin/python -m pytest tests/integration/test_client_state.py -q` → missing functionality fails.
- [ ] Implement minimal service with short Writer commands; validate before writes; update privacy/policy revisions atomically when mode changes.
- [ ] Targeted tests + lint/types + full verification pass; explicit stage/commit/push and verify remote/CI.

### Task 2: Bounded real run and isolated MCP / 真实运行与隔离 MCP（OB-025/062—066/075）

Files: create `application/agent_runtime.py`, `providers/stream_transport.py`, `tools/mcp/container_read.py`, `services/mcp_fixture/read_server.py`, `tests/integration/test_agent_runtime.py`; reuse OperationService, ApprovalService, DispatchService, recovery receipts, ArtifactStore.

Consumes Task 1 state APIs. Produces `AgentRuntime.start(task_id)`, `close()`, `health()`; `ContainerReadTool.read(arguments, ownership)`; actual SDK streaming transport for existing OpenAICompatibleAdapter.

- [ ] Reproduce no task execution after submission; test model proposal → approval → actual bounded MCP read → verified artifact, plus malformed model JSON, cancellation/restriction, timeout, restart and missing isolation failures.
- [ ] RED targeted tests; implement real bounded orchestration outside writer transactions, retaining Operation/Attempt identity and runtime-owned adapter selection.
- [ ] Read-only fixture MCP must initialize/negotiate before call, be hash pinned, run in network-disabled container with read-only input, exact image digest and bounded cleanup by container ID.
- [ ] Test synthetic loopback streams and isolated fixture independently; perform one real model workflow when credentials are injected. Commit/push/remote/CI.

### Task 3: Authenticated client API and daemon composition / 客户端 API 与 daemon（OB-081）

Files: modify `adapters/local_api/server.py`, `cli.py`; create `adapters/local_api/client_routes.py`, `tests/contracts/local_api/test_client_control.py`.

Consumes ClientState + AgentRuntime. Produces fixed `/v1/client/{settings,settings/preview,settings/apply,runs,approvals,health}` and per-task trace/start paths; CLI supports actual workspace and non-echoing credential injection.

- [ ] RED: wrong scope/profile/origin, invalid size/cursor, authenticated create/start/list/trace/config and restart without credentials.
- [ ] Add fixed routes; owner only for configuration and run mutation; readonly scope can query redacted DTOs. Keep existing routes compatible.
- [ ] Persist no new secrets; daemon remains CLI-owned. Test real TCP subprocess and closing client without stopping it. Commit/push/remote/CI.

### Task 4: Native bilingual Tauri client / 双语原生客户端（OB-082/083）

Files: create `apps/desktop/{index.html,app.js,style.css,i18n.js}`, `apps/desktop/src-tauri/{Cargo.toml,Cargo.lock,tauri.conf.json,build.rs,src/lib.rs,src/main.rs,capabilities/main.json,permissions/control.toml}`, `apps/desktop/tests/*.test.mjs`, `docs/client.md`; component evidence/locks only for dependencies actually used.

Consumes Task 3 API. Produces fixed Rust commands for runs, trace, approvals, decisions and settings; token remains Rust state. Initial profile directory is supplied from trusted launch configuration, not arbitrary WebView input.

- [ ] RED tests for fixed routes/IDs/body validation and bilingual event projection, stale updates, inert text, unknown outcome and cursor recovery.
- [ ] Implement minimal local frontend with task list, execution graph/timeline, node details, settings preview/apply, approval center and independent health.
- [ ] Pin Tauri/Rust dependencies; no shell/fs plugins; restrict commands through AppManifest/capabilities and CSP. Build and launch unsigned macOS app, verify screenshot and real daemon traffic.
- [ ] Check locale switch, approval/config, reconnect and window closure behavior. Commit/push/remote/CI; record missing native platforms honestly.

### Task 5: Shared Feishu live entry / 飞书共享入口（OB-047/056）

Files: create `openbot_feishu/live_gateway.py`, tests and `docs/integrations/feishu-client.md`; exact optional SDK lock/admission evidence; use the same authenticated daemon route and task graph.

- [ ] RED: only paired allowlisted identity can submit, inbound deduplication, no secrets in events/logs, OFFLINE blocks connection, no second known consumer.
- [ ] Wire official SDK handlers to trusted pairing/ingress and existing approval callback; no channel-side tool execution.
- [ ] When listener is ready, tell user the exact synthetic message to send. Verify received event/task linkage; callback/user actions remain pending until real evidence. Do not send unrelated messages.
- [ ] Commit/push/remote/CI. Perform final fresh-context branch review, meaningful regressions for required findings and final full verification.

## Decisions / 实施判断

- Ruling: reuse existing event/checkpoint JSON envelopes rather than add tables; schema changes remain additive and explicit. Cost: indexed cross-run queries may need a later migration if volume grows.
- Ruling: use static JS ES modules in the thin frontend instead of adding a TypeScript bundler; no product behavior changes. Cost: frontend type checking relies on JSDoc/tests initially.
- Ruling: execute inline on the previously confirmed clean fix branch; preserve the user's per-fix commit/push workflow without another execution-method approval.
