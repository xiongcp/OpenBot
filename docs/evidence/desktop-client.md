# Native development client / 原生开发客户端（OB-082/083）

Scope: unsigned macOS ARM64 development only. Exact dependencies and Cargo.lock digest are in `components/locks/desktop-client.json`. No updater, shell/filesystem/HTTP plugins, deployment or full release qualification is included. The original catalog's full Tauri/updater qualification stays deferred; this bounded development scope was explicitly approved in the client design.

范围为用户确认的 macOS 开发客户端，非正式发布。Rust 只代理固定命令；AppManifest 与 capability 限 main 本地窗口。owner token 与 challenge 不传给 WebView，模型凭据只驻留独立 daemon 内存。远程内容纯文本显示，不保存隐藏推理。

Automated RED: missing frontend projection module. GREEN: four Node projection/i18n tests, two native Rust route/settings boundary tests; cargo test/build completed offline from the exact lock. Native build preparation initially lacked rustfmt/icon; both were resolved without modifying system toolchains or weakening checks.

Actual native UI observations / 真实原生界面：

- Displayed the real 12-event model/MCP workflow, pinned run configuration revision, 802 tokens and exactly one dispatch, with an artifact and SHA-256. Chinese/English switching updated the daemon settings immediately.
- Preview/apply advanced configuration revisions. A stale preview was rejected with CONFLICT. Native testing exposed that reconnect retained a stale editor draft; the minimal fix clears that draft on explicit reconnect. Repeating the scenario loaded the active revision and current value, then accepted a fresh preview.
- The approval center showed READ, exact `demo.txt` arguments and binding hash. Native approval made the Operation READY; a separate read verified zero Attempts. The test task was then cancelled through the client.
- An HTML `img/onerror` canary stayed literal text in the native task heading/list; no active element or script was rendered.
- Quitting/reopening the app left daemon HTTP health at 200. A second greeting task started from the native client; after window closure the daemon remained available and durably recorded a provider interruption/PAUSED rather than replaying or reporting success. This run is not counted as a successful model completion; the earlier complete real workflow is separate evidence.

界面与 daemon 分属独立进程。当前 Docker 可用性探测有时返回不可用，界面照实显示；本证据不将这视为稳定隔离后端验收。真实只读容器读取与回收已单独通过，见 `mcp-demo-container.md`。其他原生平台、签名、更新与完整发布 SBOM 均未验收。

The CI `desktop-client` workflow runs projection tests, Rust boundary tests, formatting and a native macOS build with Rust 1.91.0/Cargo.lock. CI results must be checked at the actual pushed SHA.

Core regression / 核心相关回归: `desktop-client-fixed-20261105` passed all eight checks; 399 passed / 2 explicit native-container skips. The original design checks were retained.
