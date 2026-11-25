# HANDOFF_LOG

新记录写在最上面。

---

## 2026-11-25 · ChatGPT · Owner 方向决定

- 已在 [Issue #4](https://github.com/alex20230412-svg/global-trend-radar/issues/4#issuecomment-7167038713) 代录 Owner 原话；确认不限行业、优先自动化商机、暂时私人使用、手动触发收集。
- 仅在独立分支整理方向文档并提交 Draft PR；不改 main、不开发、不启用任何任务、不支出、不自动开启讨论。
- 验证周期、报告格式、具体商业试点及技术提议尚待 Owner 决定。当前 WAIT_OWNER；下一次仅按 Owner 手动指令行动。
- 测试：仅文档变更，无运行代码或数据采集测试；费用影响 RM0。

---

## 2026-11-25 · Claude · 独立调查与初始文档

**做了什么**

- 阅读前一版方案（ChatGPT，2026-10-31 讨论，2026-11-25 整理的交接报告），逐项重新核实。
- 调查开源项目（TrendRadar 等）、各数据来源最新条款与免费额度、免费运行与存储方案。
- 实测接口：Google Trends Trending Now RSS（MY）、Bluesky trending topics、Mastodon trends、Hacker News API、Malaysiakini RSS，均返回正常。
- 写成 docs/PLAN.md 与 docs/sources.md，并建立 AGENTS.md、PROJECT_MEMORY.md、STATUS.md、DECISIONS.md。

**发现的重要变化（与前一版方案相比）**

- Reddit：2026-10-31 起不再受理新 API 申请，2026-11-13 关闭 RSS，2027-03 关闭剩余公开 API。
- YouTube：mostPopular 自 2025-07-21 起只含音乐、电影、游戏，不再等于 Trending。
- X API：全面按次付费，Trends 每次 US$0.010。
- GitHub Models：2026-07-30 已下线。
- 私有仓库 Actions 免费额度为所有私有仓库共用，用完即暂停。

**遇到的问题**

- 前一版方案的 ChatGPT 分享链接无法打开，只能依据 Owner 上传的交接报告。
- Reddit 在测试用的云端浏览器中被拦截，未能实测（结论来自公开报道）。
- GDELT DOC API 从云端浏览器请求超时，需在 Actions 环境重测。
- Harian Metro 的 RSS 被 robots.txt 禁止抓取，已排除。
- 马来西亚华文媒体尚未找到可确认的官方 RSS。

**下一步**

1. Owner 审核并合并本 PR。
2. 三方在 Issues 里讨论 DECISIONS.md 的提议项。
3. Owner 完成阶段 0 待办（Billing 确认、新 Bot），并授权进入阶段 1。
