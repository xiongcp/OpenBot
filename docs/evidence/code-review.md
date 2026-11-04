# 本轮代码审查范围与处置

采用只读独立审查与可重复反例，不把独立分支测试当作合并结果。仓库原始设计全部未跟踪且无 commit，本轮没有制造基线提交；审查按实际文件和初始 hash 清单进行。

| 审查范围 | 重要问题 | 处置 |
|---|---|---|
| 标准合同 | ref/anchor 编码环、数据位置引用目标、UTF-16/数值域、可变 canonical 构造 | 先 RED 后修复，固定合同测试覆盖 |
| 协议 PoC | 参数漂移、旧 runtime/时钟证据、CONSUMED replace/delete、UNKNOWN 换 ID | 先反例，再修复测试协议模型；仍不作生产 Broker |
| Storage | 致命异常 Future、no-op FK 损坏、commit/rollback 双 I/O、真实进程退出缺口 | 故障注入与 os._exit 测试覆盖 |
| SDK/状态边界 | 非法 usage、通用取消终态、跨 Task request_id、隐藏 schema ref | 修复并在当前完整测试重验 |
| 新增提案/审批 | canonical Operation ID 与 SQL 主键漂移 | 独立审查复现；新增失败回归后修复 |
| 新增自查 | nonce 出现在第三方异常链、request_id 跨设备读回、文件探针放开整个工作区 | 各有 RED/GREEN 与完整回归 |

独立审批审查在修复前实际跑 33 项审批/迁移测试，没有声称评审 API、持久 challenge、预览、claim/dispatch/recovery。上述明示待实现范围也未被其他审查认证。修复后由 Integrator 运行当前完整 M0/M1 套件；单测、合成服务与本机容器证据分别保留。
