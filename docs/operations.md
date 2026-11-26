# 阶段 B 手动测试与阶段 C 运行手册

本轮停在阶段 A。以下操作在 Claude 独立审核和 Owner 单独批准阶段 B 后执行。阶段 C 的 cron 激活另行审核批准。

## 阶段 B 上线前置条件

阶段 A 的 PR #7 依赖 PR #5。PR #5 由 Owner 决定是否合并。合并后，将阶段 A 提交整理到新的 `main`，将 PR #7 的目标改为 `main` 并复核差异。阶段 B 获批及代码由 Owner 合并后，真实工作流才可以接受设置。

来源审批以审核后的 `config/sources.yaml` 为准。Owner 确认一批来源及其保存权后，只将对应条目的 `retention` 从 `pending` 改为 `long_term` 并提交审核。执行时默认选用所有 `enabled: true`、`retention: long_term` 的条目。`RADAR_APPROVED_SOURCES` 留空即可，有需要时填写空格分隔的 ID 缩小范围。当前只有天气符合条件，MY 榜和全球核心榜的验收需要先确认核心来源。临时展示 Trends 相关新闻的标题和媒体名仍需单独批准，生产日报尚未接入。 [来源证据表](sources.md)

## 阶段 B 浏览器和手机设置

1. 在官方 BotFather 发送 `/newbot`，创建项目专用 Bot。保存 BotFather 发给你的 Token，稍后直接填入 GitHub。 [@BotFather](https://t.me/BotFather) · [官方说明](https://core.telegram.org/bots/features#botfather)
2. 确认专用数据仓库为 **Private**、默认分支为 `main` 且 Actions 已关闭。空仓库可添加一份空白说明，使 `main` 存在。创建限期 **fine-grained PAT**，Repository access 选 **Only select repositories**，只选 `global-trend-radar-data`，仓库权限仅增加 **Contents: Read and write**，保留 GitHub 默认的 Metadata read。 [私库 Actions 设置](https://github.com/alex20230412-svg/global-trend-radar-data/settings/actions) · [创建 PAT](https://github.com/settings/personal-access-tokens/new)
3. 在公开代码仓库创建 `radar-live` Environment，将部署分支限制为 **Selected branches and tags → Branch `main`**。填写下表的两个 **Environment secrets**。批准阶段 B 后，在 **Actions Variables** 将 `RADAR_STAGE` 设为 `b-manual`。`RADAR_SCHEDULE_FROM` 留到阶段 C。 [Environment 设置](https://github.com/alex20230412-svg/global-trend-radar/settings/environments) · [Actions Variables](https://github.com/alex20230412-svg/global-trend-radar/settings/variables/actions)
4. 打开自己刚创建的 Bot 的私人对话，发送一条 `/start`。在 15 分钟内启动绑定，确保该 Bot 专用于本项目。
5. 在 **Radar report → Run workflow → main** 选择 `bind_chat`。在自己与该 Bot 的私聊里看到通用绑定消息后，在同一工作流选择 `confirm_bind`，于发起绑定的 30 分钟内完成。收到 `BOUND` 后才可发送日报。Chat ID 由程序保存到私库，两个动作均无需填写 Chat ID 或其他工作流输入。 [Radar report](https://github.com/alex20230412-svg/global-trend-radar/actions/workflows/report.yml)

| Environment Secret 名称 | 填写值及用途 |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | BotFather 颁给这个新 Bot 的 Token，用于验证并发送私聊。 |
| `DATA_REPO_TOKEN` | 专用私有数据仓库的 fine-grained PAT，用于持久化及读回。 |

如有多个候选私聊，绑定会停止。若没有在自己的私聊收到通用确认，保持未确认，等 30 分钟到期后发送新的 `/start`。如果 Bot 已有无法核对的消息队列，先暂停并复核绑定台账。`python -m tools.get_chat_id` 保留为本人本地排查工具。密钥只填 GitHub Environment，Chat ID 留在专用私库。 [Telegram getUpdates](https://core.telegram.org/bots/api#getupdates)

## 阶段 B 首次手动运行

1. 在 [Radar collect](https://github.com/alex20230412-svg/global-trend-radar/actions/workflows/collect.yml) 选择 **Run workflow → main**。核对 8 分钟以内结束，公共日志只出现安全汇总，私库存在当小时 `observations`、`manifests` 和独立的 `runs`。小时为 UTC，观测另存实际时间。检查已批准核心来源返回了有效、新鲜的记录。
2. 同一 UTC 小时再触发一次。对比小时分区记录数及校验和，成功来源应跳过，若只部分失败则只补该失败来源。相邻小时再采集，若真实热点重复，检查两个分区都有独立的 `observed_at`、来源、地区、原始量级与排名。没有自然出现重合时继续等真实样本。按批准窗口同时派发两条手动 Collection 检查共享队列、无抢写，与禁用私库 Actions 的设置一起核对。
3. 至少取得两个不同槽的真实数据后，在 [Radar report](https://github.com/alex20230412-svg/global-trend-radar/actions/workflows/report.yml) 选择 `main`、`action=send`。核对收到 `smoke-YYYY-MM-DD`、中文栏目和 MYT、原始链接、覆盖/缺失及数据截止。真实报告刚好只有一段时，分段边界由离线用例验证。再次执行同一 MYT 日期的 `send`，证实投递流水和私聊没有重复发送。
4. 检查私库投递流水逐段有 payload 哈希、状态、尝试、时间和 API 回执 ID。成功时每段应为 `SENT`。若自然出现 `RATE_LIMITED`，等私库的 `retry_at` 后使用 `resume`。若出现 `UNKNOWN` 或 `SENDING`，按下节核对。失败补齐、429 和送达歧义的故障注入使用离线 Mock，真实验收只记录自然出现的异常。
5. 记录经实际 Actions 验证的来源覆盖、持续时间、并发、日志检查、标准 runner 和 RM0 证据。公开文档仅记录汇总，真实数据及回执留在私库。来源符合 L4 时才升级证据等级。

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
