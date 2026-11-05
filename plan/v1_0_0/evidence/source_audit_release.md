> 历史完整审查：本文固定于2993593a。交付前增量620311b4及最新CI见docs/01_current_state.md、sources R24和source_audit_late_mcp.md；不要把本文旧CI计数当作最新结果。

# OpenBot macOS MVP → v1.0.0：平台、发行与官网审查

审查日期：2026-11-05。性质：只读仓库审查和发布设计建议；本轮未构建、签名、公证、安装或在用户 Mac 上执行测试。

冻结基线：main = 98ee0365a335ed297337c3c0c9aaf9cbf3d5883e；开发分支 codex/agent-client-observability = 2993593a5bd010b85d76a6ca9e279fc4977718dc。下文 [Rxx] 为后一个固定 SHA 的仓库证据；[Sxx] 为本次核验的官方资料。所有“建议、目标、门槛”均不表示已经实现。

## 1. 结论与最小交付边界

建议 v1.0.0 首发限定 macOS Apple Silicon 的桌面产品，交付签名、公证的 OpenBot.app 与 DMG，配套真实安装证据、可恢复升级、完整资产来源、操作文档和官网。Intel、Windows、Linux 分别保留资格计划；不因为同一套 Python 测试通过而称三平台产品已交付。

开发 MVP 可继续使用受控 uv 环境、CLI 启动 daemon 和未签名开发客户端。正式 v1 用户不应为了启动产品安装 Python、uv、Rust、Xcode 或克隆源码。容器后端和本地模型属于明确说明的外部前提：选定一个受支持后端及版本范围，不默默安装 Docker、不自动拉模型，也不在能力缺失时退到宿主执行。

首发沿用仓库现有客户端决定：Tauri 2 + 静态 ES modules/CSS/SVG；常驻 daemon 与窗口分离。网站另外采用静态内容系统，不把管理 token、工具执行或本地控制 API 暴露给官网。此方案不要求同步实现原生电脑操作、通用插件商店、多用户或企业管理。

更新器纳入“拟定的 v1 桌面方案”，不是倒推成原 M3/MVP 的历史必需项。若时间或资格不足，可通过正式范围决策延期自动下载安装，保留版本提示、经验证的手工更新和完整恢复路径；一致性备份、迁移校验、兼容检查与失败恢复不能延期。[R02][R03]

## 2. 当前仓库实际具备什么

| 实际证据 | 能够支持的结论 | 不能据此宣称 |
|---|---|---|
| 客户端 spec 与 plan；计划使用 Tauri 2 + 静态 ES 模块 [R01] | 客户端边界、页面和实现方向已有设计 | 桌面客户端、安装器已经完成 |
| 固定 SHA 文件树无 apps/desktop、Cargo.toml、tauri.conf 或网站源码 | 该快照尚未交付这些构建工程 | 不能把 design/plan 的勾选或文字视作产品演示 |
| build_pilot_bundle.py 10–22 行仅返回清单标志及 uv.lock 摘要 [R04] | 有打包元数据入口 | 已生成自包含 .app、DMG、PyInstaller bundle |
| runtime-assets.json 列举 rg、grammar、tiktoken、Chromium 等类别 [R05] | 已识别部分非 Python 资产 | 清单中的资产都已入包、离线可用、各平台均已验证 |
| release-supply-chain workflow 9–20 行运行已有检查脚本 [R06] | 有供应链检查任务 | 已具备签名、公证、tag 发版、最终包验证、官网发布流水线 |
| SPDX 清单只有产品与“非 Python 资产”两个汇总包；checksums 只有五个元数据文件 [R07] | 供应链文件已有骨架 | 已覆盖 Python/Rust/前端/浏览器/容器/摘取代码，或验证最终发行字节 |
| 最新 CI 的 Mac/Linux 测试和 Windows contracts 通过，原生 Docker/可选 SDK 模块仍跳过 [R08] | 相应自动化范围在指定环境通过 | 签名应用、干净首开、真实模型/飞书/浏览器/MCP产品链路通过 |
| live-probes 记录 Darwin arm64 的单次模型流与飞书连接探针，明确无 Tauri UI/签名资格 [R09] | 特定开发环境的真实探针可追溯 | 用户从 DMG 安装后，桌面→daemon→审批→隔离执行→飞书回执的完整体验通过 |

