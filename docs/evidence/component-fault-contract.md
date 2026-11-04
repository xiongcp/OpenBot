# OB-092：SDK 副作用合同（当前子集）

真实安装：OpenAI Python 2.26.0 / httpx 0.28.1 及各自传递依赖。精确 wheel / hash / 许可 / 原锁快照在 components/admissions/m1-sdk.json；未启用产品运行能力。

命令：`PYTHONPATH=services/core/src .venv-m1/bin/python -m pytest tests/components/contracts -q`。实际结果见 evidence/implementation/m1-sdk-tests.log。合成回环 HTTP 服务的真实 TCP 请求数与适配器 reservation 计数逐次相等，429/503 均只请求一次；成功 usage 结算，首块后 EOF / 取消保留预留；请求模型不符 / deadline 无效无 HTTP 请求。显式禁 SDK / transport 自动重试、环境代理和 redirect；适配器没有 arbitrary kwargs 或工具 runner 入口。

Python audit 探针在独立解释器安装 hook 后观察 import / 文件 / DNS / socket / subprocess 事件，并以真实 canary 证明 gate 会拒绝网络和子进程。新增合成私有文件反例后，文件白名单从整个工作区缩到源码/包元数据目录和实际解释器/venv；其余工作区文件读取会触发拒绝。SDK 为生成平台头读取 macOS 公共 SystemVersion.plist；只准许该文件只读访问，未放开其他系统文件。探针不覆盖安装 hook 前的解释器启动、原生扩展直接 syscalls、未受管后代和完整 OS 网络隔离，未宣称全进程无网络。

本轮已补连接中断、307 重定向、流内 deadline、服务端工具提案 canary、环境 organization/project 继承和非法 usage（负数/字符串/bool/超限）反例；最新完整 M1 套件包含 19 项回环/探针合同，早期单独日志为加文件 canary 前的 18 项，见 m1-unit-contract-protocol.log。工具 canary 没有产生文件或追加请求，预算未因未知 usage 被清零。真实云端未调用。

当前 budget 为资格用 counter port，未替代 OB-023 的正式持久预算；只实现 text_stream 能力，正式 function-call / Provider 质量、数据出口、凭据和日志门禁仍属 OB-025 等任务。未安装 Ollama / Anthropic / lark / Playwright / MCP / detect-secrets；各自真实资格 NOT_RUN。持久预算映射与后续 SDK 各阶段资格仍待实现，不能由本子集直接宣称全部 Q04 / Q13 完成。
