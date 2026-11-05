# Client control and daemon / 客户端控制与 daemon（OB-081）

Authenticated additive client routes expose settings preview/apply, scoped Task/run lists, bounded traces, actual approval previews and independent runtime health. Writes require owner scope; query tokens cannot start runs or apply settings. Host, Origin, profile, principal and trusted context remain authoritative. Replay is read-only. Malformed/oversized HTTP framing is rejected before reading the body.

客户端只读 DTO 已连接真实核心，审批预览显示注册 manifest 的实际 effect 与脱敏参数。工作区由可信 CLI 选择并绑定；已有任务的工作区不能悄悄换根。`daemon serve --workspace-root <dedicated-demo-directory> --model-credentials` 通过交互式无回显提示，或受保护 stdin 管道接收模型地址和 API key；二者只驻留进程内存，不进配置 DTO。

RED: eight missing-client-route cases; two missing daemon credential/composition cases; three pre-body HTTP framing failures. GREEN: 14 local API/daemon cases plus existing related regressions. The actual subprocess survives dropping an HTTP client, retains locale across restart, reports credentials absent after restart, and a profile byte scan finds no synthetic credential.

完整验证 `tool-history-20261105`: 399 passed, 2 explicitly gated native-container skips, all eight checks passed. Real model-to-container workflow reached SUCCEEDED with one Operation/Attempt and CONSUMED approval; evidence in `agent-runtime.md`. This is an unsigned macOS development path, not release/signing or arbitrary MCP qualification.

No account credentials are committed. The owner control token and approval challenge store remain protected local profile files and are excluded from Git. Provider credentials are not persisted; daemon restart requires reinjection. / 关闭 UI 不停止 daemon；重启 daemon 后需重新注入模型凭据。
