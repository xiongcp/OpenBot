# 未提供的真实验收环境

本轮仅使用当前 Darwin arm64、本地合成 SQLite/HTTP、固定镜像的 Docker Desktop 测试。没有使用真实模型 key、飞书个人会话或未授权账号；未扫描用户秘密目录来寻找凭据。以下描述“本次任务未提供可用验收环境”，不声称用户机器上不存在相应账号或服务。

| 任务 | 当前缺失的最小验收条件 | 工程依赖 |
|---|---|---|
| OB-005 | 原生 Windows x64、Linux x64 物理实机完整组件准入记录 | GitHub Actions 三平台 contracts 工作流已实测通过；跨平台组件锁仍仅绑定 Darwin arm64 |
| OB-047 | 飞书交互卡片手机/客户端真人点击回调与长时重连观察 | 真实租户 API、CardKit 2.0 序列校验与 WebSocket 101 握手已实测通过 |
| OB-070 | 原生 Windows x64 机器、用户会话、Job/路径/凭据测试条件 | WSL 或 CI 最小合同检查不能替代原生 Windows M3 门禁 |
| OB-071 | 选定 Linux x64 发行版及 systemd user/cgroup/专用容器后端条件 | Mac 的 Linux arm64 VM 或 CI 合同检查不能替代原生 Linux M3 门禁 |

历史说明：本文档初版记录于 M0/M1 检查点（`ad013ea`）；当前 M1—M3 核心控制面、两次短事务 `claim/dispatch`、恢复/取消/预算、本地认证 HTTP API 与 `openbot` CLI 均已实现并完成本机验证。缺失原生环境或本地模型权重的门禁单独标记为 `BLOCKED_ENV` / `BLOCKED_CREDENTIALS`，不伪造为已通过。

## English Summary

This record documents external verification environments not available on the current Darwin arm64 development host (native Windows x64 and Linux x64 machines for `OB-005`/`OB-070`/`OB-071`, and a dedicated Feishu test tenant/app for `OB-047`). Missing external environments block only their specific real-environment acceptance gates; local M1/M2/M3 engineering tasks continue along the DAG without fabricating credentials or real-service logs.
