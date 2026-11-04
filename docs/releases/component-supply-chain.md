# 全量交付资产来源与供应链验收说明 / Release Component Supply-Chain & SBOM Verification (OB-096)

## 中文说明
- **SPDX-2.3 SBOM 与非 Python 资产覆盖**：`release/SBOM/spdx-pilot.spdx.json` 明确采用 `SPDX-2.3` 标准（绝不将 CycloneDX 冒称为 SPDX），同时覆盖 Python 锁定包与非 Python 运行时资产清单（`packaging/runtime-assets.json`）。
- **防篡改哈希与源码复用台账对齐**：`scripts/check_release_components.py` 逐项比对 `uv.lock`、`THIRD_PARTY_NOTICES.md`、`packaging/runtime-assets.json`、`components/source-reuse/feishu.json` 与 `components/source-reuse/browser-dom.json` 的 SHA-256，任何一字节篡改立即抛出 `SUPPLY_CHAIN_HASH_TAMPERED`。
- **诚实安全边界**：明确声明 `pinned_versions_guarantee_zero_vulnerabilities = False`（固定锁与哈希仅保证可追溯性，不等同于零漏洞保证）。

## English Summary
- **SPDX-2.3 SBOM & Non-Python Asset Coverage**: `release/SBOM/spdx-pilot.spdx.json` uses strict `SPDX-2.3` format and covers both Python packages and non-Python runtime assets.
- **Tamper Detection & Honest Boundary**: `scripts/check_release_components.py` verifies exact SHA-256 digests in `release/checksums.json` (`SUPPLY_CHAIN_HASH_TAMPERED` on mismatch) and explicitly states `pinned_versions_guarantee_zero_vulnerabilities = False`.
