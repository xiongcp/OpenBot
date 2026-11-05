# ADR 0013: OpenBot Root License Resolution (Apache-2.0)

## Status
Accepted (2026-11-05)

## Context
Prior to `V1-045`, `release/SBOM/spdx-pilot.spdx.json` referenced `Apache-2.0` while the repository root lacked a `LICENSE` file. `V1-035` and `V1-045` require reconciling the root `LICENSE`, `THIRD_PARTY_NOTICES.md`, and SBOM metadata.

## Decision
1. Adopt `Apache-2.0` as the authoritative license for OpenBot's first-party source code in root `LICENSE`.
2. Keep third-party package and source-reuse notices in `THIRD_PARTY_NOTICES.md` and `release/THIRD_PARTY_NOTICES.md`, verified by `ReleaseSupplyChainVerifier`.
