# STATUS

最后更新 2026-11-26 MYT，Claude。

## 当前阶段 A · WAIT_OWNER

根据 D-009 开发和离线验收。Codex 的阶段 A 在 PR #7（`codex/phase-a-trend-collection`）。Owner 于 2026-11-26 授权 Claude 执行收尾修订，交付为叠加在 PR #7 之上的 Draft PR #8（`claude/phase-a-fixes`）。PR #5 尚未合并。等待 Owner 决定来源批次、「为什么热」开关、合并顺序及是否批准阶段 B。 [PR #5](https://github.com/alex20230412-svg/global-trend-radar/pull/5) · [PR #7](https://github.com/alex20230412-svg/global-trend-radar/pull/7) · [PR #8](https://github.com/alex20230412-svg/global-trend-radar/pull/8)

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

- 逐源补足授权及 L2 证据。目前只有 MET 气象明确允许按 CC BY 4.0 保留。MY 与全球核心榜仍需取得最少字段的长期保存及个人私聊转发依据。
- 分别批准真实手动采集、真实私聊和后续定时部署。在真实环境确认来源可用、私库读写、Telegram 投递、8 分钟上限、并发和环境隔离。
- 首 24 小时至少 20 个有效、持久化的计划采集槽，核对连续 3 天日报时间及第 7 天稳定性。
- 阶段 C 前处理两项长期运行问题：一是公开仓库 60 天无提交会停用定时任务，需要保活方案；二是私库容量。按估算每小时约 500 条观测，压缩后每天约 1 MB 级，加上 first-seen 分片持续增长，约一年会接近 512 MiB 停止阈值。阶段 B 先实测每小时实际字节数，再决定归档压缩或分片清理策略（未核实，仅估算）。 [凭证和首次手动测试](docs/operations.md)

覆盖尚无马来西亚华文专源、主要社交平台或电商销量。GitHub 定时可能迟到、漏跑或因无活动停止。同一平台整体中断或 PAT 失效时，Telegram 告警可能无法安全提交。私库容量及 Git 历史删除的限制见运行手册。跨语言同义主题与全球绝对热度不在本轮能力范围。
