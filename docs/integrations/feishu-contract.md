# 飞书协议契约与脱敏夹具说明 / Feishu Protocol Contract & Sanitized Fixtures (OB-047 / M2)

## 中文说明

### 1. 范围与诚实边界
- `OB-047` 的真实飞书测试租户联调因当前环境未提供专用企业自建应用与凭据而保持 `BLOCKED`。
- 为保障 `OB-048`—`OB-055` 的网关入站、配对、卡片回调、普通卡与 CardKit 降级、健康探测及死信重投在离线环境下的严密契约验证，本文件与 `tests/fixtures/feishu/sanitized_events.json` 固定了飞书 WebSocket 入站消息（`im.message.receive_v1`）与卡片交互回调（`card.action.trigger`）的脱敏载荷格式及边界不变量：
  - WebSocket 事件 ACK 与 HTTP 回调响应严格分离；入站消息必须在 daemon `Inbox` 持久化提交成功后才返回 WebSocket ACK。
  - 审批权限权威始终在 daemon（`ApprovalService` CAS），绝不信任 `action.value` 中客户端回传的 `is_owner` 字段。
  - 严禁照搬未经本机和当前版本实测的硬编码秒数（如 24.27 秒或 28 分钟/14 天常量）。

## English Summary

### 1. Scope & Honest Boundary
- Real Feishu tenant verification (`OB-047`) remains `BLOCKED` pending a dedicated test tenant and app credentials.
- `tests/fixtures/feishu/sanitized_events.json` defines the sanitized offline replay fixtures for `im.message.receive_v1` and `card.action.trigger`, keeping WebSocket ACK semantics separate from HTTP callback responses and preserving all authorization authority in the daemon.
