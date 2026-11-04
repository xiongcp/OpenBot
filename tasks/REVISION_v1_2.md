# OpenBot v1.2 任务修订说明

日期：2026年11月4日 · 基线v1.1 → v1.2

本轮把新增组件复用报告转化为任务级实施和验收边界。原88项稳定ID及阶段保留，新增8项，合计96；全部TODO。组件的实际准入资格仍为NOT_RUN，计划文件完成不等于软件已开发或组件已测试。

## 变更统计

| 项目 | 结果 |
|---|---:|
| 原任务保留 | 88 |
| 新增任务 | 8 |
| 删除任务 | 0 |
| 原任务执行合同/验收/依赖等有修改 | 76 |
| 原任务仅补来源、设计引用及复用元数据 | 12 |
| 所有任务 | 96 |
| 原依赖删除 | 0 |
| 新增依赖边（含新任务自身依赖） | 75 |

阶段分布：M0=13、M1=37、M2=11、M3=25、M4=4、P2=6。精确字段before/after、变更类别、依赖增量和哈希在 [revision_delta.json](revision_delta.json)。最终实施事实源为 [backlog.json](backlog.json)，可读版本为 [TASKS.md](TASKS.md)。

## 8项新增任务

| ID | 阶段 | 标题 | 独立职责 |
|---|---|---|
| [OB-089](TASKS.md#ob-089) | M0 | 建立组件准入目录和分阶段依赖门禁 | 把候选来源/许可/阶段选择变成机器可检查门禁；不等同OB-004人工核验。 |
| [OB-090](TASKS.md#ob-090) | M0 | 验证Schema与JCS标准合同向量 | 标准Schema/JCS向量与深层不可变；Python权威，真实第二实现才跨实现比较。 |
| [OB-091](TASKS.md#ob-091) | M0 | 交付最小claim/dispatch崩溃协议PoC | M0只用FakeClock/SQLite/JCS/MockWorker尽早验证故障协议；不代替OB-029。 |
| [OB-092](TASKS.md#ob-092) | M1 | 建立组件副作用和重试取消故障契约 | 可复用副作用/请求重试/取消合同；实际SDK随所属任务逐个证明。 |
| [OB-093](TASKS.md#ob-093) | M1 | 验证首发OS的Supervisor与隔离后端能力 | 首发OS实际锁/进程/容器PoC；其他OS由原任务独立验证。 |
| [OB-094](TASKS.md#ob-094) | M2 | 审查飞书模板的最小源码复用 | 飞书模板比较并决定NO_COPY或有限摘取；不强制复制或整仓安装。 |
| [OB-095](TASKS.md#ob-095) | M3 | 审查DOM提取脚本的最小源码复用 | DOM代码比较并决定NO_COPY或有限摘取；不引入browser-use自治循环。 |
| [OB-096](TASKS.md#ob-096) | M3 | 验收全量交付资产来源与供应链 | M3覆盖包与非包资产的来源/SBOM/NOTICE/hash/离线首用；签名仍M4。 |

## 主要采纳边界

- 控制面、23表、14API和四对象状态协议保持自有权威；依赖只封装协议/解析/驱动/界面原语。
- M0不一次安装全部候选。组件引用不等于准入；NOT_RUN、REFERENCE_ONLY和延期项不能自动变成runtime。
- SDK只允许基础请求API，关闭隐藏重试，禁自动工具helper、未纳管托管工具/remote MCP；localhost本地服务仍需云路由与egress证据。
- WriterCommand稳定请求ID和实际持久结果独立于caller等待取消；备份保留secret_ref，排除真实秘密并保护Artifact GC。
- 补丁批准前冻结old/new hash和确切新字节，审批后不再fuzz/纠正换行；OB-034自有journal，OB-035扩展语言验证与恢复。
- 原生执行/浏览器逐OS/backend验证：父子不争同一排他锁，Windows用户会话独立，Chromium sandbox和Service Worker显式处理，容器独立回收。
- detect-secrets仅辅助离线检测，网络验证/动态插件和外部allowlist不可改变出口；不继承固定窗口/100%保证。
- NO_COPY只需明确比较与理由；实际摘取才增加commit/path/hash、LICENSE/NOTICE、差异与回归义务。

## 原任务逐项修改映射

本表归纳修改原因；完整旧值/新值均在revision_delta.json。原任务76项执行合同修订，另外12项保留执行合同，仅丰富复用边界、source_basis和docs_refs。

| ID | 任务 | 修改类别 | 本轮要点 |
|---|---|---|
| [OB-001](TASKS.md#ob-001) | 冻结用户场景与MVP边界 | 元数据/边界补充 | 保留单owner/profile/device和阶段边界；把组件建议与已准入实现分开，复用不扩大产品范围。 |
| [OB-002](TASKS.md#ob-002) | 定义信任边界和动作副作用类别 | 执行合同修订 | 明确任何组件、源码片段、重试器、MCP hints均不拥有身份/授权/派发权；增加组件主动联网、执行、下载和遥测威胁。 |
| [OB-003](TASKS.md#ob-003) | 冻结daemon与客户端生命周期 | 执行合同修订 | 生命周期ADR不变；锁/用户服务/进程监管允许复用经过OB-093实测的OS原语封装，不许宣称通用crate自动保证整树清理。 |
| [OB-004](TASKS.md#ob-004) | 核验依赖和许可证 | 执行合同修订 | 核验当前阶段最小组合；后续候选不提前安装或标已锁定。command-group不新增默认依赖；许可证按具体文件/版本/分发方式评估。 |
| [OB-005](TASKS.md#ob-005) | 建立最小仓库和工具链 | 执行合同修订 | uv及必要开发工具先锁；仅安装当前bootstrap需要的批准依赖，禁止M0一次uv add全部候选；CI从第一批PR执行组件清单一致性。 |
| [OB-006](TASKS.md#ob-006) | 定义事件与命令协议 | 执行合同修订 | 用Pydantic/jsonschema做边界校验，领域对象深层不可变；拒绝未知权威字段、重复JSON键，完整合同一致性在OB-090验证。 |
| [OB-007](TASKS.md#ob-007) | 定义工具和模型Provider契约 | 执行合同修订 | Provider/Tool合同保留自有权威字段；完整Draft2020-12验证、明确format策略、只用本地受控refs；半包或schema失败无派发。 |
| [OB-008](TASKS.md#ob-008) | 定义配置与网络模式 | 执行合同修订 | 配置/目录原语可复用；M0定义模式和runner禁云/egress资格合同并用fake验证，真实本地证明到OB-026完成，localhost不单独作保证。 |
| [OB-009](TASKS.md#ob-009) | 统一错误与时钟语义 | 执行合同修订 | 错误/UTC/单调钟语义自研；SDK timeout/取消映射不得直接等于可重试或已回滚。 |
| [OB-010](TASKS.md#ob-010) | 建立确定性系统测试夹具 | 执行合同修订 | pytest/respx/hypothesis按开发组准入；夹具计数真实HTTP尝试与外部副作用，能模拟返回前成功、调用方取消后提交、SDK重试。 |
| [OB-011](TASKS.md#ob-011) | 实现带版本的数据库迁移 | 执行合同修订 | 优先标准库sqlite3，aiosqlite仅经过PoC后可选；顺序checksum迁移自有，禁止ORM隐式写入/级联或无理由再加迁移框架。 |
| [OB-012](TASKS.md#ob-012) | 实现串行写事务与数据库背压 | 执行合同修订 | sqlite3默认、aiosqlite可选；完整WriterCommand事务由唯一writer独占，稳定request_id关联持久结果，caller取消不等于回滚。 |
| [OB-013](TASKS.md#ob-013) | 实现持久inbox与作用域去重 | 元数据/边界补充 | 持久作用域去重与ACK提交边界不变；不能改用SDK内存去重。 |
| [OB-014](TASKS.md#ob-014) | 实现任务状态与事件原子提交 | 执行合同修订 | Task、状态版本CAS、event/outbox同事务保留自研；不得交给外部Agent状态机。 |
| [OB-015](TASKS.md#ob-015) | 实现单实例daemon和调度租约 | 执行合同修订 | OS锁候选filelock/fd-lock等只能封装底层锁；profile唯一实例、epoch/fence/旧worker隔离自研。 |
| [OB-016](TASKS.md#ob-016) | 实现执行资源锁与会话排队 | 元数据/边界补充 | 资源锁与UNKNOWN quarantine保持权威账本定义，库的进程内mutex不替代持久资源隔离。 |
| [OB-017](TASKS.md#ob-017) | 实现动作意图与执行attempt日志 | 元数据/边界补充 | 保持Operation级provider幂等键、Attempt级dispatch_id与CONSUMED不可逆；组件自动重试须映射到受控尝试而非绕开账本。 |
| [OB-018](TASKS.md#ob-018) | 实现审批决定与一次性授权 | 执行合同修订 | Python为binding摘要权威，复用标准JCS与深层不可变字节；标准向量验证，不强制UI另写JCS。 |
| [OB-019](TASKS.md#ob-019) | 实现执行前授权claim和再校验 | 元数据/边界补充 | claim及CLAIMED→DISPATCHING两短事务自研，取消/epoch/resource复核不变；任何库不得在第二事务提交前发外部请求。 |
| [OB-020](TASKS.md#ob-020) | 实现按副作用类型恢复 | 元数据/边界补充 | UNKNOWN/RECONCILING、证据核对、资源quarantine及唯一恢复器安全重试不变；人工文本success不能改账本，CONSUMED不退APPROVED。 |
| [OB-021](TASKS.md#ob-021) | 实现durable outbox及投递状态 | 执行合同修订 | outbox语义/调度自研；SDK退避仅在已审定投递类型内由一个所有者执行，计数可见，不能假称远端exactly-once。 |
| [OB-022](TASKS.md#ob-022) | 实现取消和停止传播 | 执行合同修订 | 取消先落盘、派发前再查；库取消不等于效果撤回，仍可能UNKNOWN。 |
| [OB-023](TASKS.md#ob-023) | 实现任务预算和熔断 | 执行合同修订 | 预算账本自研；tokenizer按模型选择、离线资源需预置与校验，不能把OpenAI词表当全模型精确计数；重试每次计费尝试都纳入预算。 |
| [OB-024](TASKS.md#ob-024) | 实现上下文快照与摘要 | 执行合同修订 | 上下文裁剪/provenance/污点继承自有；复用tokenizer不替代上下文授权，也不额外引入Agent memory框架。 |
| [OB-025](TASKS.md#ob-025) | 实现首个云模型适配器 | 执行合同修订 | 优先官方openai异步SDK+薄转换；显式关闭或统一管理SDK内建重试，禁止叠加tenacity；fake HTTP计数、流中断/取消/半包/usage缺失契约齐全。 |
| [OB-026](TASKS.md#ob-026) | 实现Ollama或第二Provider | 执行合同修订 | Ollama SDK或httpx择一；loopback可能转云，验证model/runner配置与实际出口，不以名称或地址推断本地。 |
| [OB-027](TASKS.md#ob-027) | 补充Anthropic原生Provider | 执行合同修订 | Anthropic仅P2基础请求API；禁止tool_runner及未经纳管的Provider托管工具、remote MCP和隐藏重试。 |
| [OB-028](TASKS.md#ob-028) | 提供CLI任务和审批操作 | 执行合同修订 | Typer/Rich/httpx可复用；命令语义和审批预览不变，只有认证API访问，无SQLite旁路，JSON输出可稳定测试。 |
| [OB-029](TASKS.md#ob-029) | 交付首条持久化垂直切片 | 执行合同修订 | 完整M1 API/权限/Artifact/真实受限执行集成不变；OB-091承担早期MockWorker协议PoC，演示仍可FakeProvider/OFFLINE。 |
| [OB-030](TASKS.md#ob-030) | 实现数据库备份恢复与保留策略 | 执行合同修订 | 使用SQLite backup接口；manifest/密钥排除/引用保留与恢复判定自研，不因库copy成功就宣称备份一致。 |
| [OB-031](TASKS.md#ob-031) | 实现确定性策略评估器 | 执行合同修订 | 不默认引入OPA/Casbin；pathspec只能辅助忽略/展示规则，不得作为安全路径白名单或授权判定。 |
| [OB-032](TASKS.md#ob-032) | 实现工作区路径与文件访问守卫 | 执行合同修订 | 路径/句柄守卫继续自有；Win32/OS库为原语，不能机械删除\?\前缀或仅字符串normalize后放行，保留拒绝与原生攻击语料。 |
| [OB-033](TASKS.md#ob-033) | 实现list read search文件工具 | 执行合同修订 | rg --json在受管快照/范围内受控调用，禁用户rg配置/危险链接与环境继承；UTF-8边界不因候选charset/binary包自动扩张；可不加ripgrepy。 |
| [OB-034](TASKS.md#ob-034) | 实现补丁提议与受授权应用 | 执行合同修订 | 解析库不写宿主；审批前冻结old/new hash和确切新字节Artifact，禁止审批后fuzz/换行修正，多文件依变更日志恢复。 |
| [OB-035](TASKS.md#ob-035) | 实现显式语言验证与修改事务 | 执行合同修订 | 只用固定grammar/原生资产，安装期预置、禁网首次parse；独立有界worker承受native解析风险。 |
| [OB-036](TASKS.md#ob-036) | 实现Artifact存储与可信元数据 | 执行合同修订 | hashlib、平台原子文件原语可用；content-addressed对象、fsync/rename、分类/引用和限额自有，不无理由加MIME/对象存储框架。 |
| [OB-037](TASKS.md#ob-037) | 实现统一数据外发策略 | 执行合同修订 | 统一egress守卫仍覆盖SDK/网页/MCP及本地模型runner；审查HTTP客户端、DNS、代理、tokenizer缓存下载；localhost不能证明无云转发，脱敏不能替代出口限制。 |
| [OB-038](TASKS.md#ob-038) | 实现密钥存储与最小注入 | 执行合同修订 | keyring择已验证OS后端；缺服务/锁定/交互错误明确失败，不把任意插件或自制Fernet存储作为自动fallback。 |
| [OB-039](TASKS.md#ob-039) | 实现敏感数据输出过滤 | 执行合同修订 | detect-secrets默认CI辅助，运行时只用离线已审查检测器；关闭网络验证/动态插件，外部allowlist不生效，不承诺128字节/100%。 |
| [OB-040](TASKS.md#ob-040) | 实现结构化进程执行协议 | 执行合同修订 | 容器/进程SDK不能增添未批准argv/env/mount/network；协议仍锁定输入、执行器、镜像与backend。 |
| [OB-041](TASKS.md#ob-041) | 实现worker隔离与资源上限 | 执行合同修订 | 容器backend逐组合认证；容器归属独立于CLI，stop/wait→受限导出校验→remove，无自动host/引擎兜底。 |
| [OB-042](TASKS.md#ob-042) | 实现worker进程树取消与回收 | 执行合同修订 | 仅封装原生原语；command-group不新用。核验Job/进程组/容器最终状态，强杀与协作清理边界明确。 |
| [OB-043](TASKS.md#ob-043) | 实现本地消息草稿 | 元数据/边界补充 | 本地不可变消息草稿、明确收件人与附件hash自有，不复用上游自动发送或首次sender当owner逻辑。 |
| [OB-044](TASKS.md#ob-044) | 实现消息发送用例与受控适配端口 | 元数据/边界补充 | 发送用例仍由Broker批准并判UNKNOWN；SDK只实现transport，M1 fake/M2真实启用次序不变。 |
| [OB-045](TASKS.md#ob-045) | 交付安全工具威胁回归 | 执行合同修订 | 在M1加入导入联网、嵌套修改、隐式重试、非法refs、rg/git配置、parser下载与后端清理失败的可验证用例。 |
| [OB-046](TASKS.md#ob-046) | 发布最小本地Alpha边界说明 | 执行合同修订 | 本地Alpha报告列出启用的精确组件/资源、未支持backend与残余风险；不把候选列表当已实现能力。 |
| [OB-047](TASKS.md#ob-047) | 核验飞书真实租户协议与权限 | 执行合同修订 | 真实租户协议+锁定lark SDK的可重放样例；核验实际callback/传输/权限/时限，测冷启动与阻塞行为，不照抄24.27秒或固定超时。 |
| [OB-048](TASKS.md#ob-048) | 实现安全配对与owner撤销 | 元数据/边界补充 | 只参考配对展示；本地challenge、待确认tenant/app/user与owner授权自有，不复制上游first-user/二维码自动授权。 |
| [OB-049](TASKS.md#ob-049) | 实现飞书WebSocket入站适配 | 执行合同修订 | 用lark-oapi协议能力；独立gateway、单消费者、受限HTTP/inbox ACK边界不变，SDK升级受契约fixture保护。 |
| [OB-050](TASKS.md#ob-050) | 实现飞书审批callback处理 | 执行合同修订 | card callback适配到daemon CAS；所有拒绝/超时/异常返回合法且及时，禁止等待模型/工具或库内队列旁路批准。 |
| [OB-051](TASKS.md#ob-051) | 实现普通卡片与结果回执 | 执行合同修订 | 普通卡片先完成；只有OB-094审过的固定commit模板可移植，模板不得自带网络/Agent/owner逻辑。 |
| [OB-052](TASKS.md#ob-052) | 实现进度卡节流与更新顺序 | 执行合同修订 | card_revision、限流、合并和终态保护继续自有；不能原封不动复制上游内存流式循环。 |
| [OB-053](TASKS.md#ob-053) | 实现CardKit与更新通道降级 | 执行合同修订 | 复用已核验的CardKit构造模式；有效期/次数/权限来自实际平台与协议版本，不照抄报告硬编码28分钟/14天等。 |
| [OB-054](TASKS.md#ob-054) | 实现网关健康探测与重连 | 执行合同修订 | 先检查选定SDK是否仍有问题；通过支持的timeout/session扩展或受控最小补丁处理；初始化与ready时限分开，独立进程watchdog能收回阻塞实例。 |
| [OB-055](TASKS.md#ob-055) | 实现死信检视与安全重投 | 元数据/边界补充 | 死信/通知重投通过application，不让SDK/tenacity重播UNKNOWN业务副作用。 |
| [OB-056](TASKS.md#ob-056) | 飞书端到端真实验收 | 执行合同修订 | 保留真实租户闭环，新增所选SDK的启动、断线、取消与双消费者检测证据，分别报告各计时路径。 |
| [OB-057](TASKS.md#ob-057) | 实现专用浏览器profile与会话锁 | 执行合同修订 | 直接Playwright原语、专用profile；Chromium sandbox显式配置/验证，不能暗加--no-sandbox；外层隔离另证。 |
| [OB-058](TASKS.md#ob-058) | 实现浏览器网络与下载策略 | 执行合同修订 | BrowserContext.route / Page.route仅一层，Service Worker默认阻止绕过或由已验证更强边界覆盖；真实出口与上传下载同验。 |
| [OB-059](TASKS.md#ob-059) | 实现结构化浏览器读工具 | 执行合同修订 | 只采用OB-095核验的DOM只读片段或最小自有提取器；结果带page/frame/revision/provenance，独立预算与输出限额。 |
| [OB-060](TASKS.md#ob-060) | 实现浏览器写动作提案与确认 | 执行合同修订 | 每个浏览器写动作都经Broker、revision复验与OutcomeVerifier；不采用browser-use Agent.run()或多动作批量越权。 |
| [OB-061](TASKS.md#ob-061) | 建立浏览器结果验证回归 | 执行合同修订 | DOM污染/导航/权限变化/点击已成功回执丢失按真实效果计数，驱动返回无异常不能代表用户目标成功。 |
| [OB-062](TASKS.md#ob-062) | 实现MCP版本协商与生命周期 | 执行合同修订 | 采用锁定官方MCP SDK/stdio协议；适配到自有有界进程与流，不默认升级transport或自动安装包。 |
| [OB-063](TASKS.md#ob-063) | 实现MCP注册与工具元数据锁定 | 执行合同修订 | JCS hash覆盖完整manifest、package、命令/env/transport；refs本地化与Draft2020-12校验；list_changed隔离，annotations仅外部数据。 |
| [OB-064](TASKS.md#ob-064) | 实现MCP进程和网络权限 | 执行合同修订 | stdio server必须经已验证隔离后端与Supervisor；SDK派生子进程不准继承全部env，也不能自行触发sampling/Agent loop。 |
| [OB-065](TASKS.md#ob-065) | 建立MCP恶意与故障服务器测试 | 执行合同修订 | 覆盖SDK取消语义、服务端断连、schema/refs洪泛与变更；独立计数请求/效果，执行后断连不自动再执行。 |
| [OB-066](TASKS.md#ob-066) | 实现只读技能指令加载 | 执行合同修订 | 技能来源/版本/license与组件来源台账格式协调，但技能文本不获得依赖准入或权限修改权。 |
| [OB-067](TASKS.md#ob-067) | 交付全MVP能力集回归 | 执行合同修订 | 已选组件的合同/副作用门禁随能力集验证；记录确切组合，不把各库独立通过拼成整系统安全结论。 |
| [OB-068](TASKS.md#ob-068) | 实现用户级daemon安装与卸载 | 执行合同修订 | service-manager仅在已验证launchd/systemd用户级场景复用；Windows用户登录会话独立实现，不用系统服务替代。 |
| [OB-069](TASKS.md#ob-069) | 建立macOS原生运行门禁 | 执行合同修订 | macOS实际arch/OS/钥匙串/原生轮子/浏览器/worker残余均记录；UI不需要的屏幕权限不提前索取。 |
| [OB-070](TASKS.md#ob-070) | 建立Windows原生运行门禁 | 执行合同修订 | Windows原生验证Job创建序列、嵌套/拒绝、中文路径与依赖资产；不用WSL或crate宣传替代证据。 |
| [OB-071](TASKS.md#ob-071) | 建立Linux原生运行门禁 | 执行合同修订 | Linux发行版/服务管理/rootless容器/cgroup与keyring不可用路径明确，其他backend不能因接口相似自动标supported。 |
| [OB-072](TASKS.md#ob-072) | 建立可复现打包与运行资源清单 | 执行合同修订 | PyInstaller onedir是候选打包路线；每OS干净安装、首次离线运行、完整资源清单；可复现性按实测说明，不承诺bitwise一致。 |
| [OB-073](TASKS.md#ob-073) | 实现版本升级和迁移恢复 | 执行合同修订 | Tauri updater只做传输/签名校验，Drain/UNKNOWN处理/DB备份迁移/失败恢复自有；签名升级属M4。 |
| [OB-074](TASKS.md#ob-074) | 完成桌面安装签名与发布供应链 | 执行合同修订 | 保留M4桌面签名、公证、更新信任根/通道；M3基础SBOM/来源与摘要前移到OB-096，不等桌面阶段。 |
| [OB-075](TASKS.md#ob-075) | 实现统一可观测性与诊断 | 执行合同修订 | structlog是格式/上下文管道，跨任务contextvars绑定/清理与脱敏自有；OpenTelemetry按需单独准入，不默认远程exporter。 |
| [OB-076](TASKS.md#ob-076) | 建立真实任务质量基准集 | 执行合同修订 | 记录选定组件、模型、原生资源及样本n；性能、LOC、成本、工期以本机测量和范围为准，不继承报告保证。 |
| [OB-077](TASKS.md#ob-077) | 建立分层CI门禁 | 执行合同修订 | 早期已执行registry/锁/合同门禁，本任务整合阶段矩阵、上游升级fixture、供应链与release gate；不存在M3才加安全测试。 |
| [OB-078](TASKS.md#ob-078) | 建立断网休眠与崩溃浸泡 | 执行合同修订 | 覆盖SDK阻塞、DNS半开、daemon/客户端/容器各类死亡与遗留资源；报告样本和清理边界，不用100%表述。 |
| [OB-079](TASKS.md#ob-079) | 完成上手与故障处置文档 | 执行合同修订 | 列依赖组、安装期资产下载/批准、首次离线启动、缺backend拒绝、组件升级和NOTICE；未验证候选对用户不宣称已支持。 |
| [OB-080](TASKS.md#ob-080) | 完成MVP发布验收与风险登记 | 执行合同修订 | M3基础供应链/离线首用/真实OS支持证据为发布前置；M4签名桌面和P2组件仍后置，不逆向阻塞。 |
| [OB-081](TASKS.md#ob-081) | 在M1实现认证本地HTTP与SSE控制API | 执行合同修订 | FastAPI/Uvicorn/sse-starlette按M1需求择准入；认证、scope、Host/Origin、API用途、SSE一致性/背压/取消仍自有，proxy头不能绕过loopback。 |
| [OB-082](TASKS.md#ob-082) | 实现Tauri任务与审批UI | 执行合同修订 | Tauri v2受限Rust IPC复用，插件逐个准入；WebView无广域token/任意shell，窗口退出不停止daemon；不默认安装所有桌面插件。 |
| [OB-083](TASKS.md#ob-083) | 实现桌面接管与事件回放 | 执行合同修订 | SSE快照重取/只读回放/接管锁仍遵守daemon语义；插件事件不是权威状态。 |
| [OB-084](TASKS.md#ob-084) | 为一个OS实现原生桌面观察 | 执行合同修订 | pywinauto/PyObjC/Portal等单OS选择；权限必须运行时检查并处理撤销，不依据报告声称固定每30天行为，不强绑Tauri。 |
| [OB-085](TASKS.md#ob-085) | 实现受限桌面写动作 | 执行合同修订 | 只复用UIA/AX动作原语，逐动作审批/观察版本/互斥/UNKNOWN不变，不复用UFO推测性多动作自动提交。 |
| [OB-086](TASKS.md#ob-086) | 实现可验证记忆与删除 | 元数据/边界补充 | 未新增memory框架或向量库默认依赖；证据、删除、owner/workspace隔离自研。 |
| [OB-087](TASKS.md#ob-087) | 实现持久定时触发器 | 执行合同修订 | croniter/触发器仅计算时间，zoneinfo/DST/misfire/occurrence唯一性自有；不启APScheduler自动executor，首次使用不下载时区等资源。 |
| [OB-088](TASKS.md#ob-088) | 评估第二设备和团队扩展边界 | 元数据/边界补充 | 第二设备/团队仍仅ADR实验，不为组件复用新增中央服务、共享gateway或权限模型。 |

## 依赖增量与关键顺序

| 任务 | 新增依赖 |
|---|---|
| [OB-005](TASKS.md#ob-005) | OB-004 |
| [OB-006](TASKS.md#ob-006) | OB-089 |
| [OB-008](TASKS.md#ob-008) | OB-089 |
| [OB-011](TASKS.md#ob-011) | OB-091 |
| [OB-015](TASKS.md#ob-015) | OB-093 |
| [OB-018](TASKS.md#ob-018) | OB-090 |
| [OB-025](TASKS.md#ob-025) | OB-092 |
| [OB-026](TASKS.md#ob-026) | OB-092 |
| [OB-027](TASKS.md#ob-027) | OB-092 |
| [OB-028](TASKS.md#ob-028) | OB-092 |
| [OB-029](TASKS.md#ob-029) | OB-036、OB-041、OB-042 |
| [OB-033](TASKS.md#ob-033) | OB-092 |
| [OB-034](TASKS.md#ob-034) | OB-092 |
| [OB-035](TASKS.md#ob-035) | OB-092 |
| [OB-038](TASKS.md#ob-038) | OB-092 |
| [OB-039](TASKS.md#ob-039) | OB-092 |
| [OB-041](TASKS.md#ob-041) | OB-093 |
| [OB-042](TASKS.md#ob-042) | OB-093 |
| [OB-047](TASKS.md#ob-047) | OB-092 |
| [OB-051](TASKS.md#ob-051) | OB-094 |
| [OB-053](TASKS.md#ob-053) | OB-094 |
| [OB-057](TASKS.md#ob-057) | OB-042、OB-092 |
| [OB-058](TASKS.md#ob-058) | OB-041 |
| [OB-059](TASKS.md#ob-059) | OB-095 |
| [OB-062](TASKS.md#ob-062) | OB-092 |
| [OB-063](TASKS.md#ob-063) | OB-090 |
| [OB-064](TASKS.md#ob-064) | OB-042 |
| [OB-068](TASKS.md#ob-068) | OB-093 |
| [OB-072](TASKS.md#ob-072) | OB-089 |
| [OB-077](TASKS.md#ob-077) | OB-096 |
| [OB-080](TASKS.md#ob-080) | OB-096 |
| [OB-081](TASKS.md#ob-081) | OB-092 |
| [OB-082](TASKS.md#ob-082) | OB-089 |
| [OB-084](TASKS.md#ob-084) | OB-089 |
| [OB-087](TASKS.md#ob-087) | OB-089 |
| [OB-089](TASKS.md#ob-089) | OB-004、OB-005 |
| [OB-090](TASKS.md#ob-090) | OB-006、OB-007、OB-010、OB-089 |
| [OB-091](TASKS.md#ob-091) | OB-009、OB-010、OB-090 |
| [OB-092](TASKS.md#ob-092) | OB-007、OB-008、OB-009、OB-010、OB-089、OB-090、OB-091 |
| [OB-093](TASKS.md#ob-093) | OB-003、OB-004、OB-007、OB-008、OB-010、OB-089、OB-091 |
| [OB-094](TASKS.md#ob-094) | OB-004、OB-047、OB-089、OB-092 |
| [OB-095](TASKS.md#ob-095) | OB-057、OB-058、OB-089、OB-092 |
| [OB-096](TASKS.md#ob-096) | OB-004、OB-067、OB-072、OB-089、OB-094、OB-095 |

OB-091只依赖M0合同/夹具/标准向量。OB-029保留原依赖，并新增OB-036/041/042，保证完整M1的Artifact及真实受限执行路径；仍可FakeProvider/OFFLINE演示。OB-034拥有最小journal，OB-035依赖并扩展它，完成条件没有隐性反向边。OB-008的真实runner资格由OB-026验证，不阻塞M0。M3 OB-096核验已建成的产物后阻塞OB-077/080，不等待M4签名。

## 机器字段与PDF同步

新增 `component_refs: string[]`、`reuse_type: string`、`reuse_notes: string[]`。TASKS.md逐卡完整渲染，任务PDF应保留同样字段；旧有id/title/milestone/priority/status/owner_lane/size/req_ids/docs_refs/depends_on/risk/steps/outputs/acceptance/negative/validation/evidence/source_basis继续保留。

component_refs可以引用需要限制或延期的组件，用于审查上下文，不是安装白名单。是否引入以及引入哪个版本/特性，以catalog决策、所属阶段和真实资格结果共同决定。

## 验证与版本依据

- JSON可解析；96个唯一连续稳定ID、全部TODO；每卡2—4实施步骤、至少一个反例及证据；12类需求无空项。
- 原88项ID和阶段保留，原依赖0删除；96/96拓扑覆盖，无环、无未知依赖、无跨阶段逆向依赖。
- component_refs均在52项catalog内；docs_refs均指向现有文件；Markdown任务/RQ锚点与字段内容从JSON生成。
- 同步修正了独立审查发现的M0真实runner提前依赖、OB-034隐性反向依赖、secret_ref保留、host fallback旧句和PENDING/version撤销语义。
- 本轮检查针对设计交接包，未把资料研究或源码阅读记为产品运行通过。

基线backlog SHA-256：`dee05cd37d134fa53d3ed767f900ff104f95edd964e2a2a5c0abfdef97002e04`。

目标backlog SHA-256：`343bc2c906a0f19539db16609498bf63f796069c75995944833089a6ae550e20`。

源材料：U1《OpenBot 开源桌面智能体深度研究报告》、U2《OpenBot 架构设计与任务规划》、新增U3《OpenBot 开源组件复用评估》；具体页码保留在各卡source_basis。详细事实取舍和官方证据见 [14_revision_v1_2.md](../docs/14_revision_v1_2.md)。
