# OB-017 / OB-018：权威提案字节与审批决定

状态：接受；2026-11-04。范围是正式数据库中的提案和审批决定用例；不提供 claim、dispatch 或恢复执行入口。

既有 ToolProposal 合同冻结完整身份、工具、参数、资源、策略、期限与 nonce hash；binding_hash 不参与自身摘要。现有 operations 表仅有拆分列，无法在重启后无歧义保存完整权威 canonical bytes。选择在后续 migration 0002 为原表增加 proposal_canonical_json；不改 0001 与原设计 DDL，不新增第二账本。canonical UTF-8 字节为绑定权威，既有列是索引/约束投影，每次消费前逐项比对；发现漂移拒绝。旧行缺该字段时保持不可执行，不能补造历史批准。

提案只由认证边界传入的 InboundContext、本地 ACTIVE manifest、当前 profile/policy 和服务器生成 ID/nonce 构造；模型仅能提出 tool_name/args。canonical args 另用该 manifest 的本地受限 schema 验证。原 nonce 仅存在受保护 challenge port，不进入普通审计/outbox；challenge 丢失必须撤销旧授权，重新建 Operation。

审批决定使用既有 approval-decision 合同（对外 version 从 1 开始，SQL 内部从 0 开始，边界显式 +1/-1）。真实 actor/profile/session、绑定、nonce、TTL、当前 policy/identity、资源代次与取消在同一 writer 事务复验；PENDING CAS 最多一个决定。批准仅 READY；CONSUMED 永不复活。稳定 request_id 只关联已有 append-only event 的脱敏 receipt，不重复执行决定。

当前调用面仅为内部应用服务。未接本地认证 API、渠道预览和数据过滤，不对外开放 challenge/decision；测试使用合成数据。敏感内容预览与持久 challenge store 需要 OB-038/039/081；缺失时相应能力不可用。后续 claim 仍必须经正式策略、资源/epoch 和两次短事务。无此能力不能以审批成功启动执行。

其他方案：从当前可变 profile/manifest 重拼历史 binding 会使重启语义漂移；把完整提案存普通 events 会复制敏感参数到审计；二者均不采用。仅增加权威列与不变触发器，保持 23 张核心表。

迁移实测补充：SQLite 在 ALTER TABLE ADD COLUMN 内部调用 `quick_check(table)`，旧 authorizer 全拒 PRAGMA 会阻断合法升级。仅当当前单条语句是未加引号的受审查 ALTER TABLE ADD COLUMN 时，允许 main 中同表的只读内部 quick_check；显式 PRAGMA（包括 quick_check）仍拒绝，事务/ATTACH/SAVEPOINT 限制不变。实际跟踪已确认动作参数为 quick_check / operations / main；不全局放开 PRAGMA。
