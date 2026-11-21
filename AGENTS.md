# Project development

开发前请先核对 Git 分支、`HEAD` 与工作区状态。内部交接、设计草稿与阶段性验收报告已归档至 `archive/internal-docs` 分支。

## ListenScope 项目规则

- 文档地图：项目目标与功能见 [README](README.md)；架构见 [ARCHITECTURE](docs/ARCHITECTURE.md)；不可随意更改的决策和失败经验见 [DECISIONS](docs/DECISIONS.md)；测试、构建和 Git 流程见 [DEVELOPMENT](docs/DEVELOPMENT.md)；安装与打包见 [PACKAGING](docs/PACKAGING.md)。
- 目标机是 Windows 11、RTX 5060 Ti **8 GB 显存**、**16 GB 内存**。云端或 Linux 的结果只能写成 Linux/offscreen 验证，不能写成 Windows 音频、GPU 或 exe 已验证。未实测的功能不得写成已完成。
- 不要单方面修改 [DECISIONS](docs/DECISIONS.md) 中的约束，例如三环境隔离、cu128 约束、6 秒分块和分段、单 Worker、5120/3072/2048 MiB 内存阈值、settings schema 2、保留手动「换歌重置」。确需修改时，先取得实测依据，再同步更新文档。
- 协作安全：不要覆盖他人未提交的修改，不要重置工作区，不要 force push，不要删除 `backup/*` 分支或 `*-backup` 标签，未经授权不要创建 Release。高风险改动走分支和 PR，详见 [DEVELOPMENT](docs/DEVELOPMENT.md)。
- 完成前至少运行 `QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short`，或说明跳过原因。需要目标机验证的项目，要交付可复制执行的 Windows 复测步骤。
- 每轮使用 AI Worker 协同后，更新 [AI 协同报告](docs/AI_COLLABORATION.md)。记录任务、准确模型 ID、耗时和可用的用量、建议采纳与误报、测试结果和下一轮调度调整。用量以工具回报为准，原始任务文本、会话标识和凭据留在本机。
