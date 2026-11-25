# STATUS

最后更新 2026-11-26 MYT，Codex。

## 当前阶段 A · WAIT_OWNER

根据 D-009 开发和离线验收。交付分支为 `codex/phase-a-trend-collection`，基于未合并的 PR #5 最新修订 `a54ac7704febde6df2068ab95d7393db8eac759a`。新 Draft PR 以 PR #5 的分支为基线，保留 D-005 至 D-008。等待 Claude 独立审核及 Owner 单独批准阶段 B。 [PR #5](https://github.com/alex20230412-svg/global-trend-radar/pull/5) · [Issue #6 正式审核](https://github.com/alex20230412-svg/global-trend-radar/issues/6#issuecomment-7167409077)

| 已交付 | 阶段 A 证据 |
| --- | --- |
| 14 个地区 Google Trends、4 个本地 RSS、HN、Bluesky、Mastodon、MET 气象的适配器 | 合成样本及 Mock 测试。GDELT 默认关闭。 [覆盖与来源条件](docs/sources.md) |
| 内容去重、跨小时真实观测、同槽只补失败来源、校验和、源失败与漏跑记录 | 离线流水、校验拒绝和临时本地 Git 写入竞争验证。 |
| MY 热门、监测地区、NEW 与 RISING、商品消费和 AI 科技、社交平台与气象 | 中文模板、原文语言、分级覆盖与 MYT 离线验证。 |
| Telegram 私聊、完整条目分段、逐段落盘、429 及 UNKNOWN 恢复 | 离线模拟 API 和中断，未配置凭证或发送真实消息。 |
| 08:30 MYT 日报与每小时采集的工作流、私有健康记录 | 已测试 YAML 门禁、共享队列和默认无 cron。真实 Actions 尚待批准后验证。 |

## 实际离线结果

```powershell
.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -q
.venv/Scripts/python.exe -X utf8 -m pip check
.venv/Scripts/python.exe -X utf8 -m compileall -q radar tests tools
git diff --check
```

Windows x64 本地 Python 3.14.4 的最终离线套件 73 项通过，约 1.85 秒。依赖一致性、编译与差异检查通过。13 个版本及 wheel 哈希固定。查询各锁定发行版时，PyPI JSON 中未返回生效漏洞公告。全部来源样本为合成或 Mock，实测来源仍为 L4 0 个、L5 0 个。阶段 A 新增费用 RM0。

## 阶段 B 和 C 待办

- 逐源补足授权及 L2 证据。目前只有 MET 气象明确允许按 CC BY 4.0 保留。MY 与全球核心榜仍需取得最少字段的长期保存及个人私聊转发依据。
- 分别批准真实手动采集、真实私聊和后续定时部署。在真实环境确认来源可用、私库读写、Telegram 投递、8 分钟上限、并发和环境隔离。
- 首 24 小时至少 20 个有效、持久化的计划采集槽，核对连续 3 天日报时间及第 7 天稳定性。 [凭证和首次手动测试](docs/operations.md)

覆盖尚无马来西亚华文专源、主要社交平台或电商销量。GitHub 定时可能迟到、漏跑或因无活动停止。同一平台整体中断或 PAT 失效时，Telegram 告警可能无法安全提交。私库容量及 Git 历史删除的限制见运行手册。跨语言同义主题与全球绝对热度不在本轮能力范围。
