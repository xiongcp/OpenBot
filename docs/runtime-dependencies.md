# 可复现打包与运行时资源清单说明 / Reproducible Packaging & Runtime Asset Manifest (OB-072)

## 中文说明

### 1. M3 未签名试点包与 M4 签名发行边界
- `packaging/runtime-assets.json` 与 `scripts/build/build_pilot_bundle.py` 定义了 M3 CLI 试点包构建与运行时非包资产清单。
- M3 产物明确标记为 `M3_UNSIGNED_PILOT`（`signed_m4_release_claimed = false`），不冒充 M4 代码签名/公证桌面发行版；同时因 Windows 与 Linux 原生构建机未接入（`OB-070`/`OB-071` `BLOCKED`），仅声明 `Darwin-arm64` 本地构建已验证。

### 2. 安装期准备与首次离线运行分离
- **零首次运行静默下载（`first_use_silent_download_permitted = false`）**：`ripgrep`、Tree-sitter grammar、`tiktoken` 词表与 Chromium 浏览器必须在安装期显式就绪；运行期若缺失对应离线资产，直接返回 `CAPABILITY_UNAVAILABLE`，绝不在首次使用时联网补下载。
- **禁混入机密与缓存**：`PackagingBundleAuditor` 强制拦截任何 `.env`、`*.sqlite`、`*.key`、`*.pem`、`__pycache__` 进入产物目录。

---

## English Summary

### 1. M3 Unsigned Pilot Bundle vs M4 Signed Release
- `packaging/runtime-assets.json` and `scripts/build/build_pilot_bundle.py` define the M3 CLI pilot bundle manifest (`bundle_stage = 'M3_UNSIGNED_PILOT'`, `signed_m4_release_claimed = false`). Native Windows and Linux builds remain blocked (`OB-070`/`OB-071` `BLOCKED`).

### 2. Install-Time Provisioning vs First-Use Offline Execution
- **No First-Use Silent Downloads (`first_use_silent_download_permitted = false`)**: Missing `ripgrep`, Tree-sitter grammars, `tiktoken` vocabularies, or Chromium binaries fail closed with `CAPABILITY_UNAVAILABLE` at runtime instead of downloading over the network.
- **Secret & Cache Exclusion**: `PackagingBundleAuditor` rejects bundles containing `.env`, `*.sqlite`, `*.key`, `*.pem`, or cache directories.
