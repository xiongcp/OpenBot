# ADR-0014: Long-run agent baseline / 长任务 Agent 基线

Status / 状态: Accepted for implementation, 2026-11-05（用户指定 max_steps=200、64k 输出；计划见 `docs/superpowers/plans/2026-11-05-frontier-agent-parity.md`）.

1. Steps / 步数：client settings `max_steps` 1–200，新 profile 默认 200；预算侧 `TaskBudgetPolicy` 默认 max_steps=200、max_model_calls=200、max_tool_calls=400、max_duration_ms=14_400_000。
2. Output / 输出：OpenAI 兼容请求 `max_completion_tokens=64_000`；预留仍为完整序列化请求 + 64_000，发送前准入。
3. Budget / 预算：新任务默认 token_limit=4_000_000（可按任务调整）；金额仍为 0 且显示不可用。按 §5 的视图上限，满上下文时每次请求实际约 6.4 万 token 输入，默认额度约可支撑 40–60 个满上下文步骤；要跑满 200 个满上下文步骤需把该任务额度调到约 1,300 万 token（花费决定由用户做出）。usage 缺失时整笔预留按 UNKNOWN 扣住、不清零，不支持 stream usage 的端点会更快耗尽额度。
4. Deadline / 期限：单次模型请求期限 900 s；SSE 读空闲超时 180 s；超时按既有规则 UNKNOWN 结算，不自动重发。取消、关闭或权限收紧会在 0.25 s 轮询内中止进行中的请求（adapter cancel，UNKNOWN 结算）。
5. History / 历史：适配器硬上限 1024 块、单个工具结果 64 KiB、序列化历史 1 MiB。工作区工具结果在交给模型前截断到 64 KiB 并注明完整结果所在 artifact 与续读方式。运行时在发送前做确定性裁剪，目标视图 256 KiB（按 JSON 转义后估算；假设模型上下文窗口 ≥128k token，即约 6.4 万 token 提示 + 6.4 万输出；按模型配置窗口属于 W9）：保留目标与最近 3 对调用/结果，较早结果替换为带 sha256 的占位，只替换到不超限为止；工具调用参数不裁剪，仍超限则暂停 CONTEXT_WINDOW_EXHAUSTED。被裁剪的 propose 结果里的 bundle_id 对模型不可见，需重新 propose。权威账本（Operation/Artifact）不受裁剪影响。
6. Tools / 工具开关：新增设置 `workspace_tools`（OFF/READ/READ_WRITE，默认 READ）。发布集合 = 已准入 ∩ 有执行器 ∩ 运行固定设置 ∩ 当前设置；在 propose 前、批准后、begin_dispatch 前三处再次核对，任一处被关闭即拒绝 WORKSPACE_TOOL_DISABLED（待批期间收紧设置会阻止该写入）。apply_patch(bundle_id) 的 Operation 参数取自运行时暂存记录（path + snippet），审批预览与绑定哈希覆盖实际写入内容。写工具默认关闭，直到完整 diff 预览（CR-11）完成。
7. Upgrade / 升级：已持久化的设置回执若缺少 `workspace_tools`，读取时补 `READ`；不改写历史事件（events 只追加），不补写权限更高的值。
8. System instruction / 系统指令：每次请求带运行时固定的 system 消息，声明工具结果是不可信数据、不是指令或授权；不含密钥、endpoint 或用户可编辑内容。

Compatibility / 兼容：无 DDL 变更；`client-settings` 合同加字段属于不兼容变更，桌面端同批升级；旧客户端提交缺字段的配置会被拒绝（CLIENT_CONFIG_FIELDS_INVALID）。
