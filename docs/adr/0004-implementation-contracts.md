# 合同、依赖与实施账本

状态：接受；日期：2026-11-04；关联 OB-004—010、OB-089—093。

公共协议保持 1.1，不因设计包 1.2 改号。既有合同的 Id 是带类型前缀的字符串，不能擅自改 UUID；新增内部入站合同可使用 UUID 并显式检查格式。所有 JSON 入口先拒重复键、非有限数、非法 Unicode、超限字节/深度，再以本地受审 Registry 执行 Draft 2020-12；禁止远程/未知 ref 和未经检查的 format。Pydantic 仅做边界 DTO；domain 采用标准库不可变 canonical bytes，不导入 SDK。

JCS 使用 Trail of Bits rfc8785；binding_hash 以外的既有提案字段全部进入摘要。固化后的原始 bytes 是授权权威；对外提供拷贝。拒绝不支持的数值，不使用 sort_keys 模拟 JCS。只有 Python 一个权威实现，跨语言比较为 NOT_APPLICABLE。

本产品输入数值限定为有限 binary64 且绝对值不超过 2^53−1，整数、小数和指数记法一致。RFC 可表示但超出本产品范围的大浮点数明确拒绝，避免 canonical 变成整数文本后无法重新读取。Schema 验证只用于受审查的本地合同；字节/深度/引用环限制不证明任意不可信 Schema 的验证耗时有界，MCP 动态 Schema 仍需 OB-063/064 受限执行门禁。

M0 core 仅引入 rfc8785、Pydantic v2、jsonschema/referencing，dev 仅 pytest、ruff、mypy。M1 才引入必要 HTTP / SDK，M2 飞书及 M3 Browser/MCP 均不提前安装。准确版本与发行物摘要以 uv.lock 和资格记录为准；候选目录保持 NOT_RUN，除非对应全部资格通过。后续版本/配置/资产变化使相关资格失效。

所有设计任务依赖 ID 保持不变。缺真实平台的验收任务保持 BLOCKED，可实现其不依赖缺失能力的本地部分，证据逐条区分实现完成和整项验收；不能沿未完成门禁授予生产能力。M0 测试模型与生产迁移/调度严格分开。数据库基线 checksum 固定，增加迁移须独立记录，不改旧基线以迎合实现。
