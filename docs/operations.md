# 阶段 B 启用与阶段 C 运行手册

执行顺序依据 D-010。Claude 已经依 Owner 授权将 PR #5、#7、#8 合并进 `main`。这次的来源与无凭证工作流由 Claude 审核，Owner 同意后才合并。阶段 C 的 cron 激活另行审批。 [Issue #9](https://github.com/alex20230412-svg/global-trend-radar/issues/9)

## 一、Claude 先做无凭证实测

1. 审核通过并合并后，在 **Radar live check → Run workflow → main** 手动运行，保留运行链接和固定格式汇总。该作业用公开仓库标准 runner，独立并发组和临时本地 Git，设有 10 分钟上限。 [live-check 工作流](https://github.com/alex20230412-svg/global-trend-radar/actions/workflows/live-check.yml)
2. 核对每个启用来源的 `status`、`count`、`skipped`、HTTP 和新鲜度。同一小时两次调用采集流程，第二次跳过已成功的来源，检查观测文件校验和一致。单列检查 GDELT 的试探结果。GDELT 生产配置只有确认 Actions 连通并在后续审核中更新后才能开启。
3. 查报告是否为一段、是否降级、各栏目和「为什么热」计数是否合理。报告和观测只在当次 runner 本地临时目录生成。公开证据只引用状态与数字，合成日报由 PR 离线 CI 展示。来源失败、过旧、覆盖不足或格式不符时，按 Issue #9 退回修复。通过者按来源证据表记载日期与适用的等级。 [来源证据表](sources.md)

本步骤不需要业务凭证、environment 或 `RADAR_STAGE`。实际执行前无须 Owner 填写任何东西。

`source` 行的 `newest_age_min` 按最近有效发布日期计算，GDELT 用索引时间，无日期时为 `-`。合法的气象空结果可接受，表示该次未见警告。 `report` 行的 `chars` 为每段解析后的 UTF-16 单元数，`fresh` 计展示中标为新出现或升温的趋势，`with_context` 计显示相关新闻背景的条目，`platforms` 计有内容的平台栏目。GDELT 探测默认随手动检查执行，单列结果不影响已启用来源的报告与验收。

## 二、全项实测通过后，Owner 一次配置

Claude 经 Owner 同意创建或配置公开代码仓库的 `radar-live` environment，只允许 `main` 部署。Claude 先确认项目专用数据仓库为 Private，具有默认 `main` 且 Actions 已关闭。 [Environment 设置](https://github.com/alex20230412-svg/global-trend-radar/settings/environments) · [私库 Actions 设置](https://github.com/alex20230412-svg/global-trend-radar-data/settings/actions)

| Owner 操作 | 凭证范围 |
| --- | --- |
| 在官方 BotFather 发送 `/newbot` 创建项目专用 Bot。 | 把新 Token 直接填到 `radar-live` 的 `TELEGRAM_BOT_TOKEN`。 |
| 创建限期 fine-grained PAT | **Only select repositories**，只选 `global-trend-radar-data`。权限仅增加 **Contents: Read and write**，保留 GitHub 默认 Metadata read。把 PAT 直接填到同一 environment 的 `DATA_REPO_TOKEN`。 |
| 在自己与新 Bot 的私人对话里发送一次 `/start` | 发送后告知 Claude，供接下来的 15 分钟绑定窗口使用。Chat ID 由程序保存在专用私库。 |

凭证只填 GitHub Environment。 [BotFather](https://t.me/BotFather) · [创建 fine-grained PAT](https://github.com/settings/personal-access-tokens/new) · [Environment 设置](https://github.com/alex20230412-svg/global-trend-radar/settings/environments)

## 三、Claude 验证真实私聊与私库

1. 经 Owner 同意设置 `RADAR_STAGE=b-manual`。来源默认由审核后的 `enabled: true` 与 `retention: long_term` 控制。`RADAR_APPROVED_SOURCES` 只用于缩小范围，通常留空。执行受审 `main` 的 **Radar collect**，并依测试顺序核对同槽重跑与不同时槽的真实观测。 [Radar collect](https://github.com/alex20230412-svg/global-trend-radar/actions/workflows/collect.yml)
2. 通过 Owner 授权且由 GitHub 识别为仓库 Owner 的会话发起 `bind_chat`。Owner 在自己的 Bot 私聊看到通用确认后告知 Claude，再用同一身份在 30 分钟内发起 `confirm_bind`。只有 `BOUND` 才可继续。若无法以 Owner 身份操作，相应绑定动作交由 Owner 点击。绑定存在多个候选或收件人不明时暂停核对。 [Radar report](https://github.com/alex20230412-svg/global-trend-radar/actions/workflows/report.yml)
3. 发起 `report send`，由 Owner 确认收到私聊。经单独授权的临时只读访问核对专用私库的观测、校验和、来源状态和投递回执，再撤去只读访问。用同日重跑确认已发送段数不增加。公开报告只记录数量和状态。

如出现 `RATE_LIMITED`，按私有台账的 `retry_at` 等待。若为 `UNKNOWN` 或 `SENDING`，按下方操作核对。临时跑仍遵守 RM0 和来源条款。

## 阶段 C 启用与验收

阶段 B 通过后，Owner 批准一个独立 PR 打开 `collect.yml` 的 `17 * * * *` 和 `report.yml` 的 `30 0 * * *`。为 `RADAR_SCHEDULE_FROM` 填写第一个计划采集时间（UTC ISO 8601，分钟为 17），将 `RADAR_STAGE` 设为 `c-scheduled`。08:30 MYT 是目标时间，超过 30 分钟日报会标注延迟。GitHub 的工作流创建时间用于推断最近计划槽。跨小时排队延迟时，采集写入实际小时，原计划槽与延迟写进私有审计。原槽缺口保留，迟到运行不会替代实际小时自己的计划触发。

首 24 小时核对至少 20 个有有效核心数据并持久化的计划槽，完整、部分、失败和漏跑各自列出。连续三天查收日报并记录实际延时。第七天复核来源稳定性、真实覆盖、重复投递、容量及费用。GitHub 公开仓库长期无活动可能停用定时任务。平台整体停摆时，同仓库的告警也无法运行。 [定时触发行为](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) · [并发队列](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)

## 暂停、恢复和清理

- 删除或清空 `RADAR_STAGE` 可跳过后续真实作业。需要立即停机时停用这两个工作流，检查仍在运行的作业及私有流水。中断一个在途发送会留下待确认状态。
- 使用私库流水和私聊里的 `报告 ID · 分段 x/y` 核对。确认已收到时，在报告工作流选 `confirm_received`，填报告 ID 与段号。只有在确认未送达时才选 `confirm_unsent`。仍不确定就保留状态。确认后用 `resume` 处理剩余段；已确认或收到 API 成功回执的段会跳过。工作流输入只需日期编号和段号。
- PAT 到期或撤销时，`github_access_rejected` 等状态可见于公开 Actions，私库不可写期间无法安全记录并发出 Telegram 告警。暂停、续期并替换同名 Secret 后恢复。Bot Token 变化会阻止已部分投递报告在新身份下续发，新报告使用新凭证。
- 公开日志显示安全结果码。发生异常后在私库 `runs/` 查异常类名、radar 模块与行号，以及适用时的来源 ID 和 HTTP 状态。存储本身不可写时，审计也无法提交。
- 容量预警是 GitHub 仓库 size 元数据达到 256 MiB，512 MiB 时安全停止。GitHub 的统计可能滞后。源码和私库历史都应按规则审查。若来源许可变更，立即暂停并清除其批准项；普通 git 删除仍会保留历史，历史改写或迁移需要 Owner 单独授权。
- 以私库中的 `manifests`、`runs`、`health` 和 `deliveries` 为验收记录。公开仓库没有自动健康提交。私库校验和不符时保留证据，核对原提交与来源后再处理，缺失小时不回填。
