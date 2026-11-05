# 官网实施规格

目录建议：apps/website，独立Astro静态输出，Starlight文档；Node/package manager和依赖精确锁定。桌面仍为Tauri静态ES modules，不共享native bridge或token。

## 构建输入

Markdown/MDX内容、中英i18n词条、design_tokens、经校验的能力/发行数据、真实截图/字幕。prelaunch示例没有任何假二进制链接。

## 页面组件

Header、LocaleSwitcher、StageBadge、Hero、ScenarioCards、EvidenceDemo、HowItWorks、SupportMatrix、ReleaseDownload、DocsSearch、Footer。所有交互有键盘和读屏名称，状态不只靠颜色。

## 数据合同

release_manifest.schema.json只定义官网内容结构。生产校验还要验证HTTPS/允许的发布仓库、stage/channel一致、实际资产存在和hash、支持能力证据、两个语言的语义一致。它不是最终发布门禁，也不替代Tauri updater签名格式。

## 交付顺序

先内容骨架与预览，再首页/文档/安全/路线图，再下载联动，最后真实演示、a11y/性能/SEO和发布回退。没有稳定Release时保持stable_release=null；下载入口降为真实源码指引。

## 验收

静态构建可复现；320px和1440px宽度可用；Safari/Chrome关键路径；键盘导航和VoiceOver；全部CTA/相对路径/语言切换有效；预览noindex、生产canonical/hreflang正确；错误manifest和缺资产阻断生产部署。初期不增加账号、付款、用户数据收集或第三方广告追踪。
