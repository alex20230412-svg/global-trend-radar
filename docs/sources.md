# 数据来源证据表

最后核查：2026-11-25（Claude）

状态定义：

- **VERIFIED**：已实测，返回格式与新鲜度符合预期。这只代表当天可用，不代表长期稳定；长期稳定性由阶段 3 的 7 天连续运行证明。
- **CONDITIONAL**：可用，但有前提（需要 key、需要在 Actions 里重测、只覆盖部分内容等）。
- **UNTESTED**：未实测。
- **BLOCKED**：条款、资格或 robots 不允许，不使用。
- **PAID**：只有付费方案，需 Owner 批准。

实测方式：在云端浏览器或抓取工具里直接请求接口，确认返回格式和新鲜度。

| 来源 | 状态 | 覆盖 | 信号 | 2026-11-25 核查证据 | 限制 / 成本 |
| --- | --- | --- | --- | --- | --- |
| Google Trends Trending Now RSS（`https://trends.google.com/trending/rss?geo=MY`） | VERIFIED | 马来西亚 | 搜索飙升词、量级区间、开始时间、每条 3 篇关联新闻 | 实测返回 RSS；当天热词如 dap、epf withdrawal、kuching city f.c.，量级 100+ 至 1000+，条目时间以 10 分钟为单位 | 免 key；非正式 API，格式可能变；量级很粗 |
| [Malaysiakini 英文 RSS](https://www.malaysiakini.com/rss/en/news.rss) | VERIFIED | 马来西亚 | 新闻首发与扩散 | 实测 10 条，最新一条发布于当天 18:48 MYT | 只存标题、链接、时间 |
| Hacker News API（`https://hacker-news.firebaseio.com/v0/`） | VERIFIED | 全球科技 | 科技 / AI / 创业热度 | 实测 maxitem 接口返回正常 | 偏美国科技圈 |
| Bluesky trending topics（`app.bsky.unspecced.getTrendingTopics`） | VERIFIED | 全球（偏欧美） | 社交平台官方趋势话题 + 一句话说明 | 免登录实测返回 5 个话题 | 接口标为 unspecced，可能变动 |
| Mastodon trends（`/api/v1/trends/tags`） | VERIFIED | 全球（偏科技） | 趋势标签 + 7 天逐日使用量 | mastodon.social 实测返回标签与历史 | 用户量小 |
| Google Trends RSS（其他国家） | UNTESTED | 全球 | 同上，分国家 | 同一接口换 geo 参数，未逐国实测 | 不同国家量级不可相加 |
| 其他马来西亚英文 / 马来文 RSS | UNTESTED | 马来西亚 | Bernama、FMT、Malay Mail、Utusan、Kosmo、SAYS、Lowyat 等 | 地址来自 [Feedspot 列表](https://rss.feedspot.com/malaysian_news_rss_feeds/)；FMT 的 `/feed` 已 302 跳转到 cms 子域名 | 逐站核对 robots 与条款 |
| 马来西亚华文媒体 | UNTESTED | 马来西亚 | 星洲、中国报、东方、Malaysiakini 中文 | 尚未找到可确认的官方 RSS | 可能需要网页解析，先核对条款 |
| Wikipedia Pageviews（top / top-per-country） | CONDITIONAL | 马来西亚 + 全球 | 马来西亚地区最多人看的条目 | 官方接口免 key，必须带 User-Agent（[访问政策](https://www.mediawiki.org/wiki/Wikimedia_APIs/Access_policy)）；2026 年 3 月起对未登录请求执行全局限流（[时间表](https://www.mediawiki.org/wiki/MediaWiki_Product_Insights/Responsible_Reuse/WE5.1:_Developer_authentication_and_authorization)） | 日级数据，约晚一天 |
| GDELT DOC 2.0（`https://api.gdeltproject.org/api/v2/doc/doc`） | CONDITIONAL | 马来西亚 + 全球 | 65 种语言新闻的报道量曲线 | 免 key；本次从云端浏览器请求超时 | 需在 Actions 里重测；每次最多 250 条 |
| YouTube Data API（mostPopular, regionCode=MY） | CONDITIONAL | 马来西亚 | 音乐 / 电影 / 游戏热门视频 | videos.list 每次 1 个配额单位（[文档](https://developers.google.com/youtube/data/reference/rest/v3/videos/list)）；自 2025-07-21 起 mostPopular 只含音乐、电影、游戏（[变更记录](https://developers.google.com/youtube/v3/revision_history)） | 要建 Google Cloud 项目和 API key |
| Google Trends API（alpha） | CONDITIONAL | 全球 | 5 年可比搜索热度 | 仍是申请制 alpha（[Google](https://developers.google.com/search/apis/trends)），不含 Trending Now | 可选申请，不作依赖 |
| 中文热榜（微博 / 抖音 / 知乎） | CONDITIONAL | 中文圈 | 平台热榜排名 | 只能经 newsnow 等第三方接口 | 阶段 4 可选 |
| Telegram 公开频道 | UNTESTED | 马来西亚 | 本地热门频道动态 | 未测试 | 需要先评估条款与账号风险 |
| X / Twitter Trends | PAID | 马来西亚 + 全球 | 平台官方趋势 | 按次付费，Trends 每次 US$0.010（[X](https://docs.x.com/x-api/getting-started/pricing)） | 每小时查 1 次马来西亚约 US$7.4/月，需 Owner 批准 |
| Reddit | BLOCKED | — | — | 2026-10-31 起不再受理新 API 申请，RSS 已于 2026-11-13 关闭（[TechRepublic](https://www.techrepublic.com/article/news-reddit-rss-public-api-shutdown/)） | 不用 |
| TikTok Research API | BLOCKED | — | — | 只开放给通过审核的非营利学术研究者（[TikTok](https://developers.tiktok.com/docs/en/about-research-api)） | 抓取 Creative Center 有违反条款风险，不用 |
| Meta Content Library（FB / IG / Threads） | BLOCKED | — | — | 申请人须隶属合格学术或研究机构（[Meta](https://developers.facebook.com/docs/content-library-and-api/get-access)） | 不用登录爬虫 |
| Harian Metro RSS | BLOCKED | — | — | 网站 robots.txt 禁止抓取 | 尊重 robots，不用 |

## 更新规则

- 每次实测后更新状态、证据和核查日期。
- 状态从 VERIFIED 降级（连续失败、条款变化）时，在 HANDOFF_LOG.md 记录原因。
- 新增来源先标 UNTESTED，实测通过后才能改 VERIFIED。
