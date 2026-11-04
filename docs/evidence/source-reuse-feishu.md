# OB-094：飞书模板最小源码复用审查与 NO_COPY 决策记录 / Feishu Card Template Source-Reuse Audit & NO_COPY Decision

## 中文说明

### 1. 候选组件对比与边界审查（`nanobot` vs `langbot`）
- **`nanobot`（`REFERENCE_ONLY`）**：
  - 上游飞书适配包含二维码/首名发信人（first-user）自动成为 owner、内存流式更新循环与直接调用 SDK 发送方法。
  - 按 OpenBot 架构不变量，配对必须由本地 `owner_cli` 生成一次性短 TTL 挑战并经本地显式确认（`OB-048`），卡片构造必须为离线纯函数且由 `OutboxService` 单一掌管发送与节流（`OB-051`/`OB-052`）。
- **`langbot`（`REFERENCE_ONLY`）**：
  - 上游消息/卡片层与内部插件事件总线（channel bus）及 Agent 会话循环耦合，剥离纯 JSON 卡片字典的改造成本高于直接编写 OpenBot 自有最小普通卡构造器。

### 2. 审查结论：`NO_COPY`
- **正式决定**：`NO_COPY`（记录于 `components/source-reuse/feishu.json`，保持 `components/source-reuse-ledger.json` 的 `entries: []` 不变）。
- **理由**：OpenBot 所需的任务状态卡、脱敏审批预览卡（含 `REQUIRE_LOCAL` 降级提示）与结果回执卡均为确定性 JSON 结构，由 `services/feishu_gateway/src/openbot_feishu/cards.py` 以零网络副作用的纯函数直接生成，无需复制任何上游源码或引入 vendor 目录。
- **专属摘取验证状态**：因决策为 `NO_COPY`，源码摘取专属 diff/NOTICE 验证标记为 `NOT_APPLICABLE`。

### 3. 可复现验证命令
- `PYTHONPATH=services/core/src .venv-m1/bin/python -m pytest tests/unit/test_source_reuse_feishu.py -q`（1 passed）

---

## English Summary

### 1. Candidate Comparison & Boundary Audit (`nanobot` vs `langbot`)
- **`nanobot` (`REFERENCE_ONLY`)**: Couples Feishu card formatting with first-user auto-pairing, in-memory streaming loops, and direct SDK send invocations, which conflict with OpenBot's local-confirmation pairing (`OB-048`) and single-owner durable Outbox (`OB-021`/`OB-051`).
- **`langbot` (`REFERENCE_ONLY`)**: Tightly couples card serialization with its internal channel bus and agent loop.

### 2. Audited Decision: `NO_COPY`
- **Decision**: `NO_COPY` (recorded in `components/source-reuse/feishu.json`; `components/source-reuse-ledger.json` remains `entries: []`).
- **Rationale**: OpenBot's task, redacted approval preview (`REQUIRE_LOCAL` when sensitive impact cannot be safely previewed), and result receipt cards are implemented directly as pure, side-effect-free JSON constructors in `services/feishu_gateway/src/openbot_feishu/cards.py`. Extraction-specific diff/NOTICE verification is marked `NOT_APPLICABLE`.

### 3. Reproducible Command
- `PYTHONPATH=services/core/src .venv-m1/bin/python -m pytest tests/unit/test_source_reuse_feishu.py -q` (`1 passed`)
