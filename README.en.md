# OpenBot engineering design and implementation handoff

[中文](README.md) | [English](README.en.md)

Design baseline **v1.2 · November 4, 2026**. This repository contains the original engineering design package and an implementation checkpoint. It has **not passed OB-029** and is **not an M3 MVP**.

## Current implementation

M0 includes a minimal Python package, strict JSON/Schema/JCS contracts, deterministic fixtures, and the OB-091 SQLite crash-protocol PoC. M1 includes SQLite migrations, a bounded single writer, scoped durable inbox, partial Task state services, immutable proposals and internal approval decisions, OpenAI/httpx fault contracts, and native macOS Docker primitives.

Approval only makes an Operation READY. The current services do not provide the production claim/dispatch/recovery loop, authenticated control API, or an end-to-end CLI workflow. The design catalog remains NOT_RUN. Exact local development dependencies and limited qualification evidence live separately in `components/admissions`; passing tests does not enable runtime capabilities.

See the [bilingual checkpoint and work split](docs/handoff/2026-11-04-checkpoint.md), [Claude Code OB-093 assignment](prompts/07_claude_code_ob093.md), and [Integrator continuation prompt](prompts/08_integrator_resume.md). Each prompt has equivalent Chinese and English versions; execute one version.

## Verify locally

Python 3.12 is required. From the repository root:

```sh
uv sync --locked
.venv/bin/python scripts/verify.py
```

The separate M1 qualification environment includes the OpenAI SDK:

```sh
UV_PROJECT_ENVIRONMENT=.venv-m1 uv sync --locked --group provider-openai
.venv-m1/bin/python scripts/verify.py --phase M1
```

On Windows, use the corresponding environment's `Scripts/python.exe`. These commands are instructions, not evidence that Windows has been tested. The M1 SDK tests use a synthetic loopback HTTP server and require local loopback access. The verification script disables native container tests; their explicit command and limitations are in [backend capabilities](docs/evidence/backend-capabilities.md).

On this macOS host, inherited hidden-file flags can prevent editable `.pth` files from being loaded. Use `PYTHONPATH=services/core/src .venv/bin/python -m openbot version` when needed. The verification script sets the source path explicitly and does not modify system Python.

Latest recorded results and their real exit codes/log hashes are in [M0 verification](evidence/implementation/verification.json) and [M1 verification](evidence/implementation/m1-verification.json). Tests, synthetic services, and native/container qualification are reported separately. Dedicated tenants, model credentials, and native Windows/Linux evidence are still missing; see [external environments](docs/evidence/external-environments.md).

## Read first

1. `AGENTS.md`, `CLAUDE.md`, and `prompts/05_autonomous_project.md`: repository rules and continuous implementation scope.
2. `docs/00_scope.md`, `docs/02_architecture.md`, and `docs/10_project_plan.md`: boundaries, architecture, milestones, and gates.
3. `docs/12_component_reuse.md`, `docs/13_component_qualification.md`, and `docs/14_revision_v1_2.md`: component adoption and qualification.
4. `tasks/backlog.json`, the current task card, and `components/catalog.json`: authoritative IDs, dependencies, reuse fields, and acceptance criteria.
5. `docs/03` through `docs/09`, implementation ADRs, and `docs/evidence`: protocol details and actual limitations.

The Chinese design documents and machine-readable contracts remain authoritative. This English entry point does not replace or relax their requirements.

## Repository map

| Path | Purpose |
|---|---|
| `services/core/src/openbot` | Current Python implementation; incomplete product runtime |
| `tests/`, `scripts/` | Contract, crash, storage, SDK and native qualification; verification tooling |
| `tasks/backlog.json`, `tasks/TASKS.md` | 96 stable task IDs, dependencies, reuse decisions, status and acceptance |
| `components/catalog.json` | 52 design component decisions; not an installation or runtime grant |
| `components/admissions`, `components/locks`, `components/assets` | Exact local qualification records, phase lock snapshots and prepared assets |
| `contracts/` | Existing API/schema/state contracts and internal storage contract |
| `db/` | Original 23-table baseline and explicit checksum migrations |
| `docs/`, `docs/adr`, `docs/evidence`, `docs/handoff` | Design, implementation decisions, evidence and delegation |
| `evidence/implementation` | Actual synthetic test logs, snapshots and dependency license texts |
| `diagrams/`, `reports/`, `templates/` | Original design artifacts, review artifacts and qualification templates |
| `validation/` | Offline design and DDL checks; not product acceptance |
| `prompts/` | Bootstrap, task, review, handoff and scoped continuation prompts |

The original package retains 96 tasks (OB-001 through OB-096), 52 component decisions, 24 reuse revisions, the original 22 decision records and seven architecture diagrams, a 23-table SQL baseline, and 14 local API operations. New implementation ADRs and migrations are recorded separately. Existing PDFs are design references, not proof of implementation.

## Delivery gates

M0 contract/PoC evidence does not close OB-029. M1 must demonstrate the real local API, permissions, artifacts, Broker and qualified isolated execution; it may use a controlled fake Provider. M2 requires a real dedicated Feishu tenant. M3 additionally requires Browser/MCP, at least two Providers, native platform qualifications, quality regression and supply-chain evidence. Missing environments block their specific acceptance; independent ready work can continue.

Preserve Task/Operation/Approval/Attempt separation, irreversible CONSUMED history, two short pre-dispatch transactions, UNKNOWN reconciliation/quarantine, server-derived identity and policy, and fail-closed isolation. A localhost model endpoint does not prove local inference. Component hints and model output cannot grant permissions. Never place credentials in source, model context, ordinary logs, artifacts or diagnostic bundles.

Work on one ready task or bounded subtask at a time. Read `component_refs`, `reuse_type`, and `reuse_notes`; pin only necessary phase dependencies. Parallel work needs separate branches/worktrees, exclusive file ownership, and one Integrator for shared contracts, migrations, locks and policies. Preserve existing user changes. Actual positive/negative tests and required evidence are necessary before changing VERIFIED to DONE.

## Recheck the design package

```sh
python3 validation/verify_design.py
python3 validation/verify_components.py
python3 validation/verify_database.py
```

See `validation/VALIDATION.md` for scope. The legacy finite-keyword design validator is not the runtime JSON Schema validator. Hashes in `contracts/examples` are synthetic format examples; actual binding digests are computed by the implementation using tested RFC 8785 canonical bytes.

Track application version, protocol, database migrations, dependencies and platform capability separately. The v1.2 design label does not automatically upgrade any of them. Models propose; the control plane authorizes; components provide bounded primitives; unknown effects require reconciliation; completion requires evidence.
