# 仓库问题优先修复队列

## 使用规则

本队列基于main快照a223d36a659b7ecf32fca2b4890fc187d3e96e48和该SHA的既有CI日志。MVP-001/002有CI观察证据；其他项主要是源码观察与覆盖缺口，须在用户Mac上做最小复现并追踪实际装配路径。全部初始OPEN，未执行本地修复或push。

修复顺序建议为基础CI与收集、验收真实性、产品入口和运行服务、真实能力、最终门禁与文档。可以先针对同一问题编写会失败的回归用例，但不要把多个独立根因合成一个“大修复commit”。修完一项、通过对应本地回归后，提交并确认推送，再开始下一项。

这些16项是待分诊的问题线索，不预设最终恰好16个修复commit。若同一线索包含多个独立根因，拆成明确子问题并逐项提交；若另一条已被同一根因修复，关联证据即可，不制造重复提交。

同一候选尚有其他已知CI基线错误时，前一修复可处于PUSH_CONFIRMED / CI_BLOCKED，不能标FIXED。允许继续修已独立定位的其他阻塞；最终在包含这些修复的候选SHA上统一复验。详见逐问题提交章节。

## MVP-001：Mac和Windows的CI解释器准备失败

证据等级：CI_OBSERVED。建议严重度S1、优先级P0。contracts运行41949551726中，Mac arm64与Windows x64在setup-python步骤无法获取3.12.12；后续测试步骤全部跳过。这不是这两个平台的应用测试失败，也不是通过。

复现步骤：读取相同job日志；在拟使用的runner/架构上查询可用Python构建；用相同锁与解释器请求重新准备环境，记录下载来源与退出状态。

修复方向：先验证保留3.12.12并改用uv managed Python是否可行；若固定uv版本没有该构建，单独验证新的锁定工具版本。确需更换Python补丁版本时，在>=3.12,<3.13内选定各目标架构实际可获取的版本，统一.python-version、CI及环境证据。禁止仅删掉版本约束或升级3.13来绕过。

回归：新的Mac/Windows CI必须实际打印Python版本与架构、完成uv sync --locked并进入测试收集。报告分开记录“环境启动成功”和“应用测试通过”。建议commit主题：fix(ci): resolve locked Python bootstrap on target platforms。

## MVP-002：CI测试收集出现No module named tests

证据等级：CI_OBSERVED。建议S1/P0。Ubuntu同SHA的pytest退出码2，报告24个收集错误及2个SDK模块skip，失败集中于tests.*跨模块导入。

复现步骤：在干净checkout从仓库根分别执行uv run --no-sync pytest --collect-only -q和uv run --no-sync python -m pytest --collect-only -q，保留两份日志、收集数量和模块来源；核对tests/__init__.py和sys.path。第二种入口成功也不能掩盖当前CI原入口失败。

修复方向：优先统一CI与本地验证的python -m pytest入口，并确认仓库根及源码路径的明确设置。[T03] 如仍失败，检查editable安装、包名冲突和导入模式。共享测试夹具可后续迁到tests/support或conftest，但不为此进行无关重构。不要跳过tests/integration或吞掉ImportError。

回归：相同CI入口收集数达到冻结清单，0 collection error；实际运行关键storage、CLI、API测试。建议commit主题：fix(test): make repository test imports consistent in CI。

## MVP-003：工作流存放在不受支持的子目录

证据等级：SOURCE_OBSERVED。建议S1/P0。当前nightly/soak.yml、pull_request/gate.yml、release/supply_chain.yml位于.github/workflows子目录。GitHub官方说明不支持workflows子目录。[T01]

复现步骤：核对精确目录和触发事件，在GitHub Actions中查找对应工作流及最近运行；不能只用文件存在作为执行证据。

修复方向：将各工作流移动到.github/workflows根目录，采用不冲突文件名；同步引用这些路径的测试和文档，保持原触发目的。定时任务需要满足默认分支与调度条件，修复分支先用允许的手动或push触发验证，不自动合并main只为触发schedule。

回归：对新SHA观察到工作流被识别、触发并运行实际步骤；检查没有把旧文件和新文件同时变成重复执行路径。建议commit主题：fix(ci): register acceptance workflows at supported paths。

## MVP-004：macOS专项工作流没有准备锁定环境

证据等级：SOURCE_OBSERVED。建议S1/P0。platform-macos.yml只有checkout与python3 -m pytest，没有明确设置Python、安装锁定依赖或报告版本；文件中的job名称不能证明原生能力。

复现步骤：在干净runner上执行现有workflow，检查pytest与所需包从何处获得。缓存/预装环境的偶然成功不作为干净安装证据。

