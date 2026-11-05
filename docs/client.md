# OpenBot macOS development client / macOS 开发客户端

The client attaches to the separate CLI-owned daemon. Closing the window or quitting the app leaves the daemon running. This is an unsigned macOS development build; signing, auto-update, release packaging and other native platforms remain separate gates.

客户端通过固定 Rust IPC 读取运行记录、执行图、审批和配置。WebView 不持有 token、模型地址或 API key，也没有 shell、文件系统、任意 URL 插件。内容按纯文本显示。图与时间线重放不会调用工具。

## Prepare and start / 准备与启动

From the repository, use the locked Python environment with the optional provider SDK installed. Source execution also works with `PYTHONPATH=services/core/src:services/feishu_gateway/src`.

在仓库目录准备锁定的 Python 环境与 provider SDK；源码运行可使用上述 `PYTHONPATH`。专用工作区只放合成 `demo.txt`，不放密钥或私人文件。

```sh
uv sync --locked --group provider-openai
uv run --no-sync openbot daemon serve --profile-dir /tmp/openbot-demo-profile --workspace-root /tmp/openbot-demo-workspace --model-credentials
```

The CLI prompts without echo for endpoint and key, or reads two bounded lines from a protected stdin pipe. Never place credentials in command arguments, shell history or Git. Restarting the daemon requires reinjection. The owner token and challenge store are local protected profile files, excluded from Git.

CLI 无回显接收模型地址与密钥；不通过命令参数或环境变量传密钥。重启后重新注入。若不传 `--model-credentials`，客户端仍能读取历史与配置，但不能启动模型运行。

Prepare Rust 1.91.0 (minimum 1.90) and the macOS SDK. Fetch dependencies explicitly during development, then build offline:

```sh
cargo +1.91.0 fetch --manifest-path apps/desktop/src-tauri/Cargo.toml --locked
python3 scripts/build_desktop.py --profile-dir /tmp/openbot-demo-profile
```

Open `apps/desktop/out/OpenBot.app`. Its development launch configuration contains only the selected profile path. Alternatively run the built executable with `--profile-dir <path>`. Build outputs are Git-ignored. No launchd service is installed.

打开生成的 `OpenBot.app`；启动配置只包含 profile 路径。默认不启动或安装 daemon。若模型/MCP 不可用，健康状态会分别显示，缺少隔离时拒绝执行，不回退到宿主 shell。

## Read the graph / 阅读执行图

Each node is a persisted event linked to Task/run and, where applicable, Operation/Attempt. `Tool proposed` is a proposal; `Tool dispatched` is an actual dispatch; `Tool result verified` links a scoped artifact and hash. Select a node for details. Missing parents or UNKNOWN stay visible and cannot become success through replay. There is no hidden reasoning capture.

节点来自实际事件。提出调用不等于已经执行，收到结果也需核对回执与产物。选中节点查看 Skill 来源/hash、MCP server、操作与尝试 ID、Token 用量和产物。金额无可靠价格来源时显示不可用。暂停或待核对的旧运行不会自动重放。

## Settings and approvals / 配置与审批

Preview changes, inspect their impact, then apply. The server rechecks revision and hash atomically. Stale previews fail; reconnect discards a stale editor draft and reloads the active revision. Locale applies immediately, model defaults apply to new runs, and current restrictions are rechecked before each request/dispatch.

配置先预览后确认；旧版本不能覆盖新版本。重新连接会清除旧草稿并读取当前设置。审批中心显示注册 effect、脱敏参数与 binding hash；批准只进入 READY，仍需 claim 与派发复核。首版只准入项目自有 Skill 与专用只读 MCP demo，非通用 Skill/MCP 安装器。

Feishu onboarding and live evidence: [current live probes](evidence/2026-11-05-client-live-probes.md). / 飞书配对与实测证据见集成文档。
