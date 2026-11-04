# 单任务执行模板

本轮任务ID为：填写一个tasks/backlog.json中的稳定ID。

请读取该任务、depends_on任务的实际验证证据、相关design_refs和AGENTS.md。先检查当前代码，说明本轮会修改的模块与输出，不扩展到没有授权的功能。

按implementation_steps实现，满足acceptance与negative_acceptance。涉及持久化、审批、恢复或外部副作用时，加入与实际风险对应的失败测试；不要为简单可逆改动堆无价值测试。

不得修改权限边界、删除失败测试或用mock成功掩盖实际未实现功能。遇到合同冲突，记录具体问题与建议，先完成不受影响的部分。只有真实外部服务或平台环境不可用才标BLOCKED，并给出已完成部分和最小缺失条件。

最后输出：任务ID、修改摘要、实际命令和结果、负向场景证据、未跑验证、风险、任务状态建议。不要自动发布或发送消息。


## v1.2组件要求

读取本任务component_refs、reuse_type、reuse_notes及components/catalog.json。只引入当前任务必要组件，记录精确版本与相关Q场景证据；官方SDK同样检查重试、自动工具helper与网络出口。候选和源码参考不因被引用就自动获准安装或复制。
