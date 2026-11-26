# DECISIONS

状态说明：**已确认** = Owner 已明确同意或已执行；**提议** = 等待讨论，不得擅自实施；**否决** = 已放弃，保留理由。

## 已确认

| 编号 | 日期 | 决定 | 依据 |
| --- | --- | --- | --- |
| D-001 | 2026-11-25 | 新增费用为 RM0；任何付费项、任何对其他现有项目的写入默认不授权 | Owner 原始要求 |
| D-002 | 2026-11-25 | 使用两个独立仓库：公开 `global-trend-radar`（代码与文档），私有 `global-trend-radar-data`（数据） | Owner 已按此新建两个仓库 |
| D-003 | 2026-11-25 | 项目名称为 Global Trend Radar（全球热点雷达） | Owner 已按此命名仓库 |
| D-004 | 2026-11-25 | 所有进度、决定、测试结果、问题都记录在本仓库；改动走分支 + Draft PR，由 Owner 合并 | Owner 原始要求第 9 条 |
| D-005 | 2026-11-25 | 项目不限行业，先收集全球及马来西亚的流行趋势，优先寻找可由 AI 自动化的商业机会，不预选变现行业 | [Owner 决定](https://github.com/alex20230412-svg/global-trend-radar/issues/4#issuecomment-7167038713) |
| D-006 | 2026-11-25 | 资讯暂时仅供私人使用，不授权公开频道或对外发布 | [Owner 决定](https://github.com/alex20230412-svg/global-trend-radar/issues/4#issuecomment-7167038713) |
| D-007 | 2026-11-25 | 当前验证阶段由 Owner 手动触发 AI 收集；暂不开发，不授权定时任务、部署或实际经营试点 | [Owner 决定](https://github.com/alex20230412-svg/global-trend-radar/issues/4#issuecomment-7167038713) |
| D-008 | 2026-11-25 | 禁止两个 AI 自动循环对话；讨论由 Owner 控制，完成后 WAIT_OWNER | Owner 在 ChatGPT 会话原话：「不要让 AI 自动循环对话」；[ChatGPT 代录](https://github.com/alex20230412-svg/global-trend-radar/issues/2#issuecomment-7165465613)，[Claude 确认](https://github.com/alex20230412-svg/global-trend-radar/issues/2#issuecomment-7165568273) |
| D-009 | 2026-11-26 | 授权第一轮阶段 A，按 Issue #6 正式审核开发、使用合成样本与 Mock 离线测试、提交 Draft PR 后等待 Claude 独立审核和 Owner 决定。分别批准阶段 B 手动真实验证及阶段 C 定时运行验收。继续保持 RM0、私人使用、双仓库隔离及禁止 AI 自动循环，健康记录只写专用私库。 | Owner 2026-11-26 在 Codex 会话中的明确授权及 [Issue #6 审核意见](https://github.com/alex20230412-svg/global-trend-radar/issues/6#issuecomment-7167409077) |
| D-010 | 2026-11-26 | 全部现有候选的最少字段获 Owner 批准用于个人私聊与长期保存。新增来源须为官方 RSS 或 API、robots 允许且只采元数据。14 个 Google Trends 地区启用 `retain_related` 与「为什么热」。Claude 已依授权合并 PR #5、#7、#8。阶段 B 先由 Claude 在经审核的 `main` 无凭证实测，确认可用后才安排 Owner 配置 Telegram Token 和私库 PAT。GDELT 在 Actions 连通证据出现前保持生产关闭。 | [Issue #9 记录的 Owner 决定与任务单](https://github.com/alex20230412-svg/global-trend-radar/issues/9) |
| D-011 | 2026-11-26 | Owner 表示第一份日报「完全看不懂」，并让 Claude 安排阶段 C（「你去安排」）。Telegram 改发中文早报：有 `GEMINI_API_KEY` 时由 Gemini 免费层只根据当天条目整理，否则发白话中文原文标题版；详细版只存私库。阶段 C 开启每小时采集和 08:30 MYT 日报的 cron，只在 `RADAR_STAGE=c-scheduled` 时运行；首次计划采集自动记录开始时间；公开仓库用 API 保活；每源新闻 30 条、相关报道 2 条，容量阈值 700/900 MiB。 | [Issue #16](https://github.com/alex20230412-svg/global-trend-radar/issues/16) |
| D-012 | 2026-11-26 | Owner：「这版我看得懂了，但是里面只有新闻，我还要最新的资讯，现在最流行的是什么，最热门的话题是什么？」早报改为以流行为主：先列马来西亚最热门的搜索话题（附搜索量），再列全球热议、Apple Music 和 App Store 马来西亚榜，然后才是新闻、天气和生意线索。新增官方免费的 Apple 榜单来源；YouTube 热门待 Owner 提供 key。TikTok、Facebook、Instagram、X 没有免费合法的官方接口，暂不接入。 | [Issue #16](https://github.com/alex20230412-svg/global-trend-radar/issues/16) |
| D-013 | 2026-11-26 | Owner：「我需要YouTube 的资讯，你把这个开发写去GitHub 然后我叫codex做。codex做好了你审核了，才接进去现在的系统」。接入 YouTube 马来西亚热门（官方 Data API，`chart=mostPopular`，目前只含音乐、电影、游戏）。YouTube 开发者政策规定这类数据最多保存 30 天，所以**只发送、不存储**：早报运行时取一次，作为独立一条 Telegram 消息发出，不写进私库、公开日志或 Gemini 输入；标题保持原文，不翻译、不计算衍生指标。由 Codex 开发，Claude 审核后合并（默认关闭），Owner 填 `YOUTUBE_API_KEY` 后由 Claude 开启并实测。取代 D-012 中「YouTube 待 Owner 提供 key」的说法。 | [Issue #28](https://github.com/alex20230412-svg/global-trend-radar/issues/28) |
| D-014 | 2026-11-26 | Owner：「不符合我们『只用合法来源』的规则，这条规则删除」。来源规则改为：公开、不需登录即可访问的来源都可以用，包括非官方接口和第三方在 GitHub 公开的存档。底线保留（Claude 不会越过）：不破解登录、验证码、签名或反爬机制；robots.txt 明确禁止的网站不直接读取（例如微博、知乎本站）；每个来源每小时最多一次；不收集个人资料。同批确定早报 v5：等宽表格加折叠区、🆕 新上榜、YouTube 静音、周日周报、钥匙到期提醒、修重复和编造细节、维基百科（马来西亚）、中国热议（微博和知乎存档、百度和 B站核查后再接、中新网 RSS）；不做自动置顶。 | [Issue #33](https://github.com/alex20230412-svg/global-trend-radar/issues/33) |
| D-015 | 2026-11-27 | Owner：「你在去找看中国的资讯，现在的多数是新闻。我要的是知道当下在流行什么?」看过方案后：「1.不需要汽车 2.另发一条，早报里的中国热议也放去中国那条」。早报不再放中国栏，改为在早报之后静音另发一条「🇨🇳 中国在流行」，内容是中国热议 8 条、百度电视剧 5、电影 3、小说 3、Apple 中国区歌曲 5、App 5。百度榜和百度热搜是同一个公开接口（robots.txt 返回 404，不需要登录或签名）；游戏榜不存在；不做汽车榜。 | [PR #47](https://github.com/alex20230412-svg/global-trend-radar/pull/47) |

D-007 保留为之前手动验证阶段的历史决定。D-009 取代其中「暂不开发」的限制，生效范围为阶段 A。P-001 至 P-008 保留为历史提议，只有 D-009 所引用的修订范围获批。本轮不授权商业试点。

D-009 审核修订允许 PR 触发不带凭证的离线测试。真实流程仍使用受审默认分支并受阶段闸门限制。来源批准以审核的配置为准，运行变量只能缩小范围。D-010 记录随后批准的新闻背景与阶段 B 顺序。新闻网站的转载和再分发条款继续适用，Owner 选择个人私聊和最少字段使用。 [PR #7 审核意见](https://github.com/alex20230412-svg/global-trend-radar/pull/7#issuecomment-7168526931)

## 提议（待讨论）

| 编号 | 提议 | 提议方 | 理由摘要 | 讨论 |
| --- | --- | --- | --- | --- |
| P-001 | 不部署 TrendRadar，自建轻量 Python 采集器，只借用成熟库 | Claude | TrendRadar 热榜依赖第三方 newsnow 接口、偏中国平台、Actions 部署需每 7 天签到、历史存储需 S3/R2 | PLAN §3 |
| P-002 | 采集运行在公开仓库的 GitHub Actions，每小时一次（非整点），每次不超过 3 分钟 | Claude | 公开仓库标准 runner 免费，不占私有仓库共享额度 | PLAN §5 |
| P-003 | 原始数据存私有数据仓库的 Releases；Git 只存小型汇总 | Claude | 不限总容量、可单独删除、不膨胀 Git 历史 | PLAN §5 |
| P-004 | 第一版不使用大模型，摘要用模板 | Claude | 免费 AI 选项减少（GitHub Models 已下线）；结果可复现 | PLAN §5 |
| P-005 | 话题归并用硬线索 + 多语言向量（model2vec potion-multilingual-128M） | Claude | 中英马三语标题字面不重合，只比标题不可靠 | PLAN §7 |
| P-006 | 日报 09:00 与 20:00 MYT；升温提醒每天最多 5 条；23:00–07:00 不推送 | Claude | 先避免打扰，运行一周后再调 | PLAN §9 |
| P-007 | 全球榜覆盖 12 地：US、GB、IN、JP、KR、TW、HK、SG、ID、TH、PH、AU | Claude | 兼顾亚洲邻国，不只靠美国或中国 | PLAN §9 |
| P-008 | X Trends（约 US$7.4/月）默认不开 | Claude | 违反 RM0 | PLAN §4 |

## 待 Owner 提供

- 不预选行业（D-005）；后续根据 Owner 对真实资讯的反馈调整优先级。
- GitHub Billing 设置确认
- 阶段 B 无凭证实测通过后，由 Claude 统一通知 Owner 创建独立 Telegram Bot 与专用私库 PAT。

## 否决

| 编号 | 日期 | 方案 | 理由 |
| --- | --- | --- | --- |
| R-001 | 2026-11-25 | 使用 Reddit API / RSS | Reddit 已于 2026-10-31 停止受理新 API 申请，2026-11-13 关闭 RSS |
| R-002 | 2026-11-25 | 在私有仓库运行采集 Actions | 与其他私有仓库共用免费额度，用完会一起暂停 |
| R-003 | 2026-11-25 | 使用 Cloudflare R2 | 需要绑定付款方式 |
