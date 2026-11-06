# 执行器与模型接入设计

v1.2的默认实现组合是官方模型SDK薄适配、ripgrep搜索、unidiff解析、受验证容器后端、Playwright原语和官方MCP SDK。具体组件决策、可选项与边界见12_component_reuse；验收场景见13_component_qualification。组件名只确定实施方向，不代表版本或平台已经通过验证。

## Tool Manifest

每个内置工具登记名称、版本、input/output schema、effect、资源类型、default decision、retry_class、timeout、max_output、网络要求、secret handles、能力依赖、取消行为和reconcile方法。注册表对模型隐藏内部工具，例如策略修改、批准、凭据读取和数据库管理。

| 工具 | 输入重点 | 默认行为与完成证据 |
|---|---|---|
| workspace.list | workspace_id、相对path、depth、page_token | 返回限量条目；不遍历敏感路径 |
| workspace.read | path、line range、expected hash可选 | 带行号、文件hash与来源；跨版本读显式提示 |
| workspace.search | pattern、literal/regex、scope、max_results | 有时间与大小上限；返回路径行号和hash |
| workspace.propose_patch | file hash、patch内容 | 生成不可变diff artifact，不修改用户原目录 |
| workspace.apply_patch | patch artifact、old hash、目标工作树 | 验证旧hash后原子应用；记录before/after和backup |
| process.run | executable、argv、input snapshot、backend、limits | 隔离执行；退出码、实际argv、镜像digest与日志 |
| browser.open | profile_id、url、allowed origins | 专用profile；记录page revision与最终URL |
| browser.extract | page_id、snapshot revision、scope | 限量结构化数据，保留external来源 |
| browser.act | page/frame/target、action、input、expected revision | 写动作先审批；点击后验证目标效果 |
| message.draft | 稳定收件人ID、正文、附件refs | 本地草稿；名称歧义必须先解决 |
| message.send | draft hash、destination account、recipient ID | 明确外发审批；receipt或UNKNOWN |
| mcp.call | server_id、tool、manifest hash、args | 经过同一个Broker；不可绕过工具级策略 |

与U1/U2相比，把patch拆为propose与apply，把browser.click扩成带页面版本的browser.act。这些是减少审批后参数漂移和误操作的接口修订，不是增加一个新的Agent框架。

## Workspace与代码编辑

编辑在受管工作树或暂存副本上进行，保留原仓库脏状态。文本patch必须有准确上下文与old_sha256；多匹配、编码不支持或文件已改变时返回RESOURCE_CHANGED，不盲目覆盖。支持UTF-8文本作为MVP边界；二进制写入走artifact导入和独立策略。

审批同时绑定旧hash和确定的新内容Artifact hash。解析或暂存变换在审批前完成；批准后不让通用patch库重新猜测路径或模糊套用。单文件原子替换不等于多文件原子事务，多文件变更保留日志、恢复点和部分提交状态。Git工作树准备也可能触发post-checkout或filter，需隔离或显式禁用并测试这些执行入口。[R20][R21]

语法检查只对支持的语言执行，不能把lint全部通过当作代码正确。验证脚本本身也可能执行仓库代码，因此走隔离器。回滚只针对本次操作的变更；不允许git reset --hard清理用户既有修改，也不自动commit/push。

tree-sitter与grammar通过限额parser worker使用；不执行目标语言程序不等于native parser没有风险。grammar在安装期固定并预置，运行期禁止按需下载。patch-ng是候选，不接管路径守卫、原子提交或多文件失败语义；以实际支持子集测试决定启用。

## Process Executor

生成执行计划时锁定输入快照、可执行文件和参数、容器镜像digest、工作目录、超时、环境白名单、资源上限与网络profile。执行时生成干净HOME和TMPDIR，仅暴露任务工作区。stdout/stderr按字节流处理，保留head/tail与分页句柄，避免一次性读入内存。

普通只读系统查询也需要固定程序与参数集合；禁止通过白名单解释器拼接任意脚本绕过策略。包安装与依赖解析是另一个有网络副作用的操作，不由失败测试自动触发。返回非零退出码是工具结果，不自动升级权限。

默认超时为60秒，用户批准的长任务可提高到10分钟；这些是可配置起点。timeout、用户取消、预算耗尽和daemon退出都传播到worker，并在grace period后由supervisor回收。被终止的进程可能已经生成部分产物，须标注完整性。

## Browser Executor

首版使用直接Playwright原语与OpenBot专用user-data目录。用户在这个profile中手动登录；不自动复制日常Chrome profile、解密cookies或接管任意CDP端口。Playwright官方明确警告默认Chrome用户目录不适合直接自动化。[S07]

每次浏览器提案引用page_id、frame_id、snapshot_revision、origin与具体locator。截图坐标仅在后续Computer Use阶段启用，并必须包括scale、viewport、display_id和有效期。页面发生导航或DOM显著变更时重新观察；旧页面的element_index不能跨任务复用。

网络访问默认限制协议与域名。导航、重定向、popup、iframe、下载、上传和所有subrequest都进入网络策略；阻止file、内部地址与元数据地址。仅用Playwright BrowserContext.route / Page.route不能宣称是抗恶意网页的完整网络隔离；需要隔离网络后端时未就绪则不开放该类任务。

