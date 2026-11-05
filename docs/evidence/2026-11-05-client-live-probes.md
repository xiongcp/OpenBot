# 客户端准备与真实协议探测 / Client Preparation and Live Protocol Probes

日期 / Date: 2026-11-05 · 环境 / Environment: Darwin arm64, CPython 3.12.12
关联 / Related: OB-025/047/056/075/081/082/083

## 中文

本轮没有把模块数量或历史测试数当作已完成客户端的证明。
已确认 OB-082/083 尚为 TODO，任务入口主要接收 inbox；真实 Agent 运行编排、
配置热更新与 Skill/MCP 图仍需按双语设计实施。签名、正式发布和其他原生 OS 未验证。

使用用户指定的测试端点与凭据，经过无回显 stdin 只注入临时测试进程；
原始凭据、token、WebSocket URL、tenant/user/chat ID 和原始响应均未写入本文或 Git。
HTTP 使用 TLS 校验，不自动重定向、不读环境代理，不尝试其他模型端点。

实际执行的单次流式请求：`POST {用户提供的 HTTPS base_url}/chat/completions`，
载荷为 `model=gpt-5.5`、`stream=true`、`stream_options.include_usage=true`、
`max_completion_tokens=256`，用户文本为 `Reply exactly OPENBOT_STREAM_OK.`。
这是合成连通性测试，不包含仓库代码、工具 schema 或真实用户文档。

| 实测项目 | 实际结果 |
|---|---|
| 模型流式响应 | HTTP 200，2 个 SSE 数据帧，收到 `[DONE]`，合成 sentinel 匹配 |
| 模型时序与用量 | 单样本 3512.29 ms；prompt 10、completion 82、total 92 tokens；实际请求 1 次 |
| 飞书 token 交换 | HTTP 200，code=0，197.63 ms |
| 飞书 bot info | HTTP 200，code=0，activate_status=2 |
| WebSocket 端点发现 | HTTP 200，code=0，返回端点；敏感连接 URL 不保留 |
| 飞书消息外发 | 0 |

独立接收验证使用官方 `lark-oapi==1.7.5`（MIT），仅安装到临时目录，
从 PyPI 精确解析全部依赖并用 `--require-hashes` 安装。SDK wheel SHA-256:
`ff70fd5cdf436e26d80bf903fdd7a80cbdbd71981b87ce4c2aa49bb95fc96020`。
未将 SDK 准入为产品 runtime，未改项目 lockfile；启动前检查未发现已知仓库 gateway 进程。
接收器禁用原始 SDK 日志，仅接受指定合成文本，不打印用户消息，不执行工具、不发聊天消息。
WebSocket 已连接；真人消息匹配与完整审批/取消/重连业务门禁尚待验证。

本地验证命令：

```sh
.venv/bin/python -m pytest tests/security/test_git_secret_hygiene.py tests/unit/test_secrets_broker.py tests/unit/test_redaction.py -q
.venv-m1/bin/python scripts/verify.py --phase M1 --output-dir /tmp/openbot-client-verification --run-id secret-ignore-native-20261105
python3 validation/verify_design.py
python3 validation/verify_components.py
python3 validation/verify_database.py
```

结果：定向 25 passed；完整 346 passed / 1 skipped，8 项检查通过。
第一次完整回归受沙箱 loopback bind 禁令阻断，授权环境重跑后通过；没有放宽断言。
秘密文件保护提交 `65f8666757a61beea2e7fcfb96f1b6e72b98224f` 已推送，远端 SHA 一致，
[contracts CI](https://github.com/xiongcp/OpenBot/actions/runs/41975808103) completed/success。

## English

OB-082/083 remain TODO. The daemon currently accepts tasks primarily into the inbox;
the real bounded agent loop, configuration activation and skill/MCP graph still require implementation.
No signed desktop release or additional native platform was qualified.

Test credentials entered a temporary process through non-echoing stdin only.
This evidence stores no raw credentials, access tokens, WebSocket URLs, identities or raw responses.
The HTTPS probe verified TLS, followed no redirects, ignored ambient proxies and used only the supplied endpoint.

One synthetic Chat Completions request used `gpt-5.5`, streaming with usage enabled,
`max_completion_tokens=256`, and `Reply exactly OPENBOT_STREAM_OK.`. It sent no repository content or tool schemas.
The response was HTTP 200 with two SSE data frames, `[DONE]` and a matching sentinel.
Measured latency was 3512.29 ms; reported usage was 10 prompt / 82 completion / 92 total tokens.
Exactly one model request was made; this sample is not a performance benchmark or quality evaluation.

Feishu token exchange, bot info and WebSocket discovery returned HTTP 200/code=0;
token exchange took 197.63 ms and bot activate_status was 2. No chat message was sent.
The receive-only probe used temporary hash-locked `lark-oapi==1.7.5` (MIT), with the wheel digest above.
It did not change the project lockfile or admit the SDK into product runtime.
The WebSocket connected, but human event matching and the complete approval/cancellation/reconnect workflow remain unverified.

The commands above produced 25 targeted passes and 346 full-suite passes / one skip, with all eight verification checks passing.
An initial sandbox-only loopback restriction was resolved by rerunning in the authorized test environment without changing assertions.
The credential-file protection commit was pushed and its remote SHA matched; its contracts CI completed successfully.

Sources: [official SDK release and hash](https://pypi.org/project/lark-oapi/1.7.5/),
[Hermes Feishu setup](https://github.com/nousresearch/hermes-agent/blob/main/website/docs/user-guide/messaging/feishu.md).
Upstream documentation is reference evidence, not proof that this checkout completed a live workflow.
