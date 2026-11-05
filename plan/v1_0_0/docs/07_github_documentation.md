# GitHub 描述、Markdown 与社区入口

## 先修正访客第一屏

main 仍同时保留一些过时的“设计交接包”和实施进度表述。活动分支已解释真实 Agent 编排与桌面客户端尚未完成，但尚未合入 main。建议把根 README 改为产品入口，把历史工程包、96 项任务说明和给编码助手的指令放到开发文档入口。[R01、R02]

第一屏回答：它是什么、现在能用到哪一步、适合谁、如何尝试、下一步去哪里。最多三四个与事实相符的 badge；不在没有 LICENSE 或发行物时放相应绿色徽章。

## 可以直接采用的 About 草案

当前开发阶段英文：

> Local-first AI task assistant for macOS, in development. Explicit approvals, bounded tools, and traceable execution.

对应中文：

> 面向 macOS 优先开发的本地 AI 任务助手：明确审批、受限工具和可追踪的执行过程。

v1.0.0 验收后可改为：

> A local-first AI task assistant for macOS with explicit approvals, bounded tools, and verifiable results.

建议 Topics：`ai-agent`、`local-first`、`macos`、`python`、`human-in-the-loop`、`workflow`；`tauri`、`mcp`、`feishu` 在相应公开实现/支持范围与 README 一致时加入。Topics 是发现入口，不是资格证明。homepage 仅填已经发布、确实归属本项目的官网，不先填未上线候选域名。

## README 的推荐顺序

| 顺序 | 内容 | 具体要求 |
|---|---|---|
| 1 | 名称、一句话、当前阶段、语言切换 | 区分开发版与正式版；产品版本不沿用设计1.2 |
| 2 | 实际界面/短演示 | 真实运行生成；有文字替代；规划线框明确标示 |
| 3 | 三个用户场景 | 文件任务、可审查修改、飞书/执行追踪；按已验证状态标注 |
| 4 | Quick start | 开发者源码路径和正式用户安装路径分开；命令来自实际 parser |
| 5 | 当前能力/支持平台 | 实现、资格、限制、证据、候选版本可追踪 |
| 6 | 权限与恢复 | 解释审批、停止、UNKNOWN和网络模式，避免绝对保证 |
| 7 | 文档与贡献 | 用户手册、架构、路线图、issues、安全报告 |
| 8 | License / Notice | 与根 LICENSE、SBOM、第三方文件一致 |

中文与英文保留同样的能力状态、安装命令、已知限制和版本。正文不复制全部任务卡；链接到有维护责任的文档。

## 文档信息结构

建议在现有 `docs/` 增加面向用户的入口，而不是一次性移动所有旧文件：getting-started、install、first-task、models、network-modes、workspaces、approvals、stop-and-recover、feishu、browser、mcp、backup-and-upgrade、troubleshooting、diagnostics、supported-platforms。开发入口链接 architecture、contracts、testing、releasing、ADR 和原任务图。

先加 landing/index 和重定向/索引，再分批迁移历史设计；保持旧链接可达。旧设计顶部标“设计基线 / 历史方案 / 实施状态另见能力表”，不删除原始证据。AGENTS/CLAUDE 更新入口和当前构建命令，同时保留既有授权、UNKNOWN、隔离等不变量。

## 许可证冲突必须解决

已读 ADR 记录项目自身许可尚未选定，OB-004 的 DONE 范围主要是第三方依赖；另一方面 pilot SBOM 已将 OpenBot 写为 Apache-2.0，根 LICENSE 不存在。先核对是否已有后续有效许可决定，再补齐对应正文并修正元数据；不能仅凭 SBOM 字段代替作者授权，也不能在未核对时重新宣称用户从未选过。[R18]

公共 GitHub 仓库不自动提供完整开源许可授权。GitHub 官方建议项目以明确许可证说明使用、修改和分发权利。[W10] 本包只提供许可决策待办，不替作者签署或发布许可证。

## 社区和维护文件

新增 CONTRIBUTING、SUPPORT、CHANGELOG、CODE_OF_CONDUCT（指定真实维护入口）、issue form、PR template、release notes 模板；已有 SECURITY 需核对支持版本、报告入口、披露流程与当前实现范围。CODEOWNERS 只填真实愿意承担审阅的人，不虚构邮箱或维护团队。

Bug form 收集版本/SHA、OS/架构、安装方式、最小复现、预期/实际、脱敏诊断引用；明确不要求 API key、cookie、完整数据库或私密消息。PR 模板收集问题、行为变化、验证、涉及的契约/迁移/风险和原任务ID，不强制每个文案变更添加无意义测试。

## 维护一份能力事实源

建议新增机器可读能力清单，字段含 capability_id、implementation_ref、qualification_status、supported_platforms、limitations、evidence_refs、release_version、last_verified_at。README 支持表、官网功能列表和 release notes 从它生成或校验。

实现状态与证据状态分开：IMPLEMENTED 不自动代表 QUALIFIED；SOURCE_ONLY、SYNTHETIC、NATIVE、LIVE_EXTERNAL 是证据类型，不是同一进度条。禁止因 README 更新把任务状态批量改 DONE。

## 社交素材与真实演示

准备仓库 social preview、应用 icon 与 wordmark，使用同一视觉规范。图中文字保持少量、清楚，引用官方平台标识时遵守其使用规范。不要用自动生成界面图当作实际产品截图。

录制 60-90 秒演示：选择工作区→提交任务→审批 Diff→运行事实→产物→取消或恢复一例。视频附字幕、实际版本、场景边界和文档链接；截图先清理账号名、路径、token、聊天与租户信息。没有真实客户端前只发布标明“设计”的线框。
