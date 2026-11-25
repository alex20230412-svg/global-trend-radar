# 阶段 B 手动测试与阶段 C 运行手册

本轮停在阶段 A。以下操作在 Claude 独立审核和 Owner 单独批准阶段 B 后执行。阶段 C 的 cron 激活另行审核批准。

## 阶段 B 准备

1. Owner 审阅 PR #5 的方向记录并决定是否先合并。PR #5 合并后，将阶段 A PR 的目标改为 `main` 并复核差异。如果 PR #5 经 squash 或 rebase 合并，先基于新的 `main` 整理阶段 A 提交再复核。阶段 A PR 经 Claude 审核及 Owner 批准后由 Owner 合并。两条真实工作流只接受公开代码仓库的受审 `main`。
2. 在专用数据仓库确认可见性为 **Private**、默认分支为 `main`。空仓库可先添加一份空白说明，使 `main` 存在。关闭该仓库 Actions。用公开代码仓库标准 `ubuntu-24.04` runner，保持账户现有计费设置。 [私有仓库 Actions 设置](https://github.com/alex20230412-svg/global-trend-radar-data/settings/actions) · [GitHub Actions 计费](https://docs.github.com/en/actions/concepts/billing-and-usage)
3. 在 Telegram 打开官方 [@BotFather](https://t.me/BotFather)，发送 `/newbot`，为 Global Trend Radar 创建独立 Bot。打开新 Bot 的私聊发送 `/start`。在自己电脑的交互式终端，从本项目目录运行 `python -m tools.get_chat_id`。把 BotFather 的 Token 输入本地隐藏提示。在同一个 Bot 私聊发送工具给的一次性验证文字，再回终端按提示继续。工具只在本地显示通过核验的正数 Chat ID。Token 与 Chat ID 直接填入下表指定设置，避免聊天、终端录屏或公开文件。 [BotFather 官方说明](https://core.telegram.org/bots/features#botfather) · [getUpdates 官方说明](https://core.telegram.org/bots/api#getupdates)
4. 创建 **fine-grained personal access token**。Resource owner 选择自己，Repository access 选择 **Only select repositories**，只勾选 `global-trend-radar-data`。Repository permissions 只增加 **Contents: Read and write**，保留 GitHub 强制的 Metadata read。选择有限有效期，记录本地续期日期，随后把 PAT 填到代码仓库环境的 Secret。 [直接创建 fine-grained PAT](https://github.com/settings/personal-access-tokens/new) · [GitHub 权限说明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
5. 在公开代码仓库的 **Settings → Environments** 创建 `radar-live`，将 Deployment branches and tags 设为 **Selected branches and tags**，只添加 Branch `main`。在该环境的 **Environment secrets** 新增三个 Secret。 [公开代码仓库 Environment 设置](https://github.com/alex20230412-svg/global-trend-radar/settings/environments)

| Environment Secret 名称 | 填写值及用途 |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | BotFather 颁给这个新 Bot 的 Token，用于验证并发送私聊。 |
| `TELEGRAM_CHAT_ID` | 工具在本人终端显示的私聊 ID，用于唯一允许的收件人。 |
| `DATA_REPO_TOKEN` | 专用私有数据仓库的 fine-grained PAT，用于持久化及读回。 |

`RUN_METADATA_TOKEN` 自动由 GitHub 提供，只读取当前公开项目的工作流元数据，用来区分排队时间和实际运行时间。无需自行填写。

在 [Actions Variables](https://github.com/alex20230412-svg/global-trend-radar/settings/variables/actions) 先配置 `RADAR_APPROVED_SOURCES`，填写空格分隔的已批准来源 ID。长期保存在私有 Git 的权利须逐源留证，并在经审核的 `config/sources.yaml` 中标为 `long_term`。Google Trends 关联新闻元数据有独立的 `retain_related` 开关。阶段 A 只有天气具备明确长期保存许可，第一批应在权限核实后从 MY、少量邻近地区与本地 RSS 开始。若只允许 `weather`，可以测试管路，MY 和全球核心验收仍未完成。来源核对见 [来源证据表](sources.md)。

准备无误后将 `RADAR_STAGE` 设为 `b-manual`。本阶段两个 cron 仍是注释，`RADAR_SCHEDULE_FROM` 留空。工作流环境的三个 Secret 与变量只属于本项目。

## 阶段 B 首次手动运行

1. 在 [Radar collect](https://github.com/alex20230412-svg/global-trend-radar/actions/workflows/collect.yml) 选择 **Run workflow → main**。核对 8 分钟以内结束，公共日志只出现安全汇总，私库存在当小时 `observations`、`manifests` 和独立的 `runs`。小时为 UTC，观测另存实际时间。检查已批准核心来源返回了有效、新鲜的记录。
2. 同一 UTC 小时再触发一次。对比小时分区记录数及校验和，成功来源应跳过，若只部分失败则只补该失败来源。相邻小时再采集，若真实热点重复，检查两个分区都有独立的 `observed_at`、来源、地区、原始量级与排名。没有自然出现重合时继续等真实样本。按批准窗口同时派发两条手动 Collection 检查共享队列、无抢写，与禁用私库 Actions 的设置一起核对。
3. 至少取得两个不同槽的真实数据后，在 [Radar report](https://github.com/alex20230412-svg/global-trend-radar/actions/workflows/report.yml) 选择 `main`、`action=send`。核对收到 `smoke-YYYY-MM-DD`、中文栏目和 MYT、原始链接、覆盖/缺失及数据截止。真实报告刚好只有一段时，分段边界由离线用例验证。再次执行同一 MYT 日期的 `send`，证实投递流水和私聊没有重复发送。
4. 检查私库投递流水逐段有 payload 哈希、状态、尝试、时间和 API 回执 ID。成功时每段应为 `SENT`。若自然出现 `RATE_LIMITED`，等私库的 `retry_at` 后使用 `resume`。若出现 `UNKNOWN` 或 `SENDING`，按下节核对。失败补齐、429 和送达歧义的故障注入使用离线 Mock，真实验收只记录自然出现的异常。
5. 记录经实际 Actions 验证的来源覆盖、持续时间、并发、日志检查、标准 runner 和 RM0 证据。公开文档仅记录汇总，真实数据及回执留在私库。来源符合 L4 时才升级证据等级。

## 阶段 C 启用与验收

阶段 B 通过后，Owner 批准一个独立 PR 打开 `collect.yml` 的 `17 * * * *` 和 `report.yml` 的 `30 0 * * *`。为 `RADAR_SCHEDULE_FROM` 填写第一个计划采集时间（UTC ISO 8601，分钟为 17），将 `RADAR_STAGE` 设为 `c-scheduled`。覆盖按实际成功与缺失报告。08:30 MYT 是目标时间，超过 30 分钟日报会标注延迟。GitHub 不提供独立的原始计划时间字段，程序用工作流创建时间推断最近计划槽，排队到其他小时会记为迟到漏跑。

首 24 小时核对至少 20 个有有效核心数据并持久化的计划槽，完整、部分、失败和漏跑各自列出。连续三天查收日报并记录实际延时。第七天复核来源稳定性、真实覆盖、重复投递、容量及费用。GitHub 公开仓库长期无活动可能停用定时任务。平台整体停摆时，同仓库的告警也无法运行。 [定时触发行为](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) · [并发队列](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)

## 暂停、恢复和清理

- 删除或清空 `RADAR_STAGE` 可跳过后续真实作业。需要立即停机时停用这两个工作流，检查仍在运行的作业及私有流水。中断一个在途发送会留下待确认状态。
- 使用私库流水和私聊里的 `报告 ID · 分段 x/y` 核对。确认已收到时，在报告工作流选 `confirm_received`，填报告 ID 与段号。只有在确认未送达时才选 `confirm_unsent`。仍不确定就保留状态。确认后用 `resume` 处理剩余段；已确认或收到 API 成功回执的段会跳过。工作流输入只需日期编号和段号。
- PAT 到期或撤销时，`github_access_rejected` 等状态可见于公开 Actions，私库不可写期间无法安全记录并发出 Telegram 告警。暂停、续期并替换同名 Secret 后恢复。Bot Token 变化会阻止已部分投递报告在新身份下续发，新报告使用新凭证。
- 容量预警是 GitHub 仓库 size 元数据达到 256 MiB，512 MiB 时安全停止。GitHub 的统计可能滞后。源码和私库历史都应按规则审查。若来源许可变更，立即暂停并清除其批准项；普通 git 删除仍会保留历史，历史改写或迁移需要 Owner 单独授权。
- 以私库中的 `manifests`、`runs`、`health` 和 `deliveries` 为验收记录。公开仓库没有自动健康提交。私库校验和不符时保留证据，核对原提交与来源后再处理，缺失小时不回填。
