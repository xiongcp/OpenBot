# ADR-0010: Scoped live Feishu ingress / 飞书真实入口边界

Status / 状态: implementation of the user-approved client design, 2026-11-05.

The official SDK receives events in a separate, bounded-lifetime consumer process. An external guardian owns its lifecycle and checks current daemon settings; OFFLINE/disabled state stops that consumer and waits for exit. A profile lock prevents a second known consumer. No outbound chat/reactions/cards are enabled by this slice.

官方 SDK 仅作认证 WebSocket 入口，不接管模型或工具循环。凭据无回显输入、仅驻留内存；日志仅输出固定阶段代码，不输出含 ticket 的 WebSocket URL、原始事件或异常 body。准备阶段精确锁定 SDK 及依赖，运行期不下载。

Only a narrow `feishu_gateway` token may access the Feishu observation/event/heartbeat routes. It cannot use the generic Task mutation, approval or client configuration APIs. The local owner configures the expected app. First contact creates a bounded pending tenant/app/user/chat candidate only; explicit local owner confirmation creates the identity, audit event and local outbox atomically. No callback body chooses principal, policy or owner role.

已确认绑定的同一 tenant/app/user/chat 私聊文本，经过当前 CONNECTED + feishu_enabled 检查后写入同一个 Inbox。SDK event ID 持久去重；原始 callback 不入库。Task/run、Skill/MCP 与审批继续复用同一个 daemon。回放不启动模型或工具，未配对 sender 不创建 Task。

Remote card approvals remain fail-closed until their actor/preview/nonce scope has a separate real-service gate. Existing local approval semantics are unchanged. / 远程卡片审批在真实身份与预览/nonce 门禁闭合前仍拒绝；不伪装为已支持。