当前客户端 spec 特别声明首个增量是未签名 ARM64 开发构建，附着 CLI 已初始化的 daemon；安装、登录启动和持久 Keychain 属于后续切片。[R01] 因此从该增量到 v1 的工作不是再做一次发布按钮，而是补齐可分发产品的安装、身份、服务和恢复链。

## 3. 支持矩阵与版本契约

建议 V1-030 冻结以下矩阵，并输出机器可读的 release manifest。没有运行证据的行统一写 NOT_RUN/UNSUPPORTED，而不写“兼容”。

| 维度 | v1 建议 | 资格要求 |
|---|---|---|
| CPU | 原生 arm64；不提供未经验证的 universal2 | app、Python 原生扩展、Rust helper、浏览器及各资产逐项验证架构 |
| macOS | 以 macOS 15 为最低资格目标；发布前核对所有锁定依赖的最低要求，并跑最低目标与冻结时当前稳定系统；中间版本未测则不泛化承诺 | 官网列实际通过的主要版本和测试 build；至少一台 Apple Silicon 真机，干净 Mac/可还原 Mac VM 补安装矩阵 |
| Intel/Rosetta | 首发未承诺，独立后续资格 | x86_64 资产、Intel 真机、服务/浏览器/安装/升级全套证据；arm64 上一次 Rosetta 运行不能替代 |
| Linux/Windows | 源码及契约 CI 的范围按事实披露；不提供未经资格的桌面发行物 | 另行建立原生安装、用户服务、权限、浏览器依赖和更新通道 |
| 隔离执行 | 一个明确锁定并验证的 Mac 容器后端/版本范围 | Linux VM 内容器的网络、资源、回收和导出证据；Mac 宿主文件与钥匙串另测 |
| 浏览器 | 专用 profile、版本化浏览器资产、实际沙箱资格 | 不共享用户默认浏览器 profile；redirect/subresource/WebSocket/service worker/下载出口有实测 |
| 模型 | 一条已资格的云 Provider 路径 + 一条本地 Ollama 路径，状态分别显示 | 云端实际请求与取消/费用证据；本地模式禁云和实际出口证据，不互相替代 |
| 远程入口 | 飞书按真实测试租户与允许会话资格 | 收消息→任务→审批→执行→回执；连接探针不能替代 |
| GUI 自动操作 | 不进入这一版的必需范围 | 没有该能力就不要求辅助功能/屏幕录制权限；以后独立资格 |

“macOS 15”为建议目标，不是已证明系统下限；若冻结的 Tauri/Python/浏览器/容器依赖不能满足，V1-030 必须调整。Apple 页面与发行说明会变化，使用冻结当天实际系统 build，不把“最新”写进永久测试断言。[S01]

版本至少分开管理：产品 SemVer、桌面↔daemon 协议版本与兼容区间、数据库 schema 读写范围、policy/manifest 摘要、各运行资产版本、MCP 明确支持的协议版本。设计包 v1.2 不等于产品 1.2；不能全库替换成 1.0。SemVer 1.0 前要明确哪些 CLI/API/config 行为构成稳定公共接口；发行后的同一版本不能替换内容。[S02]

## 4. 安装、服务、凭据与权限

### 4.1 发行内容与路径

主发行物为 OpenBot-1.0.0-macos-arm64.dmg，内含 OpenBot.app。应用内使用固定路径的 PyInstaller onedir 运行时，封装 daemon/gateway 所需 Python 依赖；native supervisor 与受管 helper 都纳入版本清单。不要把纯 Python import 成功当作包含动态导入、grammar、tokenizer 缓存、浏览器及证书数据的证明。PyInstaller 不是跨平台编译器，Mac 发行包由 Mac 构建并实测。[S03]

