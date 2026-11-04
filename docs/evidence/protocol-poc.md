# OB-091 协议验收

命令：`.venv/bin/python scripts/run_protocol_poc.py`；完整行为测试：`PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/protocol -q`。

固定 seed 7；平台 Darwin arm64，Python 3.12.12；SQLite 版本及逐场景 task/operation/approval/attempt/event/outbox、provider key、quarantine 和实际 marker 数量见 evidence/implementation/protocol-poc.json。

八个崩溃点分别覆盖 claim 前、claim 提交前后、第二事务 DISPATCHING 提交前后、marker 成功后本地确认前、结果提交前后。另有三个子进程 `os._exit(78)` 窗口，退出后重新打开 SQLite 验证；这不等于物理断电测试。调用方停止等待的测试让真正 writer 线程继续提交，再通过稳定 Operation 查询 APPROVED/READY，未把取消等待误作回滚。

断言：审批只使 READY；首次 claim 消费一次授权；CONSUMED 的复活由数据库触发器拒绝；同 Operation 新 Attempt 使用新 dispatch_id、provider key 不变；同 Attempt 的 marker 交付重传只有一次实际模拟效果；派发前取消、policy/identity/resource/epoch/expiry 变化效果数为 0。DISPATCHING 后不确定即 UNKNOWN/RECONCILING 和资源 quarantine，换 task/operation 也不能绕过；只有独立 marker 账本匹配 receipt 后才可确认成功。

状态、审计与 outbox 同短事务；fake 外部执行不在 SQLite 事务内。FakeChannel 的同 scope 事件重放 100 次只返回同一 Task。FakeOutbox 仅为离线输出夹具，无真实消息外发。

正式 23 表 DDL、状态机文件和 14 API 没有变化。此模型仅在 tests/protocol，不能用于生产调度；未验证真实容器、网络隔离、模型、飞书或三平台，不能关闭 OB-029。
