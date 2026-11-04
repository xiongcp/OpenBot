# OB-092 / OB-025 / OB-026：SDK 副作用合同、云模型适配器与本地 Ollama 适配器 / SDK Fault Contract, Cloud Model Adapter, and Local Ollama Adapter

## 中文说明

真实安装：OpenAI Python 2.26.0 / httpx 0.28.1 及各自传递依赖。精确 wheel / hash / 许可 / 原锁快照在 components/admissions/m1-sdk.json；未启用产品运行能力。

命令：`PYTHONPATH=services/core/src .venv-m1/bin/python -m pytest tests/components/contracts -q`。实际结果见 evidence/implementation/m1-sdk-tests.log。合成回环 HTTP 服务的真实 TCP 请求数与适配器 reservation 计数逐次相等，429/503 均只请求一次；成功 usage 结算，首块后 EOF / 取消保留预留；请求模型不符 / deadline 无效无 HTTP 请求。显式禁 SDK / transport 自动重试、环境代理和 redirect；适配器没有 arbitrary kwargs 或工具 runner 入口。

Python audit 探针在独立解释器安装 hook 后观察 import / 文件 / DNS / socket / subprocess 事件，并以真实 canary 证明 gate 会拒绝网络和子进程。新增合成私有文件反例后，文件白名单从整个工作区缩到源码/包元数据目录和实际解释器/venv；其余工作区文件读取会触发拒绝。SDK 为生成平台头读取 macOS 公共 SystemVersion.plist；只准许该文件只读访问，未放开其他系统文件。探针不覆盖安装 hook 前的解释器启动、原生扩展直接 syscalls、未受管后代和完整 OS 网络隔离，未宣称全进程无网络。

本轮已补连接中断、307 重定向、流内 deadline、服务端工具提案 canary、环境 organization/project 继承和非法 usage（负数/字符串/bool/超限）反例；最新完整 M1 套件包含 19 项回环/探针合同，早期单独日志为加文件 canary 前的 18 项，见 m1-unit-contract-protocol.log。工具 canary 没有产生文件或追加请求，预算未因未知 usage 被清零。真实云端未调用。

当前 budget 为资格用 counter port，未替代 OB-023 的正式持久预算；只实现 text_stream 能力，正式 function-call / Provider 质量、数据出口、凭据和日志门禁仍属 OB-025 等任务。未安装 Ollama / Anthropic / lark / Playwright / MCP / detect-secrets；各自真实资格 NOT_RUN。持久预算映射与后续 SDK 各阶段资格仍待实现，不能由本子集直接宣称全部 Q04 / Q13 完成。

实现（OB-025）：新增 `services/core/src/openbot/providers/openai_compatible.py`（`OpenAICompatibleAdapter`、`ProviderCapabilityProfile`、`PROVIDER_CAPABILITY_MATRIX`、`ALLOWED_OPENAI_REQUEST_FIELDS`、`FORBIDDEN_SDK_HELPERS`、`validate_outbound_sdk_payload`）与 `tests/unit/test_openai_compatible_adapter.py`：
1. SDK API 白名单与能力矩阵：仅允许 `chat.completions.with_streaming_response.create` 与白名单请求字段（`model`、`messages`、`tools`、`tool_choice`、`stream`、`stream_options`、`max_completion_tokens`、`temperature`），硬拒绝 `beta.chat.completions.run_tools`、`responses.create`、`agents.run`、`tool_runner` 以及任何 `extra_body`、`extra_headers`、`web_search_options`、`mcp_servers` 透传；通过 `PROVIDER_CAPABILITY_MATRIX` 区分 `openai_official` 与 `openai_compatible_generic` 的流式 usage 和严格 Schema 差异。
2. 出口策略与逐次尝试预算门禁：每次真实 HTTP 尝试前先经过 `EgressGuard.evaluate`（`surface='MODEL_GATEWAY'`）并按 `f'{request_id}:try_{attempt_idx}'` 单独调用 `budget.reserve`；仅在未收到任何流分片前的 `429`/`503` 且未取消时允许网关唯一有界重试（不叠加 `tenacity` 或 SDK 内建重试），可控服务器请求计数、Gateway attempt 与预算预留三者完全一致。
3. 分片流式工具调用重组与半包/断流保护：跨多个 SSE 帧累积 `tool_calls` 的 `id`、`function.name` 与 `function.arguments` 分片，仅在收到合法 `finish_reason` 与 `[DONE]` 后经 `strict_json` 与本地 `ToolManifest` Schema（`accept_model_call`）校验生成 `ToolCall` 提案；任何批准前 canary 函数调用数为 0；半包/畸形 JSON/缺失 `tool_call_id`/首块后取消均丢弃未完成输出、将当次预留记为 `UNKNOWN`（半包丢弃不等于服务端未计费）且绝不触发重发；取消后新请求数为 0。因缺少真实云端 API Key 凭据做最终真实在线 smoke，且上游依赖 `OB-023`/`OB-024`/`OB-037`/`OB-038`/`OB-039`/`OB-092` 仍为 `IN_PROGRESS`，`OB-025` 记为 `IN_PROGRESS`。