app 包安装后视作只读：用户 profile、SQLite、artifact、诊断与受管浏览器 profile 在用户 Application Support/Cache 的产品专属目录；原工作区保持独立。用户数据目录采用最小用户权限，存放在 app 内或更新时覆盖的目录均不允许。常规安装选择 /Applications；用户无写入权限时支持经资格的用户 Applications 路径或明确说明，不请求 root 来掩盖路径设计。

所有外部下载必须展示用途、来源、大小/空间预算和网络需求，并验证锁定摘要或签名。基础 UI/doctor 在干净离线机器上应能启动并准确报告“缺少后端/模型”；只有已经预置完整模型与容器资产时才承诺离线执行。不要把“可离线打开应用”宣传成“初次安装无需网络即可运行任意模型”。

### 4.2 用户级服务

推荐现代 macOS 的用户级 LaunchAgent/helper 路径，优先评估 SMAppService 作为受支持系统 API；它在 macOS 13 起支持应用内的 login item/agent/daemon 注册，并有状态/用户批准语义。[S04] OpenBot 的后台服务属于当前用户，不应改成 root LaunchDaemon。

必须完成真实注册/启动/停止/卸载/升级再注册及用户在系统设置禁用后的行为。写出 plist 或 Popen 一个子进程不足以证明服务资格。只读 daemon identity、profile 唯一锁和 epoch 仍由核心维护；父 UI 与子 daemon 不得争同一生命周期锁造成自锁。关闭窗口不停止服务，显式停止服务必须先进入维护模式并确认受管执行域回收。睡眠不能等同取消，醒来后重验时间、连接、租约和审批有效期。

卸载先停止并注销本产品服务，默认保留 profile 和工作区。删除数据、Keychain 条目或受管浏览器 profile 均需用户明确选择；不能清理其他产品容器、共享浏览器、全盘缓存或任意同名进程。

### 4.3 密钥与系统权限

开发版的内存秘密 + 无回显 CLI 注入可以作为过渡；面向普通用户的 v1 要有已资格的 Keychain 持久路径、可用性检查、撤销/轮换/锁定后的明确错误。真实密钥不得进入 argv、日志、渲染层状态或诊断包。不能把模拟 Keychain、明文 basic backend 或只测成功分支视作 Mac Keychain 合格。

身份要用正式签名的真实 app/helper 测试：首次授权、拒绝、重新登录、升级身份连续性、Keychain 锁定与失效都要覆盖。Tauri capability 只约束 WebView 可调用的 native commands；注册的自定义 commands 默认允许所有窗口使用，需用 AppManifest 和明确 capability 白名单收紧。它不提供 worker 的操作系统沙箱。[S05]

首发如果只有本地 UI、受管文件工作区和隔离工具，就按实际动作申请权限，不在 onboarding 一次索取 Full Disk Access、辅助功能或屏幕录制。若后续增加原生桌面能力，再按对应动作申请 TCC；拒绝/撤销要禁用该能力且不循环弹窗。签名、公证、TCC、Keychain 与容器隔离是不同控制层。

## 5. 签名、公证和首开流水线

以下是要求实现的顺序，不是当前仓库已有命令：

1. 从冻结 SHA 和锁文件在指定 Mac 环境构建正式目标；枚举全部 Mach-O、Python 扩展、helper 和嵌套可执行资产。先生成内部资产清单，检查架构、路径、依赖、许可证与调试入口。
2. 对需自行签名的嵌套代码由内而外使用 Developer ID Application 身份签名，启用符合实际运行需求的 hardened runtime 与时间戳。第三方已签资产逐项设计保留/重签规则；不能全目录盲签或通过宽松 entitlement 消除错误。最终 app 不带 get-task-allow、远程调试、测试 WebDriver/IPC 或开发 token。
3. 用当前 notarytool 工作流提交可接受的分发容器，等待结果并保存完整诊断；修复拒绝和警告后再进入下一门槛。公证是 Apple 自动扫描与签名检查，不是 App Review，更不是全部产品功能通过。[S06]
4. 按实际 app/DMG 包装流程装订 ticket，验证最终发行容器与安装后的 app。装订或重新打包可能改变字节，最终 SHA256、updater 签名和 provenance 的 subject 都必须对最终交付字节计算。
5. 在干净状态通过实际下载路径保留 quarantine，按用户步骤挂载 DMG、复制、首次打开、启动后台服务和执行最小任务。再用干净快照做断网首次打开，确认装订票据可工作；开发机先前 Gatekeeper 缓存不能替代。[S07]

