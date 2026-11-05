# OpenBot v1.0.0 Baseline Audit, Scenarios, Compatibility & Environment Inventory

## 1. Fixed Baseline (`main@2028229123a6fc1d44ec54a1c905ef4c9f09fa05`) (`V1-002`)

| Module | Baseline Path | Status on `main@20282291` | v1.0.0 Hardening Target |
|---|---|---|---|
| Bounded Agent Runtime | `services/core/src/openbot/application/agent_runtime.py` | Merged (`7c936292`..`a72422eb`) | Dynamic multi-tool dispatch from `tool_registry` (`V1-010`, `V1-075`) |
| Authenticated Client API | `services/core/src/openbot/adapters/local_api/client_routes.py` | Merged (`743a934a`..`12074191`) | SSE event stream, structured Diff preview, untrusted recovery guard (`V1-013`, `V1-062`, `V1-063`) |
| Desktop Client | `apps/desktop/` | Merged (`b4af1ee5`) | Onboarding wizard, Split/Unified Diff, hierarchical DAG, Reconcile Wizard, Tray, Dark Mode (`V1-061..067`) |
| Isolated MCP Read | `services/core/src/openbot/tools/mcp/container_read.py` | Merged (`620311b4`) | Generic `McpContainerExecutor` with pinned `mcp-catalog.json` and intent log (`V1-016`, `V1-017`, `V1-068`, `V1-076`) |
| Feishu Live Gateway | `services/feishu_gateway/src/openbot_feishu/live_gateway.py` | Merged (`8a4753e1`..`54e746eb`) | Feishu 2.0 collapsible Diff & budget card, circuit breaker (`V1-027`, `V1-072`, `V1-082`) |

## 2. Evidence Provenance & Candidate Contract (`V1-003`)

- Every verification run records `run_id`, `source_sha`, `tree_sha`, `dirty_worktree`, `lockfile_sha256`, `artifact_sha256`, `provenance_kind` (`SOURCE` | `SYNTHETIC` | `NATIVE` | `LIVE_EXTERNAL`), `machine_id`, `lifecycle_state` (`IN_PROGRESS` | `COMPLETE` | `FAILED`), `exit_code`, and `log_sha256`.
- Reusing a `run_id`, attaching a stale `source_sha`, or claiming `NATIVE` with a `mock`/`synthetic` machine identifier fails closed.

## 3. Seven Core Product Scenarios (`V1-004`, `V1-009`)

1. `S1_WORKSPACE_READ_SUMMARY`: Profile setup, workspace binding, guarded file read, and bilingual cited summary.
2. `S2_WORKSPACE_PATCH_DIFF`: Exact diff proposal (`propose_patch`), human approval, hash/inode re-verification, atomic write (`apply_patch`), and `PatchCommitJournal` recovery.
3. `S3_BROWSER_READ_WRITE`: Managed Playwright ARIA snapshot (`BoundElementRef`), egress policy enforcement, highlighted target preview, and verified single-step write action.
4. `S4_ISOLATED_MCP_READ`: Pinned container MCP execution (`--network=none`, `--read-only`, `65532:65532`), schema drift quarantine, and container intent-log reaping.
5. `S5_FEISHU_INGRESS_APPROVAL`: Feishu message ingress, interactive 2.0 card approval, duplicate callback idempotency, and reaction lifecycle.
6. `S6_CLOUD_AND_LOCAL_PROVIDER`: Streaming cloud adapters (OpenAI, Anthropic, Gemini) and verified local Ollama digest with strict `OFFLINE` egress block.
7. `S7_DAEMON_CRASH_RECOVERY`: Out-of-process `SIGKILL` of the daemon holding SQLite Writer across four side-effect windows, transitioning `DISPATCHING` to `UNKNOWN`/`RECONCILING` with zero blind replay.

## 4. Public API, CLI & Event Compatibility Contract (`V1-006`)

- Public HTTP routes (`/v1/client/*`, `/v1/tasks/*`, `/v1/approvals/*`, `/v1/operations/*`), CLI JSON output (`--json`), and event stream DTOs follow SemVer `1.0.0`.
- Unknown fields in strict request schemas or incompatible protocol major versions fail closed (`UNKNOWN_CONTRACT_FIELDS_REJECTED` / `INCOMPATIBLE_PROTOCOL_MAJOR_VERSION`).

## 5. Sanitized Mac & Integration Environment Inventory (`V1-007`)

- Target host: `Darwin arm64`, Python `3.12.x`, locked `uv.lock`, Rust `1.91.0`.
- Environment reports strip and block `API_KEY`, `SECRET`, `TOKEN`, `PASSWORD`, and raw tenant messages.
