# OpenBot v1.2 实施计划

目标：保留 OB-001 至 OB-096，按依赖实施到 M3；任务完成须有正向、负向和所需真实环境证据。

## 当前范围与顺序

### 2026-11-05：macOS 客户端、配置热更新与工作流透明性

用户新增范围：中英双语 Agent 客户端、配置热更新、Skill/MCP 因果执行图、参考 Hermes 的飞书接入。保留 OB-001—096，用 OB-008/047/056/066/075/081/082/083 追踪本轮工作。

1. [complete] 已核对代码、PDF 与官方来源，完成双语设计、执行图与独立建设者审阅；用户已确认按此实施。
2. [complete] Git 敏感文件忽略规则：失败回归与完整验证通过，65f8666 已推送，远端 SHA 与 contracts CI 成功核对。
3. [in_progress] 真实模型 → 核心审批 → 隔离 MCP → 双语产物链路已成功；飞书 token/bot/discovery 已通过，真人收消息关联待验证。凭据只在进程内存。
4. [in_progress] 执行 docs/superpowers/plans/2026-11-05-agent-client.md；每项失败回归、相关验证、commit、push、远端/CI 核对。

本轮授权覆盖常规本地实现与测试、修复分支的原子提交和 push；覆盖旧计划“不推送/不使用测试凭据”的限制。未授权自动合并 main、正式发布、部署或任意第三方消息。真实密钥不得写入任何仓库文件、日志、证据或普通诊断。

1. M0 第一批：OB-001—005、OB-089。核对范围、信任与生命周期，建立最小 Python 3.12 工具链和分阶段组件门禁。
2. M0 第二批：OB-006—010、OB-090。严格 JSON / Draft 2020-12 / RFC 8785、配置、错误、可重复故障夹具。
3. M0 第三批：OB-091。真实临时 SQLite 与 mock 效果的 claim / dispatch 崩溃矩阵；不改正式 23 表基线。
4. M1：先 OB-092 与 OB-093，随后持久化、审批、策略、受控工具、本地 API，最后 OB-029 正式集成。
5. M2 / M3：按 DAG 实施可独立验证部分；真实租户、模型、隔离或原生平台缺失时记录最小阻塞条件，继续其他就绪工作。

## 验证方法

- 每项先读完整任务卡和 component_refs / reuse_type / reuse_notes；只引入本阶段必要依赖。
- 有行为改动先写失败测试；运行相关测试、完整当前测试集及原设计检查。
- 公共合同、migration、锁与策略先记录 ADR；证据写 docs/evidence 与 evidence/implementation。
- 未经真实验收的能力不启用；单元 / mock / 原生 / 真实服务分别报告。
- 所有初始设计文件当前均为未跟踪文件，保留其原始内容与清单；不创建基线提交掩盖用户现有状态。

## 状态

- [complete] 只读盘点与 M0 第一批本地实现；三 OS 实测待环境
- [complete] 标准合同、故障夹具与协议 PoC 本地验证
- [in_progress] M1 SDK / 隔离先行验证和正式集成
- [complete] OB-011/012/013/014 本机持久化与 Task 状态机/OutcomeVerifier 验收；上游三 OS 门禁未闭合，保留 VERIFIED
- [complete] M1 本地可实施任务全部落地并通过验证（OB-011—025、OB-028—046、OB-081、OB-092—093）
- [complete] M2 与 M3 全部可本地实施任务落地并通过验证（OB-048—056、OB-094、OB-026、OB-057—069、OB-072、OB-075—080、OB-095—096），生成完整 MVP 验收与风险/阻塞登记报告

## 已知错误与处理

- 2026-11-05：默认沙箱阻止 Git 写 ref，已使用授权的提升工具成功创建修复分支；完整验证的 loopback bind 被沙箱拒绝，改在授权环境重跑，不改测试断言。
- 2026-11-05：设计检查要求根 diagrams 保留原 7 张基线图；新增图移至 diagrams/client，不放宽原基线检查。一次文档补丁上下文不匹配，重新定位后成功应用。

- 首次任务读取假设 backlog 是对象，实际为数组；已更正为直接遍历数组。未改变设计内容。

## 约束

不推送、不部署、不发布、不发送第三方消息、不安装系统服务，不读取或使用用户真实凭据。

## English Summary

Goal: Implement OpenBot v1.2 through M3 following the 96-task DAG in `tasks/backlog.json`, reading `component_refs`, `reuse_type`, and `reuse_notes` for each task, writing failing RED tests before minimal implementation, running full M0/M1 verification (`scripts/verify.py`), maintaining bilingual documentation, and committing/pushing each completed task without leaking credentials.
