# ADR-0010: Scoped live Feishu ingress / 飞书真实入口边界

Status / 状态: implementation of the user-approved client design, 2026-11-05.

The official SDK receives events in a separate, bounded-lifetime consumer process. An external guardian owns its lifecycle and checks current daemon settings; OFFLINE/disabled state stops that consumer and waits for exit. A profile lock prevents a second known consumer. The existing receipt reaction is optional presentation, not evidence of admission; this contract does not enable outbound chat or card approvals.

官方 SDK 仅作认证 WebSocket 入口，不接管模型或工具循环。凭据无回显输入、仅驻留内存；日志仅输出固定阶段代码，不输出含 ticket 的 WebSocket URL、原始事件或异常 body。准备阶段精确锁定 SDK 及依赖，运行期不下载。

Only a narrow `feishu_gateway` token may access the Feishu observation/event/heartbeat routes. It cannot use the generic Task mutation, approval or client configuration APIs. The local owner configures the expected app. First contact creates a bounded pending tenant/app/user/chat candidate only; explicit local owner confirmation creates the identity, audit event and local outbox atomically. No callback body chooses principal, policy or owner role.

已确认绑定的同一 tenant/app/user/chat 私聊文本，经过当前 CONNECTED + feishu_enabled 检查后写入同一个 Inbox。SDK event ID 持久去重；原始 callback 不入库。Task/run、Skill/MCP 与审批继续复用同一个 daemon。回放不启动模型或工具，未配对 sender 不创建 Task。

Remote card approvals remain fail-closed until their actor/preview/nonce scope has a separate real-service gate. Existing local approval semantics are unchanged. / 远程卡片审批在真实身份与预览/nonce 门禁闭合前仍拒绝；不伪装为已支持。

## CR-07: internal durable ACK / 内部持久化确认

The worker sends newline-delimited JSON `{"type":"event","callback_id":"<32 hex>","event":{...}}`. Only after the authenticated, scoped daemon session returns HTTP 201 (or an accepted duplicate HTTP 200/201) with a valid Inbox Task receipt (`task_id`, `state`, `version`) may the guardian flush `{"type":"ack","event_id":"<stable SDK ID>","callback_id":"<same callback>"}` to that worker's stdin. A 201 pending pairing candidate is memory-only and MUST NOT be acknowledged. Errors, timeouts, malformed receipts and uncommitted transactions never produce an ACK. No new daemon schema or migration is needed.

SDK callbacks serialize their event/ACK exchange with one bounded wait (seven seconds including lock acquisition and framing). Both identifiers must match: a stale ACK, including one for an earlier delivery of the same event, cannot acknowledge a later callback. The random callback ID is local correlation only; it is stripped before daemon ingress and never replaces the stable SDK event ID used for Inbox deduplication. Partial frames, EOF and oversized output fail closed; event output stays capped at 64 KiB, ACK frames at 512 bytes, and guardian ACK writes have a one-second deadline. Transport markers share the worker's framed output lock.

Reaction addition/removal is outside both the current and subsequent callback ACK paths. At most one best-effort presentation job runs at a time, with at most 64 tracked reactions and no delivery queue or retry framework. Busy/full presentation may be skipped; a failed or stuck presentation job cannot delay ACKs or child shutdown. Cleanup is also best effort and may leave a visible reaction; no presentation success is claimed from an ACK. Future cards must preserve this separation and retain their own authorization gates. The channel still does not execute tools.

内部 ACK 只证明已认证 daemon 的 Inbox 持久接收（含已接收重复事件），不证明 Task 执行、reaction 或卡片成功。配对候选的 201 不代表落盘。所有回调按稳定 event ID 与单次 callback ID 双重匹配，重投递继续使用原 Inbox 身份；展示拥塞/失败可丢弃，但不得影响持久确认或停止消费者。
