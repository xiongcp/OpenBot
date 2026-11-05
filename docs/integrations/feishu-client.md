# Feishu client entry / 飞书客户端入口

Scope: macOS development, private plain-text ingress only. The official SDK is a
separate consumer; the existing daemon owns identity, Tasks, model requests, core
approvals, MCP execution and the execution graph. No message, card or reaction is
sent by this entry. Remote card approval remains disabled pending its real actor,
preview and nonce gate.

范围：macOS 开发版私聊纯文本入口。SDK 不执行工具；身份、Task、审批与执行图均由
同一个 daemon 管理。当前不发送消息、卡片或表情，不启用远程卡片审批。

## Setup / 准备

Install only the locked optional groups in a development environment. / 仅安装精确锁定的可选组：

```sh
uv sync --locked --group provider-openai --group feishu
openbot daemon serve --profile-dir /path/to/profile --workspace-root /path/to/synthetic-workspace --model-credentials
```

Enter the model endpoint and key through the protected CLI prompt. Configure
CONNECTED mode and enable Feishu in the native client's settings preview. Then
start the gateway in another terminal. / 模型地址与密钥通过 CLI 无回显输入；在客户端
预览并确认联网模式与飞书开关，再于另一终端启动：

```sh
openbot-feishu --profile-dir /path/to/profile --app-id YOUR_PUBLIC_APP_ID
```

The secret is read without echo and kept only in memory. `--secret-stdin` is for a
protected parent-process pipe; never put secrets into shell arguments or files.
Gateway control tokens are profile-scoped mode-0600 files, ignored by Git. The
native WebView never receives them. / App Secret 仅驻内存；令牌文件不进入 Git 或 WebView。

## Pairing and a visible workflow / 配对与可见工作流

1. Send a synthetic private message to the bot. First contact creates only a
   five-minute pending candidate, capped at sixteen candidates; its text is not
   run or persisted as a Task. / 首条私聊仅生成短时待确认候选，不执行任务。
2. In native Settings, verify tenant, app, user and chat IDs, then explicitly
   confirm your own private chat. Confirmation writes the channel identity,
   audit event and local outbox atomically. / 本地核对四项身份后确认绑定。
3. Send the next synthetic request. The paired event enters the existing Inbox;
   event-ID deduplication prevents another model or tool run on replay. The same
   client's Task list, FEISHU source node, Skill/MCP graph, approvals and artifacts
   show actual results. Busy or credential-less Tasks remain queued for local
   start. / 后续消息进入统一任务与执行图；重复投递不重放。
4. Tool proposals still need core authorization. Approval only makes an Operation
   READY; claim and pre-dispatch checks remain mandatory. UNKNOWN is not retried.
   / 批准不等于执行；结果不明不自动重放。

Turning Feishu off or selecting OFFLINE stops the child and waits for confirmed
exit before unlocking the profile. A failed connection requires an explicit CLI
restart. No runtime dependency download or alternate endpoint is used. The SDK
callback waits for daemon admission before successful ACK; transient admission
failure does not claim persistence. / 关闭入口或离线后确认退出；连接失败需显式重启。

## Receipt reaction / 收到回应

Feishu gives bots no read-receipt API, so (like Hermes) the gateway adds an emoji reaction (`Get`) to a paired private message, but only after the daemon has durably admitted it. Unpaired, rejected, OFFLINE or disabled events get no reaction. It is best-effort: failure never blocks ACK or logs error bodies. Requires the app scope `im:message.reactions:write_only` and a published app version. It marks receipt, not completion.

飞书没有机器人已读回执接口，与 Hermes 一样，网关在 daemon 持久接收已配对私聊后，给该消息添加 `Get` 表情回应；未配对、被拒绝、离线或未启用时不回应。失败不阻塞 ACK，也不记录错误正文。需要开通应用权限 `im:message.reactions:write_only` 并发布版本。它只表示“已收到”，不表示完成。

## Evidence and limits / 证据与边界

- Exact SDK: lark-oapi 1.7.5, MIT, official wheel SHA-256 and transitive versions in
  `components/locks/feishu-client.json` and `uv.lock`; no copied upstream source.
- Synthetic regressions cover pending confirmation, durable receipt, full
  tenant/app/user/chat scope, duplicates, redaction, OFFLINE, candidate TTL/count,
  gateway-token isolation and consumer shutdown/locking.
- Real read-only probe matched the exact user-sent test text with tenant/app/user
  fields present, zero outbound messages, zero tools and no automatic grant.
- Paired live Task linkage and updated native pairing controls are still awaiting
  the final live interaction. Full Q01/Q10, remote approval, macOS signing,
  updater and other native platforms remain unqualified by this slice.

精确 SDK 与依赖有锁和许可记录；合成测试与真人只读收消息分别记录。
配对后的真实 Task 链接仍待最后联调，不能以单元测试替代；完整 Q 门禁与正式分发未验收。
