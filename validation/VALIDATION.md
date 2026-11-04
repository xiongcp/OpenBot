# 本设计包的验证记录与边界

设计基线：1.2。验证日期：2026年11月4日（Asia/Shanghai）。

本记录描述交付前对规格、合同、任务图、组件目录、SQL基线与参考事务的验证。OpenBot应用尚未在本包中实现；以下结果不能作为真实模型、飞书、浏览器、MCP、沙箱、原生安装或生产发布通过的证据。

## 已完成的验证

| 对象 | 实际结果 | 可复查的证据 |
|---|---|---|
| SQLite基线与参考事务 | 33项全部通过；SQLite 3.53.1；退出码0 | database_report.json、verify_database.py |
| 任务完整性 | 96个唯一任务ID、初始全部TODO，依赖有效且无环，无后续阶段反向依赖，12组需求均有覆盖 | design_report.json、../tasks/backlog.json |
| 组件与资格目录 | 52个组件或组件组、16项资格场景；组件引用和阶段分布一致，真实资格全部NOT_RUN | components_report.json、../components/ |
| 基线兼容 | 原88个任务ID和阶段保留；DDL、OpenAPI、状态机3个文件的SHA-256与v1.1一致 | baseline_compatibility.json |
| API结构 | 14个操作的本地引用、路径参数与基本结构通过 | design_report.json、../contracts/openapi.yaml |
| 合同样例 | 10个正向样例通过、5个负向样例被拒绝；使用有限关键字检查 | verify_design.py、../contracts/examples/ |
| 状态定义 | 状态枚举与迁移目标一致；Approval.CONSUMED为终态 | design_report.json、../contracts/state-machine.json |
| 研究与决策映射 | 24组官方来源、22项ADR；来源ID与文档引用一致 | components_report.json、../evidence/reuse_sources.json |
| 文档与图 | 本地引用有效，7组SVG可解析，PNG与Mermaid源文件齐备；架构图已视觉检查 | design_report.json、../diagrams/ |
| PDF | 主报告55页、任务手册99页；全部页渲染并检查联系表，关键页完整查看，文字边界扫描无越界 | pdf_layout_report.json、../reports/ |

数据库验证覆盖：收件去重与payload冲突、提案不可变、审批一次消费、安全重试与原期限复核、取消与派发竞态、epoch与资源版本、审计不可覆写、Outbox事务回滚、UNKNOWN处理、fence不倒退、单owner/runtime、预算原子准入、连接重开，以及UNKNOWN资源隔离不能用新Task或Operation ID绕过。

其中一部分保护是SQL约束，一部分是脚本中的参考应用事务。脚本通过不意味着仅复制DDL就获得完整安全性；正式应用必须实现对应应用层guard、受保护challenge存储、恢复器、资源隔离和结果核对。详细分界见../db/README.md。

## 验证方法的限制

- verify_design.py及verify_components.py使用自定义有限JSON Schema关键字子集检查样例与目录；不是完整JSON Schema或OpenAPI元模式验证器。正式工程由OB-090引入完整标准实现和真实测试向量。
- 示例中的hash是合成格式值，未证明RFC 8785 canonicalization或真实授权摘要正确。正式实现必须采用经验证的实现、UTF-16排序与数值边界向量，并保持Python侧权威字节。
- 状态迁移JSON中的文字guard需要应用代码实现；枚举和DAG检查不能证明并发调度正确。
- SQLite测试使用临时数据库和参考事务，未覆盖真实多进程竞争、物理断电、全部文件系统、现有用户库升级或真实外部副作用。
- 本轮仅核验官方资料、源码边界和设计一致性；没有运行52个组件组的真实资格测试，没有生成真实依赖锁，也没有复制候选应用源码。
- 图、SQL、组件目录和任务卡均属于设计交付，不能据此把应用任务改成DONE或把资格状态改成PASS。

## 后续产品必须补充的门禁

1. 真实身份认证、owner撤销、审批挑战恢复、数据分类、规范摘要与出口控制。
2. SDK实际请求次数、唯一重试责任、tool helper限制、取消后结果核对及所有副作用路径。
3. 首发OS与隔离后端的文件、网络、进程、凭据和回收边界；无合格后端返回CAPABILITY_UNAVAILABLE，不能降级宿主执行。
4. 飞书测试租户的回调时限、重复乱序、断线重连、卡片更新、单Gateway归属与进程外启动监督。
5. 至少两个真实Provider的能力、超时、预算、上下文与工具合同；M3本地模型还需禁云、模型来源和实际出口证据。
6. Browser的Chromium sandbox、Service Worker与出口限制，MCP真实server协议与工具变化，以及UNKNOWN隔离与效果核对。
7. macOS、Windows和Linux原生环境中的进程回收、登录会话、休眠恢复、CLI安装与能力探测；后续GUI单独验证。
8. 完整发布资产、离线首次使用、版本和来源hash、许可证与NOTICE、备份恢复、迁移、日志脱敏、签名和干净机器安装。

这些工作已映射至Q01至Q16、OB-089至096和对应原任务。本次没有把后续工作写成已完成的验证。

## 复查命令

从设计包根目录运行：

~~~sh
python3 validation/verify_design.py
python3 validation/verify_components.py
python3 validation/verify_database.py --report validation/database_report.json
~~~

以上设计检查使用Python标准库。运行环境的SQLite需要支持基线所用STRICT表和JSON函数；请记录本机Python/SQLite版本，不把本次版本当作未来机器保证。verify_design.py针对未实施基线检查初始TODO；开发后应建立适应实际任务状态的工程CI，不能为了通过设计基线检查而把已完成任务改回TODO。
