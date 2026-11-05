# OpenBot Public Capability & Version Status (`V1-040`)

This document summarizes the machine-readable public status in [project-status.json](project-status.json).

- **Product Target**: `v1.0.0` (`Darwin arm64` local-first AI task assistant)
- **Source License**: `Apache-2.0`
- **Deferred Post-v1 Platforms**: `Darwin x86_64` (`V1-058`), `Windows AMD64` (`V1-056`), `Linux x86_64` (`V1-057`)
- **Core Invariants**: Explicit approval before side effects, `UNKNOWN / RECONCILING` preservation without blind replay, zero secret exposure in `argv` or WebView DOM, and `< 100ms` physical keyboard/mouse preemption during desktop actions.
