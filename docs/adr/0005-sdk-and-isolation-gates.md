# OB-092 / OB-093：M1 组件资格先行

状态：接受；日期：2026-11-04。

M0 本机合同 / 协议已验证，但三 OS bootstrap 尚缺真实执行证据，相关任务保持 VERIFIED / BLOCKED。允许继续不依赖缺失平台能力的 M1 资格子任务；不因此授予运行能力或关闭 OB-029。

M1 仅增加 provider-openai 开发资格组：OpenAI Python 2.26.0、httpx 0.28.1，在独立 .venv-m1 内对合成本地 HTTP 服务做 Q01 / Q04。M0 环境不安装该组，原 M0 锁快照保留；主 uv.lock 按阶段扩展，既有资格以实际子集的版本 / wheel / 许可 / 配置复核，新增无关组不伪造全部重验。

当前资格适配器只允许 chat.completions.with_streaming_response.create 的原始文本流与已固定 endpoint；function proposal 属后续 OB-025；不提供 client 对外访问、任意 kwargs、extra_body / extra_headers / hosted tools / runner。SDK max_retries=0、HTTP transport retries=0、trust_env=False、禁重定向。应用层是唯一重试负责人，每次实际请求有独立预算 reservation；超时 / 半流 usage 未知时保留预留，不凭取消判零费用。

资格使用回环 fake HTTP 的真实 TCP 请求计数和受限 Python audit 探针。该范围不证明 C 扩展 / 原生 socket / 全进程树 OS 网络隔离；真实云端模型质量留在 OB-025，Ollama 禁云 / egress 留在 OB-026，飞书 / Browser / MCP 各自重验。

OB-093 初次 socket 缺失是历史观察。后续已实测 Docker Desktop Engine 29.1.3 与固定 Alpine digest 的隔离和独立生命周期原语，见 ADR-0007；正式 Supervisor、旧 epoch 隔离和进程树回收尚未实现，不授予 CODE_EXECUTION 产品能力。禁止宿主兜底，不安装用户服务。
