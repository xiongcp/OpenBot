# 未提供的真实验收环境

本轮仅使用当前 Darwin arm64、本地合成 SQLite/HTTP、固定镜像的 Docker Desktop 测试。没有使用真实模型 key、飞书个人会话或未授权账号；未扫描用户秘密目录来寻找凭据。以下描述“本次任务未提供可用验收环境”，不声称用户机器上不存在相应账号或服务。

| 任务 | 当前缺失的最小验收条件 | 工程依赖 |
|---|---|---|
| OB-005 | Windows x64、Linux x64 实际安装/版本/最小测试结果 | 已有三 OS CI 配置，尚未在远程执行 |
| OB-047 | 专用飞书自建测试应用/租户、最小权限、受保护凭据注入与获准合成收件范围 | lark SDK 未安装/资格未开始；M1 仍未完成 |
| OB-070 | 原生 Windows x64 机器、用户会话、Job/路径/凭据测试条件 | OB-032/042/068 尚未实现；WSL 不能替代 |
| OB-071 | 选定 Linux x64 发行版及 systemd user/cgroup/专用容器后端条件 | OB-032/042/068 尚未实现；Mac 的 Linux arm64 VM 不能替代 |

真实模型质量、第二 Provider/本地模型资产与出口、Browser/MCP 资产、长期浸泡与 M3 发行供应链均未验证。不能只凭缺环境就把全部工程 TODO 改为完成或环境阻塞；M1 正式策略、Supervisor、claim/dispatch、recovery、取消、预算、文件/Artifact、本地认证 API 与 CLI 是明确未完成实现。

后续继续顺序：补 OB-093 的 Supervisor/旧执行域失效证据及 OB-014 终态门禁，推进 OB-015/016 与 OB-017/018/031 的正式集成，接两次短事务 claim/dispatch、恢复/取消/预算，再做 OB-029。M2/M3 只能在各自上游和真实门禁满足后验收；不将当前本地原型宣称为 MVP。

## English Summary

This record documents external verification environments not available on the current Darwin arm64 development host (native Windows x64 and Linux x64 machines for `OB-005`/`OB-070`/`OB-071`, and a dedicated Feishu test tenant/app for `OB-047`). Missing external environments block only their specific real-environment acceptance gates; local M1/M2/M3 engineering tasks continue along the DAG without fabricating credentials or real-service logs.
