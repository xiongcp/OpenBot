# 用户级常驻服务打包配置说明 / User-Session Daemon Packaging (OB-068)

## 中文说明
- **用户会话边界**：macOS 采用 `~/Library/LaunchAgents`（`macos_launchd_user_agent`），Linux 采用 `~/.config/systemd/user`（`linux_systemd_user_unit`），Windows 采用当前登录用户计划任务（`windows_user_logon_task`）。
- **安全禁令**：严禁使用 `root` 或 `LocalSystem` 系统级高权限服务控制用户桌面；严禁 Tauri 窗口直接启动第二个 daemon；卸载服务仅移除服务配置，绝不删除用户工作区。

## English Summary
- **User-Session Boundary**: Uses `LaunchAgents` on macOS, `systemd --user` on Linux, and user-logon tasks on Windows (`scope='user_session'`).
- **Safety Invariants**: Forbids `root`/`LocalSystem` system services, forbids Tauri UI windows from spawning duplicate daemons, and preserves user workspaces on uninstall.
