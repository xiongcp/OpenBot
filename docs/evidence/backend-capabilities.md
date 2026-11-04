# OB-093：首发平台隔离能力

状态：IN_PROGRESS。首测 Darwin arm64；Docker Desktop client/server 29.1.3、引擎 linux arm64。初测 socket 缺失是历史观察，后续后端已可连接；未由本轮启动用户服务或切换默认 context。

已测原语：`tests/components/native_poc/test_profile_lock.py` 在两个真实 Python 进程间验证 flock 的第二实例拒绝、客户端结束不释放 supervisor 锁、owner 强杀后释放。该测试不等于完整 Supervisor / daemon 交接、任意子孙回收、logout / sleep / Job / 容器资格。

实际命令：`OPENBOT_NATIVE_TESTS=1 PYTHONPATH=services/core/src .venv/bin/python -m pytest tests/components/native_poc/test_docker.py -q --tb=short`。本次 8 passed；日志在 evidence/implementation/native-container-tests.log，实际容器 ID、客户端 PID、stop/wait/export/remove 次序及空残留列表在 native-container.json。测试使用独立空 Docker config，只运行准备阶段固定的官方 Alpine digest、--pull=never，不使用本机企业镜像或个人 registry 登录。

| 能力 | 当前证据 | 限制 |
|---|---|---|
| 容器隔离 | 非 root、只读输入和根层、cap-drop/no-new-privileges、无 HOME/凭据/socket、无路由和 eth0 | 不是整个 macOS/VM 出口审计 |
| 配额 | cgroup 内存/PID 读回；实际 OOM exit 137；fork 被 PID 上限拒绝；CPU 配置读回 | CPU 压力和磁盘配额未实测 |
| 独立生命周期 | 杀死 Docker attach 客户端，容器仍 Running；随后按登记 ID stop/wait | 不能把客户端退出当回收 |
| 导出与回收 | 停止后有界 tar 字节验证，拒绝路径穿越/链接/超限，再 remove；4 个登记容器均回收 | 仅合成 receipt，完整 Artifact Broker 待 OB-036/041 |
| 其他平台 | Windows x64 / Linux x64 NOT_RUN | Docker Desktop Linux VM 不算原生 Linux 资格 |

内存夹具首版未制造足够实际分配，测试失败并清理；改为动态增长至 128 MiB 后实际触发 64 MiB 上限，没有把未触发压力当作通过。

仍需实现并验证：唯一 supervisor 的父子锁协议、daemon 独立启动拒绝、多代子孙/逃逸/父进程强杀与旧 epoch 接管、登记域无法核对时阻止 dispatch。正式 native/supervisor 与 python-on-whales 尚未实现/安装，不是“缺 Docker 环境”；这些是 OB-093/015/040—042 的工程待办。镜像仅为本地测试资产，完整镜像许可与发行供应链资格仍 NOT_RUN。任何失败都不得降级宿主执行。

影响：OB-029 正式隔离执行门禁尚未通过；原生进程/后端组合需完成上述缺口。存储、合同与 SDK 故障验证可继续，不以该门禁代替全部 M1 工作。
