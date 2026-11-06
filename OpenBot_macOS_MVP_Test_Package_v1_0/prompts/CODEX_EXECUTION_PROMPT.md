# 可直接交给本机 Codex / Claude Code 的执行提示词

> 使用方式：在用户 Mac 的 OpenBot 实际工作副本中，将以下正文作为执行任务。配合`docs/07_fix_commit_workflow.md`、`docs/08_release_gate.md`、实际用例矩阵和 `templates/workflow/` 使用。此提示词没有声称任何测试、修复、提交或推送已执行。

---

你要验收并修复已经存在的 OpenBot 实现。不要重建项目、用新脚手架替代当前代码，或仅输出建议。工作目标是在实际 Mac 环境验证严格 MVP，发现真实问题后逐个完成最小修复和回归，并且**每修复一个独立问题就 commit、push 一次**。

## 一、已知项目与授权

项目已经确认是 `https://github.com/xiongcp/OpenBot`。远端只读审查参考过 `main` 的 `a223d36a659b7ecf32fca2b4890fc187d3e96e48`，但你必须从当前本机 checkout 重新记录实际基线，不能把这个参考 SHA 当作当前 HEAD 或已经验证的候选。

用户已授权本轮逐问题 commit 和 push。仓库 AGENTS.md 中“未经授权不推送”的前提已经满足，**不要每完成一个修复再问用户是否允许提交/推送**。继续遵守其他项目规则，不修改 AGENTS.md 制造永久授权。此次授权不等于自动 merge、改保护规则、向 main 发布、打 release tag 或部署。

先检查当前 cwd、真实仓库、分支、上游、HEAD/tree、dirty 状态、已有暂存内容、未推送提交，以及真实 remote 的 fetch URL 和 **push URL**。优先核对 `origin`，但名称本身不是目的地证明。默认使用明确的现有开发分支，或从已确认基线建立 `mvp/macos-hardening` 修复分支；不能自动向 main 写入。仅在本机目录无法定位、多个工作副本/目的地互相冲突、push URL 指向其他仓库、已有分支归属不明等具体问题无法解析时，向用户询问最少缺失信息。已知项目地址不要再问一次。

原工作区有用户改动时，保留其文件、index、未跟踪内容和已有提交；优先新建自己拥有的独立 worktree。不要自动 stash、reset、clean 或搬运用户未提交内容。不能把用户既存未推送提交夹带到本轮发布范围。任何自己的临时工作树和日志目录，都先明确归属。

## 二、先建立可复核的执行基线

在当前代码读取实际 AGENTS.md、README、pyproject.toml、锁文件、scripts、CLI parser、测试与 CI 配置，产出命令清单。每条记录 argv、cwd、代码来源、环境键名、依赖组、超时、是否需要真实服务、是否有外部副作用。不要用 eval 执行文档文本，也不要臆造 OpenBot 命令。

参考版本存在以下真实入口，先在当前 checkout 复核：

```bash
uv sync --locked
.venv/bin/python scripts/verify.py
uv run --no-sync pytest --collect-only -q
uv run --no-sync pytest
```

README 使用前两条，当前参考 CI 使用最后一条 pytest console 入口。`python -m pytest` 的绿灯不能掩盖 `uv run --no-sync pytest` 的 collection/import 失败。

参考 `scripts/verify.py` 会设置 core 与 feishu_gateway 的 PYTHONPATH、移除 `OPENBOT_NATIVE_TESTS`、默认 phase M0 且仅接受 M0/M1，并为每条命令设置 60 秒超时。它把原始日志写到 `evidence/implementation`。不要因此宣称原生 Mac、真实服务或 M3 已通过；不要把这些原始日志自动加入 Git。默认依赖组为 `dev-contracts`，额外组有 `provider-openai`；需要时按当前已锁定组安装，例如参考版本的 `uv sync --locked --group provider-openai`。缺依赖导致 skip 不等于测试通过。

以下是参考 SHA 的只读问题线索，需在本机当前版本复核，不能直接标记为本轮已复现或已修复：

- `pr.yml` 的真实命令为 `uv run --no-sync pytest`；参考 run `41949551726` 的 Linux job 有 24 个 `No module named tests` collection errors，Mac/Windows 在 setup-python 阶段因所选 Python 3.12.12/架构构建不可用而失败，另有 SDK skip。不要用“环境问题”四个字忽略可修复的导入和配置根因。
- 参考 matrix 使用 ubuntu-24.04 / macos-14 / windows-2022。重新核对受支持的 runner image、Python 构建与实际架构；不要沿用不可运行的组合。
- `platform-macos.yml` 只在 PR / workflow_dispatch 触发，参考配置没有依赖安装；push 到修复分支不自动证明它运行过。
- 部分 soak/gate/supply-chain workflow 位于 `.github/workflows/` 子目录；GitHub 不支持在其子目录发现 workflow。YAML 文件存在不代表 CI 已执行。

这些是多个可能独立根因，要分别登记、验证、修复、提交和推送。恢复测试入口与 CI 可执行性优先于宣称产品已通过完整验收。

