# 数据来源证据表

最后更新 2026-11-26 MYT。D-010 批准启用已接入来源的最少字段，供 Owner 私人使用。现有 23 个来源加当今大马中文 RSS，合计 24 个启用来源。GDELT 只安排无凭证连通探测。配置审批、历史证据和 Actions 连通性分别记录，当前 **L4 0 个，L5 0 个**。 [D-010 与阶段 B 任务单](https://github.com/alex20230412-svg/global-trend-radar/issues/9) · [历史证据复核](https://github.com/alex20230412-svg/global-trend-radar/issues/2#issuecomment-7164683992)

## 核查等级

| 等级 | 需要的证据 |
| --- | --- |
| L1 | 目标端点可达，记录准确地址和日期 |
| L2 | 逐源核实访问条款、robots、保留字段与期限、向个人私聊转发的权利 |
| L3 | 真实目标内容、结构和新鲜度已核实。只访问同一 API 的其他方法不能替代 |
| L4 | 审核后的默认分支在 Actions 环境成功运行并核验前三级证据，达到后才标 `VERIFIED` |
| L5 | 七天连续运行验证通过 |

## 来源与保存范围

| 适配器 ID | 范围与历史证据 | 保存与使用条件 |
| --- | --- | --- |
| `trends_my` | MY 搜索飙升。历史 L1 + L3。量级是近似分档 | D-010 批准 `long_term` 和 `retain_related`。记录搜索词与量级、时间、地区及最多三条关联报道的标题、链接和媒体名。日报标出 Google Trends，展示第一条相关报道。 [RSS 导出](https://support.google.com/trends/answer/3076011) · [引用条件](https://support.google.com/trends/answer/4365538) · [Google 服务条款](https://policies.google.com/terms) |
| `trends_sg`、`trends_id`、`trends_th`、`trends_ph`、`trends_vn`、`trends_us`、`trends_gb`、`trends_in`、`trends_jp`、`trends_kr`、`trends_tw`、`trends_hk`、`trends_au` | 同型 RSS。各地端点、新鲜度和原始语言仍待逐个核查 | 与 MY 相同的 D-010 配置。同一信号在各地的量级独立，报告按地区出现与时间比较。 [Google Trends 数据说明](https://support.google.com/trends/answer/3076011) |
| `malaysiakini`、`malaysiakini_zh` | 当今大马英文 RSS 有历史 L1 + L3。官方中文站声明中文 feed，同主机 robots 允许。中文实际返回待无凭证 Actions 核对 | D-010 的同一媒体范围。只处理私人使用的最少字段，保留原站链接。报道扩散计分时中英版视为同一媒体。条款保留编辑内容复制与复用权。 [当今大马条款](https://www.malaysiakini.com/en/about/terms-of-service) · [华文核查](chinese-sources.md) |
| `malay_mail` | 马来西亚英文地区 RSS。官方列表提供入口，历史 L1 + L3 | D-010 批准最少字段。条款限制内容复制及再分发。 [官方 RSS 列表](https://www.malaymail.com/rss) · [Malay Mail 条款](https://www.malaymail.com/terms/1000) |
| `fmt` | FMT 的 `cms.` 直连 RSS。历史 L1 + L3，含英文和马来文 | D-010 批准最少字段。FMT 规定复制、再分发须获权利人同意。没有条目语言标识时记 `und`。 [FMT 版权声明](https://www.freemalaysiatoday.com/disclaimers-copyright) |
| `bernama` | 英文 `/en/rssfeed.php`。历史 L1，部分条目缺 `pubDate`，出现过编码问题 | D-010 批准最少字段。日期无值时显示首次观测，按明显错码特征尝试无损解码。发布方保留内容复制与转发权。 [官方 RSS 入口](https://rss.bernama.com/) · [Bernama 版权声明](https://www.bernama.com/en/copyrights.php) |
| `hn` | 官方 `topstories` 前 30 项。历史仅验证过 `maxitem`，实跑需验证目标数据 | D-010 批准标题、链接、分数和排名。不保留作者、正文、评论或个人资料。 [Hacker News API](https://github.com/HackerNews/API) · [Hacker News Guidelines](https://news.ycombinator.com/newsguidelines.html) |
| `bluesky` | `getTrendingTopics` 历史 L1 + L3，`unspecced` 结构可能变化 | D-010 批准话题名称、列表位次和链接。排除帖子、资料和推荐内容。 [Bluesky 条款](https://bsky.social/about/support/tos) |
| `mastodon_tags`、`mastodon_links` | `mastodon.social` 一个实例。标签历史 L1 + L3，链接仍待真实验证 | D-010 批准标签和链接元数据。不保留页面内容、预览、资料或帖子。 [Mastodon API](https://docs.joinmastodon.org/methods/trends/) · [实例条款](https://mastodon.social/terms-of-service) |
| `weather` | data.gov.my 的 MET Malaysia 天气警告。历史 L1 + L3，官方文档为 CC BY 4.0 | 保存标题、链接、发布和有效时间，标注 MET Malaysia 和许可证。无偏移量的警告时间按 MYT 解释，待真实样本验证。地震端点另议。 [天气 API](https://developer.data.gov.my/realtime-api/weather.en) · [MET 开放数据](https://www.met.gov.my/info/data-terbuka/) |
| `gdelt` | DOC 2.0 以前连续两次连接超时。本轮仅通过 Mock 实现，Actions 连通仍待验证 | 生产 `enabled: false`、`retention: pending`。无凭证工作流可单独探测 `ArtList` 的马来西亚相关及全球近一小时两组查询，每组最多 20 条，同源间隔至少 5 秒并遵守更严格的 robots 规则。只取标题、链接、索引时间、媒体来源国和语言。混合相关度说明搜索相关性，热度需独立证据。 [GDELT DOC 2.0](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) |

## 启用、限制与下一步

- D-010 是 Owner 对私人用途及字段范围的批准。官方 RSS 入口与 robots 许可并不自行授予转载或公开再分发权。新闻只保留元数据，保留原始链接。新增来源须核实官方入口、robots 与条款，耗时或许可不明即暂缓。删除 Git 文件后历史版本仍可能保留。
- 24 个启用接口每轮约 54 次数据请求，加各域 robots 与受限重试。GDELT 的两次查询属于隔离探针。固定来源、禁重定向。401/403 停止，429 按 `Retry-After` 或更严格的站点规则退避。
- 华文新增当今大马一个出版社。其余候选的官方 RSS、访问或使用条件仍有缺口。商品趋势代表现有来源信号，尚无销量。TikTok、Facebook、Instagram、Threads、X、YouTube 和 Wikipedia 本轮未接入。 [华文来源调查](chinese-sources.md)
- 默认分支确有 Actions 实跑与 L1–L3 证据时，逐源更新证据等级。合成样本与本轮静态调查只用于离线验收和来源筛选。 [历史方案](PLAN.md)
