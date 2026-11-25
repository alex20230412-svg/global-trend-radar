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

D-007 仅约束当前阶段，不取消长期自动化目标。P-001 至 P-008 及后续技术提议仍待批准；验证周期和实际商业试点尚未获批。

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
- 独立 Telegram Bot 与频道

## 否决

| 编号 | 日期 | 方案 | 理由 |
| --- | --- | --- | --- |
| R-001 | 2026-11-25 | 使用 Reddit API / RSS | Reddit 已于 2026-10-31 停止受理新 API 申请，2026-11-13 关闭 RSS |
| R-002 | 2026-11-25 | 在私有仓库运行采集 Actions | 与其他私有仓库共用免费额度，用完会一起暂停 |
| R-003 | 2026-11-25 | 使用 Cloudflare R2 | 需要绑定付款方式 |
