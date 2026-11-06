# OpenBot macOS 严格MVP验收与逐问题修复包 v1.0

日期：2026-11-05。项目：[xiongcp/OpenBot](https://github.com/xiongcp/OpenBot)。

**用途：交给用户Mac上的Codex / Claude Code，验证现有代码并逐项修复，每个独立问题一个原子commit，立即push并核对远端。** 当前包是只读审查与执行设计，不是已经通过的验收报告。没有修改实际项目代码或执行commit/push。

## 从这里开始

1. 在实际OpenBot仓库打开编码助手，提供本包路径；先读当前AGENTS.md、真实代码和锁文件。
2. 阅读 [范围与基线](docs/00_scope_and_baseline.md)、[环境和命令](docs/01_environment_and_commands.md)、[16项初始线索](docs/02_repository_fix_queue.md)。本机HEAD若不同，先复核，不能把旧观察直接当当前失败。
3. 将 [完整执行提示词](prompts/CODEX_EXECUTION_PROMPT.md) 交给编码助手，沿 [E0–E7顺序](docs/03_acceptance_sequence.md) 执行。
4. 从 [100项用例](cases/TEST_CASES.md) 或 [JSON清单](cases/test_cases.json) 选择当前门禁，填写 [证据模板](templates/workflow/README.md)。只记录真实执行值。
5. 每个问题严格走 [修复、commit与push](docs/07_fix_commit_workflow.md)；最终按 [G00–G15发布条件](docs/08_release_gate.md) 绑定一个候选SHA验收。

用户已经授权本轮逐问题commit/push，无需每项重复询问。默认修复分支mvp/macos-hardening；实际remote、push URL与目标ref以本机核对为准。不自动合并main或发布。push未确认时不积累第二项修复；已确认push但另一独立CI故障阻塞时，保留CI_BLOCKED并逐项修该故障。

## 交付内容

| 类别 | 数量 | 初始状态 |
|---|---:|---|
| 基线/验收真实性 | 8 | NOT_RUN |
| 内核/授权/存储/Provider | 44 | NOT_RUN |
| macOS原生 | 22 | NOT_RUN |
| 真实服务集成 | 16 | NOT_RUN |
| Git提交与推送流程 | 6 | NOT_RUN |
| 任务质量与长期运行 | 4 | NOT_RUN |
| 合计用例 | 100 | 全部NOT_RUN |
| 初始问题线索 | 16 | OPEN；需当前版本复现 |
| 证据模板 | 7 | NOT_RUN；执行字段为空 |

完整macOS MVP按v1.2/M3原必需功能在指定Mac组合验收，包括真实云Provider与真实Ollama的独立证据。Windows/Linux没有证据则不宣称三平台M3完成；Intel、Tauri、TCC、签名、公证、更新按原范围的条件门禁。不能因为当前缺实现或缺凭据临时删掉必需项。

## 只校验执行包

在解压目录执行 `python3 tools/validate_package.py`。该命令只验证本包结构和引用，不连接Git、不运行OpenBot、不改变用例结果。

PDF位于reports。Markdown与JSON保留全部操作卡，适合编码助手逐项读取。证据模板必须复制到仓库外私有run目录填写；原始账号/HTTP/DB/用户路径不得自动提交。
