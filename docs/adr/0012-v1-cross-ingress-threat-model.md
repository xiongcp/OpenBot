# ADR 0012: Cross-Ingress Threat Model and Trust Boundaries for v1.0.0

## Status
Accepted (2026-11-05)

## Context
With `agent_runtime.py`, `client_routes.py`, `apps/desktop` (Tauri 2), and `openbot_feishu/live_gateway.py` merged into `main@20282291`, OpenBot accepts requests and data across multiple surfaces: local owner CLI, Tauri Rust IPC, Feishu gateway, cloud/local model streams, MCP stdio/containers, browser DOM/ARIA snapshots, macOS AX trees, and workspace memory.

## Decision
1. **Untrusted Data Surfaces (`TAINTED_EXTERNAL`)**: Model outputs, skill files, workspace files, web DOM/ARIA trees, macOS `AXUIElement` labels, MCP tool metadata/results, and workspace memory entries are strictly untrusted data (`authoritative_grants=False`). None may mint approvals, alter policy, or execute tools directly.
2. **Server-Derived Principal and Recovery Proof**: Identity, owner role, policy revision, and `runtime_epoch` are derived exclusively by the daemon control plane. `/v1/runtime/recover-epoch` never trusts client-supplied `old_epoch_isolated` booleans; isolation proof comes solely from `ProcessSupervisorService` and container inspection.
3. **Scoped Token & IPC Boundaries**: `owner_cli` tokens, `desktop_ui` tokens, and `gateway` tokens are strictly scoped. Tauri IPC exposes a fixed command allowlist and forbids arbitrary URL forwarding or raw secret retrieval into WebView DOM.
4. **Zero-Argv Secret Handling**: Secrets never enter process `argv`, ambient child `env`, logs, artifacts, or diagnostics bundles.
