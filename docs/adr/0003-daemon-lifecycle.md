# OB-003：常驻生命周期与锁归属

状态：接受；首测 Darwin arm64。进程原语 PoC 为 Python 标准库 flock；未采用 Rust 候选、command-group 或用户服务安装器。OB-093 决定正式后端；初测 socket 缺失已由后续可连接 Engine 的证据更新，见 ADR-0007 与 backend-capabilities。

唯一 profile 锁拥有者是 supervisor。daemon 收到受保护启动通道与 runtime_epoch，不再获取同一把排他锁；独立启动必须先成为 supervisor 并取得锁，不能绕过。锁描述符不交给 UI/daemon；健康检查仅查询受认证端口。新 runtime 必须确认旧执行域已隔离，不能只根据租约过期接管。

| 事件 | supervisor / 锁 | daemon / worker / gateway | 用户结果 |
|---|---|---|---|
| 关闭 Tauri / CLI 断开 | 保持 | 常驻继续，客户端凭据仅连接用途 | 不隐式 stop |
| 显式 stop | 停止新 dispatch，drain 后释放 | 回收登记 worker 与容器，持久化 UNKNOWN，再关闭 writer | 已发生效果不声称回滚 |
| ephemeral CLI 结束 | 显式开发模式生命周期结束 | 排空并关闭其专用 runtime | 不与常驻 profile 混用 |
| daemon 崩溃 | 保持锁并监督重启 | 新 epoch；旧 worker 先核对、隔离 | UNKNOWN 资源不再派发 |
| supervisor 强杀 | OS 释放仅它持有的锁 | 子孙和容器不由 flock 保证终止 | 无回收证据禁止接管 |
| worker 崩溃 | 保持 | 独立判定回执；无回执 UNKNOWN | 进入核对 |
| gateway 崩溃 | 保持 | 外部 watchdog 确认旧实例终止再建 | 不同时启动两个 gateway |
| 用户登出 / OS 重启 | 用户服务依平台退出 | 断连接不假设可保持登录会话 | 下次启动重新核对 |
| 休眠 / 恢复 | OS 事实另测 | UTC/单调钟/授权与出口重验 | 不承诺远程唤醒 |

`tests/components/native_poc/test_profile_lock.py` 验证双实例竞争、客户端结束不释放 owner 锁、强杀 owner 后锁可再获取。该受控进程测试不证明 UI 已实现、任意子孙回收、容器停止、用户登出或真实睡眠行为；后者属于 OB-093 和各 OS 门禁。EOF、Drop、进程组均不是通用强杀保证。
