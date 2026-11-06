# 来源、包内容与验证边界

## 本次实际完成的工作

读取了xiongcp/OpenBot固定SHA的选定生产代码、测试入口、任务状态与CI配置，并读取同SHA的contracts CI运行41949551726及三个失败job日志。形成16项初始待分诊线索、100项待执行用例、七份证据模板和逐问题修复交接规程。没有在用户Mac运行产品，也没有修改、提交、推送任何OpenBot仓库代码。

本执行包保留v1.2工程设计及现有实现作为输入；它不替代实际仓库中的AGENTS.md、锁文件和当前代码。源码观察不是漏洞实测；相应文件之外可能存在其他已实现路径，必须通过真实入口追踪和复现后再定根因。任务状态可能更新滞后，不能凭IN_PROGRESS就认定代码不存在。

## 使用包内文件

| 路径 | 用途 |
|---|---|
| docs/00–04 | 范围、真实命令、16项线索、E0–E7执行顺序、质量与诊断 |
| docs/05–06 | 核心故障注入、macOS与真实集成详细步骤及官方依据 |
| docs/07–09 | 逐问题commit/push、G00–G15发布门禁、完整Codex执行提示词 |
| cases/TEST_CASES.md与test_cases.json | 100项同源操作卡，均NOT_RUN |
| cases/initial_findings.json | 16项初始OPEN记录，本地复现NOT_RUN、push未尝试 |
| commands/command_map.json | 观察到的真实命令与条件/负例标记，不能无条件批量执行 |
| templates/workflow | 仓库、命令、问题、测试、push、CI、候选共七份空模板 |
| evidence/repository_review.json | 固定SHA的只读仓库/CI观察，不能作为本机通过记录 |
| evidence/package_validation.json | 交付包结构验证结果，只验证本包完整性 |
| tools/validate_package.py | 仅校验本包的JSON、ID、状态和链接，不运行OpenBot或Git |
| reports | 本执行手册PDF；详细100项操作卡仍以cases文件为准 |

E0–E7是实施顺序；G00–G15是最终发布条件。两者编号不一一对应，需由实际候选记录把每个门禁关联到用例与证据。

## 主文档引用索引

下列T编号供docs/01、02引用。其他章节使用本章内的P/G/S/R局部编号，均附直接一手来源链接。动态官方资料按2026-11-05读取；执行时须核对锁定版本，不能把main文档的新合同强加到旧版本而不做适配。

| 编号 | 一手来源 | 支持的判断 |
|---|---|---|
| T01 | [GitHub工作流目录规则](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows) | .github/workflows下不支持子目录工作流发现 |
| T02 | [runner-images退役公告](https://github.com/actions/runner-images/issues/13518)、[当前runner标签](https://github.com/actions/runner-images) | macOS14于2026-11-02退出GitHub Actions；实际标签及架构须再验证 |
| T03 | [pytest导入机制](https://docs.pytest.org/en/stable/explanation/pythonpath.html) | python -m pytest会额外将当前目录加入sys.path；并非导入问题的普遍免检修复 |
| T04 | [uv的Python版本管理](https://docs.astral.sh/uv/concepts/python-versions/) | 可下载Python构建受uv版本与目标平台影响，安装方案需实际验证 |

## 此次验证与未验证

已经验证的是本包的用例字段、ID/任务引用、初始状态、JSON可读性、相对文档链接及PDF版面。逐页渲染后检查边界和缺失字形，并抽查关键页面的可读性；具体结果保存在package_validation.json。所有这些检查只涉及交付文档。

尚未执行的是用户Mac上的任一产品用例、真实租户/模型/OS故障场景、任何修复commit与push。没有生成虚构的通过数、测量时长、修复SHA、远端回执或新CI结果。当前仓库审查的历史CI失败保留原事实，新的候选结果须由实际执行产生。
