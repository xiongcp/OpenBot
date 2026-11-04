# M3 全 MVP 能力集回归与边界说明 / M3 Full MVP Capability Regression & Boundary Report (OB-067)

## 中文说明

### 1. 六大 MVP 子系统回归（`MvpCapabilityRegressionSuite`）
`services/core/src/openbot/application/mvp_regression.py` 与 `tests/integration/scenarios/mvp/test_mvp_capability_regression.py` 联合验证 M3 MVP 六大能力子系统（`security_critical_failures == 0`）：
1. `cloud_and_local_providers`：OpenAI 兼容云适配器（`OB-025`）与本地 Ollama 适配器（`OB-026`，校验模型权重哈希、无外网出口证明与零云回退）。
2. `feishu_controlled_gateway`：飞书安全配对、WebSocket 持久化后 ACK 入站、普通审批卡（`REQUIRE_LOCAL` 保护）、进度合并与 6 个故障场景（`OB-048`—`OB-056`）。
3. `workspace_aci_and_isolated_process`：工作区文件守卫、补丁冻结与回滚、受控进程与进程树监管回收（`OB-029`、`OB-032`—`OB-042`）。
4. `browser_structured_tools`：专用浏览器 profile 锁、网络与 Service Worker 策略、有界只读快照、写动作派发前复验与 5 类结果验证回归（`OB-057`—`OB-061`）。
5. `mcp_stdio_and_fault_guards`：固定版本 stdio MCP 协商、全量 JCS 元数据锁定、隔离执行与 6 类恶意/故障回归（`OB-062`—`OB-065`）。
6. `readonly_skills_loader`：只读技能指令加载与草稿隔离（`OB-066`）。

### 2. 诚实边界声明
- 未启用的 `REFERENCE_ONLY` / `DEFERRED` 组件绝不列为已启用能力（`reference_only_or_deferred_claimed_as_active = False`）。
- 单机（`Darwin-arm64`）受控回归通过不代替 Windows/Linux 原生机器实测或真实飞书生产租户验收（`claims_three_os_release_complete = False`）。

### 3. 可复现验证命令
- `PYTHONPATH=services/core/src:services/feishu_gateway/src .venv-m1/bin/python -m pytest tests/integration/scenarios/mvp/test_mvp_capability_regression.py -q`（1 passed）

---

## English Summary

### 1. Six MVP Subsystem Regressions (`MvpCapabilityRegressionSuite`)
`services/core/src/openbot/application/mvp_regression.py` and `tests/integration/scenarios/mvp/test_mvp_capability_regression.py` verify all 6 M3 MVP capability subsystems (`cloud_and_local_providers`, `feishu_controlled_gateway`, `workspace_aci_and_isolated_process`, `browser_structured_tools`, `mcp_stdio_and_fault_guards`, and `readonly_skills_loader`) with `security_critical_failures == 0`.

### 2. Honest Boundary
- `reference_only_or_deferred_claimed_as_active = False` and `claims_three_os_release_complete = False`: single-OS (`Darwin-arm64`) verification never substitutes for native Windows/Linux hardware or live Feishu tenant qualification.

### 3. Reproducible Command
- `PYTHONPATH=services/core/src:services/feishu_gateway/src .venv-m1/bin/python -m pytest tests/integration/scenarios/mvp/test_mvp_capability_regression.py -q` (`1 passed`)
