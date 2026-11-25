# AGENTS.md：给接手本项目的 AI 的规则

本文件适用于任何在本仓库工作的 AI（Claude、ChatGPT / Codex 或其他）。规则与 Owner 当前在对话中的明确指示冲突时，以 Owner 的指示为准，并把变化记录进 DECISIONS.md。

## 开始工作前，按顺序阅读

1. [PROJECT_MEMORY.md](PROJECT_MEMORY.md)：目标与约束
2. [STATUS.md](STATUS.md)：现在在哪个阶段、什么能用、什么坏了
3. [DECISIONS.md](DECISIONS.md)：已确认的决定，不要推翻；待讨论的不要擅自实施
4. [HANDOFF_LOG.md](HANDOFF_LOG.md)：最近一次工作留下的问题与下一步
5. [docs/PLAN.md](docs/PLAN.md) 与 [docs/sources.md](docs/sources.md)

## 硬规则

### 费用
- 新增费用必须为 RM0。不开通任何计费，不绑卡，不订阅付费 API，不创建会产生账单的云资源。
- 免费额度不足时，降频或安全停止并告警，不能自动升级到付费。
- 任何付费选项（例如 X API）只能写成提议，由 Owner 批准后才能实施。

### 隔离
- 不读取、不修改 Owner 的任何其他现有项目：仓库、分支、Actions、Secrets、Telegram Bot、webhook、轮询器、数据库、调度任务。
- 本项目使用独立的 Telegram Bot、独立的 Secrets、独立的数据仓库。
- 私有数据仓库 `global-trend-radar-data` 不运行任何 GitHub Actions，以免占用私有仓库共享的免费额度。

### 公开仓库的安全
- 本仓库是公开的。禁止提交：Token、密码、chat_id、API key、个人资料、Owner 其他项目的名称或业务细节、采集到的原始数据。
- Token 只放在 GitHub Secrets；代码通过环境变量读取。
- 真实工作流只允许 `schedule` 与 `workflow_dispatch` 触发。无凭证、无 environment 的离线测试可由 `pull_request` 触发。任何工作流均禁用 `pull_request_target`，第三方 Action 固定到 commit SHA。

### Git 流程
- 不直接提交到 `main`。每项工作开新分支，提交 Draft PR。
- 不自行合并。由 Owner 审核后合并。
- PR 描述必须写：改了什么、测试命令、实际测试结果、费用影响、已知限制、下一步（见 PR 模板）。

### 数据与来源
- 只使用合法、获授权的来源；遵守 robots.txt 与平台条款。
- 不绕过登录、验证码、付费墙、频控或 API 权限。遇到 401 / 403 / 429 时停止或按规则退避。
- 只保存标题、链接、时间、来源、排名与统计指标；不保存全文、图片、视频、个人资料。
- 来源状态只有在实测后才能标 `VERIFIED`，并在 docs/sources.md 写明核查日期与证据。

### 诚实
- 不把方案、模拟、测试数据写成真实运行结果。
- 漏跑或缺失的数据只记录缺口，不补造。
- 不确定的事写成 “未核实”，不要猜。

### 语言
- 代码、标识符、提交信息、配置键用英文。
- 给 Owner 的报告、文档、Issue 讨论用中文（技术名词可保留英文）。

## 每次工作结束时

1. 更新 STATUS.md。
2. 在 HANDOFF_LOG.md 追加一条记录：做了什么、遇到的问题、下一步。
3. 有新决定或提议时更新 DECISIONS.md。
