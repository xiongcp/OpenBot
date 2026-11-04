# 架构决策与证据索引

## 决策记录

| ADR | 决策 | 依据与取舍 |
|---|---|---|
| ADR01 | 自有薄控制内核，成熟执行组件通过port接入 | 保持U1主线；避免深fork和隐藏权限链 |
| ADR02 | Python业务内核，Tauri客户端后置，native supervisor独立 | 保持生态便利与常驻生命周期 |
| ADR03 | 每profile独立SQLite，状态表加审计与inbox/outbox | 单机可运维；不承诺完整事件重放执行 |
| ADR04 | 控制库WAL加FULL，短事务与有界writer | 优先已确认命令耐久性；牺牲部分吞吐 |
| ADR05 | Task、Operation、Approval、Attempt独立 | 明确授权、执行、恢复和未知结果 |
| ADR06 | Approval一次消费，dispatch属于Attempt，幂等键属于Operation | 避免安全重试要求二次消费或错误复活授权 |
| ADR07 | 单Broker执行所有副作用 | 模型、工具库与渠道不拥有独立执行权 |
| ADR08 | 不可信代码隔离执行，无后端不降级宿主 | 明确安全能力与便利性的取舍 |
| ADR09 | 单owner、单app、单活动gateway作为MVP | 飞书竞争消费不是设备路由 |
| ADR10 | LOCAL_MODEL与OFFLINE分离 | 隐私出口与远程能力不可混为一个布尔量 |
| ADR11 | OpenBot专用浏览器profile，直接Playwright原语 | 可验证逐动作审批，不自动接管日常profile |
| ADR12 | MCP固定包与完整定义，禁用未知server发起能力 | pinning配合执行隔离与更新流程 |
| ADR13 | 先CLI与普通飞书卡片，后CardKit与Tauri | 最早验证可靠任务闭环 |
| ADR14 | 平台能力分级，原生GUI另立门禁 | UI能启动不等于桌面自动化可用 |
| ADR15 | 出口治理包含模型请求、消息与artifact | 读取后发模型也属于数据外发 |
| ADR16 | 以真实验收记录任务完成，不以生成代码量估进度 | 适合Codex与Claude Code逐任务协作 |
| ADR17 | 分阶段依赖组与组件准入，默认组件也需锁定和实测 | 不在M0一次安装所有候选；记录非Python资产 |
| ADR18 | 模型请求只有一个重试负责人，API面排除自动工具helper | 避免SDK与tenacity叠加、隐藏执行和预算漏记 |
| ADR19 | 标准JCS库、严格JSON入口与权威canonical bytes | 修正UTF-16排序；浅冻结DTO不能保证授权不可变 |
| ADR20 | 源码摘取与直接依赖分别管理来源和升级责任 | 固定commit、LICENSE/NOTICE、diff、维护人和回归 |
| ADR21 | 容器、进程监督和服务安装按实际后端/平台资格验证 | 统一API不代表相同隔离、回收或用户会话保证 |
| ADR22 | native解析、流式脱敏与离线模式采用有界可验证合同 | 不沿用零风险、128字节100%脱敏或localhost必本地的假设 |

## 原材料

U1 《OpenBot 开源桌面智能体深度研究报告.pdf》，用户提供，20页。主要使用第6至17页的产品目标、架构原则、MVP范围和工程路线。其竞争项目数字与产品时事不作为本方案技术事实。

U2 《OpenBot 架构设计与任务规划.pdf》，用户提供，36页。主要使用第9至24页的协议、数据库与进程设计，以及第26至33页的任务和测试。第8、25页图片已核对。本次逐项修正见01_gap_review。

U3 《OpenBot 开源组件复用评估.pdf》，用户提供，27页。正文标题为《OpenBot 工程交接包（v1.1）架构深度对齐与开源生态复用全景研究报告》。已阅读全文及第2、11页图表。采纳/调整见12_component_reuse、13_component_qualification和14_revision_v1_2；Stars、代码行数、速度提升、固定导入耗时和绝对安全保证不作为已验证结论。

## 官方资料

核验日期为2026年11月4日。链接中的版本仅代表本次核对的页面；不将某个版本标称为“最新”。实际依赖在各阶段引入前锁定并验证；M0只覆盖当前所需组件。部分飞书页面动态渲染，检索结果与官方页面共同用于核对；无法稳定读取的token细节列为集成验证项。

[S01] 飞书长连接与回调。用于企业自建应用、竞争消费、3秒响应、回调不补推等约束。
- https://open.feishu.cn/document/ukTMukTMukTM/uYDNxYjL2QTM24iN0EjN/event-subscription-configure-
- https://open.feishu.cn/document/event-subscription-guide/callback-subscription/receive-and-handle-callbacks

[S02] 飞书卡片交互。用于区分回调携带的更新token与OpenBot业务审批期限。接口版本差异需在测试租户确认。
- https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/handle-card-callbacks
- https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/card-json-v2-components/interactive-components/image-picker

