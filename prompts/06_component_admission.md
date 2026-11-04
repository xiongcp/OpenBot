# 单个组件接入与升级提示

请在当前已就绪任务范围内接入或升级指定component_id。先读任务卡、components/catalog.json、docs/12_component_reuse.md、docs/13_component_qualification.md和现有依赖/平台证据。

确认该组件处于当前阶段，选择一种实现，记录精确版本/commit、来源、hash、LICENSE/NOTICE、可选特性与附属资产。使用分阶段依赖组，不把候选表全部安装。默认组件也需要资格验证；REFERENCE_ONLY先审查再决定COPY或NO_COPY，禁止复制自治执行循环。

按templates/component-qualification.md记录允许API、网络/代理、首次下载、重试、线程/子进程、文件、凭据、取消和cleanup。明确唯一重试与生命周期所有者，运行相关Q场景和任务负向验收。mock只证明其覆盖的transport，不证明所有外网路径都被阻断。

如果库不能满足现有合同，先尝试收窄API或采用有证据的替代件；必要窄补丁登记templates/UPSTREAM_PATCHES.md字段。不要通过host fallback、关闭sandbox、忽略UNKNOWN或扩大网络权限使测试通过。版本改变影响manifest或授权内容时，按原规则使旧授权失效。

提交适配代码、依赖/资产锁定、来源记录、实际测试与未验证范围，更新任务证据。常规可逆修改可继续执行；改变产品范围或信任边界须遵循已有用户授权和项目变更流程，不自行推断新的外部行动许可。