实现（OB-026）：新增 `services/core/src/openbot/providers/ollama.py`（`OllamaLocalProviderAdapter`、`LocalModelEndpointAttestation`、`LocalGenerationResult`）与 `tests/unit/test_ollama_provider.py`：
1. 拒绝仅凭 `127.0.0.1` 判定本地推理：强制同时核验 `local_weights_digest`、`runner_offline_egress_verified=True`、`cloud_relay_enabled=False`、`web_search_plugin_enabled=False` 与 `allow_runtime_model_pull=False`，拦截任何通过 localhost 转发云模型或联网搜索的代理配置。
2. 工具能力门禁与零云回退：当任务要求结构化工具调用而本地模型不支持时明确返回 `CAPABILITY_UNAVAILABLE_NO_TOOL_SUPPORT`；本地推理失败时返回 `LOCAL_PROVIDER_FAILED` 且 `cloud_fallback_attempted=False`，绝不自动回退云端模型。

## English Summary

- **OB-092 (`IN_PROGRESS`)**: Synthetic loopback HTTP fault contract (`tests/components/contracts/test_openai_faults.py` and `test_probe.py`) for pinned `openai==2.26.0` and `httpx==0.28.1` (`max_retries=0`, `trust_env=False`, `follow_redirects=False`), verifying 1:1 request/budget accounting on 429/503/disconnect/307/stream-cut and `sys.addaudithook` import isolation.
- **OB-025 (`IN_PROGRESS`)**: First cloud model adapter (`services/core/src/openbot/providers/openai_compatible.py` and `tests/unit/test_openai_compatible_adapter.py`, 3 passed):
  1. Enforces `ALLOWED_OPENAI_REQUEST_FIELDS` and blocks `FORBIDDEN_SDK_HELPERS` (`run_tools`, `tool_runner`, `extra_body`, `extra_headers`, `web_search_options`, `mcp_servers`); documents `openai_official` vs `openai_compatible_generic` in `PROVIDER_CAPABILITY_MATRIX`.
  2. Gates every HTTP attempt on `EgressGuard` and per-attempt `budget.reserve(f'{request_id}:try_{attempt}')` with single-owner bounded pre-stream retry (zero `tenacity` or SDK retry stacking); server HTTP count equals gateway attempts and budget reservations.
  3. Accumulates fragmented `tool_calls` SSE deltas until `[DONE]`, validating complete JSON and `ToolManifest` schema via `accept_model_call` to return `ToolCall` proposals (0 canary executions before approval); half-packets, missing `tool_call_id`, or post-chunk cancellations discard output, hold cost as `UNKNOWN`, and never retry. Real cloud smoke remains unverified without live credentials.
- **OB-026 (`IN_PROGRESS`)**: Local Ollama provider adapter (`services/core/src/openbot/providers/ollama.py` and `tests/unit/test_ollama_provider.py`, 1 passed):
  1. Verifies `local_weights_digest`, `runner_offline_egress_verified=True`, `cloud_relay_enabled=False`, `web_search_plugin_enabled=False`, and `allow_runtime_model_pull=False` instead of trusting `127.0.0.1` alone.
  2. Rejects tool-requiring tasks on text-only models with `CAPABILITY_UNAVAILABLE_NO_TOOL_SUPPORT` and never falls back to cloud providers on local failure (`cloud_fallback_attempted=False`).
