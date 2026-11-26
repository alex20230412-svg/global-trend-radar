# 阶段 B 启用与阶段 C 运行手册

执行顺序依据 D-010。Claude 已经依 Owner 授权将 PR #5、#7、#8 合并进 `main`。这次的来源与无凭证工作流由 Claude 审核，Owner 同意后才合并。阶段 C 的 cron 激活另行审批。 [Issue #9](https://github.com/alex20230412-svg/global-trend-radar/issues/9)

## 一、Claude 先做无凭证实测

1. 审核通过并合并后，在 **Radar live check → Run workflow → main** 手动运行，保留运行链接和固定格式汇总。该作业用公开仓库标准 runner，独立并发组和临时本地 Git，设有 10 分钟上限。 [live-check 工作流](https://github.com/alex20230412-svg/global-trend-radar/actions/workflows/live-check.yml)
2. 核对每个启用来源的 `status`、`count`、`skipped`、HTTP 和新鲜度。同一小时两次调用采集流程，第二次跳过已成功的来源，检查观测文件校验和一致。单列检查 GDELT 的试探结果。GDELT 生产配置只有确认 Actions 连通并在后续审核中更新后才能开启。
3. 查报告是否为一段、是否降级、各栏目和「为什么热」计数是否合理。报告和观测只在当次 runner 本地临时目录生成。公开证据只引用状态与数字，合成日报由 PR 离线 CI 展示。来源失败、过旧、覆盖不足或格式不符时，按 Issue #9 退回修复。通过者按来源证据表记载日期与适用的等级。 [来源证据表](sources.md)

本步骤不需要业务凭证、environment 或 `RADAR_STAGE`。实际执行前无须 Owner 填写任何东西。

`source` 行的 `newest_age_min` 按最近有效发布日期计算，GDELT 用索引时间，无日期时为 `-`。合法的气象空结果可接受，表示该次未见警告。 `report` 行的 `chars` 为每段解析后的 UTF-16 单元数，`fresh` 计展示中标为新出现或升温的趋势，`with_context` 计显示相关新闻背景的条目，`platforms` 计有内容的平台栏目。GDELT 探测默认随手动检查执行，单列结果不影响已启用来源的报告与验收。

## 二、全项实测通过后，Owner 一次配置

2026-11-26 无凭证实测已通过（见 [来源证据表](sources.md) 的实测记录）。会话代理禁止 AI 读写仓库的 environment、variables、secrets 和 Actions 权限设置，所以下面全部由 Owner 在浏览器或手机完成。私库已由 Claude 确认为 Private、默认分支 `main`。

| 步骤 | Owner 操作 |
| --- | --- |
| 1 | Telegram 打开 [@BotFather](https://t.me/BotFather) → `/newbot` → 取名 → 用户名以 `bot` 结尾 → 复制 BotFather 给的 Token。 |
| 2 | [新建 fine-grained PAT](https://github.com/settings/personal-access-tokens/new)：名称随意，期限选最长（1 年），**Repository access → Only select repositories → `global-trend-radar-data`**，**Repository permissions → Contents → Read and write**，生成后复制。 |
| 3 | [Environments](https://github.com/alex20230412-svg/global-trend-radar/settings/environments) → **New environment** 名称 `radar-live` → **Deployment branches and tags → Selected branches and tags → Add rule → `main`** → **Add environment secret** 两个：`TELEGRAM_BOT_TOKEN`（第 1 步的 Token）、`DATA_REPO_TOKEN`（第 2 步的 PAT）。 |
| 4 | [Actions variables](https://github.com/alex20230412-svg/global-trend-radar/settings/variables/actions) → **New repository variable**：`RADAR_STAGE` = `b-manual`。 |
| 5 | [私库 Actions 设置](https://github.com/alex20230412-svg/global-trend-radar-data/settings/actions) → **Disable actions** → Save。 |
| 6 | 最后在 Telegram 打开新 Bot 的私聊，按 **Start**（发送 `/start`），然后马上告诉 Claude「好了」。绑定窗口为 15 分钟。 |

Token 和 PAT 只填在 GitHub 页面里，**不要贴到任何对话**。

## 三、Claude 验证真实私聊与私库

1. Owner 设好 `RADAR_STAGE=b-manual` 后，来源默认由审核后的 `enabled: true` 与 `retention: long_term` 控制。`RADAR_APPROVED_SOURCES` 只用于缩小范围，通常留空。执行受审 `main` 的 **Radar collect**，并依测试顺序核对同槽重跑与不同时槽的真实观测。 [Radar collect](https://github.com/alex20230412-svg/global-trend-radar/actions/workflows/collect.yml)
2. 通过 Owner 授权且由 GitHub 识别为仓库 Owner 的会话发起 `bind_chat`。Owner 在自己的 Bot 私聊看到通用确认后告知 Claude，再用同一身份在 30 分钟内发起 `confirm_bind`。只有 `BOUND` 才可继续。若无法以 Owner 身份操作，相应绑定动作交由 Owner 点击。绑定存在多个候选或收件人不明时暂停核对。 [Radar report](https://github.com/alex20230412-svg/global-trend-radar/actions/workflows/report.yml)
3. 发起 `report send`，由 Owner 确认收到私聊。经单独授权的临时只读访问核对专用私库的观测、校验和、来源状态和投递回执，再撤去只读访问。用同日重跑确认已发送段数不增加。公开报告只记录数量和状态。

如出现 `RATE_LIMITED`，按私有台账的 `retry_at` 等待。若为 `UNKNOWN` 或 `SENDING`，按下方操作核对。临时跑仍遵守 RM0 和来源条款。

## YouTube 申请 key（审核合并后再做）

请等 Claude 审核合并后发出设置通知，再按以下步骤操作。启用前请阅读并同意本功能的隐私说明和 YouTube 服务条款。 [YouTube 功能说明](youtube.md)

1. 在 Google Cloud Console **新建**项目，例如 `trend-radar-youtube`。 [Google Cloud Console](https://console.cloud.google.com/)
2. 进入 **API 和服务 → 库**，搜索 **YouTube Data API v3**，选择 **启用**。
3. 进入 **凭据 → 创建凭据 → API 密钥**。编辑此密钥，在 **API 限制 → 限制密钥** 中只选 **YouTube Data API v3** 并保存。 [Google Cloud 密钥指南](https://docs.cloud.google.com/docs/authentication/api-keys)
4. 不开启结算，也不启动免费试用。 [YouTube API 配额](https://developers.google.com/youtube/data/determine_quota_cost)
5. 在 GitHub 项目的 **Settings → Environments → radar-live → Add environment secret** 新增 `YOUTUBE_API_KEY`。密钥只填写到 GitHub 设置页。 [Environments 设置](https://github.com/alex20230412-svg/global-trend-radar/settings/environments)

填好后告诉 Claude，让其另开 PR 将 `config/youtube.yaml` 的 `enabled` 改为 `true`，通过审批后用 **Radar report → preview** 验证两条独立的私聊消息与公开状态日志。主早报送达后才发送 YouTube 消息。同一份早报的 YouTube 投递有台账后，`resume` 不会重发。 [Radar report 工作流](https://github.com/alex20230412-svg/global-trend-radar/actions/workflows/report.yml)

## 阶段 C 启用与验收

依 D-011，`collect.yml` 的 `17 * * * *` 和 `report.yml` 的 `30 0 * * *`（08:30 MYT）已在代码中开启，但只在 `RADAR_STAGE=c-scheduled` 时运行。Owner 只需把 `RADAR_STAGE` 从 `b-manual` 改成 `c-scheduled`。`RADAR_SCHEDULE_FROM` 可以留空：第一次计划采集会把自己的计划时间写进私库 `health/schedule-start.json`，之后用来统计漏跑。`keepalive.yml` 每月 1 日和 15 日用 API 重新启用三个定时工作流，避免公开仓库 60 天无活动后被停用。08:30 MYT 是目标时间，超过 30 分钟日报会标注延迟。跨小时排队延迟时，采集写入实际小时，原计划槽与延迟写进私有审计。

Owner 收到的是中文早报（`radar/brief.py`）：有 `GEMINI_API_KEY` 时由 Gemini 整理，否则是白话中文原文标题版。想随时看一份新的，在 Radar report 选 `preview`。

首 24 小时核对至少 20 个有有效核心数据并持久化的计划槽，完整、部分、失败和漏跑各自列出。连续三天查收日报并记录实际延时。第七天复核来源稳定性、真实覆盖、重复投递、容量及费用。GitHub 公开仓库长期无活动可能停用定时任务。平台整体停摆时，同仓库的告警也无法运行。 [定时触发行为](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) · [并发队列](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)

## 暂停、恢复和清理

- 删除或清空 `RADAR_STAGE` 可跳过后续真实作业。需要立即停机时停用这两个工作流，检查仍在运行的作业及私有流水。中断一个在途发送会留下待确认状态。
- 使用私库流水和私聊里的 `报告 ID · 分段 x/y` 核对。确认已收到时，在报告工作流选 `confirm_received`，填报告 ID 与段号。只有在确认未送达时才选 `confirm_unsent`。仍不确定就保留状态。确认后用 `resume` 处理剩余段；已确认或收到 API 成功回执的段会跳过。工作流输入只需日期编号和段号。
- PAT 到期或撤销时，`github_access_rejected` 等状态可见于公开 Actions，私库不可写期间无法安全记录并发出 Telegram 告警。暂停、续期并替换同名 Secret 后恢复。Bot Token 变化会阻止已部分投递报告在新身份下续发，新报告使用新凭证。
- 公开日志显示安全结果码。发生异常后在私库 `runs/` 查异常类名、radar 模块与行号，以及适用时的来源 ID 和 HTTP 状态。存储本身不可写时，审计也无法提交。
- 容量预警是 GitHub 仓库 size 元数据达到 700 MiB，900 MiB 时安全停止（GitHub 建议仓库远低于 1 GB）。实测约 76 KB/小时，D-011 起每源新闻 30 条、相关报道 2 条。GitHub 的统计可能滞后。源码和私库历史都应按规则审查。若来源许可变更，立即暂停并清除其批准项；普通 git 删除仍会保留历史，历史改写或迁移需要 Owner 单独授权。
- 以私库中的 `manifests`、`runs`、`health` 和 `deliveries` 为验收记录。公开仓库没有自动健康提交。私库校验和不符时保留证据，核对原提交与来源后再处理，缺失小时不回填。
