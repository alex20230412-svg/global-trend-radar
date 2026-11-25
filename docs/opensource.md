# 开源复用记录

2026-11-26 MYT 核对发行元数据与官方仓库。版本和许可证按锁定发行包或下列提交记录。阶段 A 安装并使用了 Python 依赖，候选应用仅作源码及部署文档调查。

| 候选 | 核对提交及许可证 | 采用情况与差距 |
| --- | --- | --- |
| TrendRadar | [ad2221f](https://github.com/sansan0/TrendRadar/tree/ad2221fae0d908f6c11f40f70680dd5f9b41cd5d)，GPL-3.0 | 参考数据源分组和分段设计。其 Actions 部署依赖远端历史存储和签到机制，默认热榜市场与 MY 不同。未引入代码或远端存储。 |
| Horizon | [da66986](https://github.com/Thysrael/Horizon/tree/da66986a48b50db28f41e46a935fee19cabe2abd)，MIT | 评估其多源摘要。第一轮需要无模型的可解释排名、Google Trends 历史和私聊投递流水，未采用其 AI 配置或代码。 |
| auto-news | [4f1a2e0](https://github.com/finaldie/auto-news/tree/4f1a2e0fa42c8663df3efe5f798c00edfcf7b912)，MIT | 其多组件部署和模型链路超出本轮范围。未引入。 |
| GitHub OCTO Flat | [cea5ee4](https://github.com/githubocto/flat/tree/cea5ee43fce40ef71501bf5724a00d45db11641d)，MIT | 借用定时采集、Git 保存快照的模式。专用私库校验、分区幂等和 Telegram 投递需要项目自己的实现。未引入其 Action 或代码。 |
| github-trending | [349f1f0](https://github.com/fireinrain/github-trending/tree/349f1f022f56cfa55ad3afdca862b51518b22828)，MIT | 参考已推送记录的模式。支持部分送达、UNKNOWN、逐段私有持久化的状态机由本项目实现。未引入片段。 |

| 直接依赖 | 版本与许可证 | 用途 |
| --- | --- | --- |
| [HTTPX](https://pypi.org/project/httpx/0.28.1/) | 0.28.1，BSD-3-Clause | 流式 HTTP、超时、TLS 和本地 Mock。 |
| [Feedparser](https://pypi.org/project/feedparser/6.0.14/) | 6.0.14，BSD-2-Clause | RSS 标准字段与日期。 |
| [defusedxml](https://pypi.org/project/defusedxml/0.7.1/) | 0.7.1，PSF License | 解析 Trends 扩展字段并拒绝 XML 实体。 |
| [Protego](https://pypi.org/project/Protego/0.7.0/) | 0.7.0，BSD-3-Clause | robots.txt 路径及频率规则。 |
| [PyYAML](https://pypi.org/project/PyYAML/6.0.3/) | 6.0.3，MIT | 安全加载来源配置。 |
| [RapidFuzz](https://pypi.org/project/RapidFuzz/3.14.6/) | 3.14.6，MIT | 保守的标题相似度和转载去重。 |

传递依赖也使用版本及 wheel 哈希锁。HTTP Core 1.0.9（BSD-3-Clause）、h11 0.16.0（MIT）、AnyIO 4.16.0（MIT）、IDNA 3.20（BSD-3-Clause）、certifi 2026.11.20（MPL-2.0）、feedparser-sgmllib 2.0.0（PSF-2.0）、typing-extensions 4.16.0（PSF-2.0）。锁覆盖 Linux x64 与 Windows x64 的 Python 3.14。Actions 复用 [checkout v7.0.1](https://github.com/actions/checkout/tree/3d3c42e5aac5ba805825da76410c181273ba90b1)（MIT）和 [setup-python v7.0.0](https://github.com/actions/setup-python/tree/5fda3b95a4ea91299a34e894583c3862153e4b97)（MIT）的固定提交。Git 原生非强推提供提交竞争保护，消息使用 [Telegram Bot API](https://core.telegram.org/bots/api)。

项目代码补充来源权限控制、固定端点的频率与响应约束、小时观测、评分、报告与持久化投递。重试只涵盖明确可安全重试的情况和有限退避，直接复用 Python 标准库与 HTTPX，避免叠加通用重试层。
