# HANDOFF_LOG

新记录写在最上面。

---

## 2026-11-26 · Codex · 第一轮阶段 A

- Owner 明确批准 Issue #6 审核后的离线开发。完整读取项目记录、方案、Issue #6 与 PR #5 修订。分支 `codex/phase-a-trend-collection` 以 PR #5 的 `docs/owner-direction-20261125` 最新提交 `a54ac7704febde6df2068ab95d7393db8eac759a` 为基线，支持独立评审第一轮差异。
- 实现 HTTP 来源约束、适配器、小时观测和失败补齐、可解释评分、中文报告、Telegram 逐段状态机及私有健康。运行门禁只认公开代码仓库的默认 `main` 与专用私有数据仓库，源码中两条 cron 仍为注释。开源候选未直接移植代码。 [开源记录](docs/opensource.md)
- 实际测试为 `.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -q`，73 项通过。另执行 `pip check`、`compileall -q radar tests tools`、`git diff --check` 和 PyPI 固定版本的公告核对。所有业务样本由合成数据或 Mock 构成，Git 并发测试使用本地裸仓库。
- 初次哈希安装缺少 AnyIO 的传递依赖，补锁 typing-extensions 后安装通过。初次工作流测试发现 pip 参数中的冒号令 YAML 解析失败，改用折叠标量后通过。Windows 受限沙箱拦截 Git 的 MSYS 子进程，获准在沙箱外复跑同一本地离线测试，非强推竞争测试通过。
- 尚未证实真实来源、私库和 Telegram 可用，L4/L5 均为 0。核心来源长期归档权限待核实，仅天气已找到明确许可。消息 `UNKNOWN` 会暂停自动续发。GitHub 整体停摆、凭证失效、定时延迟及容量有明确运维边界。 [来源证据](docs/sources.md) · [运行手册](docs/operations.md)
- 阶段 A 新增费用 RM0。未访问真实数据仓库、运行真实采集、配置 Secrets、启用 cron、发送 Telegram 或合并 PR。交付 Draft 后等待 Claude 独立审核与 Owner 的阶段 B 指令。

---

## 2026-11-25 · ChatGPT · PR #5 文档复核修正

- Owner 转达 Claude 审核发现；核对原分支文件及 Issue #2 后确认：DECISIONS.md、STATUS.md 表格被空行截断，STATUS.md 沿用旧 VERIFIED 数量，D-008 引用未区分 Owner 原话与 AI 代录。
- 修正表格连续性、如实注明旧口径与拟议 L4 口径（0 个达到 L4）、注明 Owner 原话及代录/确认出处。旧来源证据表保留待批准更新，不擅自批准新标准。
- 仅修正文档；方向、授权、费用与 WAIT_OWNER 状态不变。

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
