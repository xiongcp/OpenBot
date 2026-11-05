# Bounded agent runtime / 有界 Agent 运行（OB-025/062—066/075）

The runtime connects the existing Writer, budgets, skills, model port, OperationService, owner approval, claim/dispatch and ArtifactStore. UI and channels do not execute tools. One durable run is pinned to each Task, with at most one active run. Restart/replay does not issue model or tool requests.

真实核心编排已连接；集成回归中的模型与工具是明确标注的合成适配器，不能代替真实模型、容器与原生 UI 验收。真实只读容器证据见 `mcp-demo-container.md`；用户模型完整工作流在 daemon 组合后验证。

RED: four missing-runtime failures, then approval preview contract, unknown timestamp/reason constraints failed before correction. GREEN targeted: seven runtime integration cases, including actual core approval consumption, verified scoped artifact, cancellation while model returns, live OFFLINE restriction, denial, missing isolation, UNKNOWN and persisted-run refusal. Actual SDK loopback: seven cases validate streaming, single request, no redirect/retry and generic secret-free errors. Existing provider tests exercise incomplete/malformed streamed tool arguments before proposal.

No model endpoint, API credential, raw callback, hidden reasoning or arbitrary tool configuration is persisted. The built-in skill is project-owned; no third-party source was copied. The MCP tool remains limited to dedicated synthetic `demo.txt`, requires native file guards and verified isolation, and has no host fallback. Windows execution is unqualified and fails closed; the portable control-plane regressions still run there.

配置收紧在每次新模型请求和派发前复验；SDK 与应用均不隐式重试。超时或回执不明保持 UNKNOWN/RECONCILING；审批不复活，持有资源等待核对。金额无可靠价格来源时显示不可用。

Full verification / 完整验证: `.venv-m1/bin/python scripts/verify.py --phase M1 --output-dir /tmp/openbot-client-verification --run-id agent-runtime-20261105`: all eight checks passed; 383 passed, 2 explicitly gated native-container skips. Logs remain outside the repository.

Durable observation regression / 持久记录观察回归: a later full suite exposed a test race between the SUCCEEDED task transaction and its subsequent RUN_FINISHED trace transaction. The test now waits for RUN_FINISHED before checking both facts; no assertions were removed. RED: full suite observed the missing trace event. GREEN: seven targeted tests and full suite 396 passed / 2 explicit native skips, eight checks passed.

## Tool continuation live gate / 工具结果续接真实门禁

A real user-authorized model test exposed flattened tool history: after verified reads the model kept proposing the same read until the bounded step limit interrupted it. Three failing regressions demonstrated lost typed provenance and unmatched-result acceptance. The adapter now retains assistant/tool roles and rejects invalid history; the bounded demo refuses a repeated completed read.

真实模型测试发现工具结果被压平成普通文字，模型重复提议读取。已补三项失败回归并修复角色与 call_id 关联；专用 demo 不会再次派发已完成读取。旧中断 Task 保留，测试通过正常取消后创建新 Task，未重放原 run。

GREEN: `pytest tests/unit/test_openai_compatible_adapter.py tests/integration/test_agent_runtime.py -q`: 13 passed. Full verification `tool-history-20261105`: 399 passed / 2 explicit native skips; all eight checks passed.

Live: `tsk_80323749dd19954d4502559814540c5a` reached SUCCEEDED with 12 factual trace events. Two actual gpt-5.5 SSE requests surrounded exactly one pinned Docker MCP read and owner decision; scoped output artifact and file hash verified. Approval remains CONSUMED. The synthetic result contains both Chinese and English. No outbound Feishu messages were sent. Local model endpoint/key are omitted from evidence and remain daemon memory only.
