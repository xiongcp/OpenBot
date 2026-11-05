# 交付前增量审查：真实受限 MCP 容器切片

审查日期：2026-11-05。固定新 SHA：620311b4d141f3c964c90cc1a6db980dedecf365；比较基线：2993593a5bd010b85d76a6ca9e279fc4977718dc。main 未变。本轮为只读源码与已有证据审查，没有运行 pytest、Docker、MCP server 或外部服务，没有修改仓库。

## 结论

这次增量是真实工程进展：新增一个固定镜像、固定自有 server、固定合成文件的 Docker MCP 适配器，实现了真实 stdio 协议往返、内容摘要核对和独立容器回收。不能再把这一切片描述成“只有 MCP 模拟/规划”。

同时，它仍属于独立受限读工具 PoC。新增代码和测试没有完成 AgentRuntime → Broker → 受管 MCP → 权威状态/审计/恢复的生产装配，不改变“完整 Agent 与生产 MCP 隔离接线尚未完成”的结论。后续应复用此切片和既有容器抽象，补接线、持久生命周期与准入，不重新造一套同类容器实现。

## 1. 核实的新增能力

- ContainerReadTool 构造时要求 python@sha256 形式镜像和匹配的 server 文件摘要；拒绝 server 符号链接。读取时再次核对 server bytes，并对 demo.txt 使用 O_NOFOLLOW/O_NONBLOCK、普通文件检查、4096 字节上限与预期 SHA-256。[A01:21–29、109–126]
- 仅把核对过的文件副本和 server 副本只读挂进容器。create 使用 pull=never、network=none、read-only、cap-drop=ALL、no-new-privileges、65532 用户及内存/CPU/PID 限制；Docker CLI 环境只传固定 PATH 与临时 HOME。[A01:65–79、127–161]
- 真正调用 Docker create/start --attach --interactive，并在启动前 inspect 网络模式、只读 rootfs、非 privileged 与所有权 labels；有实际 stdin/stdout，而不是直接调用 Python server 函数。[A01:162–183]
- 固定协议 2025-03-26，执行 initialize → initialized notification → tools/list → tools/call；核对响应 ID、返回工具名、结果结构及实际文本 SHA-256。响应读取有帧大小和单次期限。[A01:81–99、186–226]
- 正常路径及可进入 finally 的异常路径独立检查容器：核对 labels → 必要时 stop → wait → inspect 未运行 → rm；没有把 attach 客户端退出直接当成容器回收。[A01:227–254]
- Windows 缺少 POSIX 文件保护标志时显式 fail closed；新单测覆盖分别缺少 O_NOFOLLOW/O_NONBLOCK。它证明拒绝行为，不证明 Windows 容器执行资格。[A01:109–111；A04]

本代理对 GitHub 返回的 read_server.py UTF-8 内容独立计算 SHA-256，结果为 8943e4c6810d6140b506d8755f6f74831bad378727165c784f0b60f8c41bd7e0，与 mcp-demo.json 一致。这是静态文件一致性核对，不是运行或镜像来源重新认证。[A02、A05]

## 2. 已有证据的实际范围

仓库证据文档记录 Darwin arm64：最初只读 fixture 单元回归 7 passed、原生容器 1 passed；文件保护修复后的两组单测合计 9 passed。0.71s 是一个测试样本耗时，不是性能指标。以上均为仓库作者记录，本代理未复跑，也未取得独立原生执行日志。[A06:3、28–43]

原生测试必须显式设置 OPENBOT_NATIVE_MCP=1，否则 skip。它调用真实 ContainerReadTool.read，使用一个合成 demo.txt，断言返回文本、摘要与 cleanup_verified；没有在测试外部再做引擎级残留核对，也没有强杀、取消或后端失联注入。[A03:10–31]

fixture 单元测试在宿主 subprocess 中运行 read_server.py，覆盖固定文件、路径拒绝、符号链接、超限、初始化前调用及构造时 pin 拒绝；这些是协议/文件保护测试，不能计作额外真实容器样本。[A07:14–24、45–84]

主代理读取的最新 CI run 41981655070：Mac 350 passed/4 skipped；Linux 348 passed/4 skipped/1 deselected；Windows 41 contracts passed。该统计来自主代理已有日志核验，本代理未再次读取；不能用总 passed 数替代独立原生 MCP 门禁。

证据文档自己已经明确：不覆盖任意第三方 MCP server、全部 Docker 版本、其他原生平台或完整 Agent 集成。应保留这一准确边界。[A06:33–35]

## 3. 三项具体残余与最小后续

### 3.1 生产装配、可信准入和 lock 消费仍未闭合

compare 显示这 3 个提交共改 11 文件。MCP 生产新增是 container_read.py/fixture；另一个生产改动为 local_api/server.py 的审批预览摘要格式修正，没有 AgentRuntime/daemon composition 的装配增量。现有 McpIsolatedExecutor 仍只生成 McpDispatchPlan，未调用 ContainerReadTool。[A08、A09]

ContainerReadTool 由调用方直接传 image/server/server_sha256/ownership/workspace/expected_sha256；没有在该模块读取 mcp-demo.json。原生测试的 server_sha256 是从当前文件即时计算，不是从受信 lock 读入。因此“当前文件恰好匹配 lock”已经核对成立，但不能据此声称 lock 已成为生产准入权威。[A01:21、101–108；A03:16–27；A05]

