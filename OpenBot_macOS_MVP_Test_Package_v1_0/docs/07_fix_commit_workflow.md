# OpenBot：逐问题修复、提交与推送规程

版本：2026-11-05。用途：交给用户本机的 Codex / Claude Code 执行。

**本轮工作是验收现有实现和逐项修复，不重新生成项目。用户已授权每修复一个问题就 commit、push 一次，不需要逐次再询问。** 仓库中的一般性“未经授权不推送”约定已满足授权前提；其他代码、测试、安全和分支规则继续遵守，不改写 AGENTS.md 来制造永久授权。

已确认项目为 [xiongcp/OpenBot](https://github.com/xiongcp/OpenBot)。本次只读审查参考 `main` 的 `a223d36a659b7ecf32fca2b4890fc187d3e96e48`；它不是用户本机当前 HEAD，也不是已经通过验收的版本。开始执行时记录实际本机基线。建议使用 `mvp/macos-hardening` 或明确的现有开发分支，不自动向 `main` 提交或推送，不自动 merge、打发布 tag 或部署。

本规程制定期间未在用户 Mac 执行测试、修复、commit 或 push。模板里的执行结果都是 `NOT_RUN`，待执行 SHA 为 `null`。

## 1. 不可跳过的约束

1. 一个独立根因对应一个原子修复提交，包含该问题的最小代码变更、有意义的回归和必要说明。一个根因引发多个错误可以一起修；不同根因不能因为同在一个文件而合并。
2. 修复顺序为：复现 → 锁定失败回归 → 最小修复 → 针对及相关回归 → 明确文件暂存 → commit → 核验实际提交及干净 checkout → push 明确目标 → 核实远端 → 对精确 SHA 核验 CI → 才能关闭问题。
3. 同一仓库只指定一个集成人员/代理操作 index、commit、push。其他代理可并行审查或运行隔离的只读复现，不争抢工作树/暂存区。
4. **最多一个尚未确认推送的修复候选。** push 失败、鉴权阻塞或结果未知时，先处理这一项；可继续盘点、独立复现、补证据，不能继续形成第二项代码修复或未推送提交。
5. 已推送提交不 amend、不 rebase、不 squash 重写。后续回归使用新的修复提交或明确的 revert 提交，再单独验证和 push。禁止 `--force`、`--force-with-lease`、`+refspec`、`--mirror`、`--all`、绕过 hooks/保护分支。
6. 用户现有 staged、unstaged、untracked 文件和未推送提交均先识别、保留。不得用 `git add .`、`git add -A`、`commit -a` 混入；不得用 reset --hard、clean、自动 stash 或覆盖文件来获得“干净状态”。
7. 缺真实服务凭据或原生环境只阻塞相应门禁，不妨碍其他独立工作；`BLOCKED`、`SKIPPED`、未收集到测试及 `NOT_RUN` 都不等于通过。

## 2. 首次绑定仓库、分支和基线

项目地址已经明确，不再泛泛询问“仓库在哪里”。本机根据用户给出的目录、当前 cwd 与真实 Git 配置定位工作副本。只有发现多个相互冲突的工作副本、origin 指向未确认项目/分叉、多个 push URL，或目标分支无法判定时，才问这个具体差异。

在任何写操作前记录：

- 仓库绝对路径、Git 版本、当前分支或 detached 状态、HEAD commit/tree、上游分支。
- 实际 fetch URL 和 **push URL**、目标 `refs/heads/...`、远端目标是否存在及其 SHA、保护规则与 CI 触发条件。
- dirty 状态、已有暂存内容、相关未跟踪文件、子模块状态及已有未推送提交的归属。
- 当前源码与锁文件、Python/uv、macOS 版本和 CPU 架构。Rosetta 与原生运行分别记录。

以下是 Bash 模板，不是已经执行的命令；变量必须来自本机绑定记录。`raw_dir` 必须在仓库之外，使用新建的当前用户私有目录，或先验证已有目录属于当前用户、权限为 0700 且不是符号链接；umask 不会修复旧目录权限。不要把带凭据的 URL 或原始 diff 输出到聊天或公开日志。

```bash
: "${repo_dir:?先绑定真实仓库绝对路径}"
: "${raw_dir:?先绑定仓库外私有证据目录}"
umask 077
mkdir -p "$raw_dir"

git -C "$repo_dir" rev-parse --show-toplevel > "$raw_dir/repo-root.txt"
git -C "$repo_dir" rev-parse --verify 'HEAD^{commit}' > "$raw_dir/initial-head.txt"
git -C "$repo_dir" rev-parse --verify 'HEAD^{tree}' > "$raw_dir/initial-tree.txt"
git -C "$repo_dir" symbolic-ref --quiet --short HEAD > "$raw_dir/initial-branch.txt"
git -C "$repo_dir" status --porcelain=v1 -z --untracked-files=all --ignore-submodules=none > "$raw_dir/initial-status.nul"
git -C "$repo_dir" diff --no-ext-diff --no-textconv --binary > "$raw_dir/initial-unstaged.patch"
git -C "$repo_dir" diff --cached --no-ext-diff --no-textconv --binary > "$raw_dir/initial-staged.patch"
git -C "$repo_dir" worktree list --porcelain > "$raw_dir/worktrees.txt"
```

`symbolic-ref` 返回非零可能表示 detached HEAD，不应吞掉后继续猜分支。逐条保存退出码。NUL 分隔的状态文件用解析器处理，不按空格拆文件名。[G02][G03]

`origin` 只是优先检查的名称，不是已验证推送目的地：

```bash
: "${repo_remote:?从真实配置确认remote名称，通常为origin}"
git -C "$repo_dir" remote get-url --all "$repo_remote" > "$raw_dir/fetch-urls.txt"
git -C "$repo_dir" remote get-url --push --all "$repo_remote" > "$raw_dir/push-urls.txt"
```

`get-url --push --all` 会显示实际 push URL，并展开 Git URL 重写配置。确认只有一个已授权目的地；如果 fetch/push URL 不同，后续远端核验必须查 **push 端点**，不能用 fetch 端点误作成功回执。URL 含口令/token 时，不将其放入命令参数或证据摘要，改用现有安全凭据机制；不能擅自改远端或认证权限。[G04]

### dirty worktree 的默认处理

优先在确认的 commit 基线上建立独立工作树，用户原目录与原 index 保持不动。工作树有自己的 HEAD/index，但共享仓库对象和部分配置，不应当作与原仓库完全隔离的安全沙箱；创建时仍遵守已审查的 hooks。[G03]

```bash
: "${baseline_sha:?填实际确认的起点commit，不照抄参考快照}"
: "${repair_branch:?填确认的修复分支}"
: "${repair_dir:?填不存在或空的独立工作目录}"
git -C "$repo_dir" check-ref-format --branch "$repair_branch"
git -C "$repo_dir" worktree add -b "$repair_branch" "$repair_dir" "$baseline_sha"
```

分支已存在时先检查归属和是否已被另一工作树使用，不使用 `-B` 或 `--force` 覆盖。若修复依赖用户未提交改动，不声称新工作树包含它们；先指出基线差异，继续可独立执行的检查。不能把用户全部未提交内容搬进自己的修复提交。

如果拟推送范围包含归属/发布授权不明的既存未推送提交，停止该 push 范围，先明确这些提交是否属于本次授权；不能靠只写了一个新 commit 就假称只发布一项修复。

## 3. 从真实仓库发现测试命令

首先读当前 checkout 的 AGENTS.md、README、pyproject/锁文件、scripts/verify.py、测试目录和顶层 CI 配置，形成 `command_manifest`。每项记实际 argv、cwd、环境键名、依赖组、代码来源、超时、测试层级和外部副作用；不要用 `eval` 执行仓库文本。

本次参考 SHA 已存在这些入口，**本机应先复核，再运行**：

```bash
cd "$repair_dir"
uv sync --locked
.venv/bin/python scripts/verify.py
uv run --no-sync pytest --collect-only -q
uv run --no-sync pytest
```

前两个来自 README；后两个用于复现当前 CI 使用的 pytest console 入口与实际 collection。不能用另一个入口的绿灯掩盖 CI 命令的导入错误。[R01][R02]

参考版本的 `scripts/verify.py` 会：

- 设置 core 与 feishu_gateway 的 PYTHONPATH，内部以 `python -m pytest` 运行。
- 删除 `OPENBOT_NATIVE_TESTS`；默认 phase 为 M0，只接受 M0/M1。
- 将原始日志和 JSON 写到 `evidence/implementation`；每条检查有 60 秒 timeout。

因此它通过不证明原生 Mac、真实服务或 M3 已验收。原始输出先存私有证据，不因位于仓库内就全部暂存；在自己独立工作树中检查并单独管理生成文件，不能覆盖用户原目录中的证据。[R03]

`pyproject.toml` 的默认组为 `dev-contracts`，`provider-openai` 为额外组。需要 SDK 合同测试时，先核对当前组名和锁，再按现有组安装，例如该参考版本可用 `uv sync --locked --group provider-openai`。缺 SDK 导致 skip 不能代替对应测试通过。真实凭据只在专用测试环境注入，不写入命令行、Git、模型或日志。[R04]

不臆造 `openbot doctor`、`openbot acceptance`、`--profile` 等接口。需要原生启动、profile、后台服务或真实模型命令时，必须从当前 CLI/parser、脚本或测试代码找到可用入口；没有入口就登记具体缺口。

## 4. 每个问题的执行闭环

### 4.1 建立问题记录并先复现

记录 `issue_id`、严重度 S0—S3、相关测试优先级 P0—P2、当前 base SHA、受影响能力、期望/实际、最小输入、命令、真实/模拟边界和证据。一个失败首先分类为产品、测试入口、CI、环境/凭据、测试本身或尚未解释，不能将所有失败都归因环境。

运行基线用例证明问题确实存在。新增或扩展一个能锁住根因的失败回归；如果已有测试可稳定复现，保留该测试并将其纳入回归清单，不复制无意义断言。纯文案/CI 配置类问题使用有意义的配置/触发/实际运行证据，不编写只镜像改动文本的测试。

回归要证明：修复前确因该缺陷失败，修复后因正确行为通过；测试必须被收集且实际执行。导入失败不能充当业务断言失败，未触发的 workflow 不能算 CI 通过。竞态用屏障/事件确认时序，覆盖两种线性化次序，不靠 sleep 碰运气。

### 4.2 最小修复与局部验证

仅修本问题根因，不附带格式化全仓、重构、升级不相关依赖或另一个 bug。新增必要生产路径回归，不让测试只跑一份替代实现或参考 DDL。

完成针对测试、具体受影响回归和仓库要求的 lint/type/format。对授权、持久化、恢复、隔离、数据出口的修改，包含相关 P0 反例；把以前修复的相关回归加入当前集合。不能删断言、添加无理由 skip、放宽权限、catch-all 返回成功或伪造结果字段。

真实环境缺失时记录 `BLOCKED_ENV`/`BLOCKED_CREDENTIALS` 与所缺条件，可继续不依赖它的测试。未执行的真实门禁仍未通过；本地模拟通过不能补足它。

若完整基线已被另一独立问题阻塞，保存该失败的基线证据和问题关联；本问题针对验证与可运行的相关检查仍必须通过，且不能有新增回归。可以据此提交并 push 已验证的局部修复，但状态保留 LOCAL_VERIFIED/CI_BLOCKED 等相应范围，直到所需验证齐全才 FIXED。只能由 CI 验真的配置变更，以本地有意义校验作为 push 前提，以实际 CI 结果作为关闭前提。不得将自己新引入的失败称为历史问题。

### 4.3 审查并明确暂存文件

在集成人员的工作树中确认没有别人的 index 内容。形成 `approved_paths`，它是具体相对文件列表，不是目录、glob 或全仓。检查实现、测试、生成文件和必要文档是否都属于同一问题，检查依赖锁改变是否确有原因。

```bash
: "${repair_dir:?}"
: "${raw_dir:?}"
git -C "$repair_dir" diff --cached --quiet
# 若返回1表示index已有变更：先核对归属，不能盲目继续。

# fix_paths由本问题已审查的具体相对文件填入；不使用占位文件名。
((${#fix_paths[@]} > 0)) || exit 1
git --literal-pathspecs -C "$repair_dir" add -- "${fix_paths[@]}"
git -C "$repair_dir" diff --cached --check
git -C "$repair_dir" diff --cached --name-status -z > "$raw_dir/staged-paths.nul"
git -C "$repair_dir" diff --cached --no-ext-diff --no-textconv > "$raw_dir/staged.patch"
tested_index_tree=$(git -C "$repair_dir" write-tree)
```

将 staged 文件列表与 approved_paths 精确比较，核验没有用户改动、原始日志、秘密、PII、模型缓存、浏览器 profile、用户 DB 或无关构建产物。秘密扫描必须离线且审查输出，另做人工/规则审查；扫描阴性不是公开许可。`git write-tree` 只给出 index 树，需要另查工作树与测试输入一致性。[G05][G06]

### 4.4 单问题 commit 与 hooks

提交信息遵循仓库约定，至少包括问题 ID、根因/行为变化、测试命令及范围，使用现有作者/签名身份，不伪造身份，不加无依据的工具归属。

```bash
: "${commit_message_file:?私有目录中的已审查提交说明文件}"
expected_parent=$(git -C "$repair_dir" rev-parse --verify 'HEAD^{commit}')
git -C "$repair_dir" commit -F "$commit_message_file"
fix_sha=$(git -C "$repair_dir" rev-parse --verify 'HEAD^{commit}')
fix_tree=$(git -C "$repair_dir" rev-parse --verify 'HEAD^{tree}')
git -C "$repair_dir" show -s --format='%H%n%T%n%P' "$fix_sha" > "$raw_dir/commit-object.txt"
git -C "$repair_dir" diff-tree -r --no-commit-id --name-status -z "$expected_parent" "$fix_sha" > "$raw_dir/committed-paths.nul"
```

逐条检查退出码；commit 返回异常也要查询实际 HEAD，不能盲重试。核对最终提交只有预期父提交、只含这一问题、文件范围正确、内容对应已验证树。hook 修改 index/文件可能使 `fix_tree != tested_index_tree`；此时先审查实际差异，再重测最终提交，不能把 hook 当自动批准。[G07][G08]

pre-commit 失败而 HEAD 没变时，检查它改了哪些文件，仅暂存本问题的合法变动并重新测试后再提交。不要用 `--no-verify` 或改 hooksPath 绕过。若提交已生成但内容不合格，保持本问题，保存未发布候选并构建正确替代候选；没有验证通过前不 push，也不开始另一问题。

### 4.5 验证实际 commit，而不只验证工作目录

先检查最终 commit 的 parent/tree/diff、必要测试是否随提交进入 Git、未跟踪内容是否意外参与先前测试。再用新建的干净 detached 工作树运行针对与相关验证，记录**实际 checkout SHA**：

```bash
: "${verify_dir:?本问题新建的独立验证目录}"
git -C "$repo_dir" worktree add --detach "$verify_dir" "$fix_sha"
git -C "$verify_dir" rev-parse --verify 'HEAD^{commit}' > "$raw_dir/verified-checkout-sha.txt"
cd "$verify_dir"
# 按command_manifest安装实际需要的已锁依赖组，并运行实际命令。
uv sync --locked
.venv/bin/python scripts/verify.py
```

在启动测试前确认工作树仍对应该 commit，hooks未改变源码/测试/锁/配置；有偏差先查明，不把脏副本记作干净验证。

以上基线命令之外仍需该问题的目标/相关测试；涉及 provider-openai 则在本次干净环境安装其锁定组，不能因默认组缺包而把回归跳过。记录 tests collected/executed/passed/failed/skipped、每个 skip 原因和每条退出码，避免只看一行 PASS。

验证脚本生成的文件先按已审查清单保存私有证据；源文件、测试、锁或配置发生意外变动则证据失效。仅可在自己拥有的临时工作树中处理自己生成的文件，原用户工作区不动。后续任何更改都需重新确认测试对象。

### 4.6 push 精确目标

确认 `fix_sha` 已通过实际提交树验证，当前修复分支未被其他人推进；再次核对真实 push endpoint、目标 ref 与远端变化。`target_ref` 必须为完整 `refs/heads/...`。

```bash
: "${target_branch:?确认的远端修复分支，不能猜main}"
target_ref="refs/heads/$target_branch"
git -C "$repair_dir" check-ref-format "$target_ref"

# push_endpoint是已核对的单一实际推送端点，不含口令/token。
git -C "$repair_dir" ls-remote --exit-code --refs "$push_endpoint" "$target_ref" > "$raw_dir/remote-before.txt"
```

`ls-remote --exit-code` 的 2 表示没有匹配 ref，不等于鉴权失败；创建新修复分支必须是已经确认的动作。其他错误保持阻塞。不要把旧的本地 origin/... 缓存当实时远端。[G09]

明确 SHA:ref 推送，禁止附带 tags、mirror 或对子模块自动推送。已有子模块提交必须在其正确远端可达；否则单独解决，不暗中发布其他仓库。

```bash
if git -C "$repair_dir" \
  -c push.followTags=false \
  -c push.recurseSubmodules=check \
  -c "remote.${repo_remote}.mirror=false" \
  push --porcelain "$repo_remote" "${fix_sha}:${target_ref}" \
  > "$raw_dir/push.stdout" 2> "$raw_dir/push.stderr"
then
  push_exit=0
else
  push_exit=$?
fi
printf '%s\n' "$push_exit" > "$raw_dir/push.exit"
```

无论返回 0、超时、断连还是非零，都重新查询实际 push 端点对应 ref；推送意图不能代替交付回执。[G01]

```bash
git -C "$repair_dir" ls-remote --exit-code --refs "$push_endpoint" "$target_ref" > "$raw_dir/remote-after.txt"
```

### 4.7 验证远端及处理不确定结果

| 观察 | 状态及动作 |
|---|---|
| 远端目标 SHA 等于 fix_sha | `PUSH_VERIFIED`，即使客户端曾超时也不再新建或重复提交；记录回执时间/端点/ref |
| 远端比 fix_sha 更新，且能证明包含 fix_sha | 记录 `REACHABLE_NOT_TIP`：修复已可达，当前分支新 tip 尚未自动获得旧验证；选择候选重验 |
| 远端仍为原 SHA，确定没有包含本次修复 | 同一 SHA 的有界、非 force 重试；不创建第二修复提交 |
| 查询失败、鉴权不明或不能确认包含关系 | `PUSH_UNKNOWN` / `PUSH_BLOCKED`，不猜成功或失败；不积累下一项未推送修复 |
| non-fast-forward | 读取最新目标、分析新增提交；只在未发布修复上构建新基线候选，重测后正常 push，绝不 force |

确认包含关系时 fetch **实际 push 端点** 到本次专用本地 ref，而不改用户分支。`fetch_ref` 使用经过 check-ref-format 校验的唯一会话名，避免覆盖他人的追踪 ref：

```bash
: "${fetch_ref:?本次专用且尚不存在的本地ref}"
git -C "$repair_dir" check-ref-format "$fetch_ref"
git -C "$repair_dir" fetch --no-tags --no-recurse-submodules "$push_endpoint" "${target_ref}:${fetch_ref}"
remote_tip=$(git -C "$repair_dir" rev-parse --verify "${fetch_ref}^{commit}")
git -C "$repair_dir" merge-base --is-ancestor "$fix_sha" "$remote_tip"
```

ancestor 判定返回 0 为真、1 为假，其他非零为错误，不能一律当“未包含”。[G10][G11]

non-fast-forward 且本修复确未发布时，可在新的独立工作树从已核对 `remote_tip` 出发，将**本问题唯一修复**用 `cherry-pick --no-commit` 应用，解决可解释冲突，重走测试/暂存/commit。旧未发布 SHA 标 `SUPERSEDED_LOCAL`，只保留一个活动候选，不把旧候选一并 push。已发布或发布未知的提交不走这种重写流程。[G12]

### 4.8 CI 对准实际代码并关闭问题

在 CI 服务查询目标分支和明确的 commit，核对 workflow 路径、事件、branch/path filters、run/attempt/job、实际 checkout SHA、依赖组、runner OS/arch、结果和日志。只存在 YAML、run 状态 completed 或绿色 badge 都不足够。

PR 工作流可能默认测试合并合成提交。记录 PR head、run 元数据 SHA 和**实际 checkout SHA**，以真正测试的代码为准；不能把默认分支的结果嫁接到修复 SHA。定时/手动触发也要核对执行的是哪个 ref。[G13][G14]

`FIXED` 必须满足：确定性复现、有效回归、目标/相关验证通过、合法原子提交、远端已确认、针对同一 `verified_on_sha` 的所需 CI/真实门禁通过。`introduced_by_sha` 是引入修复的提交，`verified_on_sha` 是实际完成验证的提交，通常相等；若后续修复了独立 CI 基线阻塞，可在包含该修复的后续候选上重新验证，明确记录祖先关系和全部相关结果。

**避免多根因 CI 死锁：** 上一修复已经 push 且远端确认，但 CI 被另一项已识别独立基线故障阻塞时，保留 `CI_BLOCKED`，不标 FIXED；可以继续修那个独立 CI 根因，每项仍单独 commit/push。本规则不允许在 push 未确认时堆积修复，也不把 CI_BLOCKED 当通过。最终候选必须清空必需门禁阻塞。

## 5. 已知只读基线的处理顺序

参考版本的仓库/CI审查发现了这些线索，**本机须重新核对，它们不是本规程已执行的修复结果**：

- `.github/workflows/pr.yml` 由 push/pull_request 触发，三 OS matrix，固定 Python 3.12.12/uv 0.9.26；实际测试命令为 `uv run --no-sync pytest`。
- 参考 CI run [41949551726](https://github.com/xiongcp/OpenBot/actions/runs/41949551726) 失败：Mac/Windows 在解释器安装，Linux 有 24 个 `No module named tests` collection 错误，另有 SDK skip。这些应按实际根因分别复现、修复，不能用“本机环境不同”忽略 collection。
- `platform-macos.yml` 仅 PR/workflow_dispatch，直接运行 python3/pytest，未见依赖安装步骤；普通 push 不等于此工作流运行。
- 放在 `.github/workflows` 子目录中的 nightly/soak、pull_request/gate、release/supply_chain 文件不能视为已被 GitHub 识别的工作流；GitHub不支持 workflow 子目录。[G15]
- runner/解释器可用性以执行时官方支持矩阵为准；不要继续把失效 label 或缺少对应架构构建的精确版本当可运行组合。固定实际 OS image/arch 与 runtime 后重新验证。

优先恢复可运行的测试入口和 CI。runner label、解释器构建、导入根因、依赖安装和 workflow 未发现应按独立根因建记录，不能整包修改后只推一个“大修复”。

## 6. hooks、push 与回归异常决策

| 异常 | 处理 |
|---|---|
| pre-commit 改文件并失败 | 看 HEAD 是否变化；复核 hook 改动，明确暂存本问题内容，重新跑受影响测试；不 no-verify |
| hook 成功但实际 commit tree 改变 | 查实际 commit 范围并对干净 checkout 重测；未确认前不 push |
| commit 后本地验证失败 | 保留未发布证据，只继续本问题；构建合格替代候选，不推失败提交、不接下一修复 |
| push 返回超时/断连 | 先实时查目标 ref；已到达就确认，不重新 commit；不能查清就 PUSH_UNKNOWN |
| auth/签名/保护分支阻塞 | 使用既有合法认证/签名；必要登录由用户本机完成，不索要明文token；不关闭保护、不偷偷换目的地 |
| 已指定目标禁止直接 push | 遵循已经明确的修复分支/PR流程；若需要改变明确指定的目标，说明具体冲突后再确认一次，不泛问每项是否能 push |
| 远端前进 | 判断是否包含修复，或在新基线上重建未发布同一问题候选；重新测试，禁 force |
| CI pending/未触发 | 明确等待/阻塞原因，核对触发条件；不凭仓库存在 YAML 标 PASS |
| 后续修复打破先前功能 | 记录新的回归问题并使相应旧结论 REOPENED/失效；新 commit+push，不 amend 已推送历史 |
| 失败看似 flaky | 保留失败样本并定位时序/环境原因；不能只重跑到绿、删除断言或扩大timeout掩盖 |
| 暂存区/commit 含秘密 | 未发布时禁止 push，不用“下一提交删除”掩盖泄漏历史；重建干净候选。若已发布，升级S0并按授权应急流程处理，普通流程不擅自强推清历史 |

## 7. 证据、自引用与隐私

分两层保存：

- **私有原始证据**：仓库外受限目录中的完整 stdout/stderr、真实请求/回执、必要数据库快照、原生进程/容器观测、未脱敏截图。有限保留、最少采集，不进入 Git/聊天/公开 CI artifact。
- **可入 Git 的摘要**：合成 fixture、相对源码路径、用例 ID、命令及安全参数、版本/OS/arch、计数、预期/实际和脱敏结果。移除 tokens、headers/cookies、个人路径、姓名/邮件、tenant/user IDs、用户文件内容、截图可见隐私及带签名查询参数的 URL。

可审查摘要引用不透明证据 ID；私有账本再把 ID 映射到原始文件。不要把秘密的哈希或真实私有绝对路径当作安全公开替代品。扫描必须离线；外部内容的 allowlist 注释不改变脱敏/出口要求。

**不要求修复 commit 自己包含自己的 SHA。** 同一提交可放 issue_id、base_sha、run_id 和脱敏结果；若放测试树 hash，必须注明它指向哪个已测快照，不把加入摘要前的 tree 当成最终 commit tree。最终 commit/tree、push、CI 回执写到 Git 外的运行账本。禁止为了补自身 SHA 不断 amend 或为每个 bug 再推一个纯记账提交。

最终汇总如需入 Git，作为独立且明确的文档变更提交，更新候选 SHA 并跑相应门禁；也可作为仓库外、绑定固定候选 SHA 的交付报告。

## 8. 每项汇报的最小内容

`issue_id / S级 / 关联P级用例`；复现与根因；改动文件；失败回归与修复后结果；实际测试 SHA/tree；introduced_by_sha；目标 remote/ref；push 回执；verified_on_sha及CI run/job；未验证/阻塞；当前状态。没有真实 commit/push/CI 回执时写 `null` 和原因，不填示例 SHA，不把 LOCAL_VERIFIED 写成 FIXED。

## 参考来源

以下官方文档支持 Git/CI 命令语义；本规程的单问题、隐私与放行标准是针对本次用户要求制定的工程规则。

- [G01 git-push：refspec、porcelain 与推送选项](https://git-scm.com/docs/git-push)
- [G02 git-status：porcelain 与 NUL 输出](https://git-scm.com/docs/git-status)
- [G03 git-worktree](https://git-scm.com/docs/git-worktree)
- [G04 git-remote：get-url/push URL](https://git-scm.com/docs/git-remote)
- [G05 git-diff](https://git-scm.com/docs/git-diff)
- [G06 git-write-tree](https://git-scm.com/docs/git-write-tree)
- [G07 git-commit](https://git-scm.com/docs/git-commit)
- [G08 githooks](https://git-scm.com/docs/githooks)
- [G09 git-ls-remote](https://git-scm.com/docs/git-ls-remote)
- [G10 git-fetch](https://git-scm.com/docs/git-fetch)
- [G11 git-merge-base](https://git-scm.com/docs/git-merge-base)
- [G12 git-cherry-pick](https://git-scm.com/docs/git-cherry-pick)
- [G13 GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [G14 GitHub workflow events 与实际 SHA](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [G15 GitHub workflow 文件位置](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)
- [R01 参考 README](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/README.md)
- [R02 参考 pr.yml](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/.github/workflows/pr.yml)
- [R03 参考 verify.py](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/scripts/verify.py)
- [R04 参考 pyproject.toml](https://github.com/xiongcp/OpenBot/blob/a223d36a659b7ecf32fca2b4890fc187d3e96e48/pyproject.toml)