## 三、严格限定验收范围与证据

默认本轮交付声明是 **完整 macOS MVP**：按已经确认的 v1.2 / M3 功能基线在 macOS 上验收，保留全部原必需功能与安全边界，只限定本轮平台证据范围。真实云 Provider 与真实 Ollama 是两条独立必需链路，不能二选一。只支持一种模型服务时，只能如实描述为收窄的 Mac 试点或局部通过，完整 macOS MVP 仍未完成；不得执行代理自行降低要求。当前代码未实现的原必需能力是实现缺口，不能作为排除理由。实际 macOS 版本、芯片架构、原生/Rosetta、安装方式、模型和服务版本必须写明。macOS MVP 通过不能改写为原 M3 三平台完成。Windows / Linux 没有真实证据就保持 NOT_RUN。Intel 原生、Apple Silicon 原生和 Rosetta 分别记录；Docker Desktop 的 Linux VM 不证明 Darwin、TCC、launchd 或钥匙串行为。

Tauri 界面、TCC/GUI、签名、公证、自动升级等，按当前版本实际声明和原阶段范围判断。若只交付不含这些功能的 CLI/daemon MVP，可明确为范围外；不能因环境缺失或测试失败临时改为范围外。若交付声称已包含这些能力，就必须执行相应真实门禁。

采用 `docs/08_release_gate.md` 的 S0—S3 缺陷严重度和 P0—P2 测试优先级，二者不是同一字段。所有当前范围必需 P0/P1 用例需要有真实 PASS 证据；S0/S1 不能留存放行。S2/S3 也不能绕过必需需求或安全门禁。

现有测试和参考设计都要复用，但测试必须穿过实际生产 application/adapter/storage 路径。参考 DDL 或 mock 的绿灯不能替代生产路径、原生 Mac、真实 Provider、真实飞书、真实隔离或安装证据。所有尚未执行的用例从 NOT_RUN 开始，不填示例成功次数、假 SHA、假 CI URL 或不存在的命令。

特别检查：

1. CLAIMED / DISPATCHING 的持久化、取消、epoch/resource 复核，审批不可篡改、CONSUMED 不退回 APPROVED，Attempt dispatch_id 与 Operation provider idempotency key 的边界。
2. 独立接收器记录真实外部效果；分别计算 socket send、server received 和 logical effect。幂等请求可重传，但逻辑效果不能重复。不能一句“exactly once”省略证据。
3. DISPATCHING 已落盘但发包前被杀，即使夹具观测到效果 0，生产状态也应保持 UNKNOWN，直到可信回执/reconcile 证明如何处置。不能用测试全知视角直接盲重试。换 Task/Operation ID 不能绕过持久 quarantine。
4. 取消终态必须满足其辖下不存在未解决 DISPATCHING / UNKNOWN；竞态用屏障/事件固定前后顺序，覆盖两种线性化结果，不靠 sleep 随机碰撞。
5. 宿主机执行不能作为缺沙箱时的隐式后备。Docker CLI 退出不等于容器消失，回收需 stop/wait → 导出及校验 → remove。daemon 和 worker 的生存期不能绑桌面 UI。
6. localhost 的模型服务不证明本地离线；用实际选定模型、禁云配置和真实 egress 观测证明。Provider SDK 内建重试和工具执行 helper 不得绕过控制面。
7. 原始证据的来源要核对。现有 `chaos_soak` 标签、硬编码 0、固定成功 mock、手填 egress attestation、布尔型 release evaluate 输入，不自动算真实满盘/断网/睡眠/云模型/供应链/发布成功。发现逻辑缺口先受控复现，再按单问题闭环修复。

## 四、每个问题完整执行一次闭环

只指定一个集成代理操作 index、commit 和 push；其他代理可以并行做独立审查、隔离复现和只读验证，不同时争用同一工作树。

每次选一个独立根因，执行：