锁定的Chromium启动组合须显式启用并验证sandbox，不能因启动失败静默加入no-sandbox。Playwright的应用层route可能遗漏Service Worker处理的请求；选择阻断/管理Service Worker并结合真实出口边界验证，不能只看路由回调计数。非Chromium与各平台另列能力，不从一个flag推导全部浏览器保证。[R18]

浏览器会话含用户登录态，操作日志与截图可能含个人数据。默认不把整屏截图发飞书，只展示经筛选的目标区域或本地预览；登录、MFA和验证码交给用户完成，不把这些信息写入长期记忆。

## MCP Client

MVP先支持经固定版本安装的stdio server；Streamable HTTP作为单独后续能力，可在M3选做一个测试server作为兼容验证。支持版本组合写入compatibility manifest，使用SDK协商，不把特定旧版本或SSE写成唯一协议。[S05]

安装与运行分离：运行任务时不能uvx/npx下载latest。安装需本地同意、依赖锁和manifest校验；server进程在隔离环境，不能继承模型key与飞书secret。未知工具结果schema、超大返回或工具列表变化立即停止该server的写能力。

## 模型网关

| 能力 | 统一设计 |
|---|---|
| 消息表示 | Text、ImageRef、ToolCall、ToolResult，明确工具call_id |
| 流式输出 | normalized delta与final事件；半包参数不执行 |
| 工具参数 | 完整JSON后做schema校验；未知字段、NaN、重复key按合同处理 |
| 错误 | Authentication、RateLimit、Timeout、ContextLimit、MalformedOutput、Unavailable |
| 用量 | provider/model/version、prompt/output tokens、cached tokens若可得、估算标识 |
| 隐私 | 每次请求记录数据类与允许provider；禁止local模式自动云回退 |
| 兼容 | 一套真实云provider加一个本地provider作为MVP基线；各自有能力矩阵 |
| 重试 | 对模型请求独立重试和计费；不因此重放工具动作 |

适配器显式管理SDK重试，默认关闭SDK内建重试，由OpenBot作为唯一请求重试负责人。每次实际调用计入预算，断流后的费用不直接按零结算。只允许基础请求API，不调用官方SDK中的tool_runner、Agent Runner或自动执行hook；半包参数不创建可派发动作。[R03][R04]

本机Ollama地址可能路由云能力。LOCAL_MODEL/OFFLINE需验证所选模型、服务配置及模型服务出口；无法证明本地执行时禁用该保证，不以localhost或模型名过滤代替验证。SDK、词表、价格数据和模型资产分别锁定。[R05]

第一版不做多Agent swarm或隐藏的planner/editor自治链。一次任务采用单控制循环，在需要时添加无执行权限的规划或审阅模型。其输出仍是建议，与普通模型输出相同地进入policy。

上下文由用户目标、必要系统约束、当前任务状态、已批准范围、相关文件片段和最近工具结果构成。大产物通过分页读取；预算按token与字节双控；压缩摘要保留source refs和重要约束。拒绝把API key、完整cookie或secret传入模型。

预算执行采用reserve-then-settle。开始模型或工具调用前预留最大成本，完成后按实际用量结算；超时账单未知时保守保留或标记待结算。重复相同提案、连续同一错误和空转轮次达到阈值时PAUSED并说明原因。

CR-03 派发前预算合同：RuntimeBudget 必须严格解析权威持久回执，只有 `admitted` 为 JSON 布尔值 true 才正常返回；其余或无效回执抛固定 `BUDGET_ADMISSION_DENIED`，不得调用 transport 或为不存在的预留执行 settle/unknown。额度、时间、调用次数和并发占用导致的 PAUSED / paused_reason 保留。OpenAI-compatible 每次 HTTP attempt 预留 `max(调用方下限, 完整出站 JSON 的 UTF-8 byte bound + framing margin + 256 输出额度)`；完整 JSON 包含所有历史、工具结果和实际发送的完整工具 schema，使用与 SDK/httpx 一致的紧凑 UTF-8 序列化。`reserved_cost_units` 是下限而非完整请求估算，runtime 的 0 表示无额外下限，不代表免费请求。映射词表通过 hash 校验仍不能把 UTF-8/4 估算当上界；保守预留使用字节界，估算不声称精确计费。已有供应商 usage 结算和 UNKNOWN 预留保留不变；未知价格不得推定为免费，也不新增下载、重试或自动压缩。

## Skills与记忆的后续边界

Skill是可版本化的说明与工具约束，不是扩大权限的脚本入口。导入Skill保留来源、版本、license和capabilities；技能文字不能增加工具授权。自动生成技能先进入draft，不能自动安装并执行。

记忆只存可核对的偏好、项目事实和用户明确确认的信息；绑定owner、workspace、source event、有效期和删除状态。不能从恶意网页推导“用户允许发送所有文件”，不能跨workspace默认召回敏感事实。需要embedding时另立性能与隐私ADR。


## 观察结果的分类继承

worker的ToolResult是未受信输入。Broker依据权威Operation、resource snapshot与artifact元数据生成内部Observation，注入provenance和data_class，第三方工具不能自称PUBLIC而降低分类。拼接、摘要、分页读取和长期记忆继承输入中最严格的数据类别与来源限制；缺少分类时默认SENSITIVE并拒绝自动外发。

公开SSE、飞书卡片、日志和ApprovalPreview是分别过滤的投影，不直接序列化内部Observation。ModelGateway发送前按实际选入上下文的分类再次检查出口；对SECRET值本地预览也只显示存在和用途，不展示值。