修复方向：加入锁定解释器与依赖准备；把确定性合同、实际SDK、需要Docker或交互用户会话的原生测试分清。托管Mac runner若无法提供产品所需后端，标具体门禁BLOCKED，安排用户Mac或专用runner，不伪造原生通过。

回归：日志记录OS/架构/锁hash/依赖组；失去必要依赖应明确失败或阻塞；所选必需用例不可全部skip。建议commit主题：fix(ci): bootstrap macOS acceptance dependencies explicitly。

## MVP-005：macOS 14托管runner标签已经退役

证据等级：SOURCE_OBSERVED及官方公告。建议S1/P0。仓库多处使用macos-14；GitHub公布所有macOS14镜像于2026年11月2日退出GitHub Actions。[T02] 本次CI日志的直接错误仍是Python构建获取失败，不能把两种根因混为同一个。

修复方向：选择当前支持且明确架构的runner标签，例如核验后的macos-15或macos-26，记录实际uname和系统版本。托管runner升级不等于改变产品最低支持的macOS版本；如果仍承诺macOS14用户兼容，应在相应原生设备保留兼容验收。

回归：新标签被调度，架构与期望一致，完整依赖准备和对应测试实际执行。建议commit主题：fix(ci): migrate retired macOS runner labels。

## MVP-006：真实CLI没有接通task和approval命令

证据等级：SOURCE_OBSERVED。建议S1/P0。services/core/src/openbot/cli.py的main只接受version和health，内部run_cli_command支持更多动作但需要注入CliApiSession。文档提供的task create等真实命令与console入口不一致。

复现步骤：在干净安装中使用子进程运行openbot task --help，再在独立测试profile验证task创建。保留退出码、stdout/stderr和daemon是否收到真实请求；不要直接调用run_cli_command(session=fake)。

修复方向：共用命令解析器；装配实际loopback/IPC transport、profile发现和受保护认证会话；实现不可用daemon的清晰错误。不得为了让命令工作绕过Local API、直接写SQLite或将token塞进argv。

回归：installed console脚本在新进程完成create/show/approval/cancel/reconcile；错误token、跨profile、daemon停止、响应丢失均有负向结果。health必须检查实际daemon字段，不能只看退出码0。建议commit主题：fix(cli): connect authenticated product command entrypoints。

## MVP-007：用户服务安装器只生成JSON描述

证据等级：SOURCE_OBSERVED。建议S1/P0。application/daemon_installer.py当前仅写openbot-user-daemon.json，未在该实现中执行launchd注册或提供真实服务生命周期。文件存在不足以证明用户服务安装。

复现步骤：安装测试profile后，在本机用户会话查询对应服务，观察进程PID、父进程、实际监听、日志、停止和重启。登记的label应从真实配置读取，不硬编码猜测。

修复方向：补真实用户级服务与受控daemon入口的装配，或者明确将当前函数作为manifest生成器，并由独立已实现的installer负责真实注册。不得使用root系统服务替代当前用户会话；工作区与数据不能随卸载删除。

回归：登录会话内start/status/stop/restart、第二实例、关闭终端、注销/重新登录按产品声明验收；崩溃重启不放大授权。M4的Tauri窗口测试仅在UI实现后执行。建议commit主题：fix(platform): wire macOS user daemon lifecycle。

## MVP-008：macOS门禁把模拟证据标为原生通过

证据等级：SOURCE_OBSERVED。建议S1/P0。macos_gate.py中_KeychainStub使用内存字典；文件测试只读写a.txt；daemon检查manifest存在；Browser使用手填隔离声明和内存lease。返回字段却包含keychain_compartment_verified和filesystem_and_symlink_verified。

复现步骤：使真实Keychain后端不可用、不给启动浏览器能力、使用不支持的OS环境运行现有harness，观察其是否仍给出对应verified。这里只是在隔离测试里替换能力，不破坏用户真实Keychain或系统设置。

修复方向：保留有价值的模拟合同测试并标SYNTHETIC；将真实OS门禁改为实际调用、独立观测和环境条件。Keychain应创建专用canary、读回/轮换/撤销并清理；文件门禁应覆盖真实symlink/大小写/Unicode路径。缺能力输出BLOCKED，不能仅把失败吞成False后继续标整体PASS。

回归：真实能力缺失时该资格不能通过；真实canary和文件反例成功才产出证据记录。建议commit主题：fix(qa): separate synthetic macOS checks from native qualification。

## MVP-009：崩溃与浸泡结果含未执行的通过标签

