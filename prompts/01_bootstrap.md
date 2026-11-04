# 首次交给编码助手的提示

请以当前目录中的OpenBot v1.2工程设计包为基线开始实施。

先读取README.md、AGENTS.md、docs/00_scope.md、docs/02_architecture.md、docs/10_project_plan.md、docs/12_component_reuse.md、docs/14_revision_v1_2.md、tasks/backlog.json与components/catalog.json。只读检查现有仓库；如已有实现，先列出与基线的差异，不覆盖已有工作。

本轮完成OB-001至OB-005和依赖满足的OB-089；按依赖顺序推进。目标是冻结范围/威胁模型/生命周期、记录当前所需组件的来源/许可证与阶段准入、建立能运行验证的最小Python仓库和CI骨架。不要在M0一次安装所有候选；Browser、MCP、Tauri与P2重依赖在对应任务再引入。

保持以下不变量：daemon与UI分离；所有副作用经Broker；Task/Operation/Approval/Attempt分开；结果未知不能盲重试；模型与外部内容不能赋权；没有隔离后端不降级host执行。接口或状态有疑问先记录ADR，不能悄悄改语义。

交付本轮真实代码与文档、实际运行的检查命令和结果、没有验证的环境、更新后的任务证据。所有任务状态必须依据仓库真实产物；不得把设计包现有文档或SQL直接当作应用完成证据。

完成本轮门禁后报告实际结果。下一批做OB-006至OB-010、OB-090标准合同向量和OB-091最小协议PoC；OB-029继续作为M1真实API与隔离路径的集成门禁。若用户已要求持续实施，请转prompts/05_autonomous_project.md连续推进，不为每个常规步骤重复询问。