最小后续：由受信 composition 从已核验 lock/manifest 构造实例；把 profile/Operation/Attempt/epoch、工作区授权、输入摘要及预算从 Broker 权威上下文绑定；通过真实用户入口完成一次模型提案→受管执行→持久回执。增加“lock 中 server hash 与文件不一致”“镜像/工具元数据改变”拒绝测试。仅固定 demo read 的资格，不开放任意第三方 server。

### 3.2 回收依赖当前进程的 finally，尚无 SIGKILL 后持久重收证明

container ID 是局部变量，create 成功并取得合法 ID 后才进入 try/finally；本切片未登记持久 supervisor/Attempt 回收账本。SIGKILL 不执行 finally；create 在引擎成功但客户端超时/回执丢失时，可能没有拿到 ID。finally 内 attach 清理若再次异常，也可能使后面的引擎 stop/wait/rm 未执行。[A01:162–167、227–248]

这不是本轮已经复现的泄漏事故，而是代码中可见的未闭合恢复路径。正常读测试的 cleanup_verified=True 只在本次 rm 成功后返回，不能当作强杀恢复证明。

最小后续：复用统一容器管理与持久所有权账本，创建前登记意图及可发现身份、取得 ID 后持久绑定；启动恢复时按受信 profile/Attempt/epoch 清点并回收。attach 清理和引擎清理隔离异常，未能证明旧执行域失效时保留隔离状态。补 create 回执丢失、SIGKILL、后端失联恢复和独立引擎残留核对；禁止按宽泛容器名删除其他资源。

### 3.3 当前期限和测试范围还不是任务级取消/完整后端资格

read 是同步接口，未接任务取消信号或 Operation 总期限；当前是每次 Docker 命令 10 秒、每个回复帧 10 秒及局部进程回收期限。它们不能单独证明用户取消及时阻止后续 tools/call，也不能证明总任务预算受控。[A01:69–99、186–216、227–248]

实际 inspect 只核对网络、只读 rootfs、privileged 和 labels；资源限制、用户、capabilities、no-new-privileges、实际 mount/镜像等虽然已经明确传入 create，原生测试尚未逐项独立验证。socket 选择仅支持两个固定 Mac 路径，应记录实际选中的 backend/engine 版本和系统，而不是宣传所有 Docker 后端已资格。[A01:31–55、137–176；A03]

最小后续：接统一总期限/取消与 supervisor 回收，补取消发生于各协议阶段、超时/断帧、后端退出的反例；扩展真实 inspect/独立探针对所声明边界取证。保留该自有固定工具限制，动态 tools/list_changed、未知 server 消息和通用 MCP 生命周期另走资格，不借用本测试当作通过。

## 4. 对现有发布计划的影响

- 更新 V1-017/current_evidence 为“已有受限 MCP 真实容器读工具与仓库记录的单次原生通过；生产接线和故障资格未完成”。不将整个任务标 DONE。
- V1-010 的 Agent 主循环、V1-013/014 的可信恢复与真实强杀、V1-029 的进程生命周期、V1-037 的真实平台资格仍保留。
- V1-030/035 保留锁与资格的可信消费、资产/镜像来源和发行清单要求。
- 审批预览 sha256: 前缀修复属于另一独立改善；不与 MCP 容器资格合并计数。其文档记录相关回归 28 passed，本代理只读该记录。[A10]

## 固定 SHA 证据链接

A01 适配器（全部行号以上文为准）：
https://github.com/xiongcp/OpenBot/blob/620311b4d141f3c964c90cc1a6db980dedecf365/services/core/src/openbot/tools/mcp/container_read.py

A02 自有 fixture：
https://github.com/xiongcp/OpenBot/blob/620311b4d141f3c964c90cc1a6db980dedecf365/services/mcp_fixture/read_server.py

A03 原生测试：
https://github.com/xiongcp/OpenBot/blob/620311b4d141f3c964c90cc1a6db980dedecf365/tests/components/native_poc/test_mcp_container.py

A04 文件保护回归：
https://github.com/xiongcp/OpenBot/blob/620311b4d141f3c964c90cc1a6db980dedecf365/tests/unit/test_mcp_file_guards.py

A05 lock：
https://github.com/xiongcp/OpenBot/blob/620311b4d141f3c964c90cc1a6db980dedecf365/components/locks/mcp-demo.json

A06 已有运行记录：
https://github.com/xiongcp/OpenBot/blob/620311b4d141f3c964c90cc1a6db980dedecf365/docs/evidence/mcp-demo-container.md

A07 fixture 单元测试：
https://github.com/xiongcp/OpenBot/blob/620311b4d141f3c964c90cc1a6db980dedecf365/tests/unit/test_mcp_read_fixture.py

A08 增量比较：
https://github.com/xiongcp/OpenBot/compare/2993593a5bd010b85d76a6ca9e279fc4977718dc...620311b4d141f3c964c90cc1a6db980dedecf365

A09 现有 MCP 派发计划：
https://github.com/xiongcp/OpenBot/blob/620311b4d141f3c964c90cc1a6db980dedecf365/services/core/src/openbot/tools/mcp/executor.py

A10 预览摘要修复记录：
https://github.com/xiongcp/OpenBot/blob/620311b4d141f3c964c90cc1a6db980dedecf365/docs/evidence/approval-preview-hash.md

最新 CI： https://github.com/xiongcp/OpenBot/actions/runs/41981655070
