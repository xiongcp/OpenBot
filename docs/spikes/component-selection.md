# 当前组件选择

OB-004：先使用标准库 SQLite、受限 Schema / JCS 与开发工具；官方 SDK 在 M1 做真实故障合同后再准入，Browser / MCP 在 M3。

OB-003：用首测 OS 的 flock 验证唯一 owner 和强杀释放，未据此推导整棵进程树清理。初测 socket 缺失已更新：Docker Desktop Engine 29.1.3 / linux arm64 与固定 Alpine digest 的 CLI 隔离原语通过；正式 Supervisor、旧执行域隔离及 python-on-whales 适配仍待实现和验证，不能据此授予运行能力。

未安装 command-group、service-manager、PyInstaller、AstrBot 或任何候选自治框架；没有源码摘取。路径守卫、隔离和供应链仍由各自任务真实验收。