可用的诊断工具及条件：

| 工具 | 适用条件与用途 |
|---|---|
| codesign --verify --deep --strict --verbose=2 /path/OpenBot.app | 已完成打包/签名的真实 app；只读验证嵌套签名。这里的 --deep 用于验证，不作为盲目递归重签方案 |
| codesign -d --entitlements :- /path/OpenBot.app | 只读检查实际 entitlements；还需检查相关 helper，日志不能收集私人路径/秘密 |
| xcrun notarytool submit /path/archive --keychain-profile PROFILE --wait | 受保护发布环境，具备 Xcode 工具和预配置公证凭据；不是普通用户安装步骤 |
| xcrun stapler validate /path/OpenBot.app | 对实际分发流程中已装订对象验证；DMG 也按本次包装策略验证 |
| syspolicy_check distribution /path/OpenBot.app | macOS 14 及以后，对候选 app 做 Gatekeeper 分发评估；仍需真实首次打开 |
| spctl -a -t exec -vvv /path/OpenBot.app | Apple 文档给出的较旧系统/辅助评估路径；不能以此替代下载首开 |
| shasum -a 256 /path/OpenBot-1.0.0-macos-arm64.dmg | 与发布 manifest 对照最终字节；普通摘要本身不证明发布者身份 |

上述绝对路径仅为占位，发布 runbook 必须使用本次构建的明确产物路径。不得指导用户关闭 Gatekeeper、批量删除 quarantine、chmod 777、关闭 SIP、降级 Chromium 沙箱或进行宿主执行兜底。

## 6. 升级和恢复必须与 daemon 一起设计

一个可用更新器不能单独替换 Tauri.app 就认为升级完成。release manifest 至少关联 desktop/core/gateway/supervisor、native assets、协议范围、DB schema 读写范围、policy 摘要、后端资格与签名身份。跨组件组合不受支持时应拒绝启动新任务并给出可执行恢复说明。

升级事务建议为：发现与下载 → 验证签名/摘要/架构/版本 → 验证兼容性与磁盘空间 → 进入持久维护态并停止新派发 → 安全停止受管 worker/容器并确认旧 epoch 失效 → 一致性备份 DB、必要 artifact 清单和配置 → 迁移并校验 → 原子激活新组件 → daemon/session/UI 健康检查 → 恢复接单。持久 UNKNOWN 和资源 quarantine 不得在升级、回滚或服务重注册时清除；未核对的外部操作不得自动重发。[R02]

备份不直接导出 Keychain 密钥；保存 secret_ref 的恢复条件并测试钥匙串不可用时的失败体验。Artifact 必须与数据库引用及 pin 一致，不能只复制一个运行中的 SQLite 主文件。升级期间的事件/审批状态要可恢复，policy、工具 schema、资源或 manifest 改变后重新判定批准是否仍有效。

回滚分三种：

| 情况 | 允许的恢复 |
|---|---|
| 新版本尚未写入新数据，旧版本可读当前 schema | 回退预先验证的旧组件集，保留审计事件 |
| 迁移失败，尚未对外执行新操作 | 按冻结的安全窗口恢复一致性备份，并重新核对进程/epoch/资源 |
| 已产生新写入或外部副作用，旧版本不兼容 | 停止新派发，优先向前修复或显式数据迁移；展示恢复旧备份会丢哪些数据，不能“一键无损” |

自动更新采取用户确认、受支持版本递增和受控通道。Tauri updater 要求专用更新签名，生产传输使用 HTTPS；Mac updater archive 与其签名是另外的资产。这一信任根与 Apple Developer ID 不同，也不自动提供数据库兼容判断。[S08] 核心升级协调应留在受信 Rust/daemon 一侧，不能给 WebView 绕过维护事务的任意 install 能力。

