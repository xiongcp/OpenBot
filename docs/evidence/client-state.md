# 配置与运行记录基础 / Settings and Run Record Foundation

关联 / Related: OB-008/075/081 · 2026-11-05 · Darwin arm64, Python 3.12

新增 ClientState，使用现有 Writer、events 和 checkpoint，保持 23 表与 migration 不变。
配置预览只读；应用必须确认并匹配 canonical hash/expected revision，owner 撤销后拒绝访问。
权限字段变化与新 policy revision 同事务提交，使旧授权无法保持旧权限。
run 保留开始时配置版本；事件只允许有限字段并在持久化前脱敏，父事件必须属于同 run。
读取图和重放不会派发工具。

Added ClientState on the existing Writer/events/checkpoint with no migration or new dependency.
Preview is read-only; apply requires confirmation, canonical hash and revision CAS. Revoked owners
cannot read or mutate. Permission changes atomically advance policy revision. Runs pin their start
configuration. Bounded, allowlisted events are redacted before persistence and parents remain in-run.
Graph queries and replay never dispatch tools.

验证 / Validation:

```sh
.venv/bin/python -m pytest tests/integration/test_client_state.py -q
.venv/bin/python -m ruff check services/core/src/openbot/application/client_state.py tests/integration/test_client_state.py
.venv/bin/python -m mypy services/core/src/openbot/application/client_state.py
.venv-m1/bin/python scripts/verify.py --phase M1 --output-dir /tmp/openbot-client-verification --run-id client-state-20261105
```

RED：10 项缺少实现失败，补充边界测试后观察到 3 项错误类型/起始事件失败。
GREEN：14 passed；lint、format、types、完整验证 8 项通过。/ Initial RED: ten missing-service
failures and three additional boundary/root-event failures. GREEN: 14 targeted passes and all eight full checks passed.

这是持久基础，不代表真实 Agent/MCP 编排、完整热更新派发、Tauri 或飞书业务闭环已验收。
This foundation does not qualify the real agent/MCP loop, dispatch-time activation, Tauri or Feishu workflow.