[S03] SQLite PRAGMA与WAL。用于NORMAL/FULL耐久性、单写者、WAL并发与本地文件系统约束。
- https://www.sqlite.org/pragma.html
- https://www.sqlite.org/wal.html

[S04] OWASP MCP Security Cheat Sheet。用于完整工具定义摘要、动态变更和工具输出边界；具体策略为本方案推导。
- https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html

[S05] MCP工具、生命周期与传输。2026-07-28工具页和2025-11-25生命周期/传输页均已核对；实现只能选择经实际测试的完整协议/SDK组合，不能混搭不同版本字段。
- https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle
- https://modelcontextprotocol.io/specification/2025-11-25/basic/transports

[S06] RFC8785 JSON Canonicalization Scheme。用于跨语言哈希需要确定性表示的设计依据。
- https://www.rfc-editor.org/rfc/rfc8785

[S07] Playwright BrowserType。用于专用持久profile、默认Chrome profile不受支持的注意事项。
- https://playwright.dev/python/docs/api/class-browsertype

[S08] Microsoft进程监督。用于Job Object、breakaway和CREATE_SUSPENDED语义；受控启动顺序是本方案工程设计。
- https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
- https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags

[S09] Microsoft Interactive Services。用于区分系统服务与交互用户桌面。
- https://learn.microsoft.com/en-us/windows/win32/services/interactive-services

[S10] Docker Engine Security。用于容器配置、daemon攻击面与权限隔离的设计边界。
- https://docs.docker.com/engine/security/

[S11] Tauri Capabilities与Sidecar。用于界面能力与外部二进制接入；它们不替代执行器sandbox。
- https://v2.tauri.app/security/capabilities/
- https://v2.tauri.app/develop/sidecar/

[S12] XDG RemoteDesktop Portal。用于Linux会话授权与输入能力边界。macOS部分以权限实测为交付要求，不沿用固定周期断言。
- https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html

[S13] PyInstaller Operating Mode。用于目标OS专属构建与onedir/onefile选择。
- https://pyinstaller.org/en/stable/operating-mode.html

[S14] Tauri Updater。用于签名验证与更新包契约；数据迁移和回滚规则由OpenBot自行定义。
- https://v2.tauri.app/plugin/updater/

## 尚待实测的内容

真实飞书租户的权限、SDK版本与卡片行为；目标机器冷启动和重连时间；macOS录屏与Accessibility授权状态；Windows嵌套Job与原生路径；Linux发行版与Wayland差异；模型工具调用质量与成本；容器隔离配置；签名安装与升级恢复。

这些项目已经进入任务清单。没有跑过的真实环境测试不会在本报告中被标成已通过。


## v1.2组件核验来源

以下资料支持本轮组件行为核对。文档/源码核对不代表目标平台运行测试；历史issue不是普遍性能基线。移动分支不能替代实际锁定发行物。机器可读索引见evidence/reuse_sources.json。

[R01] RFC8785与所选实现。UTF-16码元排序、严格输入域；库负责规范化，不负责授权。
- https://www.rfc-editor.org/rfc/rfc8785.html
- https://github.com/trailofbits/rfc8785.py

[R02] DTO与JSON Schema。frozen不深冻结；format需显式启用；当前Registry默认不自动联网，旧RefResolver不同。
- https://docs.pydantic.dev/latest/concepts/models/#faux-immutability
- https://python-jsonschema.readthedocs.io/en/stable/validate/
- https://python-jsonschema.readthedocs.io/en/stable/referencing/

[R03] OpenAI官方SDK与工具。内建重试与配置；基础模型请求、function提案和服务端工具需分开。
- https://github.com/openai/openai-python
- https://developers.openai.com/api/docs/guides/tools

[R04] Anthropic官方SDK。基础Messages、默认重试与tool_runner自动执行helper；按实际版本限制入口。
- https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python

[R05] 本地模型与token资产。Ollama支持云功能，存在禁云配置；tiktoken缺缓存时可获取词表，估算不能当全Provider账单。
- https://docs.ollama.com/faq
- https://github.com/openai/tiktoken/blob/main/tiktoken/load.py

[R06] 原生parser与grammar。Tree-sitter可含C external scanner；language-pack当前文档包含首次按需下载。
- https://tree-sitter.github.io/tree-sitter/creating-parsers/4-external-scanners.html
- https://github.com/xberg-io/tree-sitter-language-pack/blob/main/README.md

[R07] 容器CLI适配。python-on-whales可切换CLI，Podman/nerdctl为best-effort，不证明配置语义等价。
- https://gabrieldemarmiesse.github.io/python-on-whales/docker_client/
- https://gabrieldemarmiesse.github.io/python-on-whales/sub-commands/container/
- https://docs.podman.io/en/latest/markdown/podman-machine.1.html

