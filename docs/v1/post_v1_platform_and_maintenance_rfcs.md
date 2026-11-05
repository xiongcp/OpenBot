# Post-v1 Platform Qualification, Multi-Agent RFC & Maintenance Cadence (`V1-039`, `V1-056..060`)

## 1. Windows Native Qualification Gate (`V1-056` / `OB-070`)
- Status: `POST_V1`. Requires native Windows Job Object (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` before `ResumeThread`), `WinVaultKeyring` compartment verification, and signed MSIX/installer qualification. `contracts` CI on Windows never substitutes for native qualification.

## 2. Linux Desktop & systemd User Service Gate (`V1-057` / `OB-071`)
- Status: `POST_V1`. Requires delegated `cgroup v2` process-tree containment, `SecretService` keyring verification, and AppImage/deb packaging.

## 3. Intel Mac (`x86_64`) & Rosetta Boundary (`V1-058`)
- Status: `POST_V1`. `v1.0.0` targets `Darwin arm64`; `Darwin x86_64` requires dedicated native hardware/VM verification before claiming universal binary support.

## 4. Multi-Device Routing & Parallel Multi-Agent RFC (`V1-059`)
- Status: `POST_V1`. Preserves single-owner per-workspace lease fencing; cross-device sync and parallel sub-agent sandboxes require separate fencing and budget isolation ADRs.

## 5. Post-Release Maintenance, Rollback & v1.0.1 Patch Cadence (`V1-039`, `V1-060`, `V1-084`)
- **Emergency Rollback**: Revoke bad version in `SignedReleaseChannelUpdater` manifest and restore pre-upgrade snapshot via `UpgradeTransactionStateMachine`.
- **Triage SLA**: S0 security/data-integrity issues triaged within 24h; patch releases (`v1.0.1+`) ship immutable signed archives without overwriting existing tags.
