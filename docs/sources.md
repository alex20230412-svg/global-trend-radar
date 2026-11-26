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
- 华文新增当今大马一个出版社。其余候选的官方 RSS、访问或使用条件仍有缺口。商品趋势代表现有来源信号，尚无销量。YouTube 已实现并默认关闭，TikTok、Facebook、Instagram、Threads、X 和 Wikipedia 尚未接入。 [华文来源调查](chinese-sources.md) · [YouTube 功能说明](youtube.md)
- 默认分支确有 Actions 实跑与 L1–L3 证据时，逐源更新证据等级。合成样本与本轮静态调查只用于离线验收和来源筛选。 [历史方案](PLAN.md)

## 实测记录（无凭证 live-check，main，GitHub Actions ubuntu-24.04）

| 日期 | 运行 | 结果 |
| --- | --- | --- |
| 2026-11-26 | [45745818302](https://github.com/alex20230412-svg/global-trend-radar/actions/runs/45745818302) | 21/24。`malaysiakini`、`malaysiakini_zh`、`weather` 为 `http_301`（RSS 与 API 地址变更，PR #11 修正）；GDELT `network_error` |
| 2026-11-26 | [45746194730](https://github.com/alex20230412-svg/global-trend-radar/actions/runs/45746194730) | 23/24。`malaysiakini` 一次 `invalid_xml`（偶发，浏览器同时可正常解析） |
| 2026-11-26 | [45746616949](https://github.com/alex20230412-svg/global-trend-radar/actions/runs/45746616949) | 23/24。`bernama` 一次 `ConnectTimeout`（PR #13 连接超时放宽到 8 秒） |
| 2026-11-26 | [45746864621](https://github.com/alex20230412-svg/global-trend-radar/actions/runs/45746864621) | **24/24**，两次采集幂等，日报 1 段 3,473 字，未降级 |
| 2026-11-26 | [45746980188](https://github.com/alex20230412-svg/global-trend-radar/actions/runs/45746980188) | **24/24**，日报 1 段 3,491 字，未降级 |

GDELT 在全部 5 次运行中都连不上（诊断为 `ConnectTimeout`，8 秒连接超时也一样），判断为不接受 GitHub runner 的连接，保持 `enabled: false`。私库写入和 Telegram 投递待 Owner 完成凭证设置后实测。

## 流行榜单（D-012，2026-11-26）

| 来源 | 地址 | 依据与证据 |
| --- | --- | --- |
| `apple_music_my` | `rss.marketingtools.apple.com/api/v2/my/music/most-played/25/songs.json` | Apple 官方 Marketing Tools 榜单，不需要 key。robots.txt 只有一行注释，没有规则（Claude 2026-11-26 核查）。只存排名、歌名、歌手、类型和链接，不存封面图。live-check [45772752652](https://github.com/alex20230412-svg/global-trend-radar/actions/runs/45772752652)：`ok`，25 条 |
| `app_store_my` | `rss.marketingtools.apple.com/api/v2/my/apps/top-free/25/apps.json` | 同上。Claude 15:00 前后用浏览器访问曾返回 502/504，live-check 时已恢复：`ok`，25 条 |
| YouTube 马来西亚热门（已实现、待启用） | YouTube Data API `videos.list?chart=mostPopular&regionCode=MY` | D-013。自 2025-07-21 起榜单条目来自热门音乐、电影和游戏榜。视频元数据只用于当次私聊发送，系统不存储。默认关闭，等待审核、Owner 设置密钥及真实预览。 [变更记录](https://developers.google.com/youtube/data/revision_history#july-10-2025) · [功能说明](youtube.md) |
## 早报 v5 新来源核查（D-014）

2026-11-26 22:42 MYT 核查了公开政策、robots 和一轮有限的公开端点样本。下列 HTTP 状态和数量来自这次公开探查。Draft PR 的新代码尚未合并，现有 `main` 的 live-check 不含这些适配器，L4 实测留给合并后。 [Issue #33](https://github.com/alex20230412-svg/global-trend-radar/issues/33)

| 候选 | 核查证据 | 本轮配置 |
| --- | --- | --- |
| 维基百科马来西亚 `wikipedia_my` | `wikimedia.org/robots.txt` 返回 404，未取得禁止规则。马来西亚 top-per-country 前一天返回 HTTP 200、22 条，核对了 `article`、`project`、`rank`、`views_ceil`。Wikimedia 要求可辨识且可联系的 User-Agent。 | 启用日级数据。保存条目名、浏览量、榜内位次、日期及生成的 Wikipedia 链接。配置可排除常驻词条及命名空间，前一日未发布时试再前一日。 [开放数据说明](https://developer.wikimedia.org/use-content/data/) · [User-Agent 政策](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy) · [robots.txt](https://wikimedia.org/robots.txt) |
| 微博 `weibo_archive` | `justjavac/weibo-trending-hot-search` 授权文件为 MIT。官方 GitHub Contents API 的 `raw/2026-11-26.json` 返回 HTTP 200、101 个 `title/url` 项，`Last-Modified` 为 04:53:19 UTC，与最新文件提交 `4ff7be3` 相符，距核查约 10 小时。 | 启用 GitHub 上的公开存档。只读固定仓库与路径，要求时间头且不超过 48 小时。不会请求微博本站。保留排行及规范链接供本人点击。 [存档与许可](https://github.com/justjavac/weibo-trending-hot-search) · [文件变更记录](https://github.com/justjavac/weibo-trending-hot-search/commits/master/raw) |
| 知乎存档 | `typeofNaN/hot` 的 `zhihu-hot-topic` 及 justjavac 知乎存档候选最后更新在 2025-05。检查的另一 MIT 候选 SnailDev 最后更新为 2026-11-15，超过 48 小时。 | 暂缓，等待新鲜度和许可均能核实的 GitHub 存档。 [typeofNaN/hot](https://github.com/typeofNaN/hot) · [justjavac 候选](https://github.com/justjavac/zhihu-trending-top-search) · [SnailDev 候选](https://github.com/SnailDev/zhihu-hot-hub) |
| 百度热搜 | `top.baidu.com/robots.txt` 返回 404。一次公开榜单检查找到了数据标记，但数据未能用 JSON 解析器验证。 | 关闭。保留格式未核实结论，今后需证明无需登录、Cookie 或签名即可按规则稳定取数。 [robots.txt](https://top.baidu.com/robots.txt) · [公开榜单](https://top.baidu.com/board?tab=realtime) |
| B 站热门 | `api.bilibili.com/robots.txt` 返回 200，通用组包含 `Disallow: /`。网页主站规则不构成 API 域名的许可。 | 排除。此次仅取得 robots 证据，热门 API 不请求。 [API robots.txt](https://api.bilibili.com/robots.txt) · [网站 robots.txt](https://www.bilibili.com/robots.txt) |
| 中新网 `chinanews_rss` | 官网公开 RSS。主机 robots 通用组允许根路径。本轮 RSS HTTP 200，30 条 RSS 记录。 | 启用，复用 RSS 解析，只保存标题、规范链接和时间，链接限定在发布方主机。 [官方 RSS](https://www.chinanews.com.cn/rss/scroll-news.xml) · [robots.txt](https://www.chinanews.com.cn/robots.txt) |

新来源在生产小时槽先写入一次探测标记，成功或失败均不在同一小时重复；维基百科只在前一天无数据时试备用日期。GitHub 存档仅在固定 Contents API 路径使用 Actions 只读凭证。上游失败和存档停更通过来源状态表达，真实响应及条目原文不出现在公开 Actions 日志。
