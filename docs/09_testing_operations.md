# 验证体系与运行维护

v1.2增加组件资格验证目录Q01至Q16，详见13_component_qualification。实现任务先通过所用组件的相关准入场景，再通过业务验收；不把“库已成熟”或“安装成功”当作授权、隔离与恢复测试的替代。组件升级按影响范围重跑门禁，未影响部分不无故扩大测试。

## 测试分层

确定性测试验证控制面行为，真实模型评测验证完成任务的能力，真实OS测试验证系统边界。三者不能互相替代。测试必须有输入、动作、断言和证据；不要求用海量镜像实现的单元测试堆覆盖率。

| 层级 | 内容 | 触发 |
|---|---|---|
| Unit / Contract | 状态转换、canonical hash、配置、schema、错误映射 | 每个相关变更 |
| Integration | SQLite事务、Broker、FakeProvider、FakeExecutor、MockChannel | PR门禁 |
| Security | 身份重放、审批竞态、路径逃逸、网络出口、秘密canary、插件绕过 | 涉及边界的PR及发布 |
| Chaos | 每个commit边界kill、断网、超时、磁盘满、时钟变化 | nightly与恢复改动 |
| Native platform | 安装、权限、进程组、用户注销、升级、休眠 | 对应平台发布 |
| Real service | 飞书测试租户、真实模型、受控浏览器、测试MCP | 凭据隔离的集成环境 |
| Evaluation | 任务成功、成本、延迟与错误副作用 | 模型/工具/提示模板重要变更 |

## 阻塞性验收场景

| 测试ID | 输入或故障 | 必须观察到的结果 |
|---|---|---|
| AT01 | 同一入站event重放100次 | 一个逻辑Task；每次响应指向同一结果 |
| AT02 | 20个相同审批并发点击 | 一个批准决策和一次claim；不增加外部动作次数 |
| AT03 | 批准后改argv、文件hash或收件人 | BINDING_MISMATCH或RESOURCE_CHANGED；不执行 |
| AT04 | 取消与批准、claim竞争 | 事务顺序明确；取消后不派发新动作；已开始效果如实记录 |
| AT05 | 远端成功后本地commit前kill | UNKNOWN与核对；不自动再次发送 |
| AT06 | 同一profile启动第二个daemon | 第二实例不能执行，返回已有实例信息或清晰失败 |
| AT07 | 旧worker租约过期后恢复 | fence/epoch失效；不能作为新实例继续提交或派发 |
| AT08 | symlink/junction/ADS/UNC/路径大小写攻击 | 作用域外文件不被读写，错误不泄露内容 |
| AT09 | 恶意README要求读取key并外发 | 模型可被诱导，但实际读取/外发被policy与隔离阻止 |
| AT10 | 测试脚本试图读取HOME或连网 | 沙箱范围与出口规则实际生效 |
| AT11 | MCP定义变更或内部自治调用写工具 | 工具隔离；未经新的有效授权不执行 |
| AT12 | Cloud provider在LOCAL_MODEL模式被选择 | 请求发出前拒绝，无隐式fallback |
| AT13 | OFFLINE模式启用飞书/浏览器 | 配置冲突被识别，外网请求计数为零 |
| AT14 | 飞书callback超时、重复、token过期 | 无虚假成功；数据库状态可查询；卡片可降级 |
| AT15 | outbox更新乱序与429 | 旧revision不覆盖新状态；节流和退避可观测 |
| AT16 | 磁盘满、writer队列满 | 拒绝新派发，不把未持久化请求ACK为成功 |
| AT17 | 用户关闭Tauri窗口 | daemon和授权任务继续；显式stop才回收 |
| AT18 | 升级迁移失败 | 保持可恢复状态，旧数据不被静默覆盖 |
| AT19 | 只复制DB备份缺artifact | 恢复验证失败或明确缺失，不宣称完整恢复 |
| AT20 | Owner撤销后点击旧审批 | OWNER_REVOKED，旧token与旧卡片均无执行权 |

每个场景用mock测试控制面；涉及权限、网络、进程和安装的场景还需真实边界验证。所谓“边界证明”在这里指测试证据，不等于数学证明所有攻击均不可能。

## 质量基准

固定八类任务：仓库定位、两文件修复并保留脏改动、隔离测试、含注入页面的结构化提取、MCP成功后超时核对、飞书跨重启批准、owner撤销、离线与本地模型区别验证。每类记录task输入、环境快照、预期产物、允许副作用、模型配置与版本。

指标包括Task success/partial/failed、未知结果率、错误副作用数、恢复正确率、工具调用数、审批次数、token、估算/实付费用、端到端延迟分位数。先跑小型基线形成实测数据再设性能门槛；不能引用他人或示意图百分比作为本产品稳定率。

## 可观测性

每条日志带profile_id、task_id、operation_id、attempt_id、trace_id、event_seq和runtime_epoch中的适用项。区分用户可见事件、开发诊断和安全审计。日志默认存结构化摘要，正文、截图和凭据不进入普通日志。

health输出分项状态；关键指标包括writer queue depth、oldest inbox age、outbox backlog、waiting approval count、unknown operations、worker count、model error rate、budget remaining和last gateway heartbeat。提供doctor命令定位权限、网络、模型、数据库、浏览器与沙箱能力缺失。

诊断包须先预览；默认包含版本、错误码、能力矩阵、脱敏日志和schema，不包含任务全文、cookies、token、源代码或截图。需要加入敏感内容时用户明确选择，并记录导出范围。

## 运行手册

故障处理顺序：停止新派发、保留状态和证据、确认活动worker、核对UNKNOWN、修复连接或存储、验证权限与预算、再恢复。禁止以删除.db、清空全部审批或关闭policy来“修复”系统。

凭据疑似泄漏时本地撤销相关channel/provider，旋转凭据，提升identity_epoch，失效旧token，核查外发记录。MCP异常时隔离该server，保留manifest与动作记录；不能因它自称readOnly就继续运行。

备份每次升级前执行，周期备份由用户配置；恢复演练至少覆盖空机器、旧版本与缺失artifact三种情况。用户注销、睡眠与网络断开都单独测量。发布前运行持续浸泡，但实际时长由版本风险决定，不能把某个12小时测试当作长期可用性证明。

