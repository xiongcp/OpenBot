# OB-095：浏览器 DOM 提取脚本最小源码复用审查与 NO_COPY 决策记录 / Browser DOM Extractor Source-Reuse Audit & NO_COPY Decision

## 中文说明

### 1. 候选方案对比（`browser-use` DOM 脚本 vs OpenBot 自有最小提取器）
- **`browser-use`（`REFERENCE_ONLY`）**：
  - 上游 DOM 脚本将元素高亮注入、跨 frame 索引缓存与 `Agent.run()` 自治多步执行循环耦合；且整段 JS 体积大、修改了宿主页面 DOM 树样式。
  - 按 OpenBot 架构不变量，任何网页文本与属性均属 `TAINTED_EXTERNAL`，元素引用必须绑定 `(page_id, frame_id, snapshot_revision, origin)`，且每次写动作必须单独经过 Broker 审批并在 `DISPATCHING` 前复验 revision（严禁 `Agent.run()` 批量自治越权）。
- **OpenBot 自有最小只读提取器（`services/core/src/openbot/tools/browser/read.py`）**：
  - 仅提取有界节点数量与字符长度的只读快照，不向页面注入高亮样式或触发额外网络请求，天然携带 `page_id`、`frame_id`、`snapshot_revision`、`final_origin` 与 `provenance_kind='TAINTED_EXTERNAL'`。

### 2. 审查结论：`NO_COPY`
- **正式决定**：`NO_COPY`（记录于 `components/source-reuse/browser-dom.json`，`autonomous_agent_run_permitted = false`，`extraction_verification = 'NOT_APPLICABLE'`）。

### 3. 可复现验证命令
- `PYTHONPATH=services/core/src .venv-m1/bin/python -m pytest tests/unit/test_source_reuse_browser_dom.py -q`（1 passed）

---

## English Summary

### 1. Candidate Comparison (`browser-use` vs OpenBot Native Extractor)
- **`browser-use` (`REFERENCE_ONLY`)**: Couples DOM tree traversal with in-page highlight mutations and autonomous `Agent.run()` multi-action loops.
- **OpenBot Native Read-Only Extractor (`services/core/src/openbot/tools/browser/read.py`)**: Extracts bounded, side-effect-free snapshots bound to `(page_id, frame_id, snapshot_revision, final_origin)` with `provenance_kind='TAINTED_EXTERNAL'`.

### 2. Audited Decision: `NO_COPY`
- **Decision**: `NO_COPY` (`components/source-reuse/browser-dom.json`, `autonomous_agent_run_permitted = false`, `extraction_verification = 'NOT_APPLICABLE'`).

### 3. Reproducible Command
- `PYTHONPATH=services/core/src .venv-m1/bin/python -m pytest tests/unit/test_source_reuse_browser_dom.py -q` (`1 passed`)
