# 最新交接

- **目标和结果**：按 ai-dev-kit 协议审计 AI 接手记忆并做最小补全。未改软件代码。
  - 新增 [REQUIREMENTS](REQUIREMENTS.md)、[ARCHITECTURE](ARCHITECTURE.md)、[DECISIONS](DECISIONS.md)、[DEVELOPMENT](DEVELOPMENT.md)。
  - [AGENTS.md](../AGENTS.md) 增加项目规则段落。
  - 更新 [CURRENT_STATE](CURRENT_STATE.md)，并修正 [README](../README.md) 中过期的待验收段落。
  - 新增仅测试用的 CI：[.github/workflows/tests.yml](../.github/workflows/tests.yml)。
  - 没有单独建 PROJECT_CONTEXT，项目背景由 README 和 CURRENT_STATE 承担。
- **Evidence commit**：6d9ade0d362ba3355f911e4c5022c3e784fd388b（本次改动前的 `main`）
- **分支**：`docs/ai-memory-audit`，经 PR 合并到 `main`。远端状态见本文件末尾。
- **Skills**：`.agents/skills/` 锁定 ai-dev-kit `150782a`。与中央仓库 `93c1d0c` 比较，四个 SKILL.md 完全相同。`scripts/install.ps1 -Project` 预演没有需要更新的文件，所以未重新安装。
- **验证**：
  - 中央仓库 `scripts/audit.ps1 -Project`：Structural checks passed。在 Linux 上用 PowerShell 7.4.6 运行。
  - 云端 Linux（Debian 12，Python 3.11.2）运行 `QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short`：115 passed。只装 requirements-core 和 pytest 的全新 venv 结果相同。
  - 本次没有在目标机复测。GitHub Actions 的首次运行结果见远端状态。
- **独立接手验证（静态模拟，不是隔离的实时 Agent 会话）**：只读仓库文件就能回答以下 8 个问题：
  - 目标：README
  - 已实现功能：REQUIREMENTS
  - 代码位置：README 模块树和 ARCHITECTURE
  - 稳定基线：CURRENT_STATE，目标机为 `f03dbf1`
  - 风险：CURRENT_STATE
  - 运行和构建：DEVELOPMENT、PACKAGING
  - 不可改的决策：DECISIONS
  - 下一步：本文件

  待确认：在线 torch 下载停滞的根因；近实时触发内存保护的具体原因（目前只是推断）；SMTC 是否会重复重置。真实双客户端验收方法见 ai-dev-kit `docs/CROSS_AI_CHECK.md`，尚未执行。
- **下一步**：
  1. 为 [`pull_mixed_block`](../streaming/live_separator.py#L810-L835) 补跨回调顺序消费和游标推进的回归测试，再修复。修复时保留内存保护。
  2. 为单轨 MIDI 在 `work_dir` 内覆盖同名文件的问题补隔离测试并修复。
  3. 为 SMTC 自动重置补事件计数，再交给目标机复测。

## 远端状态

待推送后填写。
