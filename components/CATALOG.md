# 组件决策目录

这是设计选择，全部真实资格验证为NOT_RUN；精确版本和许可证在对应实施任务中核验。按catalog.json更新本表。

| ID / 名称 | 决策与阶段 | 端口 / 关联任务 | 必须满足的边界 |
|---|---|---|---|
| fastapi-stack / FastAPI / Uvicorn / sse-starlette | DEFAULT_ADAPTER / M1 | LocalControlApi；OB-081, OB-028 | loopback与Host/Origin校验；认证与SSE游标由应用控制；限制连接、缓冲与请求体 |
| pydantic-jsonschema / Pydantic v2 / jsonschema / referencing | DEFAULT_ADAPTER / M0 | ContractValidator；OB-006, OB-007, OB-081, OB-090 | strict与extra forbid；frozen不深冻结；显式format checker；只用本地Registry；拒重复键 |
| rfc8785 / Trail of Bits rfc8785 | DEFAULT_ADAPTER / M0 | Canonicalizer；OB-018, OB-063, OB-090, OB-091 | 按UTF-16 code units排序；采用标准向量；严格输入域；保存权威canonical bytes |
| sqlite3 / Python sqlite3 / SQLite backup | DEFAULT_ADAPTER / M0 | StateStore；OB-011, OB-012, OB-013, OB-014, OB-017, OB-018, OB-019, OB-020, OB-030, OB-091 | M0仅标准库PoC，生产持久化M1；单writer独占事务；WAL FULL foreign_keys实测；有界配额；backup加artifact manifest |
| aiosqlite / aiosqlite | GATED_CANDIDATE / M1 | StateStore；OB-011, OB-012, OB-030 | 可选异步驱动；await SQL可用但禁止其他协程插入事务；不与sqlite3路径双重维护 |
| model-openai / 官方OpenAI Python SDK基础请求 | DEFAULT_ADAPTER / M1 | ModelTransport；OB-007, OB-023, OB-025, OB-092 | 显式max_retries=0或唯一重试负责人；拒自动执行helper/未授权托管工具；端点逐个验能力 |
| model-ollama / Ollama SDK或受控HTTP客户端 | DEFAULT_ADAPTER / M3 | ModelTransport；OB-008, OB-026, OB-037, OB-092 | loopback不是本地证明；禁云功能与自动模型下载；验证模型服务实际egress与模型来源 |
| model-anthropic / Anthropic SDK基础Messages API | DEFERRED / P2 | ModelTransport；OB-027 | 按P2任务接入；禁tool_runner自动执行；统一重试、usage与供应商特有字段 |
| httpx / HTTP客户端适配层 | DEFAULT_ADAPTER / M1 | HttpTransport；OB-025, OB-026, OB-028, OB-081, OB-092 | 随锁定SDK选择兼容transport；明确proxy/TLS/redirect/deadline；不默许环境代理改变出口 |
| tiktoken / 适用模型的token预估 | DEFAULT_ADAPTER / M1 | TokenEstimator；OB-023, OB-024, OB-025, OB-096 | 词表安装期预置与hash校验；非通用精确计数；供应商usage优先；缺词表不联网 |
| tenacity / 有界重试辅助库 | GATED_CANDIDATE / M1 | RetryPolicy；OB-025, OB-054, OB-092 | 只承担已审查的重试机制；不叠加SDK重试；不重试UNKNOWN工具动作；遵守总deadline |
| litellm / LiteLLM协议适配候选 | GATED_CANDIDATE / P2 | ModelTransport；OB-007, OB-027, OB-092 | 仅协议层；本地价格表与遥测配置需实测；禁止隐式云fallback和自动工具执行；MVP不用作默认 |
| lark-oapi / 飞书官方Python SDK | DEFAULT_ADAPTER / M2 | FeishuTransport；OB-047, OB-049, OB-050, OB-051, OB-052, OB-053, OB-054, OB-055, OB-056 | 独立Gateway；初始化/握手分计时；阻塞请求需有界或进程外hard deadline；补丁固定commit |
| nanobot / HKUDS/nanobot飞书参考 | REFERENCE_ONLY / M2 | CardRenderer；OB-048, OB-051, OB-053, OB-094 | 只参考模板/降级；QR应用注册不是owner授权；摘取须来源记录；不复制队列和AgentLoop |
| langbot / LangBot飞书适配参考 | REFERENCE_ONLY / M2 | FeishuTransport；OB-051, OB-053, OB-094 | 参考附件/消息容错；独立验证选定API；不继承权限和重试假设 |
| astrbot / AstrBot功能对照 | REFERENCE_ONLY / P2 | FeatureReference；OB-004, OB-089 | 默认不复制/链接未经许可评估的代码；按精确许可证与目标分发方式记录，不作普遍法律结论 |
| ripgrep / ripgrep固定二进制 | DEFAULT_ADAPTER / M1 | WorkspaceSearch；OB-032, OB-033, OB-096 | 清理用户配置；不跟随不受管路径；全局字节/结果/时间限额；ignore不是授权 |
| pathspec / pathspec忽略匹配 | DEFAULT_ADAPTER / M1 | IgnoreMatcher；OB-032, OB-033 | 仅产品筛选；不替代路径句柄守卫；精确版本许可证单独核验 |
| unidiff / unidiff解析 | DEFAULT_ADAPTER / M1 | PatchParser；OB-034 | 只生成内存补丁计划；路径、旧hash、文件操作与提交由OpenBot控制 |
| patch-ng / patch-ng应用器候选 | GATED_CANDIDATE / M1 | PatchApplier；OB-034, OB-092 | 固定支持子集；拒模糊套用；先在暂存区计算；不将可解析等同可安全应用 |
| tree-sitter / tree-sitter和必要grammar | GATED_CANDIDATE / M1 | SyntaxParser；OB-035, OB-041, OB-092 | native代码独立限额worker；固定grammar；畸形输入/超时/崩溃验证；语法正确不代表功能正确 |
| tree-sitter-language-pack / 多语言parser包 | GATED_CANDIDATE / M1 | SyntaxParser；OB-035, OB-096 | 核实首次下载行为；只安装需要的grammar并预置；无资产时不自动联网 |
| git-worktree / Git受管工作树 | DEFAULT_ADAPTER / M1 | WorkspaceSnapshot；OB-032, OB-034, OB-035 | 固定Git来源与环境；禁项目hooks/过滤器隐式执行路径；不reset用户脏改动或自动commit/push |
| python-on-whales / python-on-whales Docker适配 | DEFAULT_ADAPTER / M1 | IsolationBackend；OB-040, OB-041, OB-042, OB-093 | 首个后端逐配置验证；默认无网络、只读输入、无HOME/socket；容器ID独立追踪和回收 |
| podman-nerdctl / Podman / nerdctl替代后端 | GATED_CANDIDATE / P2 | IsolationBackend；OB-041, OB-069, OB-070, OB-071, OB-093 | best-effort不是等价证明；需要独立完整后端矩阵；不作为未经验证的自动fallback |
| bubblewrap / bubblewrap替代后端 | DEFERRED / P2 | IsolationBackend；OB-041, OB-071 | 逐发行版验证user namespace/网络/挂载；不把bwrap默认参数当完整sandbox |
| playwright / Playwright Python原语 | DEFAULT_ADAPTER / M3 | BrowserPrimitive；OB-057, OB-058, OB-059, OB-060, OB-061, OB-096 | 专用Profile；启用并验证Chromium sandbox；route不覆盖全部出口；禁止失败后no-sandbox兜底 |
| browser-use / browser-use DOM参考 | REFERENCE_ONLY / M3 | BrowserExtractor；OB-059, OB-095 | 只审查只读提取算法；不得复制Agent.run/模型调用/自动点击；无收益可决定NO_COPY |
| mcp-sdk / 官方MCP Python SDK | DEFAULT_ADAPTER / M3 | McpTransport；OB-062, OB-063, OB-064, OB-065, OB-096 | 锁定完整SDK/协议组合；显式受控env；隔离stdio；禁sampling/自动安装；list_changed重审 |
| windows-sys / Windows系统API绑定 | DEFAULT_ADAPTER / M1 | ProcessSupervisor；OB-015, OB-042, OB-068, OB-070, OB-093 | 挂起创建→检查Job绑定成功→恢复；拒breakaway；错误路径须回收；Job不是sandbox |
| processkit-process-wrap / processkit / process-wrap候选 | GATED_CANDIDATE / M1 | ProcessSupervisor；OB-003, OB-015, OB-042, OB-093 | 锁定一个合适封装；核实Drop/强杀/setsid边界；不得宣称100%整树清理 |
| ur-taking-me-with-you / 父子管道清理候选 | GATED_CANDIDATE / M1 | ProcessSupervisor；OB-042, OB-069, OB-093 | 仅用于已证明场景；独立外部监督；测试守护进程同时被杀和后代逃逸 |
| command-group / 已弃用command-group | REJECTED_MVP / M1 | ProcessSupervisor；OB-004, OB-042, OB-089 | 不新增该依赖；评估维护中的继任者或OS原语；不沿用旧推荐 |
| service-manager / service-manager平台适配候选 | GATED_CANDIDATE / M3 | UserServiceInstaller；OB-068, OB-069, OB-070, OB-071 | 仅验证支持的用户级后端；Windows单独设计登录会话，不默认sc.exe系统服务 |
| profile-locks / fd-lock / filelock / portalocker候选 | GATED_CANDIDATE / M1 | ProfileLock；OB-015, OB-093 | 选择一种profile锁所有者；测试双启动与崩溃释放；避免Supervisor与Daemon互锁同一排他锁 |
| keyring / 系统钥匙串适配 | DEFAULT_ADAPTER / M1 | SecretStore；OB-038, OB-093 | 限定backend；测锁定/无D-Bus；不明文fallback、不自动选keyrings.alt；不宣称隔离同用户恶意程序 |
| detect-secrets / 离线检测器与CI扫描候选 | GATED_CANDIDATE / M1 | OfflineSecretDetector；OB-039, OB-076, OB-092 | 禁联网验证与动态插件；外部allowlist无效；不替代分类策略；不保证128字节全覆盖 |
| structlog / 结构化日志 | DEFAULT_ADAPTER / M1 | Observability；OB-039, OB-075 | 脱敏在持久化前；上下文正确清理；不记录原始secret/nonce；限制cardinality与长度 |
| opentelemetry / OpenTelemetry可选追踪 | GATED_CANDIDATE / M3 | Observability；OB-075, OB-078 | 默认不开外部exporter；精确插件锁定；trace同受出口控制；不自动全量采集模型内容 |
| cli-toolchain / uv / Typer / Rich / pytest等工具链 | DEFAULT_ADAPTER / M0 | CliAndDevelopment；OB-005, OB-010, OB-028, OB-089 | dev与runtime分组；只安装当前任务依赖；终端控制字符过滤；记录CI实际镜像版本 |
| pyinstaller / PyInstaller onedir分发 | DEFAULT_ADAPTER / M3 | ReleaseBuilder；OB-066, OB-072, OB-096 | 各目标OS原生构建；清点浏览器/native资产；核验bootloader例外与实际第三方许可证 |
| tauri / Tauri v2及官方更新插件 | DEFERRED / M4 | DesktopClient；OB-073, OB-074, OB-082, OB-083 | Rust白名单IPC；UI不持广域token；关UI不关daemon；签名不代替迁移恢复 |
| macos-permissions / macOS权限插件候选 | GATED_CANDIDATE / M4 | CapabilityProbe；OB-069, OB-082, OB-084, OB-085 | 按固定插件/OS版本验证API；不保证每30天行为；P2 GUI每次动作前复核权限 |
| scheduling-libs / croniter / APScheduler触发计算 | DEFERRED / P2 | ScheduleCalculator；OB-087 | 仅计算时区/DST与触发；持久occurrence创建普通Task；禁后台自动函数执行与危险补跑 |
| sbom-tools / CycloneDX Python / Syft | DEFAULT_ADAPTER / M3 | SupplyChainInventory；OB-004, OB-074, OB-096 | 工具与格式一致；包括浏览器、grammar、容器、Rust、前端和摘取代码；SBOM不等于漏洞全清 |
| yoyo-migrations / yoyo-migrations备选 | GATED_CANDIDATE / M1 | MigrationRunner；OB-011 | 原生SQL/校验和优先；库不能替代恢复与兼容策略；不以80行预算选型 |
| opa-casbin / OPA / Casbin策略引擎 | DEFERRED / P2 | PolicyEvaluator；OB-031 | MVP采用可审查纯代码策略；延后不代表引擎不能表达ABAC；改变需独立ADR |
| encoding-detectors / charset-normalizer / binaryornot候选 | GATED_CANDIDATE / M1 | EncodingProbe；OB-033, OB-034 | MVP优先UTF-8；探测为建议而非权威；不依赖探测结果绕过二进制或敏感路径限制 |
| dulwich / Dulwich Git备选 | GATED_CANDIDATE / P2 | WorkspaceSnapshot；OB-034 | 先用受控Git worktree；按精确许可分支/行为测试决定；不因纯Python声称无副作用 |
| crypto-storage / 加密文件凭据后端 | DEFERRED / P2 | SecretStore；OB-038 | 需要独立主密钥、恢复、权限和威胁模型；不作为钥匙串失败时自动兜底 |
| native-gui / UIA / PyObjC / Portal等原语 | DEFERRED / P2 | DesktopPrimitive；OB-084, OB-085 | 原生会话与权限独立门禁；不复用UFO自治loop；不与三平台CLI能力混淆 |
| model-runner / 自治Agent框架与自动工具helper | REJECTED_MVP / M1 | ModelTransport；OB-007, OB-025, OB-027, OB-060, OB-064 | 禁止绕过Broker的auto execution；若未来接入必须逐动作同一授权与恢复合同 |
