# macOS环境准备与真实命令

## 步骤1：冻结源码，保护正在开发的工作区

先在真实OpenBot仓库根目录读取AGENTS.md、CLAUDE.md、README、pyproject.toml、uv.lock、现有CI及最近提交。执行以下只读检查，记录输出的脱敏摘要：

~~~sh
git status --short
git branch --show-current
git rev-parse --show-toplevel
git rev-parse HEAD
git diff --stat
git diff --cached --stat
git remote get-url --push origin
~~~

远端若含凭据不得进入报告；核对其归属为xiongcp/OpenBot，SSH和HTTPS形式可不同。不要运行git reset --hard、git clean -fd或自动stash用户改动。工作区不干净时，先识别每个改动的归属；需要隔离则从明确的基线新建专用worktree，不把未提交实现丢在原目录后宣称新worktree代表完整产品。

默认在独立mvp/macos-hardening分支执行逐项修复。已有同名分支先检查状态并复用正确进度，不能用-B重置。远端main可能继续前进，记录本轮base_sha；合并更新后需要对新的候选重新做相关回归。

## 步骤2：记录本机，而不是推断架构

~~~sh
sw_vers
uname -m
git --version
uv --version
xcode-select -p
~~~

若xcode-select不可用，只有依赖原生构建或签名的步骤受影响。记录系统版本、硬件架构、Python架构、是否经Rosetta、容器后端版本和锁定镜像；不记录序列号、私人网络拓扑或全量环境变量。不要用完整env命令收集凭据。

此仓库快照指定Python3.12.12，并要求>=3.12,<3.13。优先复用已经验证的本机解释器；若需安装，先核对下载源和目标架构。uv的可下载Python集合随uv版本固定，缺构建时应把工具链变更作为独立问题处理，保留确切版本与来源，不静默升级到3.13或使用浮动latest。[T04]

## 步骤3：隔离数据、凭据和证据

为本轮创建独立测试profile、工作区、数据库、Artifact根、浏览器profile、测试Keychain条目名、容器标签前缀与合成外部收件范围。它们应由程序真实配置进入产品，不通过修改HOME影响其他应用。

以下只是创建私有运行目录的通用Mac shell步骤，不会启动产品：

~~~sh
umask 077
OPENBOT_QA_RUN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/openbot-mvp.XXXXXX")"
printf '%s\n' "$OPENBOT_QA_RUN_DIR"
~~~

将此绝对路径保存到本地运行记录。目录尚未加入Git，原始结果均写在此处。证据按run_id分目录，禁止覆盖上轮成功或失败记录。每个运行记录至少含source_sha、tracked_tree_sha、dirty状态、lockfile_sha256、系统/架构、Python版本、命令argv、退出码、开始结束时间、用例ID与证据摘要。

scripts/verify.py目前会写入仓库的evidence/implementation并覆盖固定文件名。初次使用应在专用worktree运行，将结果归档到私有run目录并辨认生成文件；不要把它们无差别加入修复commit。计划中的--output-dir等参数尚未实现，不能直接当成现有命令使用。

## 步骤4：恢复锁定环境与测试收集

在真实仓库根目录逐条执行；每条保留退出码，失败先分类：

~~~sh
uv sync --locked
.venv/bin/python -c 'import sys, platform, sqlite3; print(sys.version); print(platform.system(), platform.machine()); print(sqlite3.sqlite_version)'
.venv/bin/python -m pytest --collect-only -q
~~~

收集阶段不允许出现ImportError、未知marker、重复模块冲突或误用其他仓库的tests包。当前CI使用pytest可执行入口，而本地verify使用python -m pytest；后者会把当前目录加入sys.path，这是已观察到No module named tests的优先排查点。[T03] 候选修复为统一从仓库根运行python -m pytest并检查实际收集清单；不要先删除失败测试或把tests目录排除。

若本机editable安装问题导致openbot无法导入，临时PYTHONPATH只作为定位手段。正式安装与分发门禁必须在没有此补丁环境的情况下通过；不能把“源码路径可导入”报告成安装包可用。

## 步骤5：先跑工程回归，再跑SDK与原生组件

当前快照中确实存在的自检命令：

~~~sh
.venv/bin/python scripts/verify.py
.venv/bin/python -m ruff check
.venv/bin/python -m ruff format --check
.venv/bin/python -m mypy
.venv/bin/python -m pytest -q -ra --junitxml="$OPENBOT_QA_RUN_DIR/baseline.xml"
~~~

