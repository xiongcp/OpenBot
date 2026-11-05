# ADR 0011: v1.0.0 macOS-First Product Scope and Original M3 Relationship

## Status
Accepted (2026-11-05)

## Context
OpenBot's original v1.2 engineering design (`OB-001`..`OB-096`) defines a three-OS M3 milestone (`Darwin`, `Windows`, `Linux`). On `main@2028229123a6fc1d44ec54a1c905ef4c9f09fa05`, `contracts` passes across macOS, Ubuntu, and Windows (`399 passed, 2 skipped`), while native OS supervision, Keychain compartments, and Tauri desktop packaging are verified on `Darwin arm64`.

## Decision
1. **v1.0.0 Target Platform**: `v1.0.0` is scoped as a **macOS Apple Silicon (`Darwin arm64`)** single-owner local control-plane release (`V1-001`, `V1-030`).
2. **Preservation of Original M3**: Original three-platform tasks (`OB-070` Windows, `OB-071` Linux) and Intel/Rosetta (`V1-056..058`) remain explicitly separate (`POST_V1`) and are never marked complete based on `contracts`-only CI runs.
3. **Dual Backlog Isolation**: The v1.0.0 execution package (`V1-001..084`, 140 test cases, `G1..G8`) is mounted at `plan/v1_0_0/` without overwriting root `tasks/backlog.json` (`OB-001..096`).

## Consequences
- Every public capability claim in `README.md`, `docs/project-status.json`, and `apps/website` is bound to verified platform and provenance evidence (`SOURCE`, `SYNTHETIC`, `NATIVE`, `LIVE_EXTERNAL`).
- Passing `contracts` on Windows or Linux never generates a `supported` native product claim.
