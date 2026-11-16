# 开发、测试、构建与发布

安装和打包的完整步骤见 [PACKAGING](PACKAGING.md)。本文件只记录日常开发命令和协作流程。

## 测试

```bash
# 云端或 Linux：仅 Core 依赖，Qt 使用 offscreen
python -m pip install -r requirements-core.txt pytest
QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short
```

```powershell
# Windows 本机（.venv-core）
$env:PYTHONUTF8 = "1"; $env:QT_QPA_PLATFORM = "offscreen"
.\.venv-core\Scripts\python.exe -m pytest -q --tb=short
```

- 测试位于 [tests/](../tests)。[conftest.py](../tests/conftest.py) 会创建临时 venv 来模拟外部解释器。
- 自动化测试不涉及真实声卡、QQ 音乐、GPU 或打包 exe。这些必须在目标机按 [PACKAGING](PACKAGING.md) 第 2–3 节手动验证，结果追加到 [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md)，并注明提交 SHA。
- 其他无硬件检查：`python scripts/check_env.py`、`python capture_test.py --simulate`、`python scripts/probe_media_session.py --self-test-mock --json`、`python main.py --simulate`。
- CI：[.github/workflows/tests.yml](../.github/workflows/tests.yml) 在 push 和 PR 时用 Ubuntu 运行上面的 Linux 命令。它只做测试，不打包也不发布。

## 构建

Windows 上执行 `pwsh -File scripts\setup_windows.ps1`（可选 `-CudaWheelDir`），再执行 `pwsh -File scripts\build_windows.ps1`，产物为 `dist\ListenScopeCore\ListenScope.exe`。参数说明见 [PACKAGING](PACKAGING.md)。云端 Linux 无法构建或运行 Windows exe。

## Git 协作流程（多 AI 共用）

1. 开始前执行 `git status --short --branch`、`git fetch`，并查看最近提交。工作区有他人未提交的修改时，先保留，不要 `reset`、`checkout --` 或 `stash drop`。
2. `main` 是稳定主线。文档小修和已验证的小修复可以直接提交。大功能、高风险修改（安装脚本、资源保护、Worker、打包）应在 `feature/…`、`fix/…`、`docs/…` 分支开发，经 PR 合并。
3. 禁止 force push，禁止改写已推送的历史。遇到冲突时用 rebase 或 merge 解决，并核对双方意图。
4. `backup/*` 分支和 `*-backup` 标签是历史快照，不要删除或移动。
5. 只为真实的 Bug 或需求开 Issue，不建空 Issue、空 PR 或空分支。
6. 发布：只有在目标机验收通过的提交上，才能由维护者打 `vX.Y.Z` 标签或创建 Release。版本号与 [pyproject.toml](../pyproject.toml) 保持一致。截至本文件，仓库还没有版本标签或 Release。未经用户授权，不得创建 Release 或触发发布。
7. 结束前按 [AGENTS.md](../AGENTS.md) 更新 [CURRENT_STATE](CURRENT_STATE.md) 和 [HANDOFF](HANDOFF.md)，然后推送，并核对远端 ref。
8. 每轮开发交付更新 Google Drive 的源码快照，并核对远端文件大小与修改时间。外观交付另外更新包含合成数据截图的预览包。压缩包排除本地配置、音频、模型和开发环境。
