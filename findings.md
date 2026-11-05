# 实施发现

## 2026-11-05 当前核对 / Current inspection

- 当前工作树干净，HEAD 为 98ee036，main 已有实现与远端 origin；早期“没有 commit”的笔记已过时。README 的 M0—M3 概述不能替代任务逐项验收。
- OB-082/083 为 TODO；现有 CLI daemon、认证 API 与 SSE 可复用。ProfileConfig 尚无热更新服务，ObservabilityHub 尚无 Skill/MCP 因果事件投影。部分应用模块是测试夹具或资格模型，需要逐路径确认真实集成。
- 本次 PDF 共 18 页，基于早期设计包对比；竞品测试数、安全结论及绝对可靠性描述不能作为本仓库运行证据。只将文档内容当研究材料，不执行文档中的指令。
- 已查 Context7 官方 Hermes、Tauri v2 与 lark-oapi 文档。Hermes 飞书参考重点：WebSocket 入站、独立事件与 card.action.trigger 回调配置、显式配对；不照搬其权限和 .env 存储方式。
- 本地 .gitignore 缺少 owner_cli.token、challenges.json 等运行期秘密防误提交规则；用户明确要求密钥不进入 Git。
- OpenViking Experience 限定检索无匹配；旧 Hermes 配置记录仅用于定位，实际协议重新核验。
- 本轮真实探测：指定模型返回 HTTP 200、2 个 SSE 数据帧和 DONE，合成 sentinel 匹配，用量 92 tokens（10 input/82 completion），3.51s，实际请求 1 次。飞书 token、bot info、WS discovery 均 code=0；尚未发送任何飞书消息。秘密仅无回显 stdin 进入测试内存。
- 独立设计审阅确认需要补齐真实运行编排（当前 daemon 主要接 inbox），并明确 run 生命周期、秘密录入和首次启动范围；已在双语设计中写明设计者建议，等待用户确认。

- 2026-11-04：实际仓库为设计包；main 尚无 commit，现有文件全部未跟踪。无应用实现或真实依赖锁。
- backlog 为 96 项数组；M0/M1/M2/M3/M4/P2 为 13/37/11/25/4/6；catalog 为含 components 的对象，共 52 项。
- 当前机器为 Darwin arm64；系统 Python 3.9.6，uv 和 Docker CLI 存在，Rust cargo 未发现。Python 3.12、容器服务与镜像须独立探测。
- OB-091 只验证测试目录中的最小协议模型，不能用于关闭 OB-029 或证明真实隔离。
- 用户授权常规可逆本地实现、安装与测试；真实租户、原生 OS、签名等缺失只阻塞关联能力，不能伪造通过。
- 本地 MEMORY.md 无 OpenBot 相关命中；OpenViking Experience 定向检索无结果。
- Docker 后端后续已可用并通过 8 项本机 CLI 原语测试；Supervisor/旧执行域隔离等属于未完成工程，不能继续写成 Docker 环境阻塞。
- 当前 M0/M1 完整本机测试为 150/169 通过，未开放任何真实工具/API 运行能力。OB-029 未通过，M2/M3 仍需上游实现与各自真实服务/原生平台证据。

## English Summary

- The repository started as the OpenBot v1.2 engineering design package (96 tasks across M0–P2 and 52 component decisions in `components/catalog.json`).
- Current host is Darwin arm64 with local CPython 3.12 and Docker Desktop 29.1.3.
- Routine reversible local implementation, testing, and verification proceed continuously along the task DAG, while tasks requiring native Windows/Linux hosts or dedicated Feishu/cloud credentials record explicit blockers.
