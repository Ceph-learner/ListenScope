# Contributing to ListenScope

欢迎为 **ListenScope** 提交 Issue 与 Pull Request！

## 开发环境约定

为保持 Core 桌面端轻量且无重型 ML 依赖，项目采用三环境隔离结构（详见 [docs/PACKAGING.md](docs/PACKAGING.md)）：

- **Core 环境**（`requirements-core.txt`）：PySide6、PyQtGraph、NumPy/SciPy、librosa、SoundFile、mido（零 PyTorch / CUDA / TensorFlow 依赖）。
- **GPU AI 环境**（`requirements-ai.txt`）：独立子进程运行 Demucs / MDX-Net ONNX（受 `constraints-ai-cu128.txt` 约束）。
- **CPU MIDI 环境**（`requirements-midi.txt`）：独立子进程运行 Basic Pitch。

## 运行测试

在 Core 环境中即可运行全量自动化回归测试（Linux 或无显示器环境请设置 `QT_QPA_PLATFORM=offscreen`）：

```bash
pip install -r requirements-core.txt pytest
QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short
```

无声卡或非 Windows 环境下可使用 `--simulate` 启动模拟信号模式：

```bash
python main.py --simulate --headless-smoke
```

更多测试分层、基准测试（A-BENCH / `realistic_mix`）与回归测试编写规范见 [docs/TESTING.md](docs/TESTING.md) 与 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

## 分支、PR 与提交规范

- 从最新 `main` 创建功能或修复分支（如 `feature/...`、`fix/...`、`docs/...`），通过 Pull Request 合并。
- 推荐使用 Conventional Commits 风格（如 `feat:`、`fix:`、`docs:`、`test:`、`refactor:`）。
- 请保持 Core 环境零 PyTorch / CUDA / TensorFlow 依赖。
- 涉及 UI 改动请同步验证亮暗双模与四语本地化（`zh` / `en` / `ko` / `ja`，详见 [docs/I18N.md](docs/I18N.md)），确保无硬编码文案或控件遮挡。
- 目标硬件基线为 Windows 11 · 8 GB VRAM · 16 GB RAM，请勿在未实测的情况下降低安全内存/显存阈值（详见 [docs/DECISIONS.md](docs/DECISIONS.md)）。

## 关于 AI 工具

允许在遵守开源协议的前提下使用 AI 工具辅助开发，但**所有贡献者必须对所提交代码的正确性、安全性、许可证合规性及测试结果自行负责**，不得提交未经审查的生成代码或未核对出处的第三方复制代码。

## 开源许可说明

向本项目提交的任何贡献（包括代码、文档与测试），均视为同意以本仓库的 [MIT License](LICENSE) 进行授权与分发。
