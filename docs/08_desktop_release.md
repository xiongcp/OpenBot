# 桌面产品与跨平台交付

v1.2采用分平台监督与安装适配。service-manager仅在已验证支持的launchd/systemd用户级路径使用；它的Windows服务后端不能直接证明登录用户会话能力。Windows启动、注销、会话切换与GUI范围单独验收，不能改用LocalSystem逃避验证。[R13]

进程组、管道EOF、Drop和Job Object分别记录覆盖范围。command-group已弃用，process-wrap/processkit是待资格验证候选；supervisor强杀、Unix逃逸与容器独立生命周期必须有明确限制和恢复流程，不宣称100%整树清理。[R12][R14]

打包先验证PyInstaller onedir，保留调试和非Python资产可见性；不因复用库而承诺固定体积或冷启动耗时。发布清单与SBOM至少覆盖Python、Rust、前端、浏览器、grammar、容器与摘取代码；CycloneDX与SPDX按实际工具输出区分。[R17]

## 平台能力矩阵

| 能力 | macOS | Windows | Linux | 发布条件 |
|---|---|---|---|---|
| CLI、状态机、SQLite、飞书 | 目标支持 | 目标支持 | 目标支持 | 原生CI加真实主流程 |
| 文件ACI与patch | 路径/权限适配 | 驱动器、junction、ADS适配 | symlink与权限适配 | 路径攻击回归通过 |
| 隔离Shell | 受支持容器后端 | 受支持Linux容器后端 | 受控容器/cgroup | 无后端明确禁用；不是任意原生命令 |
| 专用Chromium profile | 版本化浏览器资产 | 版本化浏览器资产 | 额外系统依赖预检 | 登录态隔离和崩溃恢复 |
| 本地stdio MCP | 受验证的隔离后端 | 受验证的隔离后端 | 受验证的隔离后端 | server不得继承核心秘密 |
| Tauri界面 | M4 | M4 | M4 | 签名/依赖与IPC兼容检查 |
| 原生桌面观察与操作 | Accessibility/ScreenCapture权限 | 活跃用户session与UIA | X11/Wayland分别实现 | 后续独立资格验证 |
| 锁屏/注销后GUI动作 | 不承诺 | 不承诺 | 不承诺 | 不绕过OS限制 |
| 休眠/关机远程唤醒 | 不属于MVP | 不属于MVP | 不属于MVP | 需另行网络与硬件方案 |

Windows系统服务不应被当作交互桌面工具；原生GUI执行器在登录用户session运行，而不是提升到LocalSystem解决问题。[S09] macOS权限在每次相关动作前预检；撤销权限后返回CAPABILITY_UNAVAILABLE与本地恢复说明，不自动修改TCC。Wayland必须按portal与桌面环境验证，不能用X11结果替代。[S12]

## 桌面核心页面

| 页面 | 必须显示 | 用户操作 |
|---|---|---|
| 首次设置 | profile、工作区、网络模式、模型、飞书、隔离后端、真实能力 | 明确确认工作区与凭据、运行doctor |
| 任务列表 | 状态、来源、工作区、最后事件、费用与待处理项 | 新建、取消、暂停、恢复 |
| 任务详情 | 用户目标、实际动作、policy原因、产物、错误与未知结果 | 查看diff、下载、进入核对 |
| 审批中心 | 完整影响范围、hash、执行环境、目的地、有效期 | 批准、拒绝、查看变化、要求重新生成 |
| 运行健康 | daemon/gateway/model/executor分别健康 | 重连、启动/停止服务、导出诊断 |
| 权限与隐私 | workspace grant、数据出口、owner、已启用工具 | 撤销、调整模式、查看权限变更 |
| 更新与恢复 | 当前版本、兼容范围、迁移风险、备份状态 | 下载并验证、安排维护、恢复备份 |

时间线记录输入摘要、上下文来源、工具提案、策略依据、授权、实际执行和结果。它不是模型隐藏思维链的导出器；仅展示模型主动给出的简明计划/说明和可审计事实，不依赖或要求provider暴露内部推理。

主按钮文本要区分“关闭窗口”“退出界面”“暂停接单”“取消任务”“停止服务”。关闭窗口默认保留daemon。界面崩溃时飞书继续；daemon崩溃时界面显示恢复或失联，不能仅因WebView仍在就显示运行正常。

## 桌面与daemon的安全连接

Tauri能力只授予专用Rust命令，不给WebView任意spawn/execute。界面加载本地受控资源，启用CSP，禁止remote页面获得native IPC。用户点击外链打开系统浏览器。渲染Markdown和tool output时禁用脚本与危险HTML。

Rust bridge从受保护通道读取session token，校验daemon identity与协议版本，代理有限操作；默认不把管理员token交给JS。开发调试接口只在dev profile开启；release构建不含可供其他页面访问的管理后门。Tauri capability并不自动把sidecar沙箱化。[S11]

## 打包策略

初期开发安装采用uv与受控依赖锁；发布先使用PyInstaller onedir以简化资源与原生库排查，onefile在后续测量后选择。PyInstaller产物依赖目标OS和Python环境，不能在一个OS构建后声称三平台可用。[S13]

发布清单包含core、gateway、supervisor、desktop、协议版本、DB schema范围、Python与SQLite版本、MCP SDK、浏览器build、容器镜像digest、SBOM与licenses。需要下载浏览器资产的安装模式要明确网络需求、校验hash和离线失败体验。

每个平台分别打包与验收：macOS应用及helper签名公证；Windows安装包与程序签名、WebView2和用户级启动检查；Linux依赖、glibc与desktop环境预检。证书与发布密钥位于受保护发布环境，普通PR任务不能读取。

## 升级与回滚

升级顺序是下载、签名校验、兼容检查、暂停新派发、等待可安全停止点、停止workers、制作一致性备份、迁移、启动新版本、健康检查、恢复接单。旧批准在policy或manifest改变后失效。

Tauri updater签名验证保护更新包真实性；OpenBot仍需自行定义跨组件和数据库兼容性。[S14] 回滚二进制不必然能读新schema。迁移后已有新写入时，恢复旧备份会丢失这些新写入；必须展示这个事实，不能宣称“无损一键回滚”。MVP优先向前兼容迁移，自动回滚只在预先定义的安全窗口内。

卸载默认保留用户数据并给出路径；清除数据是显式选项。不能删除用户原工作区、共享浏览器或非OpenBot管理的进程。

