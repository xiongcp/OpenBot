# 验收目标、仓库基线与证据规则

版本1.0；日期2026年11月5日；用户时区Asia/Shanghai。

## 本轮要得到的结果

在用户的Mac上，从真实安装入口启动OpenBot，使用独立测试profile和合成工作区，验证CLI、持久化、审批、受限执行、恢复、飞书、Browser、MCP与两个Provider的实际闭环。每个问题都应留下复现、修复、回归、独立commit、push确认及对应CI记录。最终结论只覆盖实际测试的操作系统、架构、资产与配置组合。

本手册与机器用例清单用于交给Mac本机的Codex执行。本次已完成GitHub源码与既有CI记录的只读审查，没有连接用户的Mac，没有运行该Mac上的测试，也没有修改或推送产品代码。下述源码发现不是本次新执行的运行测试。

## 已核对的实际仓库

| 项目 | 只读核对结果 |
|---|---|
| 仓库 | https://github.com/xiongcp/OpenBot |
| 分支与快照 | main；a223d36a659b7ecf32fca2b4890fc187d3e96e48 |
| 快照提交时间 | 2026-11-05 09:35:26，Asia/Shanghai |
| Python合同 | pyproject要求 >=3.12,<3.13；.python-version为3.12.12 |
| 本地自检入口 | uv sync --locked；.venv/bin/python scripts/verify.py |
| 可选SDK依赖 | provider-openai依赖组；默认只启用dev-contracts |
| 当前任务字段 | 96项：DONE 4、VERIFIED 12、IN_PROGRESS 67、BLOCKED 3、TODO 10 |
| 同SHA的CI | contracts，run 41949551726，结论failure |

任务字段可能尚未同步，不能仅凭字段断定代码不存在。验收应以真实仓库、独立执行路径和可复查证据为准。用户Mac上的未推送改动、新分支和后续提交不在此快照内；执行前必须重新记录实际HEAD和工作区状态。

参考来源：仓库[README](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/README.md)、[pyproject](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/pyproject.toml)、[任务状态](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/tasks/backlog.json)、[CI运行](https://github.com/xiongcp/OpenBot/actions/runs/41949551726)。

## 当前最需要先解决的事实

1. 真实CLI的main仅暴露version和health；task/approval/reconcile存在于接受注入session的内部函数中。先做真实console脚本测试和入口装配，不能用函数调用代替产品入口通过。
2. 部分macOS验收使用内存Keychain桩、手填隔离声明和manifest文件检查；需要明确标为模拟合同，并补真实OS测试。
3. 崩溃与浸泡harness存在固定效果计数、直接追加通过标签和未杀进程的恢复模拟；必须使用进程外控制器与独立效果账本补证据。
4. 同SHA的CI已经失败：Mac/Windows无法取得指定的3.12.12构建；Ubuntu出现24个测试收集错误，主要为No module named tests，另有2个SDK模块跳过。先修复环境与收集，不能把这些失败归为业务测试通过或单纯缺账号。
5. 某些工作流放在.github/workflows的子目录；官方不支持这种工作流布局。现有macOS工作流还缺少显式依赖准备。

以上发现的复现、修复和回归详见“仓库问题优先修复队列”。这不是对全部源码逐行审计；发现某条路径使用模拟对象，不代表其他未读路径也必然未实现。验收者应追踪产品实际装配图后确认。

## 先冻结发布范围

| 资格名称 | 必需内容 | 可以声明的范围 |
|---|---|---|
| Mac开发回归 | 类型/格式、合同、SQLite、合成HTTP/进程与安全反例 | 当前源码与受控环境的工程回归 |
| macOS MVP内测 | 真实Mac进程入口、持久化、Keychain、实际隔离、真实飞书、真实Browser/MCP、云与本地Provider、恢复与产物 | 记录的macOS版本和架构组合 |
| 原设计三平台M3 | macOS、Windows、Linux各自通过对应原生门禁，M3功能全量满足 | 原设计的三平台MVP |
| 桌面分发/M4 | Tauri、签名、公证、安装升级及回滚按实际分发形态验收 | 已验证的桌面发行包 |

当前先完成macOS MVP内测，不把Windows/Linux缺环境写成Mac测试失败；同时保持原三平台M3未满足的状态。M4签名UI不是源代码方式Mac内测的倒置前提；如果准备向他人分发安装包，则必须补相应安装与签名门禁。Apple Silicon、Intel和Rosetta分别记录，不借用其中一项结果代表另外两项。

## 什么证据能支持通过

每条用例记录输入、前置条件、实际动作、断言、观察证据、源代码SHA、测试命令、退出码、时间和环境。用例状态采用NOT_RUN、PASS、FAIL、BLOCKED、NOT_APPLICABLE；BLOCKED与NOT_APPLICABLE必须写具体原因、适用范围和下一条件。pytest的skip与xfail不能直接映射为必需门禁PASS。

证据分为四层：源码审查；确定性模拟合同；真实本地进程/SDK/OS；真实外部服务。调用方传入的verified=True、固定计数、文件名含native/e2e、测试标签数量或模型自述，均不足以证明更高一层的能力。报告应显示evidence_kind和未测边界，而不是把模拟合同累计成原生能力。

推荐的三方观测是：产品只读状态、产品审计日志、独立于产品的真实效果记录。控制器记录request_count和effect_count两个不同指标，不能把收到一次HTTP请求当成发生一次业务效果。最终成功状态必须与产物或外部回执一致。

## 缺陷严重度和测试优先级

| 分类 | 定义 | 处理 |
|---|---|---|
| S0缺陷 | 越权副作用、秘密泄漏、不可恢复数据损坏、未知结果导致重复危险效果 | 停止相关派发；保全证据；优先修复；阻止发布 |
| S1缺陷 | 关键流程不可用、恢复或隔离失效、验收错误声称通过 | 阻止相关MVP范围发布，先复现再修复 |
| S2缺陷 | 有可靠替代路径的非核心功能或性能问题 | 明确影响、负责人和目标；按发布范围决策 |
| S3缺陷 | 不改变行为的文案、易用性与低影响问题 | 可排后续，保留问题记录 |

P0/P1/P2是测试执行优先级，与S0/S1/S2/S3缺陷严重度分开。P0必需用例不允许通过降低断言或删除测试而变绿。最终已选择发布范围内的所有必需用例均需PASS，缺环境的必需项仍阻塞资格。

## 原始证据与Git摘要

原始日志、模型响应、测试数据库、截图、诊断包和含租户标识的网络记录放在受限的本地运行目录。入Git的内容限于脱敏摘要、复现测试、合成夹具和必要配置。不要提交Keychain导出、API token、cookie、真实消息正文、完整用户路径或生产数据库。报告必须能指向私有证据的位置或摘要，而不把私有原件复制进公开仓库。

## 用户已授权的提交规则

用户已明确要求每修复一项问题就提交并推送一次；本机执行代理按已确认仓库和目标分支连续执行，无需每项重复确认。此规则不授权强推、覆盖用户未提交改动、自动合并main、生产部署或向未知真实收件人发送测试消息。真实服务测试限定用户明确配置的专用测试应用和合成收件范围。具体原子提交与推送恢复流程见后续章节。
