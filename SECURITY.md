# 安全策略与架构不变量声明 / Security Policy & Architectural Invariants (OB-079)

## 中文说明

1. **统一 Broker 与零模型赋权**：所有工具副作用必须经 Broker、六维策略与一次性 `CONSUMED` 审批授权；模型输出、网页文本（`TAINTED_EXTERNAL`）、只读技能与第三方 MCP 注释（`readOnlyHint`）绝不能直接赋权。
2. **本地控制 API 防护**：仅监听 `127.0.0.1`/`::1`，强制校验本地 `Host`、`Origin`、`X-OpenBot-Profile` 与分域 Token（`owner_cli`、`feishu_gateway`、`webview_readonly`），并拒绝一切 `X-Forwarded-For` 代理伪造头。
3. **机密零落盘与离线脱敏**：凭据仅通过受批准的 OS Keychain 后端与单次 IPC 句柄按需注入，绝不写入源码、模型提示词、普通日志、Artifact 或诊断包。
4. **未知结果零盲目重放**：`DISPATCHING` 后结果不明一律进入 `UNKNOWN`/`RECONCILING` 并冻结资源，必须先提供核对证据完成 reconcile。

## English Summary

1. **Unified Broker & Zero Model Authority**: Every side effect is gated by the Broker, 6D policy evaluator, and one-time `CONSUMED` approval grants; model outputs, web pages (`TAINTED_EXTERNAL`), skills, and third-party MCP hints never grant authority.
2. **Loopback Control API Hardening**: Enforces loopback IP, `Host`/`Origin` validation, proxy-header rejection, profile binding, and scoped tokens.
3. **Secret Isolation & Offline Redaction**: Secrets reside only in approved OS keychains and single-use worker IPC handles, scrubbed from all logs, artifacts, and diagnostics via `RedactionPipeline`.
4. **No Blind Replay on `UNKNOWN`**: Unconfirmed post-dispatch outcomes transition to `UNKNOWN`/`RECONCILING` with resource quarantine until evidence-backed reconciliation completes.
