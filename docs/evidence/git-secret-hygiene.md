# Git 敏感文件防误提交 / Git credential file protection

关联 / Related: OB-008, OB-038, OB-039 · 2026-11-05

## 中文

独立问题：仓库依赖用户全局 Git ignore 才能忽略 `.env`、SQLite 等文件，
并未保护 daemon 的 `owner_cli.token`、`challenges.json` 或 profile 目录。
新机器或不同全局配置下，这些文件可能被普通 `git add` 暂存。

最小修复：仓库自身忽略本地环境文件、token、挑战存储、会话元数据、数据库及其日志、
私钥容器和本地 profile。保留无秘密的 `.env.example`、`.env.template` 和已有源码可跟踪。
本轮测试凭据不写入仓库文件；提交仅使用明确路径并审查暂存内容。

验证：`.venv/bin/python -m pytest tests/security/test_git_secret_hygiene.py -q`。
禁用 `core.excludesFile` 后，修复前 14 failed / 6 passed，修复后 20 passed。
测试只传文件名给 `git check-ignore --no-index`，不创建任何真实密钥。

边界：ignore 不会清除已跟踪文件、阻止 `git add -f` 或扫描任意正文；
仍须审查明确暂存内容。本次没有改写 Git 历史，也未提交真实凭据。

## English

Problem: repository rules relied on global Git ignores for environment/database files and
did not cover daemon owner tokens, approval challenge stores, or local profiles.
Ordinary staging on another machine could therefore include private runtime state.

The minimal fix adds repository rules for these files, database sidecars and private key
containers, while preserving public environment templates and credential-handling source.
Test credentials stay out of repository files; commits use explicitly reviewed paths.

Validation: `.venv/bin/python -m pytest tests/security/test_git_secret_hygiene.py -q`.
With global excludes disabled: before 14 failed / 6 passed; after 20 passed.
Tests query filenames only and create no real credentials.

Limits: ignore rules do not remove tracked files, defeat forced staging, or detect every
secret embedded in text. Staged-content review is still required. No history was rewritten.
