# STATUS

最后更新 2026-11-26 MYT，Claude。

## 早报 v5 · 已派给 Codex（2026-11-26）

- Owner 确定整批改动（D-014），任务单见 [Issue #33](https://github.com/alex20230412-svg/global-trend-radar/issues/33)：
  - 等宽表格加折叠区，🆕 新上榜，YouTube 静音；
  - 周日周报，私库钥匙到期提醒，修跨栏重复和 AI 编造细节；
  - 维基百科（马来西亚），中国热议。
- 来源规则已改：公开、不需登录的来源都可以用，底线是不破解反爬机制、不直接读 robots.txt 禁止的网站。
- 流程：Codex 分 3 个 PR 提交，Claude 审核合并，发预览给 Owner 确认。

## YouTube 热门 · 已启用，真实预览通过（2026-11-26）

- 按 D-013 接入官方 YouTube Data API 马来西亚 `mostPopular`。条目来自音乐、电影和游戏榜。主早报送达后独立发送一条，视频元数据只在当次进程使用，不进入归档、公开日志或 Gemini。 [Issue #28](https://github.com/alex20230412-svg/global-trend-radar/issues/28) · [功能说明](docs/youtube.md)
- Windows Python 3.14.4 本地 160 项测试通过，包含原有 137 项和新增 23 项。合成端到端测试核对 Gemini 请求、私库 Mock 的每次写入和公开日志。样本的 YouTube 消息为 1 段、311 个 UTF-16 单元。真实 API、密钥和私聊投递留待后续预览。新增费用 RM0。
- Claude 审核通过并合并（PR #30）。审核时补了一处：开关关闭时 YouTube 部分完全不动作（不读台账、不写审计），配置格式错误时记为 `invalid_config`。CI 共 162 项通过。
- Owner 已填 `YOUTUBE_API_KEY`（20:12 MYT）。Claude 用 PR #31 启用。
- 真实预览 `preview-2014-2026-11-26`（run 45817775056）：公开日志显示 `report delivery=SENT parts=1`、`youtube status=ok items=18 sent=SENT`。
- Claude 核对私库：YouTube 台账只有 `payload_hash` 和 `delivery_state`，审计只有状态码和数量；全库搜索没有 YouTube 链接或页脚文字。之后每天 08:30 的早报后会接着发 YouTube 一条。 [设置步骤](docs/operations.md#youtube-申请-key审核合并后再做)

## 中文早报与阶段 C · 等待 Owner 确认并切换 `c-scheduled`（2026-11-26）

- Owner 反馈第一份日报「完全看不懂」，D-011 改为在 Telegram 发中文早报（`radar/brief.py`）。
  - **AI 版**：Gemini 免费层，先试 Flash，超时或出错就换 Flash-Lite。
  - **兜底版**：中文栏目加原文标题。
  - **代码负责、不交给模型的部分**：合并体育、去重、限制条数；地区名单只由代码按数据填写；没有真实条目编号的行一律丢弃。
- 4 次真实预览暴露的问题都已修复：体育刷屏、同一事件重复、模型编造约 35 国的地区名单、Flash 超时后没有换备用模型（PR #20–#23）。最新预览为 AI 版、`gemini-flash-lite-latest`、brief-v2，24/24 来源正常。
- 阶段 C 代码已合并（PR #18、#19）：
  - 每小时 :17 采集，08:30 MYT 发早报，只在 `RADAR_STAGE=c-scheduled` 时运行；
  - 首次计划采集自动记录开始时间；
  - `keepalive.yml` 防 60 天停用；
  - 每源新闻 30 条、相关报道 2 条，容量 700 MiB 预警、900 MiB 停止。
- 下一步：Owner 确认早报看得懂后，把 `RADAR_STAGE` 改为 `c-scheduled`。新增费用 RM0。

## 阶段 B · 真实私库与 Telegram 实测通过（2026-11-26）

- Owner 完成凭证设置（`radar-live` environment、两个 secret、`RADAR_STAGE=b-manual`、私库关闭 Actions）。
- 真实采集：24/24 来源正常，334 条观测写入私库。同一小时重跑跳过全部来源，`rows_added=0`，校验和不变。
- Telegram：`bind_chat` → Owner 确认收到 → `confirm_bind`，结果为 `BOUND`；chat_id 只存私库。日报 `smoke-2026-11-26` 1 段 `SENT`。同日再次 send 不重发，`attempts` 仍为 1。
- 第一次 `bind_chat` 找不到 `/start`。Owner 在 Bot 私聊补发 `/start` 后成功，原因未核实。
- 实测容量：每小时观测压缩后约 76 KB，约 1.8 MB/天。按此推算约 9 个月会到 512 MiB 停止阈值，阶段 C 前需要定归档策略。
- 下一步：Owner 批准阶段 C（开启每小时采集与 08:30 MYT 日报的 cron），另开 PR 处理。cron 仍为注释。新增费用 RM0。

## Claude 收尾修订（PR #8）

- 日报改为手机友好的单段格式（`compact-v1`）：每个话题只出现一次，用 🚀（附量级变化）和 🆕 标记，行尾带地区与分类标签，来源状态压成一行页脚。合成样本由 2 段约 5,600 字降为 1 段约 1,300 字。完整排名快照不变。
- 未核准或关闭的来源不再让日报显示「降级」；只有已启用来源失败或过旧才算降级。
- 「为什么热」改由 Trends 条目的 `retain_related` 单一开关控制：批准后相关报道标题、链接和媒体名随观测存入私库并自动显示在话题下方；未批准时既不保存也不显示。删除了未接入生产的临时展示投影。
- robots fixture 换成 9 个主机 2026-11-26 的原文，测试允许与禁止的 URL、具名爬虫分组和 crawl-delay。
- 阶段 B 首次手动运行拆成「Owner 点按钮、看 Telegram」与「AI 核对私库」两栏。
- 离线 CI 每次额外打印合成日报，供审核者直接看到格式。

## 审核修订

- 来源默认以审核后的 `enabled` 和 `long_term` 为准，可用可选名单缩小范围。已把未来审批步骤收敛为只改批准条目的 `retention`。本轮批准前只有天气具备归档资格。
- Trends 链接按地区和词生成。跳过坏条目并保存计数，超过半数坏项时来源失败。跨小时迟到触发采进实际小时，计划槽和延迟写入私有审计。
- 公开日志只显示状态。私有审计记录异常类名、模块、行号及适用的来源 ID 和 HTTP 状态。浏览器绑定保留两个 Secret，先向唯一候选私聊发送通用消息，再由 Owner 确认。
- Linux PR 测试仅用合成样本与 Mock，检查锁定 wheel 安装，不读取 Secrets 或 Environment。V3 根据审核公开的 HN 原文规则片段、延迟值和历史结论建模。审核留言缺九份完整原文，证据范围限于重建 fixture（PR #8 已换成原文）。P2 临时相关新闻投影已通过离线验证（PR #8 改为 `retain_related` 单一开关并删除投影）。
- 修订后本地 Windows Python 3.14.4 套件 94 项通过。V1–V9 的逐项证据、Linux Actions 运行和完整的两段合成日报见 PR #7。 [Draft PR #7](https://github.com/alex20230412-svg/global-trend-radar/pull/7)

| 已交付 | 阶段 A 证据 |
| --- | --- |
| 14 个地区 Google Trends、4 个本地 RSS、HN、Bluesky、Mastodon、MET 气象的适配器 | 合成样本及 Mock 测试。GDELT 默认关闭。 [覆盖与来源条件](docs/sources.md) |
| 内容去重、跨小时真实观测、同槽只补失败来源、校验和、源失败与漏跑记录 | 离线流水、校验拒绝和临时本地 Git 写入竞争验证。 |
| MY 热搜、其他地区热搜、NEW 与 RISING 标记、分类标签、本地新闻、社交平台与气象 | 单段精简中文日报（compact-v1）、话题去重、来源页脚与 MYT 离线验证。 |
| Telegram 私聊、完整条目分段、逐段落盘、429 及 UNKNOWN 恢复 | 离线模拟 API 和中断，未配置凭证或发送真实消息。 |
| 08:30 MYT 日报与每小时采集的工作流、私有健康记录 | 已测试 YAML 门禁、共享队列和默认无 cron。带真实数据或投递的 Actions 尚待批准后验证。 |

## 实际离线结果

```powershell
.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -q
.venv/Scripts/python.exe -X utf8 -m pip check
.venv/Scripts/python.exe -X utf8 -m compileall -q radar tests tools
git diff --check
```

PR #8 的 Linux CI（ubuntu-24.04、CPython 3.14.10、哈希锁定 wheel）为 `Ran 99 tests … OK`，[run 45738527426](https://github.com/alex20230412-svg/global-trend-radar/actions/runs/45738527426)。Claude 的本地环境缺少 httpx 等依赖且不能安装，只本地运行了 delivery 测试、编译和 `git diff --check`。

修订前初次阶段 A 交付为 73 项。修订后 94 项通过，约 1.91 秒，依赖一致性、编译与差异检查通过。13 个版本及 wheel 哈希固定，初次核对 PyPI 发行元数据时未返回生效漏洞公告。来源样本为合成或 Mock，实测来源仍为 L4 0 个、L5 0 个。阶段 A 新增费用 RM0。

## 阶段 B 和 C 待办

- Claude 审核、Owner 同意后合并本 PR。Claude 在 `main` 先做无业务凭证的实测，核对来源、新鲜度、同槽幂等与真实数据的一段日报。GDELT 结果单列，连通与后续审核均通过才启用。
- 全项通过后才通知 Owner 一次性设置 Bot 和专用 PAT。Owner 另行同意环境和阶段变量后，Claude 验证真实私聊和私库；凭证只留在 GitHub Environment。 [运行手册](docs/operations.md)
- 首 24 小时至少 20 个有效、持久化的计划采集槽，核对连续 3 天日报时间及第 7 天稳定性。
- 阶段 C 前处理两项长期运行问题：一是公开仓库 60 天无提交会停用定时任务，需要保活方案；二是私库容量。按估算每小时约 500 条观测，压缩后每天约 1 MB 级，加上 first-seen 分片持续增长，约一年会接近 512 MiB 停止阈值。阶段 B 先实测每小时实际字节数，再决定归档压缩或分片清理策略（未核实，仅估算）。 [凭证和首次手动测试](docs/operations.md)

华文覆盖目前仅有当今大马候选，主要社交平台或电商销量仍有缺口。GitHub 定时可能迟到、漏跑或因无活动停止。同一平台整体中断或 PAT 失效时，Telegram 告警可能无法安全提交。私库容量及 Git 历史删除的限制见运行手册。跨语言同义主题与全球绝对热度不在本轮能力范围。
