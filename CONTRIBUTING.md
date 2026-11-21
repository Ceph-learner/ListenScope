# Contributing to ListenScope

欢迎为 **ListenScope** 提交 Issue 与 Pull Request！

## 开发环境约定

为保持 Core 桌面端轻量且无重型 ML 依赖，项目采用三环境隔离结构（详见 [docs/PACKAGING.md](docs/PACKAGING.md)）：

- **Core 环境**（`requirements-core.txt`）：PySide6、PyQtGraph、NumPy/SciPy、librosa、SoundFile、mido（零 PyTorch/CUDA/TensorFlow 依赖）。
- **GPU AI 环境**（`requirements-ai.txt`）：独立子进程运行 Demucs / MDX-Net ONNX。
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

## 提交规范

- 请保持 Core 环境零 PyTorch / CUDA / TensorFlow 依赖。
- 涉及 UI 改动请同步验证亮暗双模与四语本地化（`zh` / `en` / `ko` / `ja`），确保无硬编码文案或控件遮挡。
- 目标硬件基线为 Windows 11 · 8 GB VRAM · 16 GB RAM，请勿在未实测的情况下降低安全内存/显存阈值。