stable 与 beta 通道使用不同明确指针，切换需用户确认，绝不因 stable 指针回退就默认降级。撤回坏版本可以暂停推送和指向已验证修复版；若必须降级，需要专门验证旧版本的数据兼容、最低安全版本与恢复方案。签名 key 丢失/泄漏也要有轮换与紧急手工恢复说明。

## 7. 发行物、供应链与 CI

### 7.1 需要交付的文件

必需：正式 DMG/app、machine-readable release manifest、最终 SHA256 清单、实际组件 SBOM、对应 THIRD_PARTY_NOTICES/licenses、release notes、安装/升级/卸载/恢复指南、明确平台/功能资格矩阵、测试证据索引。若启用自动更新，再交付实际 .app.tar.gz、签名与通道 manifest。另行打 CLI 压缩包、PKG、universal2 都是新增资格负担，首发不必同时做。

SBOM 必须从实际构建产物及锁文件导出，覆盖 Python、Rust、前端依赖、浏览器、grammar、tokenizer 数据、容器镜像与摘取代码，并区分“入包”和“运行时另行获取”。记录实际 digest、来源/版本、许可证与许可证文本；不能将整个非 Python 资产归成 MIT AND Apache-2.0。容器/浏览器可再分独立 SBOM，并在总清单建立关系。打包扫描要检查文件内容与符号链接目标，现有文件名级 clean 标志不证明没有秘密。

GitHub artifact attestation 用于验证产物来源、workflow/commit 与摘要，不证明程序无漏洞、不替代 Apple 签名/公证，也不因开启一个 action 就获得完整 SLSA 声明。[S09] 它必须绑定最终 app/DMG/updater archive，验证者实际检查仓库、workflow、ref、subject digest；有 SBOM attestation 时同时验证真实 SBOM。

当前官方 GitHub 文档使用 actions/attest 的接口；实施时锁定经过复核的完整 action SHA，而不是照抄本报告中的浮动版本。可在支持的仓库启用 immutable releases：先完成草稿的全部资产与校验，发布后 tag 和资产被锁，标题/说明仍可编辑。不可把同名版本换包当修复；应发新 patch 版本。[S10]

### 7.2 流水线层次

| 层 | 应完成的事 | 不应被混淆的范围 |
|---|---|---|
| PR/LINUX | 静态检查、契约/核心测试、前端纯逻辑、文档构建、清单校验；显式列出 skip | 不能验证 Mac app、TCC、Keychain、SMAppService 或 Gatekeeper |
| PR/MAC | 锁定 Python/Rust/前端构建与 Mac 专用集成；记录系统与架构 | GitHub Mac runner 不代表干净真实下载用户或睡眠/外设硬件 |
| MAC UI TEST | 实际 Tauri + WKWebView，真实 Rust bridge；可用受控测试专用驱动 | 浏览器 mock invoke 的渲染测试不能冒充真实客户端 |
| RC BUILD | 冻结 SHA，原生构建、供应链、签名、公证，保存最终字节和证据 | 不能签完后再悄悄重构建、补文件却复用旧摘要 |
| RC NATIVE | 干净安装、登录服务、Keychain、离线首开、睡眠/断网/空间不足、升级恢复 | 不能由单纯 Linux 容器内测试覆盖 Mac 宿主风险 |
| PUBLISH | 资格聚合、发行说明核对、发布受保护 tag/资产、更新官网和最后的通道指针 | 有构建产物不等于允许公开宣传所有能力 |

官方当前 Tauri 文档已推荐 @wdio/tauri-service 的嵌入式 WebDriver 路径，支持 macOS；直接 tauri-driver 的原生路径仍有平台差异。因此不能沿用“Mac 完全无法做 Tauri 自动化”的旧结论。[S11] 需要驱动插件的构建必须为测试专用，发行构建不能包含能调用后端任意代码的测试接口；对最终签名发行物另做人工/系统级烟雾验证。

