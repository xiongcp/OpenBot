# 严格测试、证据与问题修复

## 测试结构

保留旧手册 100 项语义用例，并增加 16 项配置、客户端、安装更新和文档一致性用例。新包中的执行结果全部重新置为 NOT_RUN；旧记录只作为历史参考。命令、入口、模型和环境必须绑定本次实际候选，不把旧 a223d36 的问题状态移植到当前 SHA。

测试分为合同/单元、真实本地进程、隔离执行域、真实外部服务、真实桌面发行物五层。各层单独列出 PASS/FAIL/BLOCKED/NOT_APPLICABLE，不用模拟调用累计替代更高层证据。

## 在 Mac 上的执行顺序

1. 记录 `git status --short`、HEAD、分支与已核对的远端归属；确认本次包括哪些已推送和未推送变更，保护用户工作区。
2. 记录 `sw_vers`、`uname -m`、Python/uv/SQLite 版本、实际容器后端和镜像 digest；不导出整个环境变量。
3. 建立独立 QA profile、临时工作区、浏览器 profile、Keychain 条目、效果服务和原始证据目录。避免改写 HOME 或接管日常浏览器。
4. 按锁文件安装当前测试阶段依赖，先做现有脚本与测试收集；可选 SDK 和 native Docker 使用独立资格命令。
5. 以真实 `openbot daemon serve` 与 CLI/HTTP 入口跑第一条任务；确认没有靠内部测试调用完成状态迁移。
6. 执行审批、取消、预算、工作区、秘密和隔离反例；再做真正 daemon/worker 强杀与未知效果恢复。
7. 执行云/本地 Provider、真实 Browser/MCP、专用飞书测试租户的闭环；记录不支持的具体能力。
8. 在干净 Mac 用户/设备测试最终安装包、首开、上手、常驻、休眠唤醒、断网、升级、恢复与卸载。
9. 固定最终 RC，运行累计回归、浸泡与用户场景，装配所有门禁证据后再考虑发布。

当前仓库已存在的基础命令为：[R02、R05]

```sh
uv sync --locked
.venv/bin/python scripts/verify.py
UV_PROJECT_ENVIRONMENT=.venv-m1 uv sync --locked --group provider-openai
.venv-m1/bin/python scripts/verify.py --phase M1
```

这些是工程回归入口，不是“运行一次即通过全部 MVP”的命令。CLI 子命令先读取当前 `--help` 和实际 parser 后记录到命令映射；包内不虚构尚未实现的一键生产验收命令。

## 哪些结果必须独立观察

| 场景 | 产品自身观察 | 独立观察 |
|---|---|---|
| 模型请求 | request attempt、预算预留、usage | 受控 HTTP 服务器收到的请求数与实际响应 |
| 工具写动作 | Operation/Attempt/事件/回执 | 文件 hash、测试站点效果账本或远端查询 |
| 取消 | cancel revision、派发拒绝 | 取消确认之后新请求/新效果的实际计数 |
| 强杀恢复 | epoch、UNKNOWN、quarantine | 真实进程出生时间与存活、容器状态、外部效果 |
| OFFLINE | 策略拒绝日志 | 受管域真实出站捕获/阻断与隐式下载检查 |
| 安装与更新 | 安装日志、版本、DB migration | Gatekeeper、签名、最终包 hash、重启后的真实数据 |

回归用例必须区分 request_count 和 effect_count。一次网络请求可能没有效果，也可能在本地超时前已经成功，不能靠其中一个猜另一个。

## 产品放行门禁

| 门禁 | 内容 | 必需结果 |
|---|---|---|
| G1 基线与契约 | 候选、范围、稳定接口、用例映射 | SHA/树/锁/最终包明确；命令真实存在 |
| G2 任务闭环 | 七条产品场景、产物验证 | 范围内成功/失败可解释，没有人工伪造成功 |
| G3 权限与秘密 | 撤销/审批绑定/工作区/密钥/数据出口 | 关键负例全部拒绝且实际效果为 0 |
| G4 恢复与取消 | 真正强杀、旧 epoch 隔离、UNKNOWN | 不产生重复不可逆效果，不假称已回滚 |
| G5 集成 | 云+本地、Browser、MCP、飞书 | 每个声明能力有真实环境证据 |
| G6 桌面与 Mac | Tauri、安全 IPC、安装、服务、休眠 | 声明的架构和系统版本逐项通过 |
| G7 发布与升级 | 最终制品、签名、公证、SBOM、迁移 | 验证最终发布字节，破坏/降级负例拒绝 |
| G8 用户与公示 | 上手、质量、诊断、README、官网 | 文档可执行，下载可用，支持表与证据一致 |

本表是新计划的八个汇总门禁；旧手册 G00-G15 的细分规则继续通过映射保留，不要求编号一一对应。BLOCKED、skip、xfail 或 NOT_RUN 不能满足必需门禁。

## 候选证据记录

每份记录至少有：run_id、source_sha、tree_sha、dirty、lock_hashes、artifact_hashes、test_id、command、exit_code、started_at/ended_at、platform/arch、evidence_kind、result、skip/block reason、日志摘要 hash、原始证据的受限位置。事实由执行器和 CI/系统采集器产生；调用者提交一组 `verified=true` 不能被直接提升为发布资格。

同一个 run_id 不覆盖历史结果；IN_PROGRESS 必须实际运行结束后才转 COMPLETE，超时/中断不得沿用上轮 PASS。先验证证据来源、必需 test_id 覆盖和候选一致，再做 release predicate。只检查文件个数、标签或 SHA 字符串相等不足以装配可信候选。

## 质量和性能目标建议

以下是待冻结的项目目标，不是当前实测值：每个合格 Provider 对每个适用核心场景至少执行 5 次，记录 n、完成率、PARTIAL/FAILED/RECONCILING、成本和延迟；核心任务集目标完成率不低于 90%。所有安全负例必须通过，一次越权、秘密外泄、重复不可逆效果或数据损坏即阻断发布，不用平均完成率抵消。

本地健康/状态 API 可先设 p95 300 ms、取消持久确认 p95 1 s、暖启动客户端 3 s 的初始目标；至少 30 次样本、明确机器和工作负载后调整。模型响应延迟另算。建议至少一次 24 小时混合任务浸泡和 7 天小范围 beta；观察内存、FD、子进程、容器和 outbox 是否持续增长。样本通过只支持被测范围，不代表绝对无损或可用性 SLA。

## 缺陷修复闭环

严重度 S0/S1 阻断范围内发布；S2/S3 只有不违反必需需求且存在明确替代方案时可登记后续。每项缺陷记录：复现条件、实际/预期、根因、最小改动、回归、introduced_by_sha、verified_on_sha、远端 ref、push/CI 回执和剩余边界。

先复现再修复。针对有实际风险的行为增加回归测试；低影响文案修改只做必要链接/渲染检查，不编写复述文案的测试。每个独立问题单独 commit/push，具体规程见执行章节。
