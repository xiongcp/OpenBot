# OB-011 / OB-012：正式存储实施边界

状态：接受；日期：2026-11-04。

正式 schema 保持原 23 表；`db/migrations/0001_baseline.sql` 是设计基线的逐字副本，manifest 保存 SHA-256。旧 `db/001_baseline.sql`、OpenAPI 与状态机不修改。无版本的既有库、未来版本、版本空洞、checksum 漂移均拒绝自动迁移，尤其不覆盖未知 11 表旧库；实际遇到它时需显式映射 ADR / migration。

标准库 sqlite3，连接显式 LEGACY_TRANSACTION_CONTROL + isolation_level=None，应用用 BEGIN IMMEDIATE 管理短事务；WAL / FULL / foreign_keys / recursive_triggers 每连接设置并读回。已存在数据库先以只读方式检查版本，兼容后才取得 writer。迁移前为既有已版本化库生成不可覆盖的 SQLite backup。

不在已开启事务中调用 executescript；按 sqlite3.complete_statement 拆分受审迁移（含 trigger），逐 statement execute，使 schema 与 migration checksum 同一提交。迁移执行期间 authorizer 拒绝事务控制、PRAGMA、ATTACH / DETACH / SAVEPOINT，避免未来有误的迁移提前提交。全部失败回滚并保留旧版本与备份。

OB-012 的单 writer 将是唯一连接持有者；命令携带 request_id、总 deadline、用途类别和完整事务，caller 停止等待不能取消已进入提交的命令。批准/取消/结果/入站拥有独立配额；轮转避免普通命令无限饥饿。事务结果通过既有权威记录核对，不新增第二业务账本。

这些本地存储行为不依赖缺失 Docker，可独立实现和测试；没有通过 OB-093 / OB-029 前仍不开放工具执行。正式 daemon 的跨进程锁与完整 profile 路径归属分别由 OB-015 / OB-032 验证，不能据临时库测试宣称它们已实现。
