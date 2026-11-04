# 任务质量基准评分规则 / Task Quality Benchmark Rubric (OB-076)

## 中文说明
- **OutcomeVerifier 唯一权威**：模型输出的 `final` 仅表示模型请求结束，必须由 `OutcomeVerifier` 核对产物哈希且无未决 `UNKNOWN` 操作才可判定为 `SUCCEEDED`。
- **未决 `UNKNOWN` 阻断成功**：若存在未核对的 `UNKNOWN` 动作，结果强制记为 `RECONCILING`，绝不计入 `SUCCEEDED`。
- **诚实声明**：离线 mock 测试仅验证协议与安全边界（`mock_accepted_as_intelligence_proof = False`），且不以固定代码行数或加速倍数作为验收承诺（`fixed_loc_or_speedup_promised = False`）。

## English Summary
- **OutcomeVerifier Authority**: Model `final` text only requests completion; `SUCCEEDED` requires `OutcomeVerifier` artifact verification and zero unresolved `UNKNOWN` operations.
- **Honest Boundary**: Offline mock runs verify protocol/safety invariants only (`mock_accepted_as_intelligence_proof = False`, `fixed_loc_or_speedup_promised = False`).