证据等级：SOURCE_OBSERVED。建议S1/P0。chaos_soak.py直接追加sqlite_backup_and_disk_full_guard；dangerous_blind_retry_count固定0。vertical_slice的故障路径未执行真实SIGKILL/进程重启，效果数由变量赋值；部分核对证据也是harness自行生成。

复现步骤：用独立控制器记录产品PID及启动代次、外部效果账本和数据库重开事件；确认现有测试是否真的制造各标称故障。将效果观察器置于故障进程外，禁止由待测报告自己证明效果次数。

修复方向：加入确定性故障屏障，在已知事务提交点由控制器终止目标进程并等待退出；以同一持久profile重启产品，读取真实WAL/状态与效果账本。满盘使用受限临时卷或配额，不填满用户系统盘。睡眠与断网分别增加真实Mac场景，时钟模型测试继续保留。

回归：覆盖claim前、claim后dispatch前、dispatch提交后发包前、效果后回执前、持久化成功后反馈前；UNKNOWN不得自动重发。任何统计字段来自记录事件而不是固定常量。建议commit主题：fix(qa): measure real crash recovery and external effects。

## MVP-010：Browser验收未证明真实启动和跨进程profile互斥

证据等级：SOURCE_OBSERVED。建议S1/P0。抽查的BrowserProfileSessionManager仅用内存字典维护lease并接受隔离布尔声明；该文件没有启动Playwright。它可作为合同层，但不能单独证明浏览器原生能力。

复现步骤：从两个独立进程竞争同一测试profile；启动实际锁定Chromium并导航到受控页面；观察真实PID、profile文件、出口和回收。追踪其他启动适配器是否实际装配，避免仅据单文件断言整个项目缺实现。

修复方向：把已实现的真实启动适配器接入产品；缺失时实现明确的浏览器worker与OS级profile归属。Chromium自身沙箱和外层文件/网络边界分别验收；Service Worker、iframe、重定向、下载与弹窗一起验证。

回归：跨进程争用只有一个成功，未授权出口无实际连接；进程崩溃后不靠删除锁文件强行接管旧活动实例。禁止no-sandbox降级。建议commit主题：fix(browser): qualify real workers and cross-process profile ownership。

## MVP-011：MCP验收没有实际stdio握手和流式输出上限

证据等级：SOURCE_OBSERVED。建议S1/P0。抽查的negotiate_initialize只比较传入版本字符串；bound_response_bytes接收完整bytes后截断。这证明部分合同逻辑，不证明真实进程、JSON-RPC握手和读入期间的内存上限。

复现步骤：启动固定包的测试MCP server，记录真实initialize/initialized、tools/list与tools/call；注入不匹配版本、半帧、无限流、stderr洪泛、超时和成功后断连。效果账本独立记录tool是否真的执行。

修复方向：接通或实现受限stdio进程与协议适配器，按流读入预算与帧边界拒绝过量输出，清理归属与deadline可验证。工具定义hash变化触发重新授权，server不能通过自己声称readOnly获得权限。

回归：握手失败不能返回协商成功；内存上限在读入期间生效；未知效果不自动新建ID重试。建议commit主题：fix(mcp): exercise bounded stdio transport and real protocol handshake。

## MVP-012：组合MVP用模拟Ollama代表云与本地两Provider

证据等级：SOURCE_OBSERVED。建议S1/P0。mvp_regression.py给_OfflineOllamaTransport固定响应，手填runner_offline_egress_verified=True，并把这一段计为cloud_and_local_providers；该段没有调用真实云Provider。

修复方向：将报告拆成模拟Provider合同、实际SDK-loopback、真实云服务、真实本地runner四个资格。真实云使用受限测试账户与预算；真实Ollama记录模型权重、runner配置和整个进程树出口。缺少其中一项不能用另一项的PASS代替。

回归：不给云凭据时真实云资格BLOCKED；停止本地runner时本地资格失败且无云回退；真实工具计划仍由Broker执行。任务完成率、token和成本来自实际响应与记录。建议commit主题：fix(qa): qualify cloud and local providers independently。

## MVP-013：Mac试点发布判定没有纳入全部必需证据

证据等级：SOURCE_OBSERVED。建议S1/P0。mvp_release_gate.py对供应链缺失加入blocking_reasons，但pilot_ok仅依赖security_critical_failures和darwin_arm64_verified。手填布尔值也不足以证明当前候选实际通过。

复现步骤：传入Mac已验证但供应链记录缺失/资产hash不符的报告，观察pilot标志；再使用不同SHA的过期通过记录，验证候选是否被错误接受。