签名、公证、更新私钥仅给受保护的 release job。PR job 无权读取；构建与发布最小权限、临时 Keychain、日志脱敏，结束后移除临时材料。GitHub Environment 可将分支与审批/密钥获取约束在发布环境，具体保护能力取决于仓库类型和计划。[S12] 这是拟实施项目流程，不是本次研究要求用户另行批准任何动作。

## 8. 真机质量门槛

必须把开发探针与用户流程分别保存证据。至少覆盖：

- 从下载 DMG 到第一次成功任务的完整新用户路径，含权限拒绝和无后端；原生 arm64、没有开发工具、没有预先缓存。
- 登录、注销、重启、用户禁用后台项、重复启动 app/CLI、daemon 崩溃、窗口关闭/重开；唯一 profile 与旧 epoch 失效证据。
- 真机睡眠/唤醒、网络断连/恢复、代理变化、受控磁盘空间不足；工具执行与外部回执不确定时仍 UNKNOWN，恢复后不重发。
- Keychain 锁定/拒绝/轮换、正式签名身份升级；secret 不出现在 argv、进程诊断、WebView、日志/导出中。
- 已声明的 Browser/MCP/云 Provider/Ollama/飞书真实链路；后端关闭和能力缺失都 fail closed，缺凭据则对应门禁 BLOCKED，不用 mock 顶替。
- 下载中断、签名/架构错误、app 路径变化、迁移中断、备份不足/损坏、升级后健康失败、已新写入时回滚的恢复决策。

性能以 V1-009 冻结的可重现基准为准，记录硬件/系统/网络/模型、冷/热启动条件和分位数。分开测本机 UI 响应、daemon 开销与远端模型耗时；原文件的固定毫秒、包体、bug 数字不能沿用为事实。建议 beta 至少覆盖连续日常试用与受控故障循环，记录失败率、取消到停止延迟、残留进程/容器、内存/磁盘增长和首次成功率；阈值在测试前写入，不能看结果后临时降低。

## 9. 官网的最小技术与内容方案

仓库尚无官网技术栈。推荐 Astro 静态输出 + Starlight 文档，默认静态 Markdown 内容、少量按需交互、中文/英文路由；不引入账户系统、支付、数据库或第二套 agent API。Astro 的构建时内容适合项目文档，Starlight 提供多语言路由和 UI 文案机制；翻译 fallback 不等于关键页面已经翻译完成。[S13][S14]

桌面仍保留仓库已选静态 ES 模块。官网可以共享色彩/排版 token、图标和文案模型，但不能共享 desktop bridge/token 或让官网页面获取 native IPC。若后续桌面复杂度证明需要框架，再用独立 ADR 决策；当前发布不为统一技术栈重写 UI。

建议信息架构：

1. 首页：一句话目标、已经资格的三到五个用户工作流、明确限制、真实演示的版本标签。
2. 下载：唯一 stable 版本、arm64/系统清单、后端前提、大小与摘要、公证信息、发行说明、历史版本和验证方式。
3. 入门：安装→首次设置→模型/后端→一个可重复的只读任务→受审批写入→取消与恢复。
4. 文档：工作区授权、飞书测试会话、Browser/MCP 限制、网络模式、升级/备份、UNKNOWN 核对。
5. 安全与隐私：本地/云端数据去向、钥匙串、日志/诊断、权限、漏洞报告途径；“本地”不等于“绝不联网”。
6. 发布/支持：changelog、已知问题、支持范围、诊断包脱敏、许可证/归属、联系方式或 issue 模板。

开源项目信息站可优先用 GitHub Pages 的静态部署，配自有域名和 HTTPS；下载大文件放版本化 Releases。它支持正确配置自定义域名后的 HTTPS，但不能作为敏感凭据交易页面。[S15] 若需要自定义响应头策略、区域性能保证或后端，再单独评估静态托管；不在 v1 假定已有这些能力。

网站和 updater 读取同一个经过资格的发行 manifest，避免手写“最新版”链接落错包。发布顺序是验证最终发行资产→核对网站内容→上线版本页→最后更新 stable 指针；未发布的目标能力用 roadmap 标示。网站部署不包含任何用户数据、密钥或私有诊断证据。

