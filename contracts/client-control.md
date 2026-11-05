# Client Control v1 / 客户端控制 v1

All routes require existing profile-bound authentication and loopback/Host/Origin checks. 配置写入、运行启动和审批决定仅 owner scope；查询允许已授权只读 scope。

- `GET /v1/client/settings` → `{revision, config}`; config contains `locale`, `model`, `mode`, `max_steps`, `skill_enabled`, `mcp_enabled`, `feishu_enabled`. No endpoint or secrets.
- `POST /v1/client/settings/preview` body `{expected_revision, config}` → `{expected_revision, preview_hash, config, changes, activation}`.
- `POST /v1/client/settings/apply` returns the whole preview envelope (`preview_hash`, `changes`, `activation`) plus `confirm:true`; identical re-delivery uses Idempotency-Key. Stale revision/hash → 409; invalid config → 400; owner failure → 403. Effective settings and audit event commit atomically.
- `GET /v1/client/runs` → `{runs:[{task_id, goal, state, version, run_id?, config_revision?, updated_at}]}` (max 100, owner/session scoped).
- `POST /v1/client/tasks/{task_id}/start` → persisted run receipt; same active Task cannot start twice.
- `GET /v1/client/tasks/{task_id}/trace?after_seq=N` → `{task_id, run_id, events, last_seq}` (max 128); unknown task/owner → 403, invalid cursor → 400, expired cursor → 410 with snapshot instruction. No tools execute on GET.
- `GET /v1/client/approvals` → redacted pending approval previews, owner scoped.
- `GET /v1/client/health` → independent runtime/credentials/executor/gateway availability, no secret values.

事件字段 / Trace DTO: `schema_version:"1", event_id, global_seq, task_id, run_id, parent_event_id?, kind, occurred_at_ms, config_revision, data`.
Kinds: `RUN_STARTED`, `SKILL_LOADED`, `MODEL_REQUESTED`, `MODEL_RETURNED`, `TOOL_PROPOSED`, `WAITING_APPROVAL`, `TOOL_DISPATCHED`, `TOOL_RETURNED`, `OUTCOME_VERIFIED`, `RUN_FINISHED`, `RUN_INTERRUPTED`.
Only allowlisted scalar/string-list data, redacted before persistence; no generic raw payload passthrough.