1. 建立 issue_id、S级、关联用例/P级、base SHA、期望/实际、最小复现和证据。先运行基线，区分产品错误、入口/CI错误、真实环境缺口和测试本身错误。
2. 新增或扩展有意义的失败回归；已有稳定用例可直接纳入，不复制无意义测试。证明修复前失败点与根因一致。配置问题使用真实配置识别/实际 job 证据，不写仅断言某字符串存在的镜像测试。
3. 做最小修复，运行目标回归、具体受影响回归以及项目必需检查。安全/状态修改必须含对应 P0 反例。保留以前修复的相关回归，禁止以删除断言、加 skip、扩权、无条件成功或伪造结果过关。
4. 若完整基线已有另一独立失败，明确保存其证据和关联 issue；本问题的针对验证与可运行相关检查必须通过。不得把自己新引入的失败称为基线问题。CI 才能验证的配置结论等到实际 CI 后才能闭环。
5. 明确审查并仅暂存该问题具体路径，不用 `git add -A`、整目录或不受控 glob。检查暂存内容没有用户改动、秘密、PII、真实 DB/profile、原始日志或无关生成物。
6. 按项目约定创建一个原子修复 commit，使用现有真实作者和签名配置。不要为工具额外加 attribution。记录实际 parent、tree 和文件范围；hooks 修改内容时重新审查/测试，不使用 --no-verify 绕过。
7. 在新建干净 checkout 上针对实际 commit SHA 运行相关验证。先前工作树有未跟踪文件或 hook 改动参与测试时，不能把旧结果挂到新 commit。
8. 使用已确认 remote 和完整 `refs/heads/...`，把精确修复 SHA 推到明确目标。禁 force、mirror、all、附带 tag 或悄悄发布其他子模块。
9. push 无论返回成功还是超时，都实时核对实际 push 端点目标 ref。相同 SHA 已到达就记已确认，不重复 commit。远端已前进则证明 ancestry；只有可达不等于新的 tip 已通过测试。查不清就 PUSH_UNKNOWN，不能猜。
10. 核对实际被识别、被触发的 CI workflow、run/attempt/job、依赖组、runner OS/arch 和真正 checkout SHA。PR 合成 merge SHA 与修复 head 不能混用。相关真实门禁与 CI 对齐 `verified_on_sha` 后才能 FIXED。

提交自引用不需要解决：修复提交可以包含 issue_id、base_sha、run_id 和脱敏结果，**不要要求它包含自身 SHA**。commit/push/CI 回执写到 Git 外私有运行账本；最终可另作汇总报告，不为每个问题再 amend 或补一个纯记账 commit。

## 五、阻塞和后续回归的规则

- **最多一个尚未确认推送的修复候选。** push 失败或结果未知，先解决它；可继续盘点、独立复现或补证据，不形成第二个代码修复/未推送提交。
- push 超时先查远端；已成功不重复提交。确实未到达可对同一 SHA 有界重试。不能因为超时擅自 force。
- non-fast-forward 先看最新远端。仅对确定未发布的本问题候选，可从已确认新基线重建并重新测试；旧候选记 SUPERSEDED_LOCAL。已发布或发布未知的提交禁止改写。
- 认证/保护分支阻塞时使用用户已有合法认证；必要登录在用户本机完成，不索要明文 token、不放宽权限、不关闭分支保护。若需要改变用户明确指定的目标，再解释具体冲突并确认该改变。
- 上一项 **已确认 push**，但 CI 被另一项已识别的独立基线故障挡住，可以保留 CI_BLOCKED，继续单独修那个 CI 根因并 commit/push；不能提前 FIXED。最终用后续候选重新跑相关测试。记录 `introduced_by_sha` 与 `verified_on_sha`，证明后者包含前者。
- 缺真实飞书/模型凭据或原生环境时，只阻塞对应门禁，继续独立可完成工作。不要伪造成功，不把缺环境变成 N/A，不让 release gate 忽略它。
- 后续修改使已通过用例回归，要使旧结论 REOPENED/失效；用新修复 commit 或明确 revert 修复并独立 push。已推送历史不 amend、rebase 或 squash。
- 同一失败偶尔重跑变绿不等于根因消失，保留失败样本与时序证据。发布候选必须运行最终累计的相关回归。

## 六、证据与汇报

原始证据放在仓库之外的私有、权限受限目录。真实 HTTP/headers、cookie、token、飞书用户/租户 ID、用户路径/文件内容、DB 和截图先最少采集，再保存；不要进入模型上下文、公开日志、Git 或 CI artifact。可入 Git 的只有审核过的合成夹具、相对路径、用例/版本/计数、脱敏摘要和不透明证据 ID。秘密扫描离线执行，外部 allowlist 注释不获得豁免；扫描阴性也需要内容审查。

使用给定 JSON 模板并在实际执行后填写。每条命令保留退出码、时间、代码 SHA/tree、环境、收集/执行/失败/skip 数及具体 skip 原因。`introduced_by_sha`、`verified_on_sha`、remote ref、CI URL、artifact hash 都只能填实际观测值，没有就 null。

持续简短汇报正在验证的风险、已确定根因、当前问题状态和阻塞。每项结束报告 issue_id、根因、文件、回归、commit SHA、push 目标与远端回执、同代码 CI/真实门禁结果。没有做过的步骤直接写未做。

最后冻结一个实际候选 SHA，完成 `docs/08_release_gate.md`，提交：

- 当前 Mac/架构/安装/服务范围、真实命令清单和最终候选 SHA/tree；
- 全部用例结果、原始证据的安全索引和脱敏摘要；
- 每个问题的 introduced_by_sha、verified_on_sha、push/CI 回执和后续回归关系；
- 明确剩余 NOT_RUN / BLOCKED / FAIL 与所缺条件，不把它们折成 PASS；
- 结论仅为证据实际支持的 macOS MVP 范围，不把本次结论扩张成三平台或正式签名桌面发布。

如果目标尚未完成，继续所有已授权且独立可做的工作；只有客观缺失信息、凭据或权限挡住对应动作时说明具体原因。不要以“已提供计划”替代本机实际执行。
