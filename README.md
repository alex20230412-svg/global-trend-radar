# global-trend-radar

Free automated trending-topic radar for Malaysia and the world.

全球热点雷达收集马来西亚及监测地区的搜索飙升、本地媒体和社交科技信号，保存小时观测，生成 08:30 MYT 私人 Telegram 日报。报告包含热门榜、新出现及升温、社交科技、气象和覆盖缺口。

> **当前状态为阶段 B 的来源和无凭证检查准备。** Draft PR 等待 Claude 审核。定时触发尚未启用。 [状态](STATUS.md)

## 先读这些

| 文件 | 内容 |
| --- | --- |
| [docs/PLAN.md](docs/PLAN.md) | 早期调查与长期方案，第一轮范围见 D-009 及 Issue #6 审核 |
| [docs/sources.md](docs/sources.md) | 数据来源证据表：每个来源的状态、实测证据、限制 |
| [docs/opensource.md](docs/opensource.md) | 开源候选、锁定版本、许可证和复用记录 |
| [docs/operations.md](docs/operations.md) | 凭证、首次手动运行、调度验收及恢复步骤 |
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
| `global-trend-radar-data` | 私有 | 获准长期保存的小时观测、报告、投递流水和健康记录 |

本仓库是公开的，任何人都能看到。**不要在这里提交任何密码、Token、私人资料或其他项目的信息。** Token 只放在 GitHub Secrets。

## 本地离线测试

在 Linux x64 或 Windows x64 使用 Python 3.14，在项目的虚拟环境执行以下命令。测试使用合成样本或 Mock，并用临时本地 Git 仓库验证写入竞争。

```bash
python -m pip --isolated --disable-pip-version-check install --no-cache-dir --index-url https://pypi.org/simple --require-hashes --only-binary=:all: -r requirements.lock
python -m unittest discover -s tests -v
```

合并并通过审核后，Claude 先在 `main` 运行无业务凭证的来源与本地 Git 空跑检查。验证通过后再安排 Telegram 和私库设置。 [运行手册](docs/operations.md)

## 怎么参与讨论

Owner、Claude、ChatGPT 三方都以这个仓库为准：

1. 每个要讨论的问题开一个 Issue（用 “讨论主题” 模板）。
2. 任何一方的意见都写成 Issue 留言。AI 不能直接留言时，由 Owner 复制粘贴，并注明来自哪个 AI。
3. 定下来的结论写进 [DECISIONS.md](DECISIONS.md)，然后关闭 Issue。
4. 代码和文档改动一律走分支 + Draft PR，由 Owner 审核后合并。
