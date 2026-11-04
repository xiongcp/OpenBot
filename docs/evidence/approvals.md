# OB-017 / OB-018：本地内部提案与审批决定子集

先读取两项 component_refs/reuse_type/reuse_notes：复用已通过本机标准向量的 rfc8785/jsonschema；SQLite 标准库经唯一 writer 使用。没有引入新 SDK、ORM、自动 runner 或第二账本。

实现：Operation 从本地 ACTIVE manifest、可信上下文、固定 TTL/nonce 和工具 args schema 构造；完整 JCS 字节保存到原 operations 表新增列，索引投影逐项复核。新增 migration 0002，原 0001/23 表设计基线未改。批准只使 Operation READY；本子集不创建 Attempt、不派发工具。审批状态、Task、脱敏 event/outbox 在同一事务提交；稳定 request_id 包含认证来源作用域。

实际命令：`PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/integration/storage -q --tb=short`，当前 49 passed，见 evidence/implementation/m1-storage-tests.log。完整验证命令为 `.venv/bin/python scripts/verify.py` 与 `.venv-m1/bin/python scripts/verify.py --phase M1`，各自真实退出码/日志 hash 位于 verification.json、m1-verification.json；容器需单独显式资格命令，验证脚本不继承启用容器的环境变量。

验证包含：并发互斥决定仅一个落盘；body actor、错设备、旧 identity/policy/resource、nonce/hash/version、取消、过期/倒退时钟/新控制进程均不能 READY；重复请求不再执行决定；外部 dict 修改不改权威字节；SQL 重绑定被拒绝；challenge 丢失撤销旧审批。原 nonce 与 args 不进入普通审计/outbox；schema 失败的标准 traceback 不包含原 nonce。

独立只读审查发现：canonical.operation_id 未与账本主键比对；在开启 FK 和保留触发器的异常记录下可使另一主键 READY。已先补 RED 反例再修复，并在全套中通过。自查另发现第三方 Schema ValidationError 的异常链会打印 nonce；公共 ContractError 现抑制该链。对应 RED 日志保留，合成 nonce 摘录已明确脱敏，不含真实凭据。

当前限制：仅 local/internal 用例，未接认证 API、飞书、安全 ApprovalPreview 或真实持久 challenge store。测试 challenge 为内存夹具；没有跨重启时间权威时敏感批准拒绝。普通 service 不提供 CONSUMED 复用/claim/dispatch/recovery；它们仍待 OB-015—020/031 等正式实现。未消费授权的撤销端口、完整受保护 challenge 生命周期和终态验证也待补齐。因此 OB-017/018 保持 IN_PROGRESS，不凭该子集关闭 OB-029。
