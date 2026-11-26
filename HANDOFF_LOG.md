# HANDOFF_LOG

新记录写在最上面。

---

## 2026-11-26 · Claude · YouTube 任务单

- 早报 brief-v4 已合并（#27）。最新预览 `preview-1527-2026-11-26` 全部中文：App 写明用途，热门话题附搜索量，26/26 来源正常。
- YouTube：
  - 核实 [YouTube API 开发者政策](https://developers.google.com/youtube/terms/developer-policies)：非授权数据最多保存 30 天（III.E.4.d），不能用 API 数据计算衍生指标（III.E.4.h），必须显示 YouTube 服务条款链接并标明来源（III.A.1、III.F.2.a）。
  - 核实 [API 变更记录](https://developers.google.com/youtube/v3/revision_history)：2025-07-21 起 `mostPopular` 只来自音乐、电影、游戏榜。
  - 写成 Codex 任务单 [Issue #28](https://github.com/alex20230412-svg/global-trend-radar/issues/28)：只发送、不存储，独立一条消息，最多发一次，默认关闭。
- 下一步：
  - Owner 让 Codex 按 #28 开发，Claude 审核 PR；
  - 另外仍等 Owner 把 `RADAR_STAGE` 改为 `c-scheduled`。

---

## 2026-11-26 · Claude · 中文早报与阶段 C

- 新增 `radar/brief.py` 和 `preview` 动作（#17）。阶段 C 的 cron、开始时间自动记录、保活和容量限制（#18）。热修：开始时间写到了不允许的私库根目录（#19，影响约 3 分钟，没有写入任何数据）。
- Gemini 实测迭代：
  - key 空白和失败原因记录（#20）；
  - 输入先在代码里整理：体育合并、去重、限条数（#21）；
  - 防编造：地区由数据决定，丢弃没有编号的行，先用 Flash（#22）；
  - 模型超时就换下一个（#23；第一次提交误删 GeminiWriter，CI 拦下，修正后才合并）。
- 最新预览 `preview-1433-2026-11-26`：AI 版正常。还可以改进：Flash-Lite 偶尔把主题保留成英文小写；同一人物在不同栏目仍可能重复（相关标题不完全相同时去重不掉）。
- 等待 Owner 确认格式，并把 `RADAR_STAGE` 改为 `c-scheduled`。

---

## 2026-11-26 · Claude · 阶段 B 真实运行通过

- Owner 完成 6 步设置后，Claude 依次触发：`bind_chat`（第一次 `binding_private_start_required`，Owner 补发 `/start` 后 `ACK_SENT`）、collect（24/24，334 条）、`confirm_bind`（`BOUND`）、同小时 collect（跳过全部，`rows_added=0`）、report send（`SENT`，1 段）、同日 send（不重发）。
- Claude 以临时只读权限核对私库：manifest、run 审计、first-seen 分片、投递台账、日报快照都齐全。公开仓库只记录数量和状态。
- 实测每小时观测约 76 KB（gzip）。阶段 C 前需要处理容量策略和公开仓库 60 天无活动停用定时任务的问题。

---

## 2026-11-26 · Claude · 阶段 B 无凭证实测通过

- 依 Owner 指示合并 PR #10（Codex，T1–T5），并在 main 运行 `live-check` 5 次。发现并修复：当今大马英文和中文 RSS 及 MET API 地址变更（301）、中文 RSS 声明的语言错误、GDELT 读取超时（PR #11）；新增只含类名、位置和结构标签的失败诊断（PR #12）；连接超时放宽到 8 秒（PR #13）。
- 最后两次运行 24/24 来源正常，两次采集幂等，日报 1 段约 3,500 字，未降级。GDELT 从 GitHub runner 一直 `ConnectTimeout`，保持关闭。
- 会话代理禁止 AI 设置 environment、variables、secrets 和 Actions 权限，改由 Owner 一次完成（运行手册第二节）。私库已确认为 Private、`main` 存在、只有 README。
- 下一步：Owner 完成 6 步设置并按 Start 后，Claude 依次运行 collect、`bind_chat`、`confirm_bind`、report send，并用只读权限核对私库。费用 RM0。

---

## 2026-11-26 · Codex · Issue #9 阶段 B 准备

- 从 `main` 的 `5cedf11` 开 `codex/phase-b-sources`，记录 D-010。原有 23 个来源开启最少字段，14 个 Trends 开启相关新闻背景。当今大马中文 RSS 加入现有主机白名单范围，和英文版在独立媒体计数中合并。
- 实现 GDELT 的两个固定查询，5 秒同源间隔，生产配置保留关闭。其余华文来源因官方入口、访问或归档条件缺证据暂缓。 [来源证据表](docs/sources.md) · [华文调查](docs/chinese-sources.md)
- 实现仅 `workflow_dispatch`、仅 `main` 的 `live-check`，成功来源只联网探测一次，第二轮重播同一失败结果，核验无新增观测与校验和一致。Git 仓库和报告在 runner 临时目录，哨兵测试证明公开业务输出只有固定字段。
- 运行 Windows 本地 116 项离线测试、依赖检查、编译、差异检查和单段合成报告。真实数据环境的连通、内容和运行耗时留待合并后由 Claude 核验。无凭证实测先于 Owner 设置，详情见 [运行手册](docs/operations.md)。
- 合成报告新增中文新闻后，测试发现来源状态时间与观测不一致，且合成的中英文版被标记成同一语言。修正时间及语种后复验。
- 未触发 `live-check`，未开启 cron、改动阶段变量、操作 Secrets 或访问真实私库。Draft PR 与 Issue #9 提供本轮检查证据，等待 Claude 审核。 [任务单](https://github.com/alex20230412-svg/global-trend-radar/issues/9)

---

## 2026-11-26 · Claude · 阶段 A 收尾修订（PR #8）

- Owner 授权 Claude 本轮直接执行修订。为保持作者清晰、便于 Codex 复核，没有改动 PR #7 分支，而是开叠加在其上的 Draft PR #8（`claude/phase-a-fixes` → `codex/phase-a-trend-collection`）。
- 日报重写为单段精简格式（`radar/report.py`，`compact-v1`），排名与评分逻辑不变；排名条目新增 `geos`（本地榜）和 `context`（仅在 `retain_related` 批准后存在）。未核准来源不再触发「降级」。
- 「为什么热」从未接入的临时投影改为 `retain_related` 单一开关，删除 `Report.display_blocks` 及其测试，改为测试保留的相关报道只在话题下显示一次且正确转义。
- robots fixture 改用 2026-11-26 抓取的 9 个主机原文。阶段 B 手册拆成 Owner 与 AI 两栏。离线 CI 增加打印合成日报一步。
- 实际测试：PR #8 Linux CI `Ran 99 tests … OK`。本地缺 httpx、feedparser、protego、rapidfuzz 且无法安装，只跑了 delivery 测试与编译。第一次 CI 失败一项：合成样本的相关报道标题里含话题原文，导致去重断言计数为 2，已改样本文字。
- 未做：来源批准（需 Owner 决定）、阶段 C 的保活与容量策略（已写入 STATUS 待办）、PR #5 合并与 rebase。新增费用 RM0。当前 WAIT_OWNER。

---

## 2026-11-26 · Codex · PR #7 第一轮审核修订

- 同一分支修正来源审批、词条链接、坏条目容错、跨小时迟到和私有诊断。保留原来的批准范围，天气以外的来源仍为待核准。
- PR 只触发无凭证的 Linux 离线检查。真实工作流保留默认分支环境和两道批准关口。浏览器绑定仅需两个 Secret，并要求 Owner 看到私聊的通用消息才确认。完整步骤见 [运行手册](docs/operations.md)。
- 本地 94 项离线测试通过，另通过依赖一致性、编译和差异检查。Linux 运行、V1–V9 结果及 `python -m tools.sample_report` 生成的整份两段合成日报见 [PR #7](https://github.com/alex20230412-svg/global-trend-radar/pull/7)。
- V3 使用审核留言公开的 HN 原文规则、两站延迟值和历史结果重建样本。由于留言未附九份完整 robots 文件，没有用实时站点补取。P2 的可选新闻标题/媒体名展示已做离线投影，真实接入需 Owner 单独核准。
- PR #5 尚未合并，继续以其修订分支为基线。真实来源、Secret、cron 与合并均未触发。当前 WAIT_OWNER。 [Claude 审核](https://github.com/alex20230412-svg/global-trend-radar/pull/7#issuecomment-7168526931)

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
