> 历史完整审查：本文固定于2993593a。交付前增量620311b4及最新CI见docs/01_current_state.md、sources R24和source_audit_late_mcp.md；不要把本文旧CI计数当作最新结果。

# OpenBot 最新源码审查与核心实施边界

审查日期：2026-11-05。本文是只读源码审查和实施建议，没有修改仓库、发消息、执行产品测试或提交代码。

## 1. 固定基线与结论

- main 比较基线：98ee0365a335ed297337c3c0c9aaf9cbf3d5883e；分支存在不等于应用正式发布。
- 本轮活动分支：codex/agent-client-observability，固定 SHA 2993593a5bd010b85d76a6ca9e279fc4977718dc。
- [固定比较](https://github.com/xiongcp/OpenBot/compare/98ee0365a335ed297337c3c0c9aaf9cbf3d5883e...2993593a5bd010b85d76a6ca9e279fc4977718dc)：活动分支领先 3 个提交、落后 0 个提交，18 个文件变化。新增生产模块是 ClientStateService；其余变化主要为合同、计划、证据说明与测试。CLI、Local API、runtime 恢复、密钥、MCP、Browser 的生产代码没有在这 3 个提交中改变。
- 已读取根 AGENTS.md / CLAUDE.md；这两个文件在比较范围内没有改变。本文坚持单 Broker、审批不等于执行、UNKNOWN 不盲重放、所有事实须标明证据层级，不把计划文档中的未来文件算成实现。
- 最新 CI 状态由主审查者读取并提供：contracts run 41979113332，Darwin arm64 341 passed / 3 skipped，Linux 339 passed / 3 skipped / 1 deselected，Windows 41 passed（仅 contracts）。3 个 skip 涉及可选 SDK 组和原生 Docker 显式开关。它们不是云模型、容器或全部 macOS 产品路径已经通过的证据。
- 现有旧任务状态为 DONE 4、VERIFIED 12、IN_PROGRESS 67、BLOCKED 3、TODO 10；状态口径不同，不据此计算产品完成百分比。

**核心判断：不是从零重写，也不是已经只剩界面打磨。** 持久 inbox、串行 Writer、Task/Operation/Approval/Attempt、预算、资源锁、文件守卫和多种适配器已有实质实现。当前缺口集中在生产组合根没有把这些模块连成可恢复的真实 Agent 链路，以及若干已存在模块仍把调用者声明当作隔离、结果或生命周期证明。

活动分支的 ClientStateService 是有价值的新基础：配置 CAS、预览 hash、权限复核、稳定 run_id、运行配置快照、脱敏事件和有界回放已经存在。它尚未被 CLI/API 装配，不等于已交付设置页面、事实图或真实 Agent。README 现在也明确说明这个范围。[S01][S02][S03]

## 2. 证据层级及不应重复开发的部分

| 层级 | 已有事实 | 仍不能推导的结论 |
|---|---|---|
| 合同/应用服务 | TaskStateService.complete 会检查未决 Operation/Approval/预算、产物归属和结果要求；DispatchService 在 claim/dispatch 复核授权、取消、epoch、资源租约 | 生产 daemon 已自动执行任务，或真实副作用已经由这些服务完整收口 |
| 本地真实传输 | CLI 实际启动 daemon、走认证 TCP HTTP；MCP 已真实 stdio initialize；Browser 已启动真实 Chromium dump-dom | MCP 已容器隔离，Browser 全部子请求已封堵，真实浏览器动作已执行 |
| 模型模块 | OpenAI 文本 SDK transport 有关闭重试、总 deadline、取消、usage 校验；Ollama 有实际 HTTP probe/chat | function-call transport 已接入生产 loop，LOCAL_MODEL 或 OFFLINE 出口证明已完成 |
| 配置/可视化基础 | ClientStateService 和测试存在；配置保存与 run 快照实际持久化 | 运行中限制立即生效、客户端路由存在、Tauri 可运行、图中的任意节点都绑定真实 domain 事实 |
| 仓库证据文件 | client-state.md 明确记录基础测试，并排除 Agent/MCP/Tauri/Feishu 真实资格 | 本轮审查执行过那些测试，或分支成果已经合并发布 |

上述现有服务应被复用和连接；新任务应写成补齐组合、边界修复、真实验证，而不是建立第二套状态机或事件库。[S04][S05][S06][S07][S08]

## 3. 十二项关键缺口

以下 AR-G 编号是审查编号；新实施任务使用 V1-010–029，并继续映射原 OB 任务，不更改原任务编号或 DoD。

### AR-G01：生产 AgentRuntime 尚未装配，已实现的状态服务没有自动驱动链路

**源码事实。** cli.py 的 serve_daemon 装配了 inbox、任务、审批、dispatch、recovery、artifact 等服务并提供 HTTP；没有 ClientStateService、Provider、Skill、执行器和持续调度 loop 的组合。新计划中的 agent_runtime.py、stream_transport.py、container_read.py、client_routes.py、live_gateway.py、apps/desktop 在固定树中不存在。SkillLoader 验证了元数据和能力，但把传入 sha256 放入 Manifest，没有计算 instructions_markdown 的实际字节摘要。[S02][S09][S10]

**影响与推断。** 接收 Task 成功只能证明入队；不能展示“模型正在思考/工具已运行”。若后续直接把工具返回接到 UI，可能绕过已有 Broker 边界。未核验的 Skill 内容 hash 也不能证明运行时用到的是准入版本。

**最小切片。** 先交付单 profile、单 owner、一个 active run、有限 max_steps 的 daemon runtime：受信身份 → Inbox → Scheduler → run/settings/context 快照 → 真实模型 proposal → Operation/Broker → 执行器 → 可信回执 → TaskStateService.complete。只读 fixture 最先接通，写工具保持禁用直到各自门禁完成；Skill 的实际字节摘要进入 context 和审计。

**优先级/映射。** P0，V1-010；依赖范围和证据口径 V1-001/003。原 OB-015/016/023/024/029/066。

**验收。** 从外部客户端提交目标，不调用测试专用状态推进；独立接收端和 DB/audit 关联显示同一 run 真正经过模型与只读工具；预算耗尽、取消或无能力时停止，不能越过 max_steps；修改 Skill 字节而保留旧 hash 必须拒绝加载。

### AR-G02：模型 proposal 适配器尚缺生产流式传输、总期限和及时取消的一致实现

**源码事实。** openai.py 是真实、仅文本的 SDK transport，显式 max_retries=0、trust_env=False、asyncio.timeout、inflight task.cancel 和 SDK.close。openai_compatible.py 有完整 JSON tool assembly、schema 检验、出口和每 attempt 预算，但 transport 契约返回 list[bytes]，generate 在 L180 等完整列表；计算 remaining_s 后没有围住真实请求；cancel 只向集合加 ID，close 只设标志。持久 BudgetService 存在，但不是这套 RequestBudget 接口自动持久化的保证。[S06][S07][S11]

**影响与推断。** 这不是“没有 Provider”；是两套互补模块尚未合成一个生产能力。挂起的 stream transport 可以使 cancel 不能及时生效；部分模型请求发生后 usage 未知不能自动当作零成本或直接重试。不能依据可选包可导入把真实 SDK 故障用例判 PASS。

**最小切片。** 合并成一个经过准入的实际 SDK 流式端口，逐块有界解析，连接/首包/空闲/总 deadline 明确，取消能关闭实际请求并等待终止；RequestBudget 适配到持久 BudgetService，同一 model_request/attempt 具备预留、已知结算、UNKNOWN 三态。继续禁止 SDK 自动工具、环境代理和多层重试；仅 Gateway 管理已限定的重试。

**优先级/映射。** P0，V1-011/012，原 OB-023/025/092。

**验收。** 独立 HTTP 接收端记录真实请求次数；429/503、首包前断线、首包后断线、缺 usage、取消、总 deadline 分别对应明确次数和预算状态。取消一个真实挂起请求后，在规定期限内无新增请求；真实云调用仅用授权 synthetic 数据，保存 provider request ID/usage 和费用口径，不假装终止本地请求等于服务端没有计费。

### AR-G03：恢复隔离证明仍来自客户端布尔值，真实崩溃夹具不足

**源码事实。** Local API recover-epoch 使用 bool(body.get("old_epoch_isolated", True))；RecoveryService 据此标记旧 epoch STOPPED 并允许新 epoch 接管。UserDaemonInstaller.restart_daemon 也提交 True。Supervisor 有真实进程组信号，但 current_start_token 和 container_reclaimed 仍是调用者参数。旧 vertical_slice 的“kill worker”杀的是独立 sleep 子进程，随后正常 writer.close 再打开 DB；效果账本由测试函数自己递增。[S12][S13][S14][S15]

**影响与推断。** owner 权限不是旧执行域已经停止的证明。接通真实写动作前必须把该信任缺口封住。现有测试可证明状态服务行为，不证明正在派发的 daemon 在进程级崩溃后的真实恢复。

**最小切片。** HTTP 只接受“请求恢复”，由 Supervisor 获取 OS 进程创建身份、容器/执行域状态和旧 epoch fence，产生内部不可由客户端伪造的 recovery evidence。不能确认旧域退出就 quarantine 并拒绝新派发。增加真实 daemon PID 的确定性 kill 点：claim 前后、DISPATCHING 提交后/发送前、服务端 effect 后/receipt 前、结果事务提交前后。

**优先级/映射。** P0，V1-012/013/014/029；原 OB-020/022/029/042/068/078/091/093。

**验收。** 两个独立进程分别保存效果与状态；杀真实 daemon 后无需正常 close，重启能保留 UNKNOWN 和资源封锁；旧 worker/伪 PID token/未回收容器不得获得新 dispatch；新 Task/Operation ID 也不能绕过同资源 quarantine。不得用 sleep 猜测竞态，使用 socket/pipe/event 屏障。

### AR-G04：审批预览需要真实可审核内容，客户端不能变成第二个控制内核

**源码事实。** server.py 的 ApprovalPreview 目前 effect 固定 EXTERNAL_WRITE，args_preview 通常为字符串 preview，SECRET 为脱敏占位。原始审批 hash、nonce 和 CAS 机制存在，DispatchService 也已做授权复核。[S05][S12]

**影响与推断。** 用户无法据占位预览理解究竟改哪个文件、向谁发送什么、访问哪个域名。不能把“点了批准”显示成“已执行”；客户端请求不能设置 epoch 证明、执行结果或任意 Task 状态。

**最小切片。** 从不可变 Proposal 生成独立 ApprovalPreview DTO，包含 effect、精确目标、旧/新摘要、diff/内容安全预览、网络/费用影响和 TTL；必要敏感值通过受控本地细节入口查看，不泄露到卡片/日志。限定公开路由只表达用户意图，内部 claim/dispatch/result 状态变更只供可信 runtime 调用。

**优先级/映射。** P0，V1-023/025；原 OB-018/019/028/050/081/082。

**验收。** UI/CLI/飞书三入口显示同一 Proposal 的可审核目标与摘要；批准后修改目标、政策、owner、workspace generation 或工具摘要均被拒绝；过期/撤销/重复卡片不触发动作；SECRET 不出现于 DOM、诊断和卡片载荷。

### AR-G05：密钥 Broker 已存在，但 macOS 写入方式会把 secret 放进进程参数

**源码事实。** MacOSKeychainCliBackend.set_secret 通过 security add-generic-password ... -w value 调用 subprocess；SecretBroker 的权限、handle TTL、attempt 绑定和 minimal_child_spec 已有实现。最新客户端设计明确首轮 secret 从非回显 CLI 输入进 daemon 内存，Tauri WebView 不接收，跨重启保留是独立切片。[S16][S03]

**影响与推断。** raw argv 是可被进程观测/诊断采集的泄漏面；本轮没有在真实系统复现泄漏，属于确切源码风险。不能因为用了 Keychain 名称就宣布密钥注入全部安全。

**最小切片。** 先沿用批准的非回显内存注入，禁用不安全的持久写入路径；需要 v1 持久保存时，通过无明文 argv 的原生凭据接口实现同一 Broker 端口，并对真实子进程使用 minimal_child_spec，不能只在单元测试调用它。

**优先级/映射。** P0，V1-015/028；原 OB-038/039/092/093。

**验收。** canary secret 不在进程列表、argv/env、WebView、DB、trace、崩溃/诊断包中；缺凭据明确需要重新输入，不从环境、任意文件或模型文本兜底；锁定 Keychain/用户拒绝授权不降级明文。

### AR-G06：MCP 真实握手已实现，但 deadline、响应语义和实际隔离仍有缺口

**源码事实。** client.py 已真实 Popen + initialize + notifications/initialized + 有界逐字节读取，不能沿用旧“仅字符串协商”的结论。init_timeout_ms 字段没有驱动阻塞读期限，stderr 管道未见持续排空；call_tool_stdio 将非空返回标为 OK，未核对 JSON-RPC id/error/通知。Manifest 检查 digest 格式与 executable basename，但真实启动使用 argv，未见实际包字节摘要与执行目标绑定。McpIsolatedExecutor.prepare_dispatch 只返回计划，尚不是容器启动器。[S17][S18]

**影响与推断。** 恶意/故障 server 可挂住初始化或让错误/串线响应被当成功；manifest 合格不等于启动了锁定程序。开始运行第三方 MCP 前必须让实际隔离证据和协议结果进入 Broker。

**最小切片。** 分两步：修 JSON-RPC 生命周期与 bounded read/write/deadline/stderr drain；再实现已准入容器/隔离 transport，锁包字节、镜像 digest、argv、mount、network、能力 manifest、runtime epoch 和 Attempt dispatch 身份。默认禁 sampling/elicitation/自动安装；无后端时 CAPABILITY_UNAVAILABLE。

**优先级/映射。** P0，V1-016/017；原 OB-062/063/064/065/092/093/096。

**验收。** 不返回换行、伪 id、error/notification、超长 stdout、大量 stderr、半包、进程退出逐项有确定期限和状态；真实 MCP 只能读 fixture 挂载，不读 HOME、不出网、不启动未准入程序；工具结果丢失按副作用处理 UNKNOWN，不自动重发写动作。

### AR-G07：Browser 真进程与锁已增加，仍需实际出口拦截、动作和独立结果核对

**源码事实。** BrowserSessionManager 已有 POSIX flock、专用 profile 和真实 Chromium dump-dom；run_headless_dom_dump 只先检查初始 URL 的 hostname，没有连接 BrowserNetworkPolicyEnforcer 对重定向/子资源进行实际拦截。隔离结构仍由布尔 attestation 驱动；Chromium 子进程没有使用 SecretBroker 的子环境构造。BrowserActions.execute_approved_action 的结果取决于传入 driver_outcome 枚举；verifier 是 fixture 级回归。[S19][S20][S21]

**影响与推断。** 只检查初始 URL 不能证明浏览器实际网络符合策略；动作函数返回 SUCCEEDED 不能证明网页发生预期变化。这里是静态缺口，不是本轮实测 SSRF/越权。

**最小切片。** 真实 BrowserBackend 绑定经过核验的隔离 profile 与浏览器资源摘要，执行每请求出口控制和明确的 Service Worker/WebSocket 策略；先交付只读访问/提取/下载隔离，再接批准后的有限写动作、真实 ElementRef 复核和独立结果 verifier。保留专用 profile 锁，禁止个人 profile 和未审 CDP 接入。

**优先级/映射。** P0 出口，P1 写动作能力；V1-018/019；原 OB-057–061/093/095/096。

**验收。** 实际网络观察覆盖初始导航、重定向、子资源、弹窗、Service Worker、WebSocket、DNS 地址变化与内网目标；实际写动作超时不能宣称失败无效果，而进入 UNKNOWN；DOM 金额/接收方改变必须停止，结果用目标服务账本或页面稳定回执独立核对。

### AR-G08：文件补丁实现应保留，但跨崩溃 journal 和生产结果收口仍需补齐

**源码事实。** WorkspacePatchTool 已固定 old/new hash、artifact 内容、父目录快照并逐文件原子写；明确不声称跨文件原子。PatchCommitJournal._flush 直接 write_bytes，备份也直接 write_bytes；未见 flush/fsync + 临时文件替换的持久协议，构造器总建新目录，恢复主要使用当前对象内存 entries。vertical_slice 用测试 SQL 直接完成 Operation/Task；已有 TaskStateService.complete 应被生产结果路径调用。[S04][S15][S22]

**影响与推断。** 普通异常时回滚测试不能证明进程在写入后崩溃可恢复；journal 自身被截断/未落盘必须有保守路径。不能强行要求 SQLite 与文件系统跨介质单事务，也不能伪造全局回滚保证。

**最小切片。** 实现可重载、带版本/摘要的 journal，定义写前备份与提交标记持久顺序；实际文件逐项核对 old/new/unknown，冲突保留用户修改并进入人工核对。执行回执绑定 Attempt、Artifact 与验证命令，Task completion 只走已有 verifier，事件/outbox 在对应数据库短事务提交。

**优先级/映射。** P0，V1-020；原 OB-032–036/014/017/020/029。

**验收。** 第一文件应用后 kill、journal 截断、备份损坏、磁盘满、权限变更、用户并发编辑都有可检查恢复结论；新进程能读取 journal，旧 hash/新 hash/冲突各自正确；不得覆盖恢复期间用户的新修改，不把 UNKNOWN 标 SUCCEEDED。

### AR-G09：配置已保存且有版本，但“运行中生效”及本地/离线证明尚未接线

**源码事实。** ClientStateService 对 settings 做 CAS，run 保存 revision/config 快照；mode/mcp/skill/feishu 变化会增加 policy_version。preview 除纯 locale 外统一给 NEXT_RUN，而设计要求收紧限制立即阻止新派发；apply receipt 只返回 revision/config。OllamaLocalProviderAdapter 使用真实 HTTP，但 generate 丢弃 privacy_mode 参数，依赖构造时布尔 attestation；真实模型文件与 runner 出口归属证明尚不能从这段代码自动得到。[S02][S03][S08]

**影响与推断。** 保存 OFFLINE 与实际停止新出口是两件事。扩大权限不能改变旧 run 的授权；既有 DispatchService 的 policy_version 复核应保留，但模型请求和其他外发路径也必须读取当前限制。

**最小切片。** 运行配置固定，实际有效权限为“run 授权上限与当前限制的交集”。提交收紧限制后 fence 模型/工具/飞书新外发并取消在途可取消请求；生效回执区分 APPLIED/NEXT_RUN/RECONNECTING/RESTART_REQUIRED/REJECTED。独立核验本地模型 hash、runner 身份/插件/云回退，区分 LOCAL_MODEL 与 OFFLINE；缺证明时不显示已离线。

**优先级/映射。** P0 配置，P1 本地能力；V1-021/022；原 OB-008/023/025/026/037/092/096。

**验收。** 在 dispatch 屏障前提交收紧配置，新派发次数为零；放宽只影响获授权的新 run；本地服务消失无云请求；安装后断网冷启动不下载缺失资产，实际出口日志与任务 mode 一致。

### AR-G10：事件事实、游标恢复和诊断持久性需要形成正式可观察合同

**源码事实。** ClientStateService._run 通过 task_record 验证 owner/session，不应误报读取未授权；record 检查类型、脱敏及 parent 同 run，但为每次调用生成随机 request_id/event_id，未核对传入 operation/attempt/approval/artifact 的归属和对应已提交事实。trace 限制 128 条，但没有合同规定的过期 cursor 410 + snapshot 分支。DiagnosticsCollector 的日志/指标是内存列表。[S02][S23]

**影响与推断。** 重试记录可产生重复“工具调用”；错误关联可能生成可信外观但没有真实因果的图。客户端断线重连必须读事件，不得重放执行；诊断内存无限增长也不适合长驻 daemon。

**最小切片。** 从业务事务事件投影 run trace，使用稳定业务事件 key、同 task/run 归属与可验证父边；明确记录提交事实、未确认事实及 UNKNOWN。实现 retention/cursor 的一致快照恢复、固定批量和无副作用回放；诊断采用有界采集、脱敏、明确本地导出同意和来源/版本说明。

**优先级/映射。** P0 事件正确性，P1 体验/诊断；V1-023/026/028；原 OB-006/014/021/075/081/083。

**验收。** 重复提交 source event 后 trace 不出现第二次动作；跨 run reference 拒绝；断连、过期 cursor、窗口重开恢复同 run 并且模型/工具请求计数不增加；可视图只显示事实关系，隐藏推理文本永不存储。

### AR-G11：Tauri 客户端仍是批准设计，需要薄壳接入和可审核 UI

**源码事实。** approved spec 与计划已经选择 Tauri 2 + daemon，实施计划明确 static ES modules/CSS/SVG，固定 Rust IPC，token 不入 WebView；fixed tree 尚无 apps/desktop 和 client_routes.py。首轮是连接已由 CLI 初始化的 macOS arm64 daemon，未签名开发构建；原生安装向导、签名和跨平台另有门禁。[S03][S09]

**最小切片。** 先增加经过认证的 client API DTO，然后固定 Rust command 白名单，再实现任务、审批、设置、能力/健康、事实图与细节重连。语言覆盖系统文案，用户内容保留原文；动态图旁提供可访问的等价列表。不要用 WebView 任意 URL fetch 或插件直接访问文件/进程。

**优先级/映射。** P1，V1-024/025/026；原 OB-082/083。

**验收。** 真实 macOS 构建连接真实 daemon，不载入 demo 状态；关窗 daemon 和任务继续，重开恢复相同 run；注入脚本/任意 IPC 路径/外部导航不能读 token、启动 shell 或修改政策。未验证能力应显示不可用及原因。

### AR-G12：飞书和用户级 daemon 仍需接到同一真实运行链，而非增加一套控制逻辑

**源码事实。** FeishuInboundAdapter 已有 tenant/app/owner 检查、Inbox 成功后 ACK 和真实 reaction HTTP；e2e_harness 仍组合本地 fixture。计划中的官方 SDK live_gateway.py 未存在。UserDaemonInstaller 已生成 plist 并可 plutil 校验，也能真实 Popen daemon；install 尚无 launchctl 注册流程，start 仍直接 Popen。[S14][S24]

**最小切片。** 飞书 SDK 入站与 callback 只转换为受信身份和业务命令，复用同一 runtime、ApprovalPreview、outbox；真实 human callback/去重/撤销/重连逐项验收。用户会话服务在单一 launchd 管理路径安装/启动/停止/卸载，token/profile 权限和进程身份可核验，UI 生命周期与 daemon 分离。发布签名、公证、升级回滚由平台工作流单独负责。

**优先级/映射。** P1，V1-027/029；原 OB-047–056/068/069/079/093/094。

**验收。** 在授权测试租户真实发起任务和点击审批，从 event_id → Task/run → Operation/Attempt → outbox/card revision 关联；重复事件仅一个任务，撤销 owner 后停新动作。真实登录会话服务注册、注销/重登、睡眠/唤醒、崩溃恢复、关 UI、不误杀复用 PID 都留证，平台不支持就保持阻塞。

## 4. 建议实施架构与依赖切法

保留现有 Python 薄内核和每 profile SQLite 单 Writer。新增 AgentRuntime 是可信组合层，不是新的权限内核；它只通过现有应用服务提交命令，通过端口接 Provider、MCP、Browser、文件和飞书。长 HTTP、模型等待、审批等待、进程回收不得发生在 Writer 事务中。

运行事实的权威是已提交的 domain 事件、Attempt 回执和独立效果证据；ClientState/trace 是投影。为每个动作保留 Task → run → Operation → Attempt → dispatch_id；provider_idempotency_key 继续属于 Operation，同 Attempt 传输重试保持 dispatch_id，新 Attempt 用新 ID；不能把模型 tool_call_id 当作执行授权。

调用顺序建议为：受信入站和持久去重 → 领取 Task/建立 run 快照 → 预算预留和上下文 → 真实模型候选 → schema/registry/policy → 冻结 Proposal → 必要审批 → claim → 派发前再次复核 → 实际执行 → 结果证据及预算结算 → TaskStateService.complete/部分完成/UNKNOWN。取消、配置收紧、owner 撤销在模型尝试和首次派发前均可阻止新动作。

安全域实现先于启用外部副作用。V1-010 可以先在受控只读 fixture 上装配 loop；真实模型、MCP、Browser、patch 分别受 V1-011、017、018/019、020 门禁控制。任务编号先后不代表可以绕过后续能力门禁。V1-013 先完成内部监督/恢复证明，V1-029 再把它接入用户会话服务，不要求恢复模块依赖未来的桌面安装器。

## 5. MVP 与 v1.0.0 范围建议

### 独立命名的 macOS arm64 开发 MVP

建议明确命名为“macOS arm64 开发 MVP”，用于这轮继续编码：单 profile/owner/active run，有限 Agent loop，真实云 Provider 与本地 Provider 的分别验证路径，准入只读 Skill/MCP，受控文件补丁，必要 Browser 读写能力，CLI/飞书/薄客户端共用一个内核，权限/预算/取消/UNKNOWN/恢复可观察。能力未通过时禁用并显示原因，不能靠全局 PASS 掩盖缺口。

原设计 M3 的全 MVP 定义和三平台原生验收保持不变。Mac 优先的开发里程碑不能直接把 Windows/Linux 阻塞任务移除并宣称旧 M3 完成；需要另列平台适用性与未完成项。新的开发里程碑不是重新定义旧任务。

### 应用 v1.0.0

v1.0.0 是应用发布版本，不是已有“工程设计包 v1.2”的降级或替换。它应具有闭合且真实验证的用户路径、可靠安装/升级/回滚、密钥录入和故障恢复、可信审批与配置生效、可访问双语 UI、明确支持平台以及同一候选 SHA/安装包 hash 的发布证据。若选择 Mac-only v1，公开支持矩阵要明确，不把其他 OS 的 contract CI 说成原生产品通过。

### P2 后置建议

本轮不扩大到多设备、团队/多租户、多任务并行调度、任意插件自动安装、任意 host shell、原生 Computer Use、远程遥测、可视工作流编辑器。真实 SSE 可以在有界轮询与 cursor 合同正确后再单独交付；不能先写“SSE 已实现”而服务端实际只返回一次 JSON。Anthropic 原生 Provider、记忆、定时触发等沿用旧任务的适用阶段，不为了 v1 名称强行提前。

## 6. 新任务交接规则

同目录 core_tasks.json 给出 20 条 V1-010–029 设计任务：全部 PLANNED；每条有现有证据、交付物、3–5 个步骤、可执行验收、反例、旧任务映射、依赖和尺寸。它是本轮建议的增量任务，不会覆盖旧 backlog 状态。依赖只使用更小 V1 编号或 V1-001/003，无循环。

每修复一个独立问题按用户要求形成独立 commit，再 push 并检查该提交对应远端 CI；真实环境证据绑定候选 SHA。本文没有授权外发测试消息、使用生产密钥、发布安装包或对仓库执行这些操作；具体执行应使用既有授权范围。NOT_RUN/BLOCKED/SKIPPED 都不能写 PASS。

## 7. 固定源码索引

以下链接全部固定到本轮活动分支 SHA，行号用于复核；不依赖会移动的分支 URL。

- **S01** [README 5–9、61](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/README.md#L5)；[client-state 证据 19–31](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/docs/evidence/client-state.md#L19)。
- **S02** [ClientStateService 90–456](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/application/client_state.py#L90)。
- **S03** [批准的 client design，157–274](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/docs/superpowers/specs/2026-11-05-agent-client-design.md#L157)；[client-control 合同](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/contracts/client-control.md)。
- **S04** [TaskStateService/OutcomeVerifier 83–166、278–340](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/application/state_machine.py#L83)。
- **S05** [dispatch 70–132、399–534](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/application/dispatch.py#L70)。
- **S06** [OpenAI 文本 transport 46–206](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/providers/openai.py#L46)。
- **S07** [BudgetService reserve/settle/unknown](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/application/budgets.py#L279)。
- **S08** [Ollama transport/adapter 12–162](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/providers/ollama.py#L12)。
- **S09** [client 实施计划 32–89](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/docs/superpowers/plans/2026-11-05-agent-client.md#L32)；[CLI 577–692](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/cli.py#L577)。
- **S10** [Skill loader 66–91](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/application/skills.py#L66)。
- **S11** [OpenAI compatible adapter 69–79、147–307](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/providers/openai_compatible.py#L69)。
- **S12** [Local API recover-epoch 320–335、preview 363–402](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/adapters/local_api/server.py#L320)。
- **S13** [RecoveryService 131–238](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/application/recovery.py#L131)。
- **S14** [UserDaemonInstaller 61–141、175–289](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/application/daemon_installer.py#L61)；[ProcessSupervisor 122–240](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/tools/executors/supervision_port.py#L122)。
- **S15** [vertical_slice 64–120、291–393](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/application/vertical_slice.py#L64)。
- **S16** [macOS Keychain / SecretBroker 55–73、233–265](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/policy/secrets/broker.py#L55)。
- **S17** [MCP client 25–34、56–182](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/tools/mcp/client.py#L25)。
- **S18** [MCP executor 29–69](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/tools/mcp/executor.py#L29)。
- **S19** [Browser session 68–112、139–196](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/tools/executors/browser/session.py#L68)。
- **S20** [Browser network policy](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/tools/executors/browser/network_policy.py)。
- **S21** [Browser actions 34–64](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/tools/browser/actions.py#L34)；[Browser verifier](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/tools/browser/verifier.py)。
- **S22** [Workspace patch 66–210](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/tools/workspace/patch.py#L66)；[commit journal 27–110](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/tools/workspace/commit_journal.py#L27)。
- **S23** [task_record 39–49](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/application/operations.py#L39)；[DiagnosticsCollector](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/core/src/openbot/observability/diagnostics.py)。
- **S24** [Feishu inbound 97–220](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/feishu_gateway/src/openbot_feishu/inbound.py#L97)；[Feishu e2e_harness](https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/services/feishu_gateway/src/openbot_feishu/e2e_harness.py)。