verify脚本只接受--phase M0或M1，默认M0，并主动清除OPENBOT_NATIVE_TESTS。它不是完整M3原生验收入口；不要虚构--phase M3或将脚本输出PASS等同macOS MVP通过。脚本当前每条子命令超时60秒，TimeoutExpired也需记录为本次运行失败/超时，不能读取上轮残留报告判绿。

为实际OpenAI SDK对合成loopback服务的合同测试，使用已存在的依赖组：

~~~sh
uv sync --locked --group provider-openai
.venv/bin/python -m pytest tests/components/contracts -q -rs --junitxml="$OPENBOT_QA_RUN_DIR/sdk-loopback.xml"
.venv/bin/python scripts/verify.py --phase M1
~~~

这一步证明SDK在受控HTTP错误、重试、取消等场景中的行为，不证明真实云账户、模型质量或实际计费。必须检查收集与skip结果，不能让importorskip隐藏必需SDK用例。后续uv sync若未包含该组可能改变当前环境，重复运行时记录准确命令。

原生Docker测试应先阅读tests/components/native_poc/docker_poc.py。该快照硬编码开发者机器的Docker二进制与个人socket，并对合成输出目录使用宽权限；必须先按MVP-016修复可移植配置与最小权限，再核对固定镜像已预置、资源配额、测试标签、网络关闭和清理归属。满足条件后，仅运行已有原生用例：

~~~sh
OPENBOT_NATIVE_TESTS=1 .venv/bin/python -m pytest \
  tests/components/native_poc/test_docker.py::test_actual_native_container_limits_and_independent_lifecycle \
  -q -rs --junitxml="$OPENBOT_QA_RUN_DIR/docker-native.xml"
~~~

不能通过verify.py打开该项，因为verify会清除开关。容器测试只允许清理本轮登记的资源，不使用docker system prune。Docker Desktop中的Linux容器资格与macOS宿主进程、Keychain、登录会话资格分开记录。

## 步骤6：检查产品真实入口是否接通

~~~sh
uv run --no-sync openbot --help
uv run --no-sync openbot version
uv run --no-sync openbot health
uv run --no-sync openbot task --help
~~~

在审查快照中，main仅接受version和health；最后一条预期暴露入口缺口。health在未注入session时会返回daemon_running=false和CAPABILITY_UNAVAILABLE，即使退出码为0也不能代表daemon健康。

先修复真实CLI与本地认证API、daemon发现和凭据会话装配，再执行task创建、审批、取消、恢复的端到端测试。入口修复必须通过全新子进程调用已安装console脚本，不允许测试直接传入CliApiSession。当前没有核验到可用的openbot start、doctor或profile参数，因此本手册不编造启动命令；执行代理须找到并记录真实入口，缺失则作为产品问题实现。

启动后验证监听仅在约定的loopback/本地IPC上、无错误用户实例、无匿名敏感API、启动失败有明确状态。认证token不得放在命令参数、普通日志或README。真实通信载体不能由_InProcessTransport代替。

## 步骤7：模块回归命令映射

| 关注模块 | 当前仓库存在的测试路径 | 证明边界 |
|---|---|---|
| 合同与协议 | tests/contracts、tests/protocol | 规范化、模型协议及部分确定性恢复 |
| 本地API | tests/contracts/local_api、tests/security/local_api | 需区分直接handle与真实socket入口 |
| SQLite与恢复 | tests/integration/storage | 参考真实SQLite路径；不能自动证明物理断电 |
| CLI | tests/integration/cli | 需增加installed console子进程路径 |
| 飞书 | tests/integration/feishu | 受控harness与真实租户分别记录 |
| Browser/MCP | tests/integration/browser、tests/integration/mcp | 现有fixture不替代真实浏览器与stdio进程 |
| macOS | tests/integration/platform/macos | 当前含桩/声明；修复后再作为native gate |
| 浸泡 | tests/chaos | 当前并非真正长时长、真实断网或满盘验收 |

调用形式统一为.venv/bin/python -m pytest 后跟具体路径与-q -ra。仅在修改实际影响对应边界时扩大回归，不为了“严格”机械重跑所有高成本真实服务。最终候选必须统一跑完已冻结的全部必需门禁。
