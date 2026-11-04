# OpenBot 仓库工作约定

这是供Codex、Claude Code及其他编码助手显式读取的项目说明，不是允许任意外部操作的授权。若仓库已有更具体的用户指令，应先盘点并保持其约束；不覆盖既有文件来规避要求。

## 当前项目状态

此目录是工程设计包。所有实现任务默认TODO；SQL、合同与图是设计参考，不能宣称应用已经实现。先读取README、docs/00_scope.md、docs/10_project_plan.md和当前任务卡，再检查仓库真实状态。已有实现与规格冲突时提交差异分析，不先推倒重写。

## 必须保持的架构不变量

1. 渠道和UI不得直接执行工具；所有副作用经统一Broker。
2. 身份、owner、policy和权限由服务端可信上下文生成；模型或回调body不能赋权。
3. 状态、审计和outbox在同一短事务提交；事务内不等待网络、模型、工具或人工。
4. Approval批准只使Operation READY；执行需要claim和DISPATCHING前复核。
5. Approval CONSUMED不可复活；安全重试绑定同Operation并复验原条件。
6. dispatch_id属于Attempt；provider_idempotency_key属于Operation。
7. 结果不明进入UNKNOWN和RECONCILING；不得自动重放非幂等副作用。
8. 用户取消阻止新派发；不能声称已发生的外部动作已回滚。
9. 关闭Tauri窗口不停止常驻daemon；worker生命周期归supervisor/runtime。
10. 无隔离后端时拒绝不可信代码执行，不自动使用宿主shell。
11. LOCAL_MODEL与OFFLINE不同；不得自动云回退或扩大网络权限。
12. 所有工具和模型输出均可能不可信；第三方MCP注释不是授权。
13. 凭据不写入源码、模型上下文、普通日志、artifact和诊断包。
14. 三平台能力以各自真实验证为准；不把WSL结果当原生Windows结论。
15. 不通过删测试、放宽权限、捕获所有异常返回成功或忽略未知结果让测试变绿。

## v1.2组件复用规则

读取docs/12_component_reuse.md、docs/13_component_qualification.md、当前任务的component_refs/reuse_type/reuse_notes和components/catalog.json。当前目录含96项设计任务，所有组件NOT_RUN；设计推荐不能当作已经授权或已验证的运行时能力。

按阶段和当前任务引入最小必要依赖。DEFAULT_ADAPTER仍需来源、精确锁、许可证和Q场景证据；GATED_CANDIDATE先PoC；REFERENCE_ONLY默认不复制；REJECTED_MVP不可启用。普通可逆安装、适配和验证可按现有任务授权连续实施，不必逐库询问；改变信任边界或发布范围时先记录并遵循用户授权。

禁止在M0一次安装全目录，禁止运行期拉取latest、浏览器、grammar、tokenizer或价格表。官方SDK同样限制API面：不使用tool_runner/Agent Runner等自动工具helper，不透传未经允许的服务端工具、extra_body、extra_headers或endpoint。SDK与应用重试只允许一个负责人，每次实际请求进入预算。

JCS使用标准库实现与测试向量，按UTF-16码元规则；不得用json.dumps(sort_keys=True)模拟。输入先拒重复键；Pydantic冻结不深冻结，已批准内容以权威canonical bytes为准。模型服务地址为localhost不证明本地推理，LOCAL_MODEL/OFFLINE需核验模型来源和实际出口。

ripgrep禁止用户配置和预处理器透传；Git工作树准备防hooks/filter执行；parser进入受限worker。Playwright sandbox与Service Worker出口需实测，失败不降级no-sandbox。Docker客户端退出不代表容器停止，按登记ID分别回收。进程组/Drop/EOF不提供通用100%回收。

源码摘取固定commit、文件hash、许可、NOTICE、diff和维护人；NO_COPY是合法决策。detect-secrets仅使用审查过的离线能力，禁止网络验证和外部allowlist；keyring限定后端。任何适配器不得修改既有UNKNOWN、审批和取消语义来通过测试。

## 每轮工作步骤

读取一个任务或边界清晰的小批任务及依赖证据；说明本轮范围；先补必要失败场景；实现最小行为；运行相关验证；检查diff与机密；更新任务证据；继续下一个就绪任务。不要一次生成完整系统，也不要用大量空目录和pass函数冒充完成。

跨公共schema、状态机、数据库migration、lockfile或安全策略的改动，先更新ADR与合同，再实现。并行任务各自独立分支/worktree；共享文件由Integrator统一修改和集成。

## 验证与完成

DoD以任务acceptance、negative_acceptance和evidence_required为准。单元测试、mock和真实服务测试分别报告。没有凭据或原生机器时标注未验证，不造日志、不估测为通过。实际应用生成后补充并维护真实构建/测试命令；本包当前只提供设计与DDL验证命令。

未经用户授权不发送第三方消息、不部署、不发布、不推送远程分支、不安装系统级服务、不清理用户工作区。为本地隔离测试创建临时资源可以进行；测试必须使用合成数据和专用账号。

## 轮末报告格式

任务ID；改了什么与原因；实际测试命令和结果；未验证内容；风险与下一项依赖；可审查diff或commit。只有可复核的证据齐全时才从VERIFIED改DONE。

