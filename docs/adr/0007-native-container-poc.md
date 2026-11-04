# OB-093：首发容器原语 PoC 补充

状态：接受；2026-11-04 后续只读复检确认本机 Docker Desktop Engine 29.1.3 / linux arm64 已可用。原先 socket 缺失记录是当时观察，不能继续当作当前状态。

仅在安装准备阶段取得 Docker Official Image `alpine:3.24.3`，随后记录实际 manifest digest / image ID；全部执行使用 digest 与 --pull=never。独立临时 Docker config 不读取个人 registry 登录信息；不使用本机已有的企业业务镜像，不切换默认 context、不操作用户容器。

PoC 直接使用受控 Docker CLI 原语，覆盖只读输入、无网络、无 HOME/socket/凭据、非 root、cap-drop、no-new-privileges、CPU/内存/PID 配额、客户端退出与容器独立生命周期、stop/wait 后受限导出再删除。python-on-whales 正式适配仍待 OB-040—042，不凭本次 CLI 证据认证该包或其他引擎。

所有临时容器使用随机本轮标识与标签，只按登记 ID 回收；不做系统 prune。Docker Desktop 的 Linux VM 证据属于该 macOS 组合，不算 Linux x64 或 Windows 原生资格。进程树和 Supervisor/daemon 交接未覆盖项仍保留 NOT_RUN，不宣称 100% 回收。

镜像来源：[Docker Official Alpine](https://hub.docker.com/_/alpine)、[Alpine releases](https://alpinelinux.org/releases/)。镜像精确资产信息在 components/assets，包内许可清单与原文按实际内容留证；本次为本地测试资产，不构成 M3 发行供应链验收。
