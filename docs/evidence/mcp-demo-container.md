# 受限 MCP 容器 / Bounded MCP Container

关联 / Related: OB-062/063/064/065 · 2026-11-05 · Darwin arm64

自有最小只读 JSON-RPC server 仅允许专用合成 `demo.txt`，上限 4096 bytes。
拒绝其他文件、路径穿越、符号链接、超限输入、重复键与初始化前调用；不执行输入代码。
客户端先 initialize/版本校验、initialized、tools/list，再 tools/call；完整回执核对内容 SHA-256。

An original minimal JSON-RPC server reads only the dedicated synthetic demo file, up to 4096 bytes.
It rejects other files, traversal, symlinks, oversized input, duplicate keys and pre-initialization calls.
It never executes input as code. The client negotiates, lists the tool, calls it and verifies the content hash.

真实 Docker 路径使用精确 image digest、pull=never、network=none、只读 rootfs/输入、
65532 用户、无 capabilities、no-new-privileges、内存/CPU/PID 限制。
子进程使用干净 HOME/环境，未继承测试模型密钥。登记 container ID 与所有权 labels，
清理先停止、wait 并核对未运行，再删除；不把 docker attach 退出当容器已停止。

The real Docker path uses an exact image digest with no runtime pull, no network, read-only
root/input, UID 65532, dropped capabilities, no-new-privileges and resource limits.
The client inherits no model credentials. Cleanup checks ownership and independently stops,
waits, verifies and removes the registered container; attach-client exit is insufficient.

锁 / Pin: `components/locks/mcp-demo.json`。镜像在准备阶段从官方固定版本解析并取得；
首次目标 socket 未发现镜像，显式在同一本地 socket 准备后通过，未改变隔离检查。
The image was resolved and prepared before runtime; an initial missing image on the target
socket was fixed by explicit preparation on that socket without weakening isolation checks.

```sh
.venv/bin/python -m pytest tests/unit/test_mcp_read_fixture.py -q
OPENBOT_NATIVE_MCP=1 .venv-m1/bin/python -m pytest tests/components/native_poc/test_mcp_container.py -q
```

RED 7 failed；GREEN 7 passed；真实容器 1 passed（0.71s 单样本，不作性能承诺）。
Native evidence covers only this synthetic read tool, not arbitrary third-party MCP servers,
all Docker versions, other native platforms or full Agent integration.
