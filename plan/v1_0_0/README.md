# OpenBot：MVP 收尾与 v1.0.0 交付方案

日期：2026-11-05。此包用于审查、设计和开发交接，未修改或发布 OpenBot。

审查基线：已同步至最新 `main@2028229123a6fc1d44ec54a1c905ef4c9f09fa05`（PR #2 已将 `codex/agent-client-observability@12074191a9c609a310cc5579eb548021b78305c1` 合并入 `main`，CI run `42005019676` 三平台各 `399 passed, 2 skipped`）。新合入的 `agent_runtime.py`、`client_routes.py`、`apps/desktop` 初版、只读 MCP 容器切片与飞书 `live_gateway.py`（及 `pyproject.toml` 中的 `lark-oapi==1.7.5` 与包路径配置）均已纳入本包基线。执行前请确保本地仓库 `git pull origin main` 同步至最新 HEAD。

## 挂载位置与防冲突约定（重要）

请将本执行包解压至仓库内的独立子目录（推荐 `plan/v1_0_0/`）或仓库外平级目录。**切勿将本包直接解压覆盖到仓库根目录**，以免覆盖根目录原有的 `tasks/backlog.json`（`OB-001..096`）、`tasks/TASKS.md`、`README.md` 或向根 `diagrams/` 混入新设计图（仓库 `validation/verify_design.py` 与 `verify_components.py` 硬编码校验根 `tasks/backlog.json` 为 96 项 `OB-*` 且 `diagrams/` 为 7 张图）。

## 使用顺序

1. 阅读 `docs/01_current_state.md`：区分已实现、已验证、仍需接线和发布缺口。
2. 阅读 `docs/02_scope_and_roadmap.md`：确定 macOS 首发的候选范围，不改写原三平台 M3 的定义。
3. 阅读架构、客户端、测试、发布、GitHub 与官网设计（`docs/03` 至 `docs/09`）。
4. 以本包 `tasks/backlog.json` 和 `tasks/TASKS.md` 选择依赖已满足的任务，保留原 `OB-001` 至 `OB-096` 全部 96 项映射。
5. 将 `prompts/CODEX_V1_EXECUTION.md` 交给本机 Codex 或 Claude Code。每个独立修复测试后单独提交、立即推送并核对结果。

## 文件说明

| 目录 | 内容 |
|---|---|
| docs/ | 当前状态、范围、架构、客户端、测试、发布、文档、官网与排程 |
| tasks/ | 60 项交付任务（100% 映射原 OB-001..096，含测试与门禁绑定，无 P0→P1 优先级倒挂） |
| github/ | 可审阅的中英 README、About/Topics、贡献与问题模板草稿 |
| website/ | `apps/website` 网站内容、页面规格、设计令牌与标为规划的线框图 |
| testing/ | 原 100 项用例与 16 项新增验收设计（全部双向绑定 `V1-*` 与 `OB-*`）及 8 个门禁映射 |
| diagrams/ | 架构与发布关系图；均为设计，不是现有运行拓扑的截图 |
| prompts/ | 连续实施提示词与逐问题 commit/push 规则 |
| evidence/ | 本次固定快照、源码/CI来源与包自身的校验结果 |
| tools/ | 支持 `--mode {plan,execution,rc}` 的计划包与执行态校验脚本 |

所有新任务初始状态为 PLANNED；测试结果为 NOT_RUN。已存在的代码不会因新任务而被要求从零重写。包内校验只验证交接材料的结构与引用，不代表 OpenBot 产品验收通过。

## 计划包自检

在解压目录运行 `python3 tools/validate_plan.py`（执行过程中更新状态后可运行 `python3 tools/validate_plan.py --mode execution`）。这只校验任务、依赖、100% OB 映射、优先级单调性、来源、测试映射与网站示例数据；不会连接产品、执行测试、提交代码或推送。
