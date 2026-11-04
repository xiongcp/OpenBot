# OB-002：信任与副作用

状态：接受；日期：2026-11-04。沿用设计 ADR01、05—12、15、18、22。

资产为 owner 身份、审批 canonical bytes、凭据、工作区、账本、artifact、外部账户及预算。防御恶意网络入站、模型/网页/文件/MCP 注入、组件隐藏执行与运行故障；同一 OS 用户完全失陷超出普通本地 token 与文件权限的保护范围。

| 边界 | 控制与失败用例 | 残余边界 / 负责门禁 |
|---|---|---|
| 入站 | 身份来自已认证接入；body 的 role/is_owner 拒绝 | 已失陷凭据不能靠 schema 修复；OB-048/081 |
| 模型 | 基础 API 白名单、零 SDK 重试、逐请求预算；拒自动 runner / hosted tools | 生成内容仍不可信；OB-025/026/092 |
| 网页 | 专用 profile、出口与 revision；重定向 / SW 另测 | 审批不替代浏览器 sandbox；OB-057—061 |
| MCP | 完整定义锁定、限制环境与进程；annotations 不授权 | 定义 pinning 不证明实现可信；OB-062—065 |
| 文件 | 路径句柄 / 快照守卫；拒 symlink / traversal / hooks / filters / rg 配置与预处理器 | 工作区可并发变化；OB-032—035 |
| OS | 受管进程和容器独立登记；未知归属保留隔离 | 进程组 / Drop / EOF 不保证全部子孙回收；OB-093 |
| 依赖 | 精确来源许可和资产；拒运行期下载 / 遥测 / 联网扫描与外部 allowlist | 静态审查不是实际出口证明；OB-089/092/096 |

effect 为 READ / LOCAL_WRITE / EXTERNAL_WRITE / CODE_EXECUTION，仅描述效果；retry_class 是独立判断。SAFE_READ 在重新授权后可重读；IDEMPOTENT_WRITE 仅同内容同目标且复验条件成立可重试；PROVIDER_IDEMPOTENT 使用同 Operation 的供应商键且在供应商保证窗口内；RECONCILE_ONLY 必须先核对；NON_RETRYABLE 不自动重放。各类在派发后失去回执都不能直接推断失败：写类保留 UNKNOWN 与 quarantine，读类亦须先明确执行和取消状态。

审批使 READY；claim 消费一次授权；第二事务复验后才 DISPATCHING。CONSUMED 永不复活。新 Attempt 新 dispatch_id，供应商键仍属于 Operation。SDK / 官方品牌 / 许可证 / annotations / 用户曾批准均不赋予额外权限，审批、Docker、argv、schema 中任何单项都不是完整安全保证。
