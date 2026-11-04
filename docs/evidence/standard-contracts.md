# OB-006 / OB-007 / OB-008 / OB-009 / OB-090 标准合同

运行：`PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/contracts tests/unit -q`；版本和发行物 hash 见 components/admissions/m0.json。

JCS 预期字符串独立来自 [RFC8785 3.2.2—3.2.3](https://www.rfc-editor.org/rfc/rfc8785.html)，覆盖负零、指数、小数舍入、嵌套、UTF-16 非 BMP/BMP 顺序与 safe-int 边界；空对象 SHA-256 为固定已知值。Python 为唯一权威实现；第二实现比较 NOT_APPLICABLE。产品数值域比 RFC 全部 binary64 更窄，见 ADR 0004；不支持的值在入口拒绝，canonical→value 闭合。

完整 Draft 2020-12 验证既有所有正反例，同时测试 allOf、本地 ref、unknown extra、UUID/date-time 格式、重复 JSON 键、非法 Unicode、超限深度/字节、未知与远程 ref、anchor / percent-encoded ref 引用环。registry 只接受已审查本地 schema，未将普通属性名或 const 中的 `$ref` 当 schema。Pydantic 严格 DTO 拒权威字段和类型强转；批准内容保存 canonical bytes，外部嵌套修改与可变 bytearray 构造均不能改变权威内容。

未注册引用在调用验证前拒绝，测试同时以 Python socket DNS/connect canary 检查。该观察范围不覆盖原生扩展、子进程或 OS 全部出口；当前验证器没有网络 retriever，不代表任意插件具备网络隔离。无环复杂 schema 的验证成本仍需人工审查，MCP 不可信 schema 的执行时限属于后续门禁。

模型仅生成 tool_name / args，由本地 Manifest 再校验；两个 fake Provider 和独立 fake executor 共用同一值对象，不给 provider 自动执行权限。事件身份/接收时间由 TrustedSource 接入上下文提供，入站 body 不能赋权。持久事件 seq 来自未来数据库 writer，事件回放没有工具执行入口。

CONNECTED / LOCAL_MODEL / OFFLINE 为独立版本配置；不允许 cloud fallback、SDK 重试叠加、宿主执行、运行期下载。没有真实本地推理 / runner / 出口证据时连接工厂返回 CAPABILITY_UNAVAILABLE；loopback 地址不作证明。UTC/monotonic/boot 变化测试使旧敏感 TTL 失效；派发后 timeout/cancel 映射 UNKNOWN，未把所有异常设为 retryable。

## English Summary

Command: `PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/contracts tests/unit -q`. Verifies OB-006/007/008/009/090 standard contracts: RFC 8785 JCS canonicalization (UTF-16 key ordering, safe integers, duplicate-key rejection), full JSON Schema Draft 2020-12 validation with local-only `$ref` registry and zero network retrieval, strict immutable Pydantic DTOs, `CONNECTED`/`LOCAL_MODEL`/`OFFLINE` configuration guards, and `ClockSnapshot` TTL verification.