### 9.1 可访问性验收

以 WCAG 2.2 AA 为工程目标，并逐项列出测试记录，不使用“自动扫描通过=全面合规”或未经评估的法律认证说法。[S16]

- 全键盘完成导航、下载、语言切换和文档搜索；合理焦点顺序、可见焦点、跳到正文链接；浮层不得把焦点完全遮住。[S17]
- 常规文字对比至少 4.5:1，大字至少 3:1；状态不能仅靠颜色。[S18]
- 交互目标按至少 24×24 CSS px 或标准允许的间距/等价例外设计；关键下载/批准按钮宜更大。[S19]
- 200% 文字缩放与 320 CSS px 宽度回流；长命令可局部滚动，不能让正文或下载按钮被裁切。
- 语义标题、按钮/链接名称、表单 label、图像替代文字、语言标记、状态提示；动效可减少。
- 自动检查之外，真实 Safari/VoiceOver 与键盘人工走关键路径；桌面应用另测 WKWebView 与原生菜单/对话框。工具调用事件不能每个 token 都刷屏打断读屏。

## 10. 发布层次与任务衔接

开发 Alpha：先完成真实 runtime、恢复/Keychain/受管执行、Tauri 控制和用户服务，获得“开发环境能用”的证据；V1-030 冻结对外契约。

可安装 Beta：V1-031 输出实际 bundle，V1-033 建立迁移/恢复；补 V1-032 签名公证资格、V1-035 完整来源。V1-037 真机和 V1-038 性能/用户试用必须使用可追溯产物。

RC：V1-034 完成签名更新和回退，或记录经批准的手工更新延期方案；V1-036 聚合所有证据，V1-039 使用同一 runbook 全程彩排。RC 中任何 artifact 变更都重算摘要并重跑受影响门禁，不只改 README。

GA：只有冻结范围的门禁齐全才发布 1.0.0，发布说明逐条对应已验证范围。没有 Apple 开发者签名身份、真实 Mac、相应凭据或后端时，把对应门禁明确列 BLOCKED；继续完成不受阻的工程任务，不能以无凭据为由停止所有工作，也不能以模拟通过掩盖缺证。

详细任务在本目录 release_tasks.json（V1-030—039）；其 status 全为 PLANNED，current_evidence 只描述本轮读到的已有材料。

## 11. 仓库证据索引（固定 SHA）

R00 文件树： https://github.com/xiongcp/OpenBot/tree/2993593a5bd010b85d76a6ca9e279fc4977718dc

R01 客户端计划与规格：
- https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/docs/superpowers/plans/2026-11-05-agent-client.md#L9-L21
- https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/docs/superpowers/plans/2026-11-05-agent-client.md#L64-L87
- https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/docs/superpowers/specs/2026-11-05-agent-client-design.md#L241-L290

R02 桌面交付/升级既有设计： https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/docs/08_desktop_release.md#L41-L61

R03 原项目范围与里程碑： https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/docs/00_scope.md ； https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/docs/10_project_plan.md

R04 现有清单生成： https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/scripts/build/build_pilot_bundle.py#L10-L22

R05 运行资产： https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/packaging/runtime-assets.json

R06 现有 release gate： https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/.github/workflows/release-supply-chain.yml#L1-L20

R07 现有汇总 SBOM 与 metadata checksum： https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/release/SBOM/spdx-pilot.spdx.json#L7-L21 ； https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/release/checksums.json#L3-L8

R08 CI： https://github.com/xiongcp/OpenBot/actions/runs/41979113332 ；本轮主代理提供并保存的明细：work/v1_plan/review_snapshot.json。Mac 341 passed/3 skipped，Linux 339 passed/3 skipped/1 deselected，Windows 41 contracts passed。这里只引用已有 run，不是本代理执行结果。

R09 局部实探： https://github.com/xiongcp/OpenBot/blob/2993593a5bd010b85d76a6ca9e279fc4977718dc/docs/evidence/2026-11-05-client-live-probes.md

## 12. 官方资料索引（均于 2026-11-05 读取/检索核验）

