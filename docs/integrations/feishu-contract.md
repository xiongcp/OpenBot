# 飞书协议契约与脱敏夹具说明 / Feishu Protocol Contract & Sanitized Fixtures (OB-047 / M2)

## 中文说明

### 1. 真实飞书测试自建应用实测结果（OB-047）
已在当前 `Darwin arm64` 环境使用专用飞书测试自建应用（`app_id` SHA-256 前缀 `24256e0cd6fa7df8`，原始凭据仅驻留内存/钥匙串，零明文落盘）对 `https://open.feishu.cn` 与 `wss://msg-frontier.feishu.cn` 执行分段实测，脱敏响应保存于 `tests/fixtures/feishu/sanitized_events.json`：
1. **分段冷启动与握手时序**：
   - 网关模块导入（`import_ms`）：`79.19 ms`
   - `POST /open-apis/auth/v3/tenant_access_token/internal`：`147.88 ms`（HTTP 200，`code=0`，`expire=7200s`）
   - `GET /open-apis/bot/v3/info/`：`169.04 ms`（HTTP 200，`code=0`，`activate_status=2`）
   - `POST /callback/ws/endpoint`：`102.11 ms`（HTTP 200，`code=0`，返回 `wss://msg-frontier.feishu.cn/...` 与服务端下发 `ClientConfig: {"ReconnectCount": -1, "ReconnectInterval": 90, "ReconnectNonce": 25, "PingInterval": 90}`）
   - `wss://msg-frontier.feishu.cn` 真实 TLS + WebSocket Upgrade 握手：`208.38 ms`（返回 `HTTP/1.1 101 Switching Protocols`）
2. **CardKit 2.0 实体创建与服务端 `sequence` 单调性实测**：
   - `POST /open-apis/cardkit/v1/cards`（独立卡片实体，不向任何群或用户发消息）：`230.84 ms`（HTTP 200，`code=0`）
   - `PUT /open-apis/cardkit/v1/cards/{card_id}`（`sequence=1`）：`259.43 ms`（HTTP 200，`code=0`）
   - 重复/乱序提交相同 `sequence=1`：飞书服务端返回 HTTP 200，`code=300317`，`msg="ErrMsg: sequence number compare failed; "`（`240.71 ms`），直接证实了 `OB-052`/`OB-053` 单调递增 `card_revision` 的必要性。
3. **权限与错误码契约实测**：
   - 已开通能力：`bot/v3/info`（`code=0`）、`im/v1/chats` 只读列表（`code=0`，`314.48 ms`）、`cardkit/v1/cards` 创建与更新（`code=0`）、WebSocket 长连接端点发现与 `101` 握手（`code=0`）。
   - 未开通权限的标准拒绝格式：`GET /open-apis/tenant/v2/tenant/query` 返回 HTTP 400，`code=99991672`（提示缺少 `tenant:tenant:readonly`）；非法 token 返回 HTTP 400，`code=99991668`。
   - 诚实边界：真实飞书服务端 API、CardKit 实体与 WebSocket `101` 长连接握手已实测通过；手机客户端人工点击卡片的交互触发仍受限于无真人在飞书客户端点击，由脱敏 `card.action.trigger` 夹具在本地端到端闭环（`OB-050`/`OB-056`）覆盖。

## English Summary

### 1. Live Feishu Test Tenant Verification Results (OB-047)
Verified against `https://open.feishu.cn` and `wss://msg-frontier.feishu.cn` using the dedicated test self-built app (`app_id` SHA-256 prefix `24256e0cd6fa7df8`, zero plaintext credentials written to disk):
1. **Segmented Latency Measurements**: `import_ms = 79.19 ms`, `token_exchange_ms = 147.88 ms` (`expire = 7200s`), `bot_info_ms = 169.04 ms` (`activate_status = 2`), `ws_discovery_ms = 102.11 ms` (`ClientConfig`: `PingInterval = 90`, `ReconnectInterval = 90`, `ReconnectNonce = 25`), and live TLS + WebSocket upgrade handshake to `msg-frontier.feishu.cn` = `208.38 ms` (`HTTP/1.1 101 Switching Protocols`).
2. **CardKit 2.0 & Monotonic Sequence Enforcement**: Creating a standalone CardKit 2.0 card entity succeeded (`code = 0`, `230.84 ms`), updating with `sequence = 1` succeeded (`code = 0`, `259.43 ms`), and re-submitting stale `sequence = 1` returned `code = 300317` (`ErrMsg: sequence number compare failed; `).
3. **Permission & Error Contract**: Verified `im/v1/chats` (`code = 0`), invalid token rejection (`code = 99991668`), and missing-scope rejection on `tenant/v2/tenant/query` (`code = 99991672`, requiring `tenant:tenant:readonly`).
