# global-trend-radar

Free automated trending-topic radar for Malaysia and the world.

全球热点雷达：自动、持续收集马来西亚和全球的最新热门资讯，找出社交媒体上刚开始爆红、正在快速升温的话题，保存历史以便比较热度变化，并通过 Telegram 推送日报和升温提醒。

> **当前状态：阶段 0（准备）。** 还没有任何代码在运行。详见 [STATUS.md](STATUS.md)。

## 先读这些

| 文件 | 内容 |
| --- | --- |
| [docs/PLAN.md](docs/PLAN.md) | 调查报告与实施方案（2026-11-25） |
| [docs/sources.md](docs/sources.md) | 数据来源证据表：每个来源的状态、实测证据、限制 |
| [STATUS.md](STATUS.md) | 当前阶段、已完成、待办、阻塞 |
| [DECISIONS.md](DECISIONS.md) | 已确认和待讨论的决定 |
| [PROJECT_MEMORY.md](PROJECT_MEMORY.md) | 不会变的目标与约束 |
| [HANDOFF_LOG.md](HANDOFF_LOG.md) | 每次工作的交接记录 |
| [AGENTS.md](AGENTS.md) | 给任何接手这个项目的 AI 的规则 |

## 核心约束

- 新增费用为 RM0。任何付费服务、付费 API、绑卡操作都必须先由 Owner 批准。
- 不需要 Owner 的电脑长期开机。
- 与 Owner 的其他现有项目完全隔离：不共享仓库、Secrets、Telegram Bot、Actions 额度或存储。
- 只用合法、获授权的数据来源；遵守 robots.txt 与各平台条款。
- 所有进度、决定、测试结果和问题都记录在这个仓库里。

## 仓库分工

| 仓库 | 可见性 | 放什么 |
| --- | --- | --- |
| `global-trend-radar`（本仓库） | 公开 | 代码、配置、文档、讨论 |
| `global-trend-radar-data` | 私有 | 采集到的数据（原始数据放 Releases，小型汇总放 Git） |

本仓库是公开的，任何人都能看到。**不要在这里提交任何密码、Token、私人资料或其他项目的信息。** Token 只放在 GitHub Secrets。

## 怎么参与讨论

Owner、Claude、ChatGPT 三方都以这个仓库为准：

1. 每个要讨论的问题开一个 Issue（用 “讨论主题” 模板）。
2. 任何一方的意见都写成 Issue 留言。AI 不能直接留言时，由 Owner 复制粘贴，并注明来自哪个 AI。
3. 定下来的结论写进 [DECISIONS.md](DECISIONS.md)，然后关闭 Issue。
4. 代码和文档改动一律走分支 + Draft PR，由 Owner 审核后合并。
