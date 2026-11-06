# 100项用例索引与执行登记

本目录完整操作卡见 cases/TEST_CASES.md，机器可读清单见 cases/test_cases.json。全部尚未执行，NOT_RUN不是失败，也不是通过。只对事先冻结范围外的条件用例使用NOT_APPLICABLE。

## 基线与验收真实性

| ID | 用例 | 优先级 | 真实环境 | 初始状态 |
|---|---|---|---|---|
| TC-QA-001 | 源码、dirty状态与远端归属冻结 | P0 | 需要 | NOT_RUN |
| TC-QA-002 | 锁定Python与依赖在实际架构可安装 | P0 | 需要 | NOT_RUN |
| TC-QA-003 | 本地与CI测试收集一致 | P0 | 需要 | NOT_RUN |
| TC-QA-004 | 验证超时和异常不得沿用旧PASS | P0 | 模块集成 | NOT_RUN |
| TC-QA-005 | 真实console入口与安装路径 | P0 | 需要 | NOT_RUN |
| TC-QA-006 | 工作流被识别并执行真实门禁 | P0 | 需要 | NOT_RUN |
| TC-QA-007 | 模拟证据不能升级为原生资格 | P0 | 模块集成 | NOT_RUN |
| TC-QA-008 | 发布证据绑定当前候选与范围 | P0 | 模块集成 | NOT_RUN |
## 内核、授权、恢复与Provider

| ID | 用例 | 优先级 | 真实环境 | 初始状态 |
|---|---|---|---|---|
| TC-CORE-001 | 真实本地入口贯通四对象与一次受控效果 | P0 | 需要 | NOT_RUN |
| TC-CORE-002 | Task 合法跃迁、终态守卫与只读回放 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-003 | 入站去重、负载冲突与身份作用域 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-004 | T1 提交前与提交后 ACK 丢失的恢复 | P0 | 需要 | NOT_RUN |
| TC-CORE-005 | 状态、审计、outbox 与完成结果的事务原子性 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-006 | 严格 JSON、JCS 标准向量与本地 Schema 边界 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-007 | 已批准提案不可变及旧新内容精确绑定 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-008 | 真实本地 API 身份、作用域与对象归属 | P0 | 需要 | NOT_RUN |
| TC-CORE-009 | 审批 nonce、TTL 与重启后的 challenge 保护 | P0 | 需要 | NOT_RUN |
| TC-CORE-010 | 同版本审批竞争与批准后合法撤销 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-011 | 批准已提交但响应丢失不产生第二授权 | P0 | 需要 | NOT_RUN |
| TC-CORE-012 | 撤销 owner 或授权与 claim 的确定性竞态 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-013 | 每次派发前复验期限、策略、身份与资源 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-014 | CLAIMED 后取消与第二派发事务的线性化 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-015 | claim 已提交、尚未派发时的真实进程崩溃 | P0 | 需要 | NOT_RUN |
| TC-CORE-016 | DISPATCHING 已提交、发包前崩溃仍须核对 | P0 | 需要 | NOT_RUN |
| TC-CORE-017 | 外部效果成功、回执落盘前崩溃不盲重放 | P0 | 需要 | NOT_RUN |
| TC-CORE-018 | 结果已提交、通知或 UI 响应丢失不重执行 | P0 | 需要 | NOT_RUN |
| TC-CORE-019 | 在途取消保留未知结果且阻止后续动作 | P0 | 需要 | NOT_RUN |
| TC-CORE-020 | 同一 Attempt 重传与 dispatch 接收去重 | P0 | 需要 | NOT_RUN |
| TC-CORE-021 | 同 Operation 安全重试、稳定幂等键与失效拒绝 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-022 | 旧 epoch、过期租约与迟到结果不能制造双执行者 | P0 | 需要 | NOT_RUN |
| TC-CORE-023 | UNKNOWN 资源 quarantine 防新 Task/Operation ID 绕过 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-024 | 核对证据、Operation.version 与人工确认来源 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-025 | 单 writer 独占完整事务与连接约束 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-026 | 调用者取消或超时后查询真实提交结果 | P0 | 需要 | NOT_RUN |
| TC-CORE-027 | 队列预留、公平性、总 deadline 与背压 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-028 | 派发前真实 SQLite 满盘或提交失败 | P0 | 需要 | NOT_RUN |
| TC-CORE-029 | 外部成功后满盘导致结果不可持久化 | P0 | 需要 | NOT_RUN |
| TC-CORE-030 | 在线备份与并发 GC 保持 DB/Artifact 一致 | P0 | 需要 | NOT_RUN |
| TC-CORE-031 | 缺失或被篡改备份的恢复必须拒绝假完整 | P0 | 需要 | NOT_RUN |
| TC-CORE-032 | 多文件补丁部分提交与用户脏改动保护 | P0 | 需要 | NOT_RUN |
| TC-CORE-033 | Artifact 文件与数据库登记之间的崩溃缝隙 | P0 | 需要 | NOT_RUN |
| TC-CORE-034 | 硬拒绝与本地确认不能被批准或工具 metadata 覆盖 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-035 | 提示注入、摘要与导入元数据不能洗白权限或数据 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-036 | OFFLINE、LOCAL_MODEL 与实际网络出口 | P0 | 需要 | NOT_RUN |
| TC-CORE-037 | 秘密按用途最小注入与凭据不可用时拒绝 | P0 | 需要 | NOT_RUN |
| TC-CORE-038 | 跨分片秘密过滤、异常日志与 scanner 隐式外发 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-039 | 实际 Provider 请求计数与唯一重试负责人 | P0 | 需要 | NOT_RUN |
| TC-CORE-040 | 流式工具参数完整性、ID 对应与异常输出 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-041 | SDK 自动工具 helper、托管工具和扩展字段旁路 | P0 | 需要 | NOT_RUN |
| TC-CORE-042 | Provider 取消、断流、deadline 与未知计费 | P0 | 需要 | NOT_RUN |
| TC-CORE-043 | 并发预算预留、重复结算与空转熔断 | P0 | 模块集成 | NOT_RUN |
| TC-CORE-044 | outbox 重复、乱序与未知 ACK 不重执行业务 | P0 | 需要 | NOT_RUN |
## macOS原生环境

