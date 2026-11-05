# 残余风险与外部环境阻塞登记表 / Residual Risk & External Blocker Register (OB-080)

## 中文说明

| 风险 / 阻塞 ID | 关联任务 | 描述与影响边界 | 处置状态与最小解除条件 |
|---|---|---|---|
| `BLK-FEISHU-MOBILE-HUMAN` | `OB-047`、`OB-056` | 已完成真实飞书服务端鉴权、CardKit 2.0（含 `code=300317` 序列校验）与 `wss://msg-frontier.feishu.cn` `101` 握手实测；尚缺真人手机客户端点击卡片的实时交互以及 `tenant:tenant:readonly` 可选权限（`code=99991672`） | `OB-047` 已推进至 `IN_PROGRESS`；真人手机点击联调时可进一步闭环 |
| `BLK-NATIVE-WIN-LINUX` | `OB-005`、`OB-070`、`OB-071`、`OB-072` | 当前机器为 `Darwin arm64`，缺少原生 Windows 11（Win32 Job Object、WinVaultKeyring）与原生 Linux（cgroup v2、SecretService）物理/CI 机器 | 保持 `BLOCKED`/`IN_PROGRESS`；接入原生 Windows 与 Linux runner 后执行对应平台门禁 |
| `RSK-POSIX-PGID-ESCAPE` | `OB-042`、`OB-093` | POSIX 进程组（`setpgid`/`killpg`）无法阻止调 `setsid()` 的双 fork 子进程逃逸 | 高风险不受信任执行必须启用容器沙箱后端并按容器 ID 独立回收 |
| `RSK-REGEX-REDACTION` | `OB-039`、`OB-075` | 正则与精确 canary 脱敏不能保证识别 100% 非结构化隐私文本 | 以数据分级（`SECRET`/`SENSITIVE`）和 `EgressGuard` 作为主防线，敏感审批强制 `REQUIRE_LOCAL` |

---

## English Summary

| Risk / Blocker ID | Tasks | Impact & Boundary | Status & Minimum Unblock Condition |
|---|---|---|---|
| `BLK-FEISHU-MOBILE-HUMAN` | `OB-047`, `OB-056` | Live Feishu API, CardKit 2.0 (`code=300317` sequence check), and `wss://msg-frontier.feishu.cn` `101` handshake verified; only live human mobile button tap and optional `tenant:tenant:readonly` scope (`code=99991672`) remain | `OB-047` advanced to `IN_PROGRESS`; complete live human mobile click when operator is online |
| `BLK-NATIVE-WIN-LINUX` | `OB-005`, `OB-070`, `OB-071`, `OB-072` | Current host is `Darwin arm64`; native Windows 11 and Linux hardware/runners are absent | Keep `BLOCKED`/`IN_PROGRESS` until native Windows and Linux runners execute the platform gates |
| `RSK-POSIX-PGID-ESCAPE` | `OB-042`, `OB-093` | POSIX process groups cannot prevent `setsid()` double-fork escapes | Require container sandbox backend and container-ID tracking for untrusted execution |
| `RSK-REGEX-REDACTION` | `OB-039`, `OB-075` | Regex and canary redaction cannot guarantee 100% detection of unstructured private text | Enforce `EgressGuard` data classification and `REQUIRE_LOCAL` approval previews as primary controls |
