# OpenBot

**A local-first AI task assistant being developed for macOS, with explicit approvals, bounded tools, and traceable execution.**

[中文](README.md) · [Getting started](docs/getting-started.md) · [Troubleshooting](docs/troubleshooting.md) · [Security](SECURITY.md) · [Development tasks](tasks/backlog.json)

> **Status: in development.** The application version is `0.1.0.dev0`. Durable tasks, approvals, an authenticated local API, CLI, and several adapters and qualification modules exist. The complete agent loop, desktop client, and stable distribution are still being built. There is no stable end-user release yet.

## What OpenBot is designed to do

- Read an explicitly authorized workspace and produce results with source references.
- Show a concrete file-change proposal, then recheck its target after approval to protect subsequent user edits.
- Let users follow tasks, handle approvals, and stop further actions through local entry points and Feishu.
- Preserve an unresolved outcome when an action may already have happened, so a timeout does not trigger a blind repeat.

These are product goals. The table below separates existing implementation from remaining qualification.

## Current progress

| Capability | Existing work | Remaining boundary |
|---|---|---|
| Persistence and approvals | SQLite, a bounded Writer, and Task/Operation/Approval/Attempt services and tests | Qualification through the real task runtime |
| Local entry points | Authenticated API and real CLI/daemon startup | Accepting a task does not prove agent execution |
| Providers, Browser, MCP, Feishu | Adapters, protocol probes, and scoped tests | Real workflows, isolation, cancellation, and recovery |
| Settings and run facts | Durable settings, run snapshots, and redacted trace foundation on the development branch | Runtime activation and complete desktop UI |
| macOS | ARM64 development/CI and some native evidence | Stable installation, signing, and upgrade qualification |
| Windows and Linux | Engineering CI with different test scopes | Full native product support |

Checkpoint: November 5, 2026, `main@20282291` ([20282291](https://github.com/xiongcp/OpenBot/commit/2028229123a6fc1d44ec54a1c905ef4c9f09fa05), merging PR #2 with `agent_runtime.py`, `client_routes.py`, initial `apps/desktop`, read-only MCP container slice, and `live_gateway.py`). See [evidence](docs/evidence) for limits. The engineering design baseline `v1.2` is separate from the application version.

The incremental checkpoint [620311b4](https://github.com/xiongcp/OpenBot/commit/620311b4d141f3c964c90cc1a6db980dedecf365) adds a real read-only MCP container slice for one synthetic fixture. Full Agent integration and production qualification remain pending.

## Verify from source

This path is for developers. Use the project's Python 3.12 requirement and uv, check the lockfile and architecture, and leave system Python unchanged.

```sh
git clone https://github.com/xiongcp/OpenBot.git
cd OpenBot
uv sync --locked
.venv/bin/python scripts/verify.py
.venv/bin/openbot --help
```

Use a separate environment for the optional OpenAI SDK qualification group:

```sh
UV_PROJECT_ENVIRONMENT=.venv-m1 uv sync --locked --group provider-openai
.venv-m1/bin/python scripts/verify.py --phase M1
```

Default tests, SDK loopback tests, native isolation qualification, and live external services are reported separately. Missing credentials, tenants, or backends leave the relevant capability unverified. Synthetic passes do not replace that evidence. See [getting started](docs/getting-started.md) and [backend capabilities](docs/evidence/backend-capabilities.md) for commands and limits.

## How authority and results are handled

Models propose actions; the control plane authorizes them. Approval makes an Operation ready. Before actual dispatch, the system rechecks identity, cancellation, policy, deadlines, and target resources. Tools and external text cannot change those rules.

Closing the future desktop window and stopping a task are separate operations; the daemon owns task lifetime. Uncertain effects remain `UNKNOWN / RECONCILING` until evidence supports a result. Stopping blocks further dispatch and does not promise to undo effects that already happened.

`CONNECTED`, `LOCAL_MODEL`, and `OFFLINE` have different requirements. A local address or model name alone does not prove that no cloud request occurs. Network claims apply only to qualified managed scopes. Never put API keys, cookies, or private business data in Issues, model context, or logs.

## Roadmap

1. Connect a bounded real agent loop to the existing budget, approval, and outcome services.
2. Qualify cancellation, recovery, secrets, Browser, MCP, and Feishu through real paths.
3. Deliver a bilingual desktop client, settings activation, and factual execution views.
4. Build installable artifacts, signing/notarization, safe upgrades, and a macOS beta.
5. Publish v1.0.0 with an explicit support scope and matching source/artifact evidence.

The original IDs and dependencies remain in [tasks/backlog.json](tasks/backlog.json). Windows/Linux, Intel, native desktop control, and additional devices have separate scope and qualification gates.

## Development and contributions

Start with [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md), and the [architecture](docs/02_architecture.md). Work in reviewable slices, preserve existing user changes, and provide relevant regressions and actual evidence for completion claims.

Bug reports should include version/SHA, OS/architecture, installation method, a minimal reproduction, and expected versus actual behavior. Attach only redacted summaries, never credentials, complete databases, or private messages. Do not disclose sensitive security details publicly. [SECURITY.md](SECURITY.md) still needs a maintainer-verified private reporting route; submit sensitive material only after that route is available and verified.

## License and third-party components

The public records for the project's own source license are being reconciled. Until the root LICENSE is resolved, third-party notices or a pilot SBOM must not stand in for a project license grant. Third-party components and their terms are recorded separately in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the component catalog.

---

This README is a proposal based on the checkpoint above. Refresh status and links before adoption. Add actual screenshots, verified downloads, and the final license statement when those deliverables exist.