| ID | 用例 | 优先级 | 真实环境 | 初始状态 |
|---|---|---|---|---|
| TC-MAC-001 | Apple Silicon 原生身份与通过报告必须来自真实能力 | P0 | 需要 | NOT_RUN |
| TC-MAC-002 | Intel 原生资格与 Rosetta 结果分开 | P1 | 需要 | NOT_RUN |
| TC-MAC-003 | Darwin 控制面与 Linux 容器执行域必须分离声明 | P0 | 需要 | NOT_RUN |
| TC-MAC-004 | 干净 macOS 用户的真实安装与首次产品启动 | P0 | 需要 | NOT_RUN |
| TC-MAC-005 | OFFLINE 干净首用不隐式补下载资产 | P0 | 需要 | NOT_RUN |
| TC-MAC-006 | Gatekeeper 真实首开、签名与公证声明一致 | P1 | 需要 | NOT_RUN |
| TC-MAC-007 | 离线 Gatekeeper 与制品篡改负例 | P1 | 需要 | NOT_RUN |
| TC-MAC-008 | launchd 登录会话中的真实服务注册和环境 | P0 | 需要 | NOT_RUN |
| TC-MAC-009 | 唯一 profile 锁、父子不自锁与客户端退出 | P0 | 需要 | NOT_RUN |
| TC-MAC-010 | 显式停止与卸载仅回收已登记资源 | P0 | 需要 | NOT_RUN |
| TC-MAC-011 | 真实睡眠/唤醒后的审批、连接与在途任务 | P0 | 需要 | NOT_RUN |
| TC-MAC-012 | 真实断网、网络切换与半开连接后的恢复 | P0 | 需要 | NOT_RUN |
| TC-MAC-013 | 注销/登录与受控重启恢复，不承诺登录前常驻 | P0 | 需要 | NOT_RUN |
| TC-MAC-014 | 真实 SIGKILL、多代/脱离进程与 PID 身份核验 | P0 | 需要 | NOT_RUN |
| TC-MAC-015 | Docker 客户端死亡、引擎重启与容器独立归属 | P0 | 需要 | NOT_RUN |
| TC-MAC-016 | 实际容器权限、出口与资源上限生效 | P0 | 需要 | NOT_RUN |
| TC-MAC-017 | 容器产物 stop/wait→校验→登记→remove | P0 | 需要 | NOT_RUN |
| TC-MAC-018 | APFS 路径、大小写/Unicode别名与真实权限 | P0 | 需要 | NOT_RUN |
| TC-MAC-019 | 真实 Keychain 后端、锁定/拒绝与最小注入 | P0 | 需要 | NOT_RUN |
| TC-MAC-020 | TCC 按实际功能和执行二进制最小授权 | P0 | 需要 | NOT_RUN |
| TC-MAC-021 | macOS 数据备份/恢复与版本变更的真实重启 | P0 | 需要 | NOT_RUN |
| TC-MAC-022 | 真实SDK/系统故障诊断不泄漏秘密或启用遥测 | P0 | 需要 | NOT_RUN |
## 真实服务与产品集成

