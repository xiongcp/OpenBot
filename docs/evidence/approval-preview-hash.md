# Approval preview binding / 审批预览绑定

OB-081: the preview returned a bare digest although the decision contract requires `sha256:<digest>`. A client using the preview could not approve; the lifecycle regression now asserts preview/proposal equality. Fix only restores the public hash format.

审批预览遗漏 `sha256:` 前缀，客户端据此批准会被合同拒绝；新增生命周期断言先失败，再修正公共格式。未改变批准、claim 或派发语义。

RED: local API lifecycle failed on preview/proposal hash equality. GREEN: local API lifecycle passed; related approval and dispatch regressions are recorded in this commit's validation.

Related validation: `pytest tests/contracts/local_api tests/integration/storage/test_approvals.py tests/integration/storage/test_dispatch.py -q`: 28 passed. Ruff passed. / 相关回归 28 项通过。
