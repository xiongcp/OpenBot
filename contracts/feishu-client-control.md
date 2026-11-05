# Feishu client ingress / 飞书客户端入口

The trusted daemon owns the local principal, session, workspace and policy. No SDK
event, model output or HTTP body may assign them. / 本地 daemon 生成身份与权限上下文。

- `feishu_gateway` tokens permit only `GET /v1/feishu/config`,
  `POST /v1/feishu/events` and `POST /v1/feishu/health`. They cannot use generic
  Task, approval, trace, artifact or settings routes. All tokens match the daemon
  profile and principal. / 网关令牌仅有入口与健康权限。
- The local owner configures an expected public App ID. Event ingress accepts only
  bounded `event_id, tenant_key, app_id, open_id, chat_id, text` strings from the
  authenticated SDK consumer; only private plain-text messages are normalized.
  Extra fields, other apps and empty identifiers fail closed. / 仅接收私聊纯文本。
- First contact produces a pending tenant/app/user/chat candidate with a short TTL;
  it creates neither an owner nor a Task. Local confirmation displays all four
  identifiers. The confirmation creates an ACTIVE channel identity plus an audit
  event and local outbox in one transaction. The confirming local principal is
  authoritative. No remote approval is implied. / 首条消息不自动配对。
- Paired text enters the existing Inbox with durable SDK event-ID deduplication.
  Current CONNECTED mode, enabled flag and full identity/account/chat scope are
  rechecked in the write transaction. Duplicate delivery never restarts a run.
  Text is redacted before persistence; raw callbacks and secrets are not stored.
  / 入库前脱敏、事务内复核、重复事件不重放工作流。
- The same daemon runtime, Broker, approvals and trace graph execute the Task.
  Busy or credential-less runtimes leave it queued for explicit local start.
  Guardian shutdown confirms the SDK child exited before releasing its profile
  lock. OFFLINE/disabled state terminates the child; no outbound chat/card/reaction
  or remote card decisions are enabled by this contract.
