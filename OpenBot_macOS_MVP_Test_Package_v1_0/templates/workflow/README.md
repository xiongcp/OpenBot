# 执行账本模板说明

这些是字段样例，不是已经完成的执行记录，也不是现有 OpenBot API。所有执行状态初始为 `NOT_RUN`，SHA、时间、退出码和成功/失败计数为空。已知项目地址和用户授权属于上下文事实；`policy` 中的规则属于执行约束，不是测试结论。

## 文件和用途

| 文件 | 作用 |
|---|---|
| repo_binding.template.json | 本机仓库、分支、push 目的地、dirty 保护和本次范围 |
| command_manifest.template.json | 从真实仓库发现并在当前 SHA 复核的命令，不臆造 CLI |
| issue_ledger.template.json | 一个独立根因从复现到验证闭环的状态和证据关联 |
| test_run.template.json | 一次实际测试的代码、环境、退出码、断言和证据 |
| push_receipt.template.json | 推送意图、客户端结果、真实端点和远端 ref 核对 |
| ci_run.template.json | 实际工作流/作业、触发条件、checkout SHA、环境和结果 |
| release_candidate.template.json | 固定候选、必需用例/门禁/产物、未关闭问题和最终结论 |

完整 macOS MVP 保留已确认 v1.2/M3 的原必需功能：真实云 Provider 和真实 Ollama 分别必须有证据。scope 不是从当前已实现功能中随意选择，缺实现不能排除。只有一种模型的局部通过不能填 PASS_MACOS_MVP；Tauri/M4仍按原阶段条件处理。

复制到仓库外私有运行目录使用；不要直接把填好的原始账本入 Git。`*_private` 字段仅私有账本可填，公开摘要删除私有路径、真实用户/租户标识、操作对象和秘密。原始证据以不透明 ID 引用，映射表留在私有目录。证据扫描应离线，且不相信外部 allowlist 注释。

模板中的 `attempt_record_shape`、`artifact_record_shape` 是记录结构说明，不算一次已执行动作或产物。实际条目加入对应数组后才能用于计数。`command_manifest` 的候选命令来自已读参考版本，必须重新核对当前 checkout；`candidate_only` 只能在该核对完成后改为 false。CMD-编号是模板记录 ID，不是产品 CLI。

## 值的约定

- 缺陷严重度：S0/S1/S2/S3；测试优先级：P0/P1/P2。未分类时为 null，不互相代替。
- 测试：NOT_RUN / RUNNING / PASS / FAIL / BLOCKED_ENV / BLOCKED_CREDENTIALS / BLOCKED_DEPENDENCY / INCONCLUSIVE。条件不适用需要执行前范围依据，才能填 NOT_APPLICABLE。
- 问题：OPEN / NOT_RUN / TRIAGED / REPRODUCED / FIXING / LOCAL_VERIFIED / COMMITTED / PUSH_UNKNOWN / PUSH_BLOCKED / PUSH_VERIFIED / CI_PENDING / CI_BLOCKED / FIXED / REOPENED / DEFERRED。
- push 核验 mode：EXACT_TIP / REACHABLE_NOT_TIP；都只能来自实际远端查询与必要的 ancestry 验证。后者不证明当前 tip 已验证。
- CI：NOT_RUN / PENDING / RUNNING / PASS / FAIL / BLOCKED / CANCELLED / INCONCLUSIVE；job skip 与 workflow 未触发不是 PASS。
- 最终结论：NOT_RUN / FAIL / BLOCKED / PASS_MACOS_MVP；可同时列多个失败和阻塞原因。
- 所有时间填写真实 UTC ISO 8601；SHA/hash 填实际观测值。不存在时保持 null，不用全零/示例十六进制字符串，不用空字符串表示成功。
- 计数未测为 null，实际测到 0 才为 0。零执行、空用例集、零验证产物绝不因为“失败数0”而通过。

`introduced_by_sha` 表示引入修复的 commit；`verified_on_sha` 表示真实测试/CI对应代码。后者若为后续候选，必须有包含前者的证据，并重新运行相关验证。`base_sha` 是该次修复实际起点，不是报告中已知的远端只读参考 SHA。

同一修复提交不需要写入自身 SHA。提交前的源码/测试快照可记录 run_id 和相应 tree hash，但需说明该 hash 指向哪个快照；加了摘要后的 commit tree 不能冒认是之前的树。commit/push/CI 回执在提交后写入私有账本，不为补字段反复 amend 或每个 bug 再 push 一个记账提交。

## 防止误用的校验规则

1. repo binding 目的地只有一个已确认 push endpoint；target_ref 是完整 refs/heads/...。用户 dirty 内容未被带入修复。
2. 每个 test_run 对应真实命令和代码 SHA/tree，记录实际执行层级、产品路径、被替换部分和环境，不仅一个 PASS 标志。
3. 对状态/恢复/网络边界记录实际 fault/barrier/接收器证据；socket 发送、服务端收到、逻辑效果分别计数。
4. issue FIXED 必须关联引入提交、远端回执、实际验证 SHA、目标/相关回归和所需 CI/真实门禁。已推送但 CI 被另一根因阻塞仍是 CI_BLOCKED。
5. push 失败或未知时只保留一个活动修复候选，不继续积累另一个未推送修复。后续回归使用新提交，不改写已发布历史。
6. CI 记录真实被识别的 workflow、触发事件/分支过滤、run/attempt/job 和实际 checkout SHA；PR 合成 merge SHA与head分开。
7. final release required_case_ids、required_gate_ids、expected_artifact_ids 必须在执行前审定且非空；每条 gate 映射用例和证据。G15是否必需取决于预先声明范围，不能因失败改为不适用。
8. 证据、实际候选、环境、产物来源一致；任何 blocking_reason 否决 ready。声明交付产物须逐一验证，不能只验证一项代表整包。
9. 模板初始状态不是放行结论，不把模板 JSON 填写或 schema 校验成功当作产品测试通过。