| ID | 官方来源 | 用于核实的事实与边界 |
|---|---|---|
| S01 | https://support.apple.com/en-us/109033 ; https://developer.apple.com/documentation/macos-release-notes | 当前 macOS 版本和发行说明入口；测试固定 build，报告不依赖“最新”标签 |
| S02 | https://semver.org/ | 公开 API 与 SemVer 1.0、版本不可替换；不是数据库兼容证明 |
| S03 | https://pyinstaller.org/en/stable/index.html ; https://www.pyinstaller.org/en/stable/feature-notes.html | 打包 Python 与依赖、非跨平台编译器、Mac 原生资产与签名要求 |
| S04 | https://developer.apple.com/documentation/servicemanagement/smappservice ; https://developer.apple.com/documentation/servicemanagement/updating-helper-executables-from-earlier-versions-of-macos | macOS 13 起的 helper 注册与用户批准/状态；仍需实际产品接入 |
| S05 | https://v2.tauri.app/security/capabilities/ | WebView/native command 权限、AppManifest、自定义命令默认范围；不是 OS worker 沙箱 |
| S06 | https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution ; https://developer.apple.com/documentation/security/customizing-the-notarization-workflow ; https://v2.tauri.app/distribute/sign/macos/ | Developer ID/hardened runtime/公证、notarytool；自动扫描不替代功能验收 |
| S07 | https://developer.apple.com/forums/thread/130560 | Apple DTS：干净机器、实际下载 quarantine、在线/离线首开、syspolicy_check 条件 |
| S08 | https://v2.tauri.app/plugin/updater/ | 更新签名不可关闭、HTTPS、Mac archive 与 signature；不负责 DB/跨组件事务 |
| S09 | https://docs.github.com/en/actions/concepts/security/artifact-attestations ; https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations | provenance/SBOM 证明与验证；不是安全性保证，仓库计划适用性需检查 |
| S10 | https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases ; https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/verify-release-integrity | immutable tag/资产及 release verification；发行说明仍可编辑 |
| S11 | https://v2.tauri.app/develop/tests/webdriver/ | 目前支持 Mac 的嵌入式驱动路径与直接 tauri-driver 限制；测试接口不能进发行包 |
| S12 | https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments ; https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/review-deployments | 发布环境保护、secrets 等待已配置门槛；不假设账户拥有所有功能 |
| S13 | https://docs.astro.build/en/guides/routing/ ; https://docs.astro.build/guides/content-collections/ ; https://docs.astro.build/en/guides/deploy/github/ | 静态路由/构建时内容/Pages 部署；实施时锁依赖版本 |
| S14 | https://starlight.astro.build/guides/i18n/ | 文档多语言路由和 fallback；不是自动完整翻译 |
| S15 | https://docs.github.com/en/pages/getting-started-with-github-pages/securing-your-github-pages-site-with-https | Pages HTTPS、自定义域名、混合内容与敏感事务限制 |
| S16 | https://www.w3.org/TR/WCAG22/ | WCAG 2.2 标准与 AA 工程目标；人工与自动化测试结合 |
| S17 | https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html | 键盘焦点不可被完全遮住；说明文档辅助解释规范 |
| S18 | https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html | 正文/大字的最低对比度及例外 |
| S19 | https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum | 24×24 CSS px 目标或规定间距/例外 |

### 尚未核实和明确不做的推断

没有取得本次签名证书、Apple 账户/公证配置、域名权限、实际用户安装测试、Intel 真机或全部锁定依赖的最低系统证明。本报告不宣称这些条件已具备。官方当前页面用于核验 API 和能力边界，不能自动替换项目锁定版本，更不能把 MCP draft 当作项目的新协议。

不将“SOCKS5 代理设置”推断为所有网络出口不可绕过；不将 Browser/MCP/Tauri 名字推断为沙箱；不将事件回放推断为安全重新执行；不将动态工具/框架 SDK 的存在推断为 OpenBot 已完成生产接线。所有这些都要进入对应执行域、协议和实际请求证据门槛。