修复方向：冻结Mac内测与三平台发行各自必需门禁；由受信验收记录汇总，校验source_sha、tree/lock/资产hash、平台与evidence_kind，不能只判断artifact数大于0。Mac范围不用Windows/Linux作为前提，但本范围供应链、真实执行和关键安全门禁必须满足。

回归：逐项删除、篡改或跨SHA替换必需证据都阻止相应发布资格；全部当前证据成立才通过。建议commit主题：fix(release): bind macOS readiness to required candidate evidence。

## MVP-014：验证记录可能覆盖历史或残留旧通过结果

证据等级：SOURCE_OBSERVED。建议S1/P0。verify.py把日志写到固定路径，子命令60秒超时后会抛异常而未必生成本轮完整失败报告；报告也没有绑定source SHA和运行ID。

修复方向：为每轮生成独立run_id与输出目录，记录每条命令的起止时间、退出码、timeout、日志hash与未运行项目；超时和异常也生成本轮终态报告并非零退出。启动时创建IN_PROGRESS记录，完成后原子替换为COMPLETE；禁止消费者把缺失新报告解释为上轮PASS。不要简单取消所有超时，分别设置短回归与长时浸泡预算。

回归：注入子命令失败、超时、写报告失败与控制器中断，均不得留下可误读的本轮PASS；历史证据不被覆盖。建议commit主题：fix(qa): make verification evidence run-scoped and fail closed。

## MVP-015：文档、任务状态与真实资格存在冲突

证据等级：SOURCE_OBSERVED。建议S2/P1；若影响发布声明则提升S1。README新进度、getting-started、external-environments和部分AGENTS段落反映了不同阶段，部分仍写M1未完成或全部TODO；本次任务字段也并非全部DONE。

修复方向：以实际完成的用例与证据为依据生成能力矩阵，分开implementation_status与verification_status；明确旧证据的日期、适用SHA和历史性质。不要批量把96任务改DONE或用更新文案替代产品接线。

回归：文档示例从真实console可执行；能力矩阵每项指向当前证据；未测/缺环境与M4范围清晰。建议commit主题：docs(qa): reconcile implementation claims with verified capabilities。

## MVP-016：Docker原生PoC绑定另一台开发机器

证据等级：SOURCE_OBSERVED。建议S1/P0。tests/components/native_poc/docker_poc.py硬编码Docker二进制绝对路径和个人用户socket，并对临时输出目录设置0o777。该文件自述为合成PoC，不是生产executor；因此不能据此判断生产隔离一定存在同样问题，也不能在其他Mac上直接把运行失败当产品失败。

复现步骤：检查当前Mac真实Docker CLI位置、当前用户受控engine/socket及固定镜像是否存在；用受限测试配置记录能力检测结果，确认脚本没有连到意外远端context。不要先改成系统root socket或提权执行来通过。

修复方向：从显式测试配置选择并验证CLI与engine，避免隐式继承未知DOCKER_HOST/context。输出使用预先设计的最小写权限，优先容器内部产物在停止后受限导出并验证，再写入私有宿主目录；不复制宽权限作为通用修复。记录每个已创建容器的ID和本轮标签，清理只作用于这些资源。

回归：两种合法本机CLI/socket布局均可定位；不存在、权限不足或指向非允许engine时明确BLOCKED/CAPABILITY_UNAVAILABLE；运行后的真实限制与stop/wait/export/remove检查通过，所有本轮资源被核对。建议commit主题：fix(test): make native Docker qualification portable and scoped。

来源：[docker_poc.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/tests/components/native_poc/docker_poc.py)。

## 修复后还必须执行的完整链路

上述问题修复不能代替后续用例：真实飞书发起任务、配对、审批与反馈；真实浏览器和MCP效果核对；真实Mac休眠、重连、用户会话和容器回收；旧数据恢复；发布资产首次离线使用；模型任务质量和预算。每个失败形成新的问题ID并沿用同样逐项commit/push流程。

## 源码索引

全部路径基于冻结SHA。主入口：[cli.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/cli.py)。门禁：[macos_gate.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/macos_gate.py)、[chaos_soak.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/chaos_soak.py)、[vertical_slice.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/vertical_slice.py)、[mvp_regression.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/mvp_regression.py)、[mvp_release_gate.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/mvp_release_gate.py)。

平台与适配器：[daemon_installer.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/application/daemon_installer.py)、[Browser session.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/tools/executors/browser/session.py)、[MCP client.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/services/core/src/openbot/tools/mcp/client.py)。验证与CI：[verify.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/scripts/verify.py)、[pr.yml](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/.github/workflows/pr.yml)、[platform-macos.yml](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/.github/workflows/platform-macos.yml)。
