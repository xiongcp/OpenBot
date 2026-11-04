# 用户级 Daemon 安装、自启与卸载指南 / User-Session Daemon Installation & Uninstall Guide (OB-068)

## 中文说明
1. **安装与自启**：通过 `UserDaemonInstaller.install(os_name=..., scope='user_session', spawn_from_tauri_ui=False)` 生成用户级服务描述文件。
2. **UI 与常驻分离**：关闭桌面 Tauri 窗口不会停止常驻 daemon，Tauri 也不得自行拉起第二个 daemon。
3. **安全卸载**：`UserDaemonInstaller.uninstall()` 仅清理服务描述文件，完整保留用户工作区代码与数据。

## English Summary
1. **Install & Autostart**: `UserDaemonInstaller.install(os_name=..., scope='user_session', spawn_from_tauri_ui=False)` writes the user-session service manifest.
2. **UI Decoupling**: Closing the Tauri window leaves the resident daemon running, and Tauri never spawns a second daemon.
3. **Safe Uninstall**: `UserDaemonInstaller.uninstall()` removes only the service manifest while preserving the user workspace.