| ID | 用例 | 优先级 | 真实环境 | 初始状态 |
|---|---|---|---|---|
| TC-INT-001 | 飞书真实测试应用接入、配对与 owner 撤销 | P0 | 需要 | NOT_RUN |
| TC-INT-002 | 真实飞书事件持久 ACK、重投去重与重启 | P0 | 需要 | NOT_RUN |
| TC-INT-003 | 真实审批卡 callback 的 deadline、重复与失效 | P0 | 需要 | NOT_RUN |
| TC-INT-004 | 普通卡、CardKit权限不足与三个独立时钟 | P0 | 需要 | NOT_RUN |
| TC-INT-005 | 飞书发送成功但本地回执丢失的 UNKNOWN 核对 | P0 | 需要 | NOT_RUN |
| TC-INT-006 | 真实 SDK 阻塞与进程外 Gateway watchdog | P0 | 需要 | NOT_RUN |
| TC-INT-007 | 真实 Chromium 启动、跨进程 profile 锁与沙箱 | P0 | 需要 | NOT_RUN |
| TC-INT-008 | 浏览器 Service Worker、重定向与实际出口 | P0 | 需要 | NOT_RUN |
| TC-INT-009 | 浏览器目标变更与点击成功后断线 UNKNOWN | P0 | 需要 | NOT_RUN |
| TC-INT-010 | MCP 真实 stdio/SDK 握手、环境与流量上限 | P0 | 需要 | NOT_RUN |
| TC-INT-011 | MCP 工具动态变化、伪造 hints 与旧授权失效 | P0 | 需要 | NOT_RUN |
| TC-INT-012 | MCP 写动作超时、取消与副作用核对 | P0 | 需要 | NOT_RUN |
| TC-INT-013 | Ollama 本地模型来源、禁云配置与实际出口 | P0 | 需要 | NOT_RUN |
| TC-INT-014 | OFFLINE/LOCAL_MODEL 实际受管域出口和模式切换 | P0 | 需要 | NOT_RUN |
| TC-INT-015 | 浏览器上传/下载和污染数据进入真实 Artifact 流 | P0 | 需要 | NOT_RUN |
| TC-INT-016 | 真实 macOS 产品从飞书任务到批准执行、重启和核对的闭环 | P0 | 需要 | NOT_RUN |
## 逐问题提交推送

| ID | 用例 | 优先级 | 真实环境 | 初始状态 |
|---|---|---|---|---|
| TC-GIT-001 | 单问题提交和用户改动隔离 | P0 | 需要 | NOT_RUN |
| TC-GIT-002 | push结果不明的幂等核对 | P0 | 需要 | NOT_RUN |
| TC-GIT-003 | 非快进与并发远端更新 | P0 | 需要 | NOT_RUN |
| TC-GIT-004 | CI状态必须对应验证SHA | P0 | 需要 | NOT_RUN |
| TC-GIT-005 | 已推送修复引入回归时追加独立修复 | P0 | 需要 | NOT_RUN |
| TC-GIT-006 | Git摘要与原始证据分离 | P0 | 需要 | NOT_RUN |
## 任务质量与长期运行

| ID | 用例 | 优先级 | 真实环境 | 初始状态 |
|---|---|---|---|---|
| TC-EVAL-001 | 冻结的24个真实任务场景 | P0 | 需要 | NOT_RUN |
| TC-EVAL-002 | 预算、请求数、成本与延迟可核对 | P0 | 需要 | NOT_RUN |
| TC-EVAL-003 | 真实时长浸泡与资源稳态 | P1 | 需要 | NOT_RUN |
| TC-EVAL-004 | 文档示例和能力矩阵与产品一致 | P1 | 需要 | NOT_RUN |
