# 马来西亚 YouTube 热门

Global Trend Radar 使用 YouTube API Services。此功能是供 Owner 一人使用的私人客户端。启用前，Owner 须阅读并同意本页的隐私说明及 YouTube 服务条款。 [YouTube 服务条款](https://www.youtube.com/t/terms) · [Google 隐私权政策](https://policies.google.com/privacy)

## 来源与显示

- 只使用官方 YouTube Data API v3 的 `videos.list`，参数为 `chart=mostPopular` 和 `regionCode=MY`。自 2025-07-21 起，此接口的榜单条目来自热门音乐、电影和游戏榜。 [接口](https://developers.google.com/youtube/data/reference/rest/v3/videos/list) · [变更记录](https://developers.google.com/youtube/data/revision_history#july-10-2025)
- 每次最多请求 25 条，仅请求视频 ID、标题、频道名、分类 ID 和观看数。标题与频道名保留原文，分组按固定分类 ID，组内按 API 返回顺序，每组默认最多 5 条。观看数仅作显示格式转换。只发送一条 Telegram 消息，必要时省略末尾条目。页脚标注 YouTube 来源及条款，点击视频链接前往 YouTube。
- 每次通过 `videos.list` 请求使用 1 个配额单位。Google 为项目提供默认配额，常用端点合计每天 10,000 单位，按太平洋时间午夜重置。本项目只用免费配额，配额不足时跳过该次 YouTube 消息。 [配额说明](https://developers.google.com/youtube/data/determine_quota_cost)

## 隐私与保留

- 仅在主早报送达后的 `send`、`preview` 或 `resume` 中取数。项目专用 API 密钥仅由报告作业通过请求头提交给 `www.googleapis.com`。YouTube 功能不采集 Owner 的 YouTube 用户资料、登录信息、账号授权、设备信息或 Cookie。API 返回的频道名称是公开视频元数据。
- 视频字段仅在当次报告进程内用于生成单独的 Telegram 消息，不进入 Gemini、日报档案、观测、排名、后台缓存或公开日志。非授权 API 数据的临时存储受 30 日上限限制，项目的归档用 Git 历史不适合保存这些字段。 [YouTube API 开发者政策](https://developers.google.com/youtube/terms/developer-policies)
- 报告通过已绑定的 Telegram 私聊交付。已发消息可能留在 Owner 的 Telegram 聊天记录中，由 Owner 在 Telegram 管理和删除。项目只持久化投递状态、消息的哈希以及状态码和数量，无法从这些记录恢复消息正文。
- 同一早报编号的 YouTube 投递台账一旦存在，后续作业跳过取数和投递。API 或 Telegram 故障均不会改变主早报状态。公开日志仅记录 `youtube status=<code> items=<n> sent=<state>`。

## 启用流程

配置默认关闭。Claude 按 Issue #28 审核并在通过后依既有授权合并。Owner 填好专用密钥后，Claude 另开 PR 启用，并用一次 `preview` 实测。当前只有离线验证。 [Issue #28](https://github.com/alex20230412-svg/global-trend-radar/issues/28) · [申请 key 步骤](operations.md#youtube-申请-key审核合并后再做)