[R08] 容器产物复制。docker cp可从已停止容器复制；权限与所有权受平台及参数影响。
- https://docs.docker.com/reference/cli/docker/container/cp/

[R09] MCP官方SDK与迁移。SDK主版本、stdio环境基线与协议功能应固定成完整组合；默认环境有选择不代表适合全部任务。
- https://github.com/modelcontextprotocol/python-sdk
- https://py.sdk.modelcontextprotocol.io/migration/
- https://github.com/modelcontextprotocol/python-sdk/blob/main/src/mcp/client/stdio.py

[R10] 飞书SDK发现请求。核对到的v2_main源码有同步requests发现调用；issue169讨论超时问题。必须对锁定版本复核。
- https://github.com/larksuite/oapi-sdk-python/blob/v2_main/lark_oapi/ws/client.py
- https://github.com/larksuite/oapi-sdk-python/issues/169

[R11] 飞书冷导入历史issue。24.25/24.27秒来自具体Windows/Hermes/lark-oapi组合的个例，不能外推为所有平台。
- https://github.com/NousResearch/hermes-agent/issues/85564

[R12] 进程组封装维护状态。command-group明确弃用并指向process-wrap；候选API仍需原生故障验证。
- https://github.com/watchexec/command-group
- https://docs.rs/process-wrap/10.0.1/process_wrap/

[R13] 服务安装层级。service-manager对systemd/launchd有用户级支持，Windows后端不直接提供同等User能力。
- https://docs.rs/service-manager/latest/service_manager/
- https://docs.rs/service-manager/latest/src/service_manager/sc.rs.html
- https://docs.rs/service-manager/latest/src/service_manager/winsw.rs.html

[R14] 进程监督能力边界。processkit的Drop/平台保证及管道协作清理有边界；不能推出通用100%回收。
- https://docs.rs/processkit/latest/processkit/
- https://docs.rs/processkit/latest/processkit/struct.ProcessGroup.html
- https://docs.rs/ur-taking-me-with-you/latest/ur_taking_me_with_you/

[R15] 凭据后端。keyring有自动后端选择与替代后端；服务会话、锁定和无图形环境需单独处理。
- https://keyring.readthedocs.io/en/latest/

[R16] 秘密扫描。detect-secrets存在网络验证、插件和allowlist机制；不等同通用实时脱敏。
- https://github.com/Yelp/detect-secrets

[R17] SBOM格式。CycloneDX Python产生CycloneDX；Syft支持SPDX与CycloneDX，实际产物需按对应格式验证。
- https://cyclonedx-bom-tool.readthedocs.io/en/stable/
- https://github.com/anchore/syft

[R18] 浏览器默认值与请求路由。Chromium sandbox配置需要显式核验；route不拦截Service Worker处理的全部请求。
- https://playwright.dev/python/docs/api/class-browsertype
- https://playwright.dev/python/docs/api/class-browsercontext

[R19] SQLite、队列与异步驱动。SQLite默认同步选项受编译配置影响；backup仅复制DB；aiosqlite每连接线程队列不等于业务事务独占。
- https://www.sqlite.org/compile.html#default_synchronous
- https://www.sqlite.org/backup.html
- https://aiosqlite.omnilib.dev/en/stable/
- https://docs.python.org/3/library/asyncio-queue.html#asyncio.PriorityQueue

[R20] 搜索与Git隐藏执行。ripgrep有配置与preprocessor；git worktree add可触发post-checkout。
- https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md
- https://git-scm.com/docs/githooks#_post_checkout

[R21] Patch职责与版本差异。unidiff解析；patch-ng发布版与开发分支能力不能混写，最终宿主提交仍由File Broker控制。
- https://github.com/matiasb/python-unidiff
- https://pypi.org/project/patch-ng/
- https://github.com/conan-io/python-patch-ng

[R22] 社区飞书参考。nanobot聊天接入和QR应用注册可参考；不能据此赋予OpenBot owner。
- https://github.com/HKUDS/nanobot/blob/main/docs/chat-apps.md
- https://github.com/HKUDS/nanobot/blob/main/docs/guides/feishu-ai-agent.md

[R23] 日志、追踪与平台权限。上下文需管理；OTel外部exporter与敏感数据需配置；Apple权限按实际状态检测。
- https://www.structlog.org/en/stable/contextvars.html
- https://opentelemetry.io/docs/security/handling-sensitive-data/
- https://opentelemetry.io/docs/languages/sdk-configuration/general/
- https://support.apple.com/guide/mac-help/control-access-screen-system-audio-recording-mchld6aa7d23/mac
- https://support.apple.com/en-my/guide/mac-help/mh43185/mac

[R24] 版本化许可证据。pathspec、Anthropic SDK与AstrBot的精确许可不同；最终以锁定发行物及使用方式审查。
- https://pypi.org/project/pathspec/
- https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/README.md
- https://github.com/AstrBotDevs/AstrBot/blob/master/LICENSE

