# ADR-0009: Versioned client control and factual run records / 客户端控制与事实运行记录

Status / 状态: Accepted for implementation after user design approval, 2026-11-05.

Use `events` aggregates `ClientSettings` and `AgentRun` and `tasks.checkpoint_json` for additive client state. No DDL or existing public event envelope is changed. The new client contract is independent of the original runtime-event schema, with its own version.

配置快照只含模型名、模式、步数上限、Skill/MCP 开关和语言，不含 endpoint、密钥或任意可执行配置。endpoint、工作区和已准入组件由可信 CLI 启动上下文决定。客户端只引用内存凭据的配置状态。

Settings preview is read-only and binds expected revision plus canonical candidate hash. Apply revalidates owner and CAS inside the single writer transaction; changing mode increments the authoritative policy revision so old grants cannot silently survive. Invalid config changes nothing. New runs pin the current settings; effective permission is the intersection with current restrictions before every request/dispatch.

run_id is persisted once in the accepted Task checkpoint. Resume/recovery retain it. Terminal reruns create a new Task/run. Trace parent IDs must already exist in the same run; UI replay and cursor recovery are read-only. Persist only allowlisted, bounded, pre-redacted DTO data. No hidden reasoning, raw callbacks or secrets.

运行事件与权威 Task/Operation/Attempt 关联，图展示实际事实。Skill 内容需核验 hash；模型仅生成提案；审批、claim、DISPATCHING 和结果核对复用核心服务。进程中断后的未完成运行进入待核对，不重新调用工具。

Tauri attaches to an existing daemon. Only fixed Rust commands can access control credentials; remote content is inert text. Window closure never changes daemon lifetime. No arbitrary network, shell or filesystem command is exposed to WebView.

Compatibility / 兼容: existing 23-table schema and original 14-operation contract remain unchanged; new client routes and schemas are additive. Native/signing/real-service qualification stays independent.
