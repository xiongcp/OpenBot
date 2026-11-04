# OpenBot 工程设计与开发交接包

[中文](README.md) | [English](README.en.md)

版本 1.2 · 2026年11月4日 · 根据《OpenBot 开源组件复用评估.pdf》修订

实施进度：已加入 M0 最小 Python 包/标准合同/协议 PoC，以及 M1 SQLite writer/inbox、内部不可变提案/审批决定、SDK 故障合同与 macOS Docker 原语验证；真实门禁与任务状态见 tasks/backlog.json 及 docs/evidence。当前尚未通过 OB-029，也未形成 M3 产品。原始设计 catalog 保持 NOT_RUN；本机开发环境的精确锁与限定证据另存 components/admissions，不能据此启用产品能力。

本地验证：`uv sync --locked`，然后 `.venv/bin/python scripts/verify.py`。本机若继承 macOS 隐藏文件标记导致 editable `.pth` 被 Python 忽略，可用 `PYTHONPATH=services/core/src .venv/bin/python -m openbot version`；验证脚本显式设置源码路径，不修改系统 Python。

本轮交接：[中英双语检查点与分工](docs/handoff/2026-11-04-checkpoint.md)。交给 Claude Code 时使用 [OB-093 专项提示词](prompts/07_claude_code_ob093.md)；合并该工作后使用 [Integrator 续做提示词](prompts/08_integrator_resume.md)。每份提示词提供中文、英文两个等价版本，选择一个版本执行即可。

本包在v1.1基础上明确开源组件的采用范围、适配职责和资格验证。包含96项任务（保留OB-001至088，新增089至096）、52个组件/组件组决策、24项本轮复用修订、22项ADR与7张架构图。沿用23张核心SQL表、14个本地API及既有授权与恢复协议。

这是设计与实施交接材料，所有应用任务初始TODO，组件真实资格验证初始NOT_RUN。SQL、合同和任务图的离线检查结果不代表真实模型、飞书、沙箱或三平台安装已经通过。

## 本轮优先阅读

1. docs/14_revision_v1_2.md：本轮采纳、纠偏、八项新增任务和实施顺序。
2. docs/00_scope.md、docs/02_architecture.md：产品边界与控制面结构。
3. docs/12_component_reuse.md、docs/13_component_qualification.md：组件、端口、离线资产和验证门禁。
4. docs/03至09：状态、审批、存储、工具、飞书、平台和运行验证。
5. docs/10_project_plan.md、tasks/backlog.json：计划与权威任务图。
6. AGENTS.md、CLAUDE.md、prompts/05_autonomous_project.md：交给编码助手持续实施。

docs/01_gap_review.md保留v1.1对原始材料的32项遗漏审查；新增材料的修订单独记录，不重编号旧任务或旧问题。

## 文件用途

| 路径 | 用途 |
|---|---|
| docs/ | 15份产品、架构、复用和项目设计文档 |
| tasks/backlog.json | 96项任务的稳定ID、依赖、步骤、复用信息与验收 |
| tasks/TASKS.md | 完整可读任务卡，和JSON同步 |
| tasks/revision_delta.json | 原88项逐项变更与8项新增任务的机器记录 |
| tasks/REVISION_v1_2.md | 人可读任务变更说明 |
| components/catalog.json | 52个组件/组件组的设计决策；不是安装清单或运行时授权 |
| components/CATALOG.md | 组件目录的可读视图 |
| components/qualification-plan.json | Q01至Q16组件验证目录 |
| components/dependency-lock.template.json | 精确依赖/资产锁定的填写结构，未伪造版本或hash |
| components/source-reuse-ledger.json | 源码摘取台账；当前为空，没有复制候选上游应用源码 |
| contracts/ | 本地API、JSON Schema、状态机和格式示例 |
| db/ | 23表基线与参考事务边界说明 |
| templates/ | 组件资格记录、源码复用记录与上游补丁模板 |
| evidence/reuse_sources.json | 本轮24组官方来源和证据范围 |
| diagrams/ | 7组PNG、SVG、Mermaid源文件 |
| validation/ | 设计、组件目录与数据库参考事务验证 |
| prompts/ | 启动、单任务、评审、交接、持续实施与组件准入提示 |
| reports/ | 更新后的架构与项目设计PDF、实施任务手册PDF |

## 交给Codex或Claude Code

把本目录内容放入目标仓库根目录；已有仓库先只读盘点，不覆盖既有AGENTS、CLAUDE或迁移。使用prompts/05_autonomous_project.md持续推进到M3；需要较小首轮时使用prompts/01_bootstrap.md。

首轮完成OB-001至005和依赖满足的OB-089，再推进合同、OB-090与OB-091。M0协议PoC采用mock效果，OB-029仍是M1真实本地API和隔离路径的集成切片。按depends_on选择任务，不能简单按数字递增。

component_refs是任务相关组件，不等于允许安装所有列出的候选。只在当前任务引入必要依赖；默认组件也要锁定、核验许可和实测。官方SDK的自动重试/工具helper、parser首用下载、Git hooks与容器独立生命周期都需按任务验收。

原始设计包不自带应用实现或有效凭据；当前仓库已加入的代码、精确锁和限定验证证据，以 tasks/backlog.json、components/admissions 与 docs/evidence 为准，尚未构成完整产品闭环。遇到缺失租户/机器/凭据，完成独立工作并标出最小阻塞条件，继续其他就绪任务；不放宽权限以消除阻塞。

## 复查本设计包

~~~sh
python3 validation/verify_design.py
python3 validation/verify_components.py
python3 validation/verify_database.py
~~~

实际通过项目和限制见validation/VALIDATION.md。设计检查使用标准库和有限Schema检查，不是完整生产JSON Schema验证器；OB-090负责引入维护中的完整标准实现。contracts/examples中的hash仍为合成格式样例，不是已计算的授权摘要。

## 版本与责任

设计基线为1.2；原通信合同与DB schema没有因本轮文档更新而自动升级。配置样例新增复用相关字段并显式标为设计样例。实际产品版本、协议、DB、组件资产与平台能力分别记录，禁止全局替换数字代替迁移设计。

模型提出建议；代码决定权限；组件通过端口提供能力；未知结果先核对；所有完成声明都需实际证据。
