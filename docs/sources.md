# 数据来源证据表

最后更新 2026-11-26 MYT，阶段 A。实现覆盖 14 个 Google Trends 地区、4 个马来西亚 RSS、4 个社交与科技接口以及 1 个气象接口。适配器的离线验证使用合成样本和 Mock。此前 Claude 的只读证据沿用其核查当日口径，本阶段没有验证实时源的新鲜度、真实默认分支 Actions、数据写入或推送。当前 **L4 0 个，L5 0 个**。 [历史实测与口径复核](https://github.com/alex20230412-svg/global-trend-radar/issues/2#issuecomment-7164683992) · [Issue #6 正式审核](https://github.com/alex20230412-svg/global-trend-radar/issues/6#issuecomment-7167409077)

## 核查等级

| 等级 | 需要的证据 |
| --- | --- |
| L1 | 目标端点可达，记录准确地址和日期 |
| L2 | 逐源核实访问条款、robots、保留字段与期限、向个人私聊转发的权利 |
| L3 | 真实目标内容、结构和新鲜度已核实。只访问同一 API 的其他方法不能替代 |
| L4 | 审核后的默认分支在 Actions 环境成功运行并核验前三级证据，达到后才标 `VERIFIED` |
| L5 | 七天连续运行验证通过 |

## 本轮候选与保存权

| 适配器 ID | 范围与历史证据 | 保存与使用条件 |
| --- | --- | --- |
| `trends_my` | MY 搜索飙升。Claude 核验过 RSS 与新鲜度，历史 L1 + L3。量级是近似分档 | Google 提供 RSS 导出并允许按条款引用，日报注明 Google Trends。阶段 B 核实实际访问规则与最小字段的长期归档范围，配置为 `pending`。关联第三方新闻元数据单独审批。 [RSS 导出](https://support.google.com/trends/answer/3076011) · [引用条件](https://support.google.com/trends/answer/4365538) · [Google 服务条款](https://policies.google.com/terms) |
| `trends_sg`、`trends_id`、`trends_th`、`trends_ph`、`trends_vn`、`trends_us`、`trends_gb`、`trends_in`、`trends_jp`、`trends_kr`、`trends_tw`、`trends_hk`、`trends_au` | 同型 RSS。各地端点、新鲜度和原始语言仍待逐个核查 | 同一信号在各地的量级独立，报告按地区出现与时间比较。与 MY 一样默认 `pending`，需要逐地通过核查。 [Google Trends 数据说明](https://support.google.com/trends/answer/3076011) |
| `malaysiakini` | 马来西亚英文 RSS。历史 L1 + L3 | 条款保留编辑内容复制、复用权。申请适用权限前保持 `pending`。 [Malaysiakini 条款](https://www.malaysiakini.com/en/about/terms-of-service) |
| `malay_mail` | 马来西亚英文地区 RSS。官方列表提供入口，历史 L1 + L3 | RSS 订阅入口与长期存储条件分别核查。条款限制内容复制及再分发，暂设 `pending`。 [官方 RSS 列表](https://www.malaymail.com/rss) · [Malay Mail 条款](https://www.malaymail.com/terms/1000) |
| `fmt` | FMT 的 `cms.` 直连 RSS。历史 L1 + L3，含英文和马来文 | FMT 明示复制、再分发须获权利人同意。配置 `pending`。混合语种在缺乏条目语言标识时记 `und`。 [FMT 版权声明](https://www.freemalaysiatoday.com/disclaimers-copyright) |
| `bernama` | 英文 `/en/rssfeed.php`。历史 L1，Claude 看到列表缺少 `pubDate` 并报告编码问题。新鲜度还需验证 | 采用来源提供日期或留空，并以系统首次观测标示，按明显错码特征尝试无损解码。发行方提供 RSS，并保留内容复制和转发权，暂设 `pending`。 [官方 RSS 入口](https://rss.bernama.com/) · [Bernama 版权声明](https://www.bernama.com/en/copyrights.php) |
| `hn` | 官方 `topstories` 前 30 个 ID，逐条读取，保留排名与原始分数。历史只验证过 `maxitem`，该证据仅说明 API 主机可达 | API 文档开放访问。投稿标题与外链的长期归档、私聊转发仍需逐字段确认。保留 `pending`，不保存作者、正文、评论或个人资料。 [Hacker News API](https://github.com/HackerNews/API) · [Hacker News Guidelines](https://news.ycombinator.com/newsguidelines.html) |
| `bluesky` | `getTrendingTopics` 历史 L1 + L3。公开 AppView 提供匿名读取，`unspecced` 结构有变更风险 | 仅候选趋势名称、列表位次和话题链接，排除帖子、个人资料和推荐条目。具体使用及保留权未核实，默认 `pending`。 [Bluesky HTTP API](https://docs.bsky.app/docs/api/app-bsky-feed-get-feed) · [Bluesky 条款](https://bsky.social/about/support/tos) |
| `mastodon_tags` | `mastodon.social` 的标签趋势，历史 L1 + L3 | 仅一个实例。使用官方趋势接口，长期保留条件未核实，默认 `pending`。 [Mastodon API](https://docs.joinmastodon.org/methods/trends/) · [实例条款](https://mastodon.social/terms-of-service) |
| `mastodon_links` | 同一实例的热门链接。具体接口和数据待阶段 B 验证 | 标题可能来自第三方网站，默认 `pending`，不保存页面内容、预览、个人资料或帖子。 [Mastodon API](https://docs.joinmastodon.org/methods/trends/) · [实例条款](https://mastodon.social/terms-of-service) |
| `weather` | data.gov.my 的 MET Malaysia 天气警告。历史 L1 + L3，官方文档列明 CC BY 4.0，L2 已核授权，实跑另验当时 robots | `long_term` 可在批准后保存标题、来源链接、发布和有效时间。标注 MET Malaysia、许可证与摘录，气象独列。当前警告时间采用带时区值，官方返回无偏移量时按 MYT 解释，待真实样本核验。地震专用端点不在本轮。 [天气 API](https://developer.data.gov.my/realtime-api/weather.en) · [MET 开放数据](https://www.met.gov.my/info/data-terbuka/) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `gdelt` | DOC 2.0 以前连续两次连接超时 | 默认禁用，无自动探测、存储或热度权重。如获后续批准，才另行单次核验端点和字段授权。 [GDELT DOC 2.0](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) |

## 启用前的证据与覆盖缺口

- 阶段 B 先选 MY、少量已获许可的地区或本地 RSS。先核对准确端点、robots、格式、时间与使用权，留存证据日期及可访问的条款出处。只有能在私有 Git 长期保存并向本人的 Bot 私聊转发相关字段的来源，才通过审核 PR 将对应 `retention` 改为 `long_term`，并加入工作流的批准清单。Google Trends 关联条目权利须单独确认后才可开启 `retain_related`。删除 Git 文件后历史版本仍可能保留。
- 只采计数、标题、规范链接、时间、排名、分档等最少字段。广告跟踪参数与已知敏感查询键去除，新闻正文、社交帖子、账号或预览内容不入库。阶段 A 的合成数据不用于计算 L1–L5，真实响应不得提交到公开仓库。证据记录最少字段及计数，记录缺失、无数据、失败与可用的区别。
- 本轮 23 个接入候选若全开，每小时约 53 次数据请求，还需检查每个活跃域名的 robots.txt，偶发重试受限。实际 Actions 时延、robots 兼容和返回大小须以批准后的单次小范围试采结果为准。固定来源、禁重定向；遇 401/403 停止，同源 429 尊重 `Retry-After`，超出本次短等待预算则停止。同源按 robots 指令与客户端最小间隔串行。
- 目前的数据代表 Google 搜索飙升、特定媒体与独立社区的趋势。商品和消费主题只从这些信号识别，尚无销售量或电商热榜；马来西亚华文和专门马来文来源缺口仍在，本轮仅 FMT 候选混有部分马来文。TikTok、Facebook、Instagram、Threads、X 与其他大型平台没有接入。YouTube、Wikipedia、SAYS 和更多媒体留待另行核查。Harian Metro 的旧机器人规则不允许抓取，保持排除。
- 阶段 B 如遇 Bernama 的空日期或编码变化、Bluesky schema 变更、RSS 重定向或权利不明，记下来源 ID、时间、状态或错误码，并维持关停直至通过审核。通过默认分支 Actions 并完成 L1–L3 的来源才升 L4，七天通过后升 L5。历史调查与早期候选记录见 [原方案](PLAN.md)。
