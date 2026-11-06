# OpenBot macOS 与真实集成 MVP 验收手册

核对日期：2026-11-05。

代码基线：[xiongcp/OpenBot 固定提交 a223d36a659b7ecf32fca2b4890fc187d3e96e48](https://github.com/xiongcp/OpenBot/tree/a223d36a659b7ecf32fca2b4890fc187d3e96e48)。

设计基线：v1.2 的 docs/07_feishu.md、08_desktop_release.md、09_testing_operations.md、12_component_reuse.md、13_component_qualification.md。用例见../cases/test_cases.json 中的平台/集成分组，共 38 项：TC-MAC-001 至 022、TC-INT-001 至 016。每项包含前提、步骤、预期、证据、诊断、修复方向和关联回归。所有用例当前均为 NOT_RUN，requires_real_environment=true。

**当前结论：已经发现真实入口和资格证据之间的缺口，不能仅凭现有 green pytest、native/e2e 文件名或报告中的 verified 字段宣布 macOS MVP 通过。** 本轮完成只读代码检查与官方资料核验，未在用户 Mac 执行这些用例，未调用真实飞书/模型账户，未修改仓库、提交或推送代码。

## 1. 先处理基线中的真实接线与证据问题

以下是固定提交中已读源码的事实，不是运行后的测试结果。若其他文件已实现完整生产接线，应把它们连同真实入口和执行证据补齐；不能据本次局部阅读武断断言全仓库绝无替代实现。

| 编号 | 固定提交中实际看见的行为 | 为什么尚不能作为相应能力已通过 | 最小修复与对应验收 |
|---|---|---|---|
| PG01 | cli.main 的 argparse 只接受 version、health；task/approval/reconcile 仅在 run_cli_command 获得外部传入 session 时可调用 | 文档中的 openbot task create 不是当前已接通的终端入口；health 无session时返回固定M0/daemon_running=false | 用真实subprocess先复现解析拒绝，再接安全会话bootstrap与真实本地HTTP/IPC；TC-MAC-001/004、TC-INT-016 |
| PG02 | MacOSNativePlatformGate 用内存 _MacKeychainStub；向 BrowserIsolationAttestation 手填两个True；仅创建a.txt读写却输出 filesystem_and_symlink_verified | 未触达真实Keychain/Chromium/链接攻击；输出“verified”比观测范围宽 | 模拟结果与真实资格分型，能力只能来自实际适配器证据；TC-MAC-001/018/019、TC-INT-007 |
| PG03 | UserDaemonInstaller.install 只生成 openbot-user-daemon.json；uninstall 只删除该JSON | 不等于LaunchAgent plist/SMAppService注册、启动、状态查询或注销 | 完整用户会话服务适配及真实launchd状态对照；TC-MAC-008/009/010/013 |
| PG04 | BrowserProfileSessionManager 只有进程内dict锁、目录与参数检查；当前所读文件没有Playwright启动 | 同目录不同名称、两个进程竞争和实际Chromium安全状态未被证明 | 真实BrowserPrimitive、跨进程目录身份互斥、可信沙箱探针；TC-INT-007至009、015 |
| PG05 | McpStdioLifecycleClient.negotiate_initialize 只比较调用者传入版本字符串；bound_response_bytes 在完整bytes已经到内存后截断 | 没有证明真实SDK/stdio握手、读入期间有界、协议帧完整性或server真正被隔离 | 接真实受控stdio与SDK，parser前限流/限帧，产物摘要实际核验；TC-INT-010至012 |
| PG06 | ProcessSupervisorService确有POSIX killpg；但start token来自调用方，container_reclaimed缺省True，残留只看已给定PID与模拟残留 | 不能单凭字符串相等证明OS创建身份；不能据默认布尔值证明engine容器已停止或任意脱离子孙已清理 | 由可信OS/engine查询提供身份/最终状态，清理未确认则隔离；TC-MAC-014/015 |
| PG07 | vertical_slice 的API为 _InProcessTransport；worker是宿主Python sleep进程；故障路径在同一对象上调recover_epoch且手填效果次数 | 可以验证部分状态逻辑，不能证明真实socket、容器执行、SIGKILL、新进程重开DB或独立外部效果 | 保留有价值的合同测试，新增真实进程/效果接收器的产品闭环；TC-MAC-014、TC-INT-005/009/012/016 |
| PG08 | chaos_soak用伪PID/ClockSnapshot和上述harness拼接故障标签，备份/满盘项直接append | 没有真实DNS/TCP、设备睡眠、kill和磁盘故障；sample_count不等于已发生的真实故障数量 | 报告注明证据层级；用真实受控故障复测，不能修改标签制造通过；TC-MAC-011/012/013/014/021及核心用例 |
| PG09 | native Docker PoC明确只测试CLI原语；硬编码Docker二进制和开发者socket路径，临时输出目录设为0777 | 有真实原语测试价值，但不可在其他Mac盲跑，也不是正式Broker/Artifact路径已通过 | 先参数化并验证当前测试用户/后端，采用最小写权限策略，再重跑PoC与产品测试；TC-MAC-003/015/016/017 |
| PG10 | README的新进度描述与external-environments、backend-capabilities中的旧IN_PROGRESS/未实现记录存在冲突 | 历史记录、当前代码与当前通过状态混在一起，无法单据一份文件判断完成 | 保留历史、按本次commit重建结果索引，区分真实API/101握手、合同、原语与产品闭环 |

### 已读仓库来源

以下链接全部固定到上述SHA，避免后来main变化影响判断：

- [CLI主入口与内部session分发](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/cli.py)
- [模块入口](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/__main__.py)
- [macOS gate](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/macos_gate.py)
- [用户服务installer](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/daemon_installer.py)
- [浏览器session](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/tools/executors/browser/session.py)
- [MCP client](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/tools/mcp/client.py)
- [进程监督Port](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/tools/executors/supervision_port.py)
- [vertical_slice](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/vertical_slice.py)
- [chaos_soak](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/chaos_soak.py)
- [Docker PoC实现](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/tests/components/native_poc/docker_poc.py)
- [Docker PoC测试入口](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/tests/components/native_poc/test_docker.py)
- [verify脚本](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/scripts/verify.py)
- [依赖组与Python要求](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/pyproject.toml)
- [README](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/README.md)
- [旧外部环境记录](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/docs/evidence/external-environments.md)
- [后端能力记录](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/docs/evidence/backend-capabilities.md)

native PoC内0777仅位于私有临时目录下，本轮不把它直接推断为正式产品漏洞；也不推荐复制此权限设置作为Mac挂载失败的解决方式。其硬编码socket必须先更正为经过核验的测试后端。当前默认verify会清除OPENBOT_NATIVE_TESTS，所以verify全绿不能包含该真实容器门禁。

## 2. 判定范围与证据层级

| 证据类型 | 可证明的范围 | 不应外推的内容 |
|---|---|---|
| 只读源码/官方文档 | 代码路径或平台合同的可见事实 | 目标机器已运行成功、服务已正确配置 |
| 合同/内存harness | 数据转换、状态机、错误映射、模拟协议条件 | 真实进程崩溃、网络、OS权限或实际服务端效果 |
| 真实原语PoC | 指定机器/版本上的一个进程组、容器、锁或API | 整个产品入口已经正确装配、所有失败窗口都安全 |
| 产品跨进程集成 | 实际CLI/HTTP/Daemon/worker/DB/artifact之间的调用与恢复 | 真实飞书租户、云模型或所有发布机器可用 |
| 真实平台与服务闭环 | 本次Mac/版本/受控租户/资产组合的实际结果 | 任意Mac、Intel、三平台M3或100%长期可靠性 |

Apple官方要求对Apple Silicon与Intel两种架构分别测试；universal仅表示包含架构代码，Rosetta执行x86_64并不等价于Intel实机资格。[P01]

Docker Desktop在Mac上运行Linux VM中的engine和容器；宿主挂载仍有Mac权限边界。因此Darwin上的控制面测试、Linux容器命令测试和原生桌面控制必须分开记录。ECI/商业版功能、Podman/OrbStack/Lima等也不能未经验证当作同一后端。[P07][P08]

### 阶段条件

- 当前优先在用户实际Mac架构上验收v1.2/M3必需功能；Apple Silicon用TC-MAC-001，Intel另用TC-MAC-002。完整macOS MVP必须分别具备真实云Provider与真实Ollama证据；仅一类模型服务只能描述为收窄试点。
- Intel仅在发布声明包含它时成为必过门禁。没有实机时是未验证/环境阻塞；不能记通过。明确不支持时才可记录有理由的不适用。
- 用户主要在Mac开发不等于Windows/Linux自动通过；macOS试点可独立推进，但不能把未完成的三平台M3写成完整完成。
- 当前M4/Tauri/桌面签名/自动更新未实现时，TC-MAC-006/007相关发行与TC-MAC-020的原生桌面子例按条件评估；MVP不要求无关录屏、Accessibility或Full Disk Access。
- 原生桌面功能被实际提供后，对应权限撤销、helper身份和活跃会话门禁必须通过。签名公证一旦被用于正式发行声明，也必须完整验收。
- v1.2/M3必需的backup/恢复、真实入口、服务常驻、Browser/MCP/飞书能力不能以“M4未实现”为由全部豁免。
- 缺代码/实际接线是实现缺口；缺专用租户、真实设备或证书是对应环境阻塞；没有凭据不能顺手把本地工程TODO一并标完成。

### 状态填写

用例初始NOT_RUN。执行后PASS必须包含原始证据、实际命令、退出码/真实响应、commit/build和环境；FAIL写最小复现与偏离；BLOCKED写最小缺少条件。只有明确不在本次发布声明内，才可将条件用例记录NOT_APPLICABLE并解释范围。pytest SKIPPED、SDK未安装、fixture返回stub、只运行开发机源码，不是平台PASS。

## 3. 执行顺序与前置准备

先保留现有工作区与上次证据，在独立QA工作区/测试用户运行。准备合成workspace、受控接收器、专用profile、固定容器/浏览器/MCP/model资产与限定预算。每次故障都要有独立观察者和有限清理步骤，不能让被杀进程自己报告“我已经成功被杀”。

| 顺序 | 执行范围 | 进入条件与结束证据 |
|---|---|---|
| 1 | PG01–PG08源码缺口复现、合同与实际命令入口 | 真实subprocess命令、真实API/socket/session；不能以函数调用代替 |
| 2 | TC-MAC-001/003/004/005/018/019 | 真实ARM64、安装资产、路径与Keychain；没有无关权限/联网补包 |
| 3 | TC-MAC-008/009/010/014/015/016/017 | 用户服务、OS锁、进程/容器与Artifact回收真实有效 |
| 4 | TC-INT-001至006、007至012、015 | 飞书/浏览器/MCP逐个真实能力闭环；缺某一环境只阻塞相应门禁 |
| 5 | TC-INT-013/014与TC-MAC-022 | 本地模型来源、实际出口、日志与诊断覆盖全部受管域 |
| 6 | TC-MAC-011/012/013/021及TC-INT-016 | 真实睡眠、断网、重启、恢复，再完成产品端到端 |
| 7 | 条件Intel/发行/桌面门禁 | 只对发布所宣称组合给出通过；真实签名/公证/干净首开另验 |

设备睡眠、注销、引擎重启等会打断本机工作，应在专用测试设备或明确空闲测试窗口执行，先保存用户其他工作。正常重启不等于物理断电；本计划不以关机断电破坏用户机器来补“强可靠性”结论。

## 4. 38项用例索引

详细步骤和定位字段以platform_cases.json为准。

| ID | 用例 | 优先级 | 门禁 |
|---|---|---|---|
| TC-MAC-001 | Apple Silicon 原生身份与通过报告必须来自真实能力 | P0 | MACOS_ARM64_BASELINE |
| TC-MAC-002 | Intel 原生资格与 Rosetta 结果分开 | P1 | INTEL_ONLY_IF_CLAIMED |
| TC-MAC-003 | Darwin 控制面与 Linux 容器执行域必须分离声明 | P0 | MACOS_EXECUTION_BOUNDARY |
| TC-MAC-004 | 干净 macOS 用户的真实安装与首次产品启动 | P0 | MACOS_INSTALL |
| TC-MAC-005 | OFFLINE 干净首用不隐式补下载资产 | P0 | MACOS_OFFLINE_FIRST_USE |
| TC-MAC-006 | Gatekeeper 真实首开、签名与公证声明一致 | P1 | DISTRIBUTION_IF_CLAIMED |
| TC-MAC-007 | 离线 Gatekeeper 与制品篡改负例 | P1 | DISTRIBUTION_OFFLINE_IF_CLAIMED |
| TC-MAC-008 | launchd 登录会话中的真实服务注册和环境 | P0 | MACOS_USER_SERVICE |
| TC-MAC-009 | 唯一 profile 锁、父子不自锁与客户端退出 | P0 | MACOS_SINGLE_INSTANCE |
| TC-MAC-010 | 显式停止与卸载仅回收已登记资源 | P0 | MACOS_STOP_UNINSTALL |
| TC-MAC-011 | 真实睡眠/唤醒后的审批、连接与在途任务 | P0 | MACOS_SLEEP_WAKE |
| TC-MAC-012 | 真实断网、网络切换与半开连接后的恢复 | P0 | MACOS_NETWORK_RECOVERY |
| TC-MAC-013 | 注销/登录与受控重启恢复，不承诺登录前常驻 | P0 | MACOS_LOGIN_REBOOT |
| TC-MAC-014 | 真实 SIGKILL、多代/脱离进程与 PID 身份核验 | P0 | MACOS_PROCESS_RECLAMATION |
| TC-MAC-015 | Docker 客户端死亡、引擎重启与容器独立归属 | P0 | MACOS_CONTAINER_LIFECYCLE |
| TC-MAC-016 | 实际容器权限、出口与资源上限生效 | P0 | MACOS_CONTAINER_ISOLATION |
| TC-MAC-017 | 容器产物 stop/wait→校验→登记→remove | P0 | MACOS_ARTIFACT_EXPORT |
| TC-MAC-018 | APFS 路径、大小写/Unicode别名与真实权限 | P0 | MACOS_FILESYSTEM |
| TC-MAC-019 | 真实 Keychain 后端、锁定/拒绝与最小注入 | P0 | MACOS_KEYCHAIN |
| TC-MAC-020 | TCC 按实际功能和执行二进制最小授权 | P0 | MVP_NO_EXTRA_TCC_AND_OPTIONAL_NATIVE |
| TC-MAC-021 | macOS 数据备份/恢复与版本变更的真实重启 | P0 | MACOS_RESTORE_AND_UPGRADE_IF_IMPLEMENTED |
| TC-MAC-022 | 真实SDK/系统故障诊断不泄漏秘密或启用遥测 | P0 | MACOS_DIAGNOSTICS |
| TC-INT-001 | 飞书真实测试应用接入、配对与 owner 撤销 | P0 | FEISHU_REAL_ENTRY |
| TC-INT-002 | 真实飞书事件持久 ACK、重投去重与重启 | P0 | FEISHU_DURABLE_INGRESS |
| TC-INT-003 | 真实审批卡 callback 的 deadline、重复与失效 | P0 | FEISHU_APPROVAL_CALLBACK |
| TC-INT-004 | 普通卡、CardKit权限不足与三个独立时钟 | P0 | FEISHU_CARD_DELIVERY |
| TC-INT-005 | 飞书发送成功但本地回执丢失的 UNKNOWN 核对 | P0 | FEISHU_UNKNOWN_SEND |
| TC-INT-006 | 真实 SDK 阻塞与进程外 Gateway watchdog | P0 | FEISHU_PROCESS_WATCHDOG |
| TC-INT-007 | 真实 Chromium 启动、跨进程 profile 锁与沙箱 | P0 | BROWSER_REAL_EXECUTOR |
| TC-INT-008 | 浏览器 Service Worker、重定向与实际出口 | P0 | BROWSER_NETWORK_BOUNDARY |
| TC-INT-009 | 浏览器目标变更与点击成功后断线 UNKNOWN | P0 | BROWSER_APPROVED_WRITE |
| TC-INT-010 | MCP 真实 stdio/SDK 握手、环境与流量上限 | P0 | MCP_REAL_TRANSPORT |
| TC-INT-011 | MCP 工具动态变化、伪造 hints 与旧授权失效 | P0 | MCP_MANIFEST_CHANGE |
| TC-INT-012 | MCP 写动作超时、取消与副作用核对 | P0 | MCP_UNKNOWN_WRITE |
| TC-INT-013 | Ollama 本地模型来源、禁云配置与实际出口 | P0 | OLLAMA_LOCAL_PROVENANCE |
| TC-INT-014 | OFFLINE/LOCAL_MODEL 实际受管域出口和模式切换 | P0 | REAL_EGRESS_ENFORCEMENT |
| TC-INT-015 | 浏览器上传/下载和污染数据进入真实 Artifact 流 | P0 | BROWSER_DATA_TRANSFER |
| TC-INT-016 | 真实 macOS 产品从飞书任务到批准执行、重启和核对的闭环 | P0 | MACOS_MVP_PRODUCT_E2E |

## 5. 已核实的项目命令及其适用条件

这里列出的是固定提交实际存在的入口；尚未运行。请在完整仓库checkout中执行，不在本次审查的零散repo_snapshot里运行。先核对HEAD与依赖锁，所有测试输出均存入本轮证据，保留上一轮日志而非悄悄覆盖历史。

### 5.1 基线与默认检查

适用条件：已安装项目要求的Python 3.12系列与uv，允许安装准备阶段联网，仓库锁文件完整。该baseline的pyproject声明Python >=3.12,<3.13；不是本手册猜测的运行时版本。

~~~bash
git rev-parse HEAD
git status --short
uv sync --locked
.venv/bin/python scripts/verify.py --phase M0
~~~

verify目前只接受M0/M1；默认M0，显式把OPENBOT_NATIVE_TESTS从子进程环境删除。它会写evidence/implementation日志/报告，而且没有启动产品服务。不能用不存在的--phase M3，不能把该命令结果当真实macOS/飞书/Browser/MCP验收。

如要按当前脚本检查M1组件准入，命令是：

~~~bash
.venv/bin/python scripts/verify.py --phase M1
~~~

两种phase都不改变“未启动真实服务”的证据边界。失败/timeout必须保留真实退出情况，不能只从最后一行PASS推导全部成功。

### 5.2 实际CLI可达性

适用条件：在项目完整根目录，安装已经完成。PYTHONPATH仅是当前源码入口诊断方式，不是最终干净安装通过的替代。

~~~bash
PYTHONPATH=services/core/src .venv/bin/python -m openbot --help
PYTHONPATH=services/core/src .venv/bin/python -m openbot version
PYTHONPATH=services/core/src .venv/bin/python -m openbot health
PYTHONPATH=services/core/src .venv/bin/python -m openbot task --help
~~~

最后一条用于无副作用复现主入口是否接受task，不创建真实任务。按当前源码应被主parser拒绝；结果仍须在目标环境用真实subprocess记录。health成功退出也不能证明daemon活着：没有session的当前分支返回固定daemon_running=false与stage=M0。

在修复真实入口以前，本手册不提供虚构的openbot daemon start、doctor、install或可直接用的task create完整命令。修复要提供真实服务启动、认证bootstrap、状态查询与受限transport，并把新命令/help/端到端回归写入对应提交。直接给run_cli_command注入内存session仍只覆盖合同层。

### 5.3 实际SDK对loopback的合同测试

适用条件：先确认需要的依赖组与锁，允许安装准备阶段联网；测试使用本地合成HTTP，不是真实云账户。

~~~bash
uv sync --locked --group provider-openai
.venv/bin/python -m pytest tests/components/contracts -q -rs
~~~

检查-rs显示的跳过原因和被收集用例；没有装可选SDK而跳过不能记模型适配已测。真正云服务质量、计费和凭据仍是另一门禁，不能从loopback合同反推。

### 5.4 真实Docker PoC——先审代码和测试后端，再运行

当前真实测试入口确实存在：

~~~bash
OPENBOT_NATIVE_TESTS=1 .venv/bin/python -m pytest tests/components/native_poc/test_docker.py::test_actual_native_container_limits_and_independent_lifecycle -q -rs
~~~

**该命令不是当前提交下可跨Mac直接复制执行的推荐命令。** 运行前至少完成：

1. 审查docker_poc.py并消除开发者特定的/usr/local/bin/docker及/Users/Zhuanz/.docker/run/docker.sock假设；用明确参数选择经过确认的当前测试用户engine，不能扫描/改用别人socket。
2. 从已锁定来源预置asset文件指向的镜像，实际验证digest、OS/arch，保持pull=never与测试镜像限制。
3. 输出区采用最小可写策略；不把原fixture的0777复制为正式权限修复。具体UID/GID/卷导出方式按Mac后端实测。
4. 确认只创建带独立run_id归属的容器、内存/PID/CPU限制和有限超时；cleanup只操作这些已登记资源。
5. 记录此命令只是原语资格，不替代真实Broker派发、Artifact登记和恢复路径。CPU配置读回不能冒称CPU压力已测，源码PoC本身也不宣称生产executor。

运行成功后仍需TC-MAC-015/016/017与TC-INT-016。未满足前提时留下BLOCKED/待修复信息，不在错误socket上试跑、不拉取latest、不关闭隔离。

## 6. macOS与外部工具诊断命令

以下命令需在目标Mac执行；本轮没有执行。OPENBOT_QA_*均是由操作者按已核实路径/身份填写的专用变量，不重设HOME等系统变量。占位符不是可原样粘贴的真实路径。任何输出在分享前删除凭据、个人目录和无关进程信息。

### 6.1 OS、架构和真实进程

~~~bash
sw_vers
uname -s
uname -m
sysctl -n hw.optional.arm64
file "$OPENBOT_QA_EXECUTABLE"
~~~

lipo存在且目标为Mach-O时，可检查lipo -archs。sysctl.proc_translated若存在可诊断当前调用进程的Rosetta状态；键不存在不等于所有进程都已证明原生。还需看Daemon、Python、Rust helper和Chromium各自的实际加载架构。[P01]

~~~bash
ps -p "$OPENBOT_QA_PID" -o pid=,ppid=,pgid=,uid=,lstart=,comm=
lsof -nP -a -p "$OPENBOT_QA_PID" -i
~~~

只传已确定属于测试域的PID。ps时间和PID是诊断资料，不能代替正式Supervisor的信号前创建身份验证，更不能只把同一个字符串传两次证明防PID重用。不要使用会泄漏环境/命令行秘密的全进程转储作为普通诊断包。

### 6.2 用户服务

适用条件：实际选型是LaunchAgent，目标GUI登录域存在，变量指向本次受测用户和服务。使用SMAppService时还要验证该API的注册/状态和系统登录项许可，不能把以下命令当全部安装实现。[P02][P03]

~~~bash
man launchctl
plutil -lint "$OPENBOT_QA_AGENT_PLIST"
plutil -extract Label raw -o - "$OPENBOT_QA_AGENT_PLIST"
launchctl print "gui/$OPENBOT_QA_UID/$OPENBOT_QA_LAUNCH_LABEL"
~~~

launchctl print可能包含配置或环境；只在私有证据目录保留原始输出，公开报告只摘必要状态/PID/退出码。通过产品正式安装/卸载执行变更；若需要用bootstrap/bootout定位，先读目标OS的man，且仅操作核实的测试label，不对system域或其他用户服务操作。

### 6.3 Gatekeeper、签名、公证

适用条件：先按用户真实下载/解包/安装方式取得制品，保留隔离属性；工具存在且适用于制品类型。Apple说明Gatekeeper首开结果受缓存影响，干净Mac/macOS VM快照每轮独立最可靠；CLI检查是补充。[P04][P05]

只读诊断：

~~~bash
xattr -p com.apple.quarantine "$OPENBOT_QA_DOWNLOAD"
xattr -p com.apple.quarantine "$OPENBOT_QA_APP"
codesign -dv --verbose=4 "$OPENBOT_QA_APP"
codesign --verify --strict --verbose=4 "$OPENBOT_QA_APP"
~~~

检查所有实际分发的可执行helper；不能只验外层图标。quarantine的原始属性是诊断信息，不把其字节格式当稳定应用API；程序需要操作属性时遵循Apple的quarantinePropertiesKey文档。[P05]

macOS14+且工具存在的.app诊断：

~~~bash
syspolicy_check distribution "$OPENBOT_QA_APP"
~~~

较旧系统或其他分发形态，依Apple文档选择，不能将三条全部对同一种文件执行：

~~~bash
spctl -a -t exec -vvv "$OPENBOT_QA_APP"
spctl -a -t open -vvv --context context:primary-signature "$OPENBOT_QA_DMG"
spctl -a -t install -vvv "$OPENBOT_QA_PKG"
~~~

适用的.app/.dmg/.pkg安装了Xcode工具时可用xcrun stapler validate验证附着票据；原始CLI二进制不能不加区分地套用stapler。notarization成功仍不替代真实首开与helper加载；离线首开必须在此前没在线信任过该制品的环境完成。[P04][P06]

不执行sudo spctl关闭防护、不删除com.apple.quarantine来“通过”、不使用xattr -dr清除目录属性、不复制chmod 777或重签未知代码作为修复。M3开发试点的签名限制如实记录，M4发行按其声明完整验收。

### 6.4 Docker实际后端与容器

适用条件：Docker CLI路径、私有QA配置目录和本次engine endpoint已确认。优先显式--config与--host，避免不知情地继承远端DOCKER_HOST/context。

~~~bash
"$OPENBOT_QA_DOCKER_BIN" --config "$OPENBOT_QA_DOCKER_CONFIG" --host "$OPENBOT_QA_DOCKER_HOST" version
"$OPENBOT_QA_DOCKER_BIN" --config "$OPENBOT_QA_DOCKER_CONFIG" --host "$OPENBOT_QA_DOCKER_HOST" info --format '{{.OSType}}/{{.Architecture}}'
"$OPENBOT_QA_DOCKER_BIN" --config "$OPENBOT_QA_DOCKER_CONFIG" --host "$OPENBOT_QA_DOCKER_HOST" container inspect --format 'id={{.Id}} running={{.State.Running}} status={{.State.Status}} exit={{.State.ExitCode}}' "$OPENBOT_QA_CONTAINER_ID"
~~~

可以用选择性inspect检查User、ReadonlyRootfs、NetworkMode、Capabilities、Memory、PidsLimit、NanoCpus、Mount目的地与只读属性，不导出完整Config.Env或个人registry配置。实际context可用docker context inspect选择性读取endpoint，确认后再使用；不要为了让测试通过切换用户默认context。[P09][P10]

回收的验收顺序是产品执行stop仍运行容器→有截止的wait/终态核对→有界暂存导出/路径类型链接权限与配额验证→Artifact登记或失败处置→remove。人为手工清理只能作为测试收尾，不能回填成产品已自动清理。Docker cp支持停止后的容器，-L会跟随源symlink；因此不使用跟随链接的导出方式，更不能把cp成功等同内容验证。[P11]

### 6.5 真实Ollama本地服务

当前官方文档有两种禁云配置：OLLAMA_NO_CLOUD=1，或server.json中disable_ollama_cloud=true，修改后须重启实际服务。关闭的是云模型/搜索；Mac App自动下载更新是另一条网络路径。必须在受控测试服务作用域验证配置实际生效，不能仅在OpenBot shell设置变量就认为已有Ollama服务继承了它。[P17][P18]

在锁定版本支持、独立测试端口已确认空闲且用户未共享该服务时，可为专用测试实例设置：

~~~bash
env OLLAMA_NO_CLOUD=1 OLLAMA_HOST=127.0.0.1:11435 OLLAMA_MODELS="$OPENBOT_QA_MODEL_DIR" "$OPENBOT_QA_OLLAMA_BIN" serve
~~~

这是一条持续前台服务命令，应由受管测试进程/harness带独立停止与资源控制启动，不在共享登录会话随意开启第二服务。11435只是示例测试端口，执行前要检查，不能假定固定空闲。模型目录只指向已准备并验明的测试资产；不执行run/pull去补缺模型，不改用户全局launchctl环境。

只读模型清单检查（确认服务监听该地址后）：

~~~bash
curl --noproxy '*' --max-time 5 --fail --show-error http://127.0.0.1:11435/api/tags
~~~

真实推理从产品模型适配器发起，并与所选本地模型digest/进程/出口对照。若用单独API探针，POST /api/generate的model、prompt与上限放合成请求文件，再经受控地址发送；它只证明服务可推理，仍不代表OpenBot的预算/取消/工具循环接通。[P19]

当前Ollama macOS文档写macOS14+、Apple M支持CPU/GPU、x86仅CPU；最终以候选锁定版和实际硬件记录为准。Mac Docker内Linux执行也不能用来证明原生Metal加速。[P18]

### 6.6 休眠、Keychain和TCC

睡眠/唤醒使用系统菜单与真实设备；注销/重启分别测试。可读取有限时间窗的pmset系统事件帮助定位，但不为测试修改全机电源策略。不要把ClockSnapshot构造、pid=8001或时间戳推进当真实系统睡眠/网络证据。

Keychain只使用独立测试用户/合成secret，记录实际keyring后端与应用签名身份。通过测试钥匙串/系统UI锁定和拒绝访问，不重置默认钥匙串、不把secret放security命令行参数、不运行会把secret打印到stdout的读取命令。Apple说明登录/睡眠/密码状态会影响钥匙串解锁，必须在launchd实际用户会话验证。[P20]

ScreenCapture/Accessibility采用实际helper的预检与系统UI授权/撤销；MVP headless无需这两项。Apple的AXIsProcessTrustedWithOptions判断当前进程，不能从UI壳得到True就给另一个helper授权。文件夹权限、录屏、辅助功能各自验证，拒绝一个不应自动索取Full Disk Access。[P21][P22][P23]

## 7. 真实集成的判定细节

### 飞书

官方长连接针对企业自建应用，多个client竞争消费而非广播；事件处理有3秒响应和超时重推规则。同步卡片callback同样有3秒回应要求，但应按其独立回调合同处理，不能复用事件重推假设。[P12][P13]

最小产品证据链是：真实测试用户输入→SDK收到真实event→inbox已提交→Task/Operation→具体审批→真实执行receipt→Outbox→真实message/card。API200、CardKit sequence小实验或WebSocket101握手是有用连通/协议资格，不能独自证明这条链。

callback token的30分钟/两次示例可在官方具体组件文档见到；它不是所有CardKit/消息PATCH的通用期限。要先产生callback，再测试它自己的token；业务approval TTL与消息生命周期分别记录。本轮不引入未经目标API核实的通用14天或30天逻辑。[P14]

平台没有公开测试故障开关时，可在自有adapter/受控receiver边界断开响应或注入错误，并明确哪段真实、哪段合成。不得为制造429向真实租户大量施压；真实消息只发送到明确获准的测试收件范围。

### Playwright

官方BrowserType说明chromium_sandbox缺省false；服务工作线程缺省allow，且context.route/page.route不能捕获被Service Worker截获的请求。[P15][P16]

因此实际用例必须启动受管Chromium、记录有效启动状态，测试SW与独立出口边界，而不是通过参数字典/默认lease字段。专用profile只是会话隔离，MCP/Browser名称本身也不是沙箱。跨进程profile互斥要按目录身份验证，不能只靠内存profile_name字典。

### MCP

按锁定SDK/协议版本发送真实消息并核验初始化；定义变化通过真实通知触发冻结。annotations不具有权限权威；list_changed/hash只能约束被观察到的定义，不能证明服务器实现代码和运行行为安全。[P24]

响应上限必须约束读入期间的内存/时间/帧；对已经完整分配到内存的bytes再截断不能证明有界。超时后不能把截断JSON或没有receipt当成功，也不能将取消通知/进程结束等同写副作用回滚。

### 云 Provider 与真实 Ollama 分开验收

真实云 Provider、官方SDK对loopback的合同测试、真实Ollama本地推理是三个独立结果。TC-INT-016按所宣称的Provider组合分别留下结果：选择云Provider时，应使用获准测试账户、合成任务、硬预算和真实产品适配器，记录实际模型/请求ID、用量、工具循环以及取消/超时后的结果；SDK本地故障服务器通过不能替代这次真实服务测试。选择Ollama时，另执行TC-INT-013/014验证模型资产、禁云配置与实际出口，不能拿一个云模型成功响应作为本地模式通过证据。

若本次Mac试点明确仅支持一种已验证组合，其他组合可暂不纳入发布声明；如果README或MVP声明同时支持云Provider与Ollama，两者都要各自通过。缺云凭据只阻塞相应真实云门禁；不阻塞已经具备环境的本地工程复现，也不能把未接通的本地产品入口归类为凭据缺失。

### 网络观测

“未见请求”必须写观察范围：OpenBot自身、Gateway、Worker、browser、native helper、Docker backend/VM和Ollama可能不在同一进程/网络域。仅mock httpx无法覆盖requests、DNS、原生扩展或子进程。

至少先用获准canary目的地证明监测链工作，再按模式验证允许/禁止路径。记录IPv4/IPv6、DNS、代理与未覆盖协议；没有足够平台边界时就把强离线保证标未验证，不能临时放行外网掩盖问题。LOCAL_MODEL限制模型路径不等于自动禁用飞书，其他通道仍按其policy明示；OFFLINE则不应启用互联网飞书/浏览能力。

## 8. 与核心状态/恢复用例衔接

平台用例使用真实OS/SDK/服务观测；核心用例检验权威状态，不重复发明另一套恢复语义。

| 平台用例 | 需联合核验的核心场景 |
|---|---|
| TC-MAC-014、TC-INT-005/009/012 | TC-CORE-015–018：claim/dispatch/外部成功/结果提交四类真实崩溃窗口 |
| TC-MAC-009/014/015、TC-INT-016 | TC-CORE-019–024：在途取消、去重、安全重试、旧epoch、UNKNOWN quarantine、新ID绕过与核对证据 |
| TC-MAC-021 | TC-CORE-028–031：限量测试卷满盘、外部成功后满盘、在线备份、缺失Artifact/secret_ref恢复 |
| TC-INT-013/014 | TC-CORE-036：模式、代理与首用出口；本文件提供真实Ollama与受管域证据 |
| TC-MAC-019/022 | TC-CORE-037/038：最小秘密注入、钥匙串失效、跨片段脱敏与扫描器不联网 |
| SDK/模型/网络相关 | TC-CORE-039/042：实际请求数、唯一重试责任、预算与取消/断流计费未知 |

故障注入必须可证明已达到目标持久化边界，再由外部控制器发故障；在同一个对象里直接调用recover方法，不构成新进程恢复证据。效果次数由独立持久计数器/真实服务receipt获得，不能在测试里手填0或1再断言正确。

## 9. 失败定位、修复与提交的工作方式

按单个可复现问题推进，保留失败证据后再修复；一个问题一个独立commit并push，以用户要求为准，不把多个无关问题一次提交。Git操作细节由配套Git闭环手册执行，本文件不做远端写入。

每个问题记录：

1. 受测commit/build、用例与真实环境、实际命令和退出码、最小输入。
2. 首次偏离发生在哪个边界：入口/认证→真实transport→应用用例→writer→Broker→SDK/OS→独立效果→receipt。
3. 失败前后的状态、真实PID/container/message ID和脱敏证据hash。
4. 原因与最小修复；不能删除失败测试、把断言放宽、关闭policy、清空DB/审批或降低隔离。
5. 修复后的同一负例、一个正常例和关联回归；commit SHA与push成功的远端SHA。
6. 本问题修复并push后再开始下一问题；若push失败保留commit与明确错误，不记远端已完成。

不要把某次原生用例不通过一律归因为“缺环境”。例如CLI parser拒绝task、installer只写JSON、MCP没有transport是实现/接线问题；没有Intel实机、专用飞书测试应用或发布证书才是相应外部条件缺失。

## 10. 证据与退出条件

每次真实用例至少记录：case_id、commit、build hash、执行UTC时间、OS build/arch、用户会话类型、SDK/engine/browser/model版本与资产digest、具体步骤/命令、预期与实际、真实退出/响应、关联IDs、原始日志hash、被观察范围、剩余限制和状态。

不要把凭据/完整环境、cookie、授权nonce、个人源码/聊天、原始截图或未脱敏网络载荷提交Git。用合成canary和最小元数据；原始敏感取证保留在受保护位置，提交去敏证据与摘要。

macOS MVP通过须同时满足：

- 当前公开的产品入口可真正创建/查询/批准/取消任务，跨进程访问权威Daemon。
- 该Mac与声明后端的P0用例通过，实际生命周期/容器/Keychain/Browser/MCP/飞书能力没有用stub替代。
- UNKNOWN、取消与旧epoch的核心门禁和真实副作用计数一致，恢复不盲重发。
- 真实飞书、模型或发布资产缺环境时分别列BLOCKED，不将未验能力写成可用；若它属于所声明MVP必备能力，则该版本MVP结论仍未通过。
- Intel、Windows、Linux、M4桌面及发行能力按实际范围单列；不因Mac本地通过改写三平台完成状态。
- 每项已修复问题有独立commit、push记录和相关回归；存在未解决P0时不宣称严格MVP验收完成。

## 11. 官方资料核验索引

本轮于2026-11-05访问。以下是平台合同/文档证据，不是OpenBot在目标环境的通过证据；版本与发布资产仍需锁定。未依赖第三方博客或未经复现的历史issue来设定统一性能指标。

| 编号 | 官方资料 | 已核实事实与使用边界 |
|---|---|---|
| P01 | [Apple universal macOS binary](https://developer.apple.com/documentation/apple-silicon/building-a-universal-macos-binary)、[Porting to Apple silicon](https://developer.apple.com/documentation/Apple-Silicon/porting-your-macos-apps-to-apple-silicon) | universal/原生/Rosetta区分；所有helper与本地库也需架构验证 |
| P02 | [Apple Service Management](https://developer.apple.com/documentation/servicemanagement) | LoginItem/LaunchAgent在用户会话中运行，不能用高权限系统服务替代用户agent |
| P03 | [Apple Creating Launch Daemons and Agents](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)、[SMAppService](https://developer.apple.com/documentation/servicemanagement/smappservice) | 用户agent与登录生命周期；旧归档命令不能替代目标OS的man和实际API状态 |
| P04 | [Apple DTS Testing a Notarised Product](https://developer.apple.com/forums/thread/130560) | 干净机器/快照、quarantine真实下载、按用户方式首开；可选离线测试票据；按制品类型选择诊断 |
| P05 | [Apple DTS Resolving Trusted Execution Problems](https://developer.apple.com/forums/thread/706442) | quarantine传播、Gatekeeper缓存、syspolicy_check及签名/加载问题区别 |
| P06 | [Apple notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)、[macOS14 release notes](https://developer.apple.com/documentation/macos-release-notes/macos-14-release-notes) | 公证要求与工具适用条件；syspolicy_check从14提供，不把工具成功当全部首开验证 |
| P07 | [Docker Mac permission requirements](https://docs.docker.com/desktop/setup/install/mac-permission-requirements/) | Docker engine/containers运行于Linux VM；宿主bind mount权限仍适用 |
| P08 | [Docker platform FAQ](https://docs.docker.com/faqs/platform/)、[Desktop settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/) | 宿主共享目录与容器bind mount范围；ECI/VM/后端能力需逐组合核验 |
| P09 | [Docker context inspect](https://docs.docker.com/reference/cli/docker/context/inspect/) | 可读取实际context endpoint；不应盲继承用户默认上下文 |
| P10 | [Docker container inspect](https://docs.docker.com/reference/cli/docker/container/inspect/) | 可按字段读取实际容器状态；不依赖客户端进程退出推断容器结果 |
| P11 | [Docker container cp](https://docs.docker.com/reference/cli/docker/container/cp/) | 可从已停止容器复制；权限/所有权有方向和参数差异，-L跟随symlink |
| P12 | [飞书长连接事件接收](https://open.feishu.cn/document/ukTMukTMukTM/uYDNxYjL2QTM24iN0EjN/event-subscription-configure-) | 企业自建应用、事件3秒响应/超时重投、client竞争消费 |
| P13 | [飞书接收callback](https://open.feishu.cn/document/event-subscription-guide/callback-subscription/receive-and-handle-callbacks)、[callback概述](https://open.feishu.cn/document/event-subscription-guide/callback-subscription/callback-overview) | 实际card.action.trigger与3秒响应；动态页面正文可见度有限，重推语义须按选定版本再次确认并保留原文/真实记录 |
| P14 | [飞书交互组件token示例](https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/card-json-v2-components/interactive-components/image-picker) | 具体callback token示例30分钟/两次；不是所有卡片API的通用期限 |
| P15 | [Playwright BrowserType](https://playwright.dev/python/docs/api/class-browsertype) | persistent profile、Chromium sandbox与env缺省等需显式配置 |
| P16 | [Playwright BrowserContext](https://playwright.dev/python/docs/api/class-browsercontext)、[Service Workers](https://playwright.dev/python/docs/service-workers)、[Network](https://playwright.dev/python/docs/network) | route与SW的覆盖边界、service_workers=block；路由不等于OS网络隔离 |
| P17 | [Ollama FAQ](https://docs.ollama.com/faq)、[官方envconfig源码](https://github.com/ollama/ollama/blob/main/envconfig/config.go) | 禁云参数及重启要求；loopback不证明本地推理，Mac App还有更新网络行为 |
| P18 | [Ollama macOS](https://docs.ollama.com/macos) | 当前OS/CPU/GPU要求与文件位置；须按锁定版本实测 |
| P19 | [Ollama list models API](https://docs.ollama.com/api/tags)、[generate API](https://docs.ollama.com/api/generate) | 实际模型清单与生成接口；示例模型名不作为项目默认模型 |
| P20 | [Apple Keychain自动锁定](https://support.apple.com/en-is/guide/keychain-access/kyca1242/mac)、[Keychain登录密码状态](https://support.apple.com/en-mide/guide/keychain-access/kyca2429/mac) | 登录/睡眠/密码状态影响解锁；本计划不重置个人钥匙串 |
| P21 | [Apple录屏权限](https://support.apple.com/guide/mac-help/control-access-screen-system-audio-recording-mchld6aa7d23/mac)、[Privacy & Security](https://support.apple.com/en-me/guide/mac-help/-mchl211c911f/mac) | 用户可逐功能授予/撤销，不是全权限先决条件 |
| P22 | [AXIsProcessTrustedWithOptions](https://developer.apple.com/documentation/applicationservices/1459186-axisprocesstrustedwithoptions)、[CGPreflightScreenCaptureAccess](https://developer.apple.com/documentation/coregraphics/cgpreflightscreencaptureaccess%28%29) | 权限以实际执行进程与API结果为准，不推断永久授权 |
| P23 | [Apple APFS格式](https://support.apple.com/en-gb/guide/disk-utility/dsku19ed921c/mac)、[控制共享权限](https://support.apple.com/en-gb/guide/mac-help/mchl2b29231a/mac) | 大小写敏感与普通APFS分别测试；文件夹/TCC权限具体化 |
| P24 | [MCP tools规范](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)、[当前官方规范源码](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/server/tools.mdx) | 工具提示不可信；固定协议/SDK组合，动态工具变化不得提升授权 |

### 本轮未实测与未确定项

没有用户Mac的实际OS build、硬件、已启动服务、签名证书、Keychain/TCC状态、Docker endpoint、浏览器/MCP资产、Ollama模型或飞书测试会话执行结果。本轮也没有验证任何新commit或push，未测物理断电、Intel实机和其他平台。动态官方文档或main源码的现状不能覆盖锁定发行版本；执行前要再核对对应版本。环境实际就绪后逐用例留下证据，不从本手册生成虚假的PASS。

