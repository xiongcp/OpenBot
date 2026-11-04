# 内部提案存储合同（ADR-0008）

HTTP/模型 DTO 不变；完整内部 ToolProposal 遵循 tool-proposal.schema.json。服务器先生成不含 binding_hash 的标准 JCS 字节，计算 SHA-256，再附加摘要并将完整 canonical JSON 写 operations.proposal_canonical_json。加载时验证规范字节、完整 schema、重算不含自身的摘要，并比对 operations/approvals 的索引投影。SQL 的 digest 为 64 位小写 hex，JSON 的 Hash 使用 `sha256:` 前缀；policy `policy-N` 映射 SQL 正整数 N。转换失败拒绝。

提案创建不派发。审批内部 SQL version 0 对应 API version 1；每次决定同时递增 Operation 和 Approval 版本，更新 Task 状态并追加脱敏 event/outbox。普通事件不包含原 nonce、完整提案或 args。旧 schema v1 的无 canonical 字节行不得被自动授权，须显式废止并创建新 Operation。

challenge port 必须支持按 approval_id 保存/读取/删除原 nonce，并由受保护存储提供。内存夹具只作测试；本机真实 keyring 后端通过资格前不宣称重启可恢复 challenge。挑战不可读时不接受 callback 携带的 nonce作为替代权威。
