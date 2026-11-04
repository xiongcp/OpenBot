# OB-004 / OB-089：阶段依赖证据

实际精确锁见 uv.lock；当前 macOS ARM64 安装版本、来源 wheel、sha256、完整许可原文与 hash 见 components/admissions/m0.json、evidence/implementation/licenses。该清单仅准许本地开发和合同测试，不提供产品运行能力。

M0 core 使用 jsonschema 4.26.0 / referencing 0.37.0、Pydantic 2.12.5、rfc8785 0.1.4；date-time 的实际 checker 由 rfc3339-validator 0.1.4 提供。pytest / ruff / mypy 为开发组；安装清单由真实虚拟环境导出，传递依赖也逐项保存许可。Python 3.12.12 在仓库内，uv 0.9.26；SQLite 构建与 PRAGMA 由协议 PoC 实测。

pathspec 1.1.1 仅由 mypy 传递引入，发行物 LICENSE 为 MPL-2.0；没有复制其源码或把它作为文件权限实现。保留许可文本；未来若分发它，需按实际文件/改动与发行方式再次审查。rfc8785 发行物 LICENSE 为 Apache-2.0，Pydantic/jsonschema/referencing 为 MIT；完整说明以安装原文为准。项目自身许可证未由用户选定，不替用户决定。

command-group 上游明确 Deprecated 并推荐 process-wrap；本项目不安装。service-manager 仅登记候选，不推断 Windows 系统服务等于用户登录会话。官方资料核对：[command-group](https://github.com/watchexec/command-group)、[service-manager](https://docs.rs/service-manager/0.11.0/service_manager/)。它们不是本机资格通过记录。

飞书、模型 SDK、Browser、MCP、PyInstaller、Rust、grammar、tokenizer 和镜像不属于 M0 安装；目录中的推荐仍 NOT_RUN。源码候选未复制，NO_COPY 可在所属审查任务中决定；没有 vendor 或上游自治循环。

本阶段官方实现文档：[jsonschema 引用](https://python-jsonschema.readthedocs.io/en/stable/referencing/)、[RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html)、[rfc8785.py](https://github.com/trailofbits/rfc8785.py)。每个已安装包的精确 PyPI 版本元数据 URL、wheel URL/hash、LICENSE 文本定位均由实际锁和安装包生成。
