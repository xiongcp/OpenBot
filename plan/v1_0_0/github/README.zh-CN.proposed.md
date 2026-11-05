# OpenBot

**面向 macOS 优先开发的本地 AI 任务助手：明确审批、受限工具和可追踪的执行过程。**

[English](README.en.md) · [入门](docs/getting-started.md) · [故障排查](docs/troubleshooting.md) · [安全说明](SECURITY.md) · [开发任务](tasks/backlog.json)

> **当前阶段：开发中。** 应用版本为 `0.1.0.dev0`。已有持久任务、审批、认证本地 API、CLI 和多种适配/验证模块；完整 Agent 运行闭环、桌面客户端与正式分发仍在建设。尚无可供普通用户安装的稳定版 Release。

## OpenBot 想解决什么

让一个 AI 任务从“提出建议”走到“得到可核对的结果”：

- 在明确授权的工作区读取资料，生成带来源的结果。
- 修改文件前展示具体提案，在批准后复验目标，保护用户随后做出的修改。
- 从本地入口或飞书跟踪任务、处理审批和停止后续动作。
- 动作结果不确定时保留核对状态，不把超时当作“什么也没发生”。

这些是产品目标。下表说明当前实现与验收范围；不把设计目标写成全部已交付能力。

## 当前状态

| 能力 | 当前进展 | 边界 |
|---|---|---|
| 持久化与审批 | SQLite、Writer、Task/Operation/Approval/Attempt 服务与测试已存在 | 仍需真实任务运行链的整体验收 |
| 本地入口 | 认证 API、真实 CLI/daemon 入口已存在 | 入队成功不等于 Agent 已完成任务 |
| Provider/Browser/MCP/飞书 | 适配器、协议探针和限定测试已存在 | 真实场景、隔离、取消与恢复分项验收 |
| 配置与运行事实 | 活动分支已有持久配置、run 快照和脱敏 trace 基础 | 尚未构成完整热更新和桌面 UI |
| macOS | 有 ARM64 开发/CI 与部分本机证据 | 正式安装、签名、升级资格尚待完成 |
| Windows/Linux | 有不同范围的工程 CI | 不代表原生产品完整支持 |

状态核对点：2026-11-05，`main@20282291`（已合入 PR #2 [20282291](https://github.com/xiongcp/OpenBot/commit/2028229123a6fc1d44ec54a1c905ef4c9f09fa05)，包含有界 `agent_runtime.py`、`client_routes.py`、`apps/desktop` 初版、只读 MCP 容器切片与飞书 `live_gateway.py`；仍需完成安全恢复加固、签名安装包与真机生产门禁验收）。完整限制见 [证据目录](docs/evidence)。工程设计基线 `v1.2` 与应用版本不同。

## 从源码验证

适合开发者；需要项目规定的 Python 3.12 和 uv。先查看锁文件与本机架构，不更改系统 Python。

```sh
git clone https://github.com/xiongcp/OpenBot.git
cd OpenBot
uv sync --locked
.venv/bin/python scripts/verify.py
.venv/bin/openbot --help
```

可选 OpenAI SDK 资格环境单独安装：

```sh
UV_PROJECT_ENVIRONMENT=.venv-m1 uv sync --locked --group provider-openai
.venv-m1/bin/python scripts/verify.py --phase M1
```

默认工程测试、SDK loopback 测试、原生隔离资格和真实外部服务分别记录。缺少模型凭据、测试租户或后端时，对应能力保持未验证，不用模拟通过替代。真实命令、环境限制和修复步骤见 [入门](docs/getting-started.md) 与 [后端能力说明](docs/evidence/backend-capabilities.md)。

## 权限和结果如何处理

模型提出动作建议，控制面决定是否允许。批准只让对应 Operation 就绪；真正执行前再次检查身份、取消、策略、时限和目标资源。工具与外部文本不能修改这些权限规则。

关闭未来桌面窗口与停止任务是两个动作；任务生命周期由 daemon 管理。执行结果未知时保持 `UNKNOWN / RECONCILING`，需要证据核对。停止请求用于阻止后续派发，不承诺撤销过去已经发生的效果。

`CONNECTED`、`LOCAL_MODEL` 与 `OFFLINE` 有不同约束。本地地址或本地模型名称不能单独证明没有云请求；只对实际验证的受管范围声明网络能力。不要把 API key、cookie 或真实业务数据放进 Issue、模型上下文或日志。

## 路线图

1. 接通真实有界 Agent loop，复用既有预算、审批和结果验证。
2. 完成取消、恢复、秘密与 Browser/MCP/飞书的真实门禁。
3. 交付中英桌面客户端、配置生效与事实执行图。
4. 完成可安装包、签名公证、升级恢复与 macOS beta。
5. 以同一候选的代码和制品证据发布明确范围的 v1.0.0。

原任务与依赖保留在 [tasks/backlog.json](tasks/backlog.json)。Windows/Linux、Intel、原生桌面控制与多设备等按独立资格和范围推进。

## 开发与贡献

从 [AGENTS.md](AGENTS.md)、[CLAUDE.md](CLAUDE.md) 和 [架构](docs/02_architecture.md) 了解边界。一次处理一个可验收的切片，保护用户已有修改；行为修复应带相关回归，声明已完成需提供实际证据。

问题反馈请包含版本/SHA、OS/架构、安装方式、最小复现、预期与实际表现。只附脱敏摘要，不上传密钥、完整数据库或私人消息。安全问题请勿公开披露细节。当前 [SECURITY.md](SECURITY.md) 尚需补充经维护者核实的私密报告入口，入口启用并验证后再提交敏感材料。

## 许可与第三方组件

项目自身源码许可的公开记录正在核对；根 LICENSE 补齐前，不以第三方 NOTICE 或 pilot SBOM 代替项目授权。第三方组件及其许可独立记录在 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与组件目录中。

---

此文件是基于上述快照的 README 提案。采纳前更新状态和链接；正式版发布后再加入真实截图、安装包下载与最终许可证声明。
