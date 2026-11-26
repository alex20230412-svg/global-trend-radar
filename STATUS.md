# STATUS

最后更新 2026-11-26 MYT，Codex。

## 当前阶段 A · WAIT_OWNER

根据 D-009 开发和离线验收。第一轮 Claude 审核修正在原分支 `codex/phase-a-trend-collection` 交付。PR #5 尚未合并，PR #7 继续以其最新修订 `a54ac7704febde6df2068ab95d7393db8eac759a` 为基线。等待 Owner 决定是否复审及是否单独批准阶段 B。 [PR #5](https://github.com/alex20230412-svg/global-trend-radar/pull/5) · [PR #7 审核及验收](https://github.com/alex20230412-svg/global-trend-radar/pull/7#issuecomment-7168526931)

## 审核修订

- 来源默认以审核后的 `enabled` 和 `long_term` 为准，可用可选名单缩小范围。已把未来审批步骤收敛为只改批准条目的 `retention`。本轮批准前只有天气具备归档资格。
- Trends 链接按地区和词生成。跳过坏条目并保存计数，超过半数坏项时来源失败。跨小时迟到触发采进实际小时，计划槽和延迟写入私有审计。
- 公开日志只显示状态。私有审计记录异常类名、模块、行号及适用的来源 ID 和 HTTP 状态。浏览器绑定保留两个 Secret，先向唯一候选私聊发送通用消息，再由 Owner 确认。
- Linux PR 测试仅用合成样本与 Mock，检查锁定 wheel 安装，不读取 Secrets 或 Environment。V3 根据审核公开的 HN 原文规则片段、延迟值和历史结论建模。审核留言缺九份完整原文，证据范围限于重建 fixture。P2 临时相关新闻投影已通过离线验证，生产接入等待单独批准。
- 修订后本地 Windows Python 3.14.4 套件 94 项通过。V1–V9 的逐项证据、Linux Actions 运行和完整的两段合成日报见 PR #7。 [Draft PR #7](https://github.com/alex20230412-svg/global-trend-radar/pull/7)

| 已交付 | 阶段 A 证据 |
| --- | --- |
| 14 个地区 Google Trends、4 个本地 RSS、HN、Bluesky、Mastodon、MET 气象的适配器 | 合成样本及 Mock 测试。GDELT 默认关闭。 [覆盖与来源条件](docs/sources.md) |
| 内容去重、跨小时真实观测、同槽只补失败来源、校验和、源失败与漏跑记录 | 离线流水、校验拒绝和临时本地 Git 写入竞争验证。 |
| MY 热门、监测地区、NEW 与 RISING、商品消费和 AI 科技、社交平台与气象 | 中文模板、原文语言、分级覆盖与 MYT 离线验证。 |
| Telegram 私聊、完整条目分段、逐段落盘、429 及 UNKNOWN 恢复 | 离线模拟 API 和中断，未配置凭证或发送真实消息。 |
| 08:30 MYT 日报与每小时采集的工作流、私有健康记录 | 已测试 YAML 门禁、共享队列和默认无 cron。带真实数据或投递的 Actions 尚待批准后验证。 |

## 实际离线结果

```powershell
.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -q
.venv/Scripts/python.exe -X utf8 -m pip check
.venv/Scripts/python.exe -X utf8 -m compileall -q radar tests tools
git diff --check
```

修订前初次阶段 A 交付为 73 项。修订后 94 项通过，约 1.91 秒，依赖一致性、编译与差异检查通过。13 个版本及 wheel 哈希固定，初次核对 PyPI 发行元数据时未返回生效漏洞公告。来源样本为合成或 Mock，实测来源仍为 L4 0 个、L5 0 个。阶段 A 新增费用 RM0。

## 阶段 B 和 C 待办

- 逐源补足授权及 L2 证据。目前只有 MET 气象明确允许按 CC BY 4.0 保留。MY 与全球核心榜仍需取得最少字段的长期保存及个人私聊转发依据。
- 分别批准真实手动采集、真实私聊和后续定时部署。在真实环境确认来源可用、私库读写、Telegram 投递、8 分钟上限、并发和环境隔离。
- 首 24 小时至少 20 个有效、持久化的计划采集槽，核对连续 3 天日报时间及第 7 天稳定性。 [凭证和首次手动测试](docs/operations.md)

覆盖尚无马来西亚华文专源、主要社交平台或电商销量。GitHub 定时可能迟到、漏跑或因无活动停止。同一平台整体中断或 PAT 失效时，Telegram 告警可能无法安全提交。私库容量及 Git 历史删除的限制见运行手册。跨语言同义主题与全球绝对热度不在本轮能力范围。
