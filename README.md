# ListenScope

**免费、离线、本地运行**的 Windows 桌面听歌分析、A/B 循环与扒谱练习工具。

不需要下载加密音乐缓存，也不需要折腾音频驱动桥接。在 QQ 音乐、网易云音乐、浏览器或任意播放器正常听歌时，ListenScope 直接按进程捕获音频流，提供实时频谱、和弦进行、调性、BPM、120 秒回溯选区、本地 AI 分轨和 Cubase 兼容 MIDI 导出。

---

## 主要功能

| 模块 | 功能概览 |
| :--- | :--- |
| **实时捕获与频谱** | Windows 进程环回捕获（Build ≥ 20348，无需虚拟声卡）或系统环回；实时波形、FFT / 对数频谱、基频 `F0` 与 `-50 ~ +50 cents` 音准刻度条 |
| **和弦、调性与移调** | 12-bin Chroma 热图、大/小三和弦与构成音实时识别、自然大调 / 自然小调罗马级数、12 步和弦轨迹、纯 CPU **Capo / 乐器移调联动**、24 调和弦练习弹窗（支持试听与 `.mid` 导出） |
| **120 秒回溯与 A/B 练习** | 固定 120s 环形缓冲（`48 kHz / Stereo / float32`）、拖拽 A/B 选区、`0.5x–1.25x` 不变调变速回放、12 个练习书签、Tap 定速节拍器（含预备拍）及带节拍器的练习 WAV 导出 |
| **本地 AI 分轨** | 独立 `.venv-ai` 进程按需运行 2-Stem（Vocals / Instrumental）或 4-Stem（Vocals / Drums / Bass / Other）分离，默认 6 秒流式分块，随时可紧急停止并释放显存 |
| **分轨混音与扒谱** | 四轨独立静音/独听、**贝斯独听 `0–24 dB` 可调增益**（默认 `+12 dB`，超过 `+12 dB` 自动护耳提示，可选写入导出 WAV）、FFT-YIN 贝斯最低音（低至 `B0`/`E1`）与半程转调检测、16 步鼓组律动、`.md/.csv` 扒谱表 |
| **MIDI 转录与 Cubase 适配** | 支持分轨后一键转 MIDI 或直接打开本地单轨 WAV 转 MIDI；所有和弦、鼓点与单轨 MIDI 均统一规范为 **Steinberg Cubase 兼容 SMF Type-0 (`480 TPB`)** |
| **界面与个性化** | 默认启用 **酸性遥测（Acid Telemetry · 临床浅色）** 工业视觉，支持暗夜 / 临床浅色双模快切；同时提供经典、Lenso、Codex、Claude 主题（非酸性主题支持自定义字体、配色与背景壁纸）、**中 / 英 / 韩 / 日** 四语切换及无边框圆角窗口 |

---

## 环境架构

为保证主界面轻量流畅（无需显卡即可使用全部实时分析与 A/B 练习功能），项目采用三环境隔离设计：

```text
ListenScope/
├── core/         # 配置与同级便携路径、多语言 (zh/en/ko/ja)、外观模型、本机 PyTorch 扫描、资源守卫与诊断打包
├── audio/        # WASAPI 进程/系统环回捕获、120s 固定环形缓冲、WSOLA 变速、节拍器、和弦/鼓点试听与四轨混音引擎
├── analysis/     # 纯 CPU 频谱/Chroma/和弦/调性/BPM、FFT-YIN 贝斯与转调分析、Cubase SMF Type-0 MIDI 导出
├── ai/           # 离线分轨模型注册表、流式分块守护与独立 AI 子进程管理
├── separation/   # 2-Stem MDX-ONNX 与 4-Stem HTDemucs 后端
├── streaming/    # 实验性近实时 2-Stem 监听（默认关闭）
├── ui/           # PySide6 + PyQtGraph 桌面界面、酸性遥测样式引擎、紧凑 [?] 说明徽标与设置面板
├── packaging/    # PyInstaller 打包规范与 requirements-ai / requirements-midi 依赖约束
├── scripts/      # Windows 环境初始化 (setup_windows.ps1)、硬件自检与 Inno Setup 安装脚本
└── docs/         # 架构说明、开发接手记录 (CURRENT_STATE.md / HANDOFF.md)、打包指南与 Windows 实测报告
```

- **Core 环境（`.venv-core`，Python 3.12）**：仅包含 GUI、WASAPI 捕获与纯 CPU DSP，不依赖 PyTorch 或 TensorFlow。
- **GPU AI 环境（`.venv-ai`，Python 3.12 + CUDA 12.8）**：仅在点击离线分轨或近实时分轨时由子进程按需启动；软件内置 **本机 PyTorch 自动扫描器**，若未安装会提供官方下载指引。针对 `8 GB VRAM / 16 GB RAM`（如 RTX 5060 Ti 8GB）默认采用 6 秒安全分块。
- **CPU MIDI 环境（`.venv-midi`，Python 3.11 + Basic Pitch）**：独立 CPU 单轨转 MIDI 环境，未配置时自动回退至内置轻量算法。

---

## 快速上手

### 1. 直接使用安装包 / 便携版

从 Release 下载 `ListenScope-Setup-Windows-x64.exe` 或 `ListenScope-Core-Windows-x64-Portable.zip`。
程序默认将配置文件（`settings.json`）、离线工作区和导出的 WAV/MIDI **保存在软件同级目录**，不会往 `C:\` 盘写入垃圾文件。

### 2. 从源码运行（Windows）

推荐使用 PowerShell 7 (`pwsh`) 在短路径目录（如 `E:\LS`）初始化环境：

```powershell
# 一键创建 Core / GPU AI / CPU MIDI 三个虚拟环境（若有本地 CUDA Wheel 目录可加 -CudaWheelDir）
pwsh -ExecutionPolicy Bypass -File scripts\setup_windows.ps1

# 启动 ListenScope（会自动探测同级或本机已安装的 PyTorch / MIDI 环境）
.\.venv-core\Scripts\python.exe main.py
```

### 3. 开发与测试（Windows / Linux）

仅安装基础依赖即可运行桌面 UI（非 Windows 下使用 `--simulate` 合成信号）与自动化测试：

```bash
pip install -r requirements-core.txt pytest
python main.py --simulate
QT_QPA_PLATFORM=offscreen pytest -q --tb=short
```

---

## 文档导航

工程细节、打包流程与开发接手记录已归档至 `docs/` 目录：

- [项目当前状态与开发记录 (docs/CURRENT_STATE.md)](docs/CURRENT_STATE.md)
- [维护接手指南 (docs/HANDOFF.md)](docs/HANDOFF.md)
- [架构设计 (docs/ARCHITECTURE.md)](docs/ARCHITECTURE.md) & [设计决策 (docs/DECISIONS.md)](docs/DECISIONS.md)
- [Windows 打包与环境配置 (docs/PACKAGING.md)](docs/PACKAGING.md)
- [Windows 11 + RTX 5060 Ti 实测报告 (docs/WINDOWS_TEST_REPORT.md)](docs/WINDOWS_TEST_REPORT.md)

---

## 致谢与反馈

本项目基于众多优秀的开源音频算法与模型构建，详见 [致谢与来源 (ACKNOWLEDGMENTS.md)](ACKNOWLEDGMENTS.md)。

如果 ListenScope 对你的听歌、练琴或扒谱有帮助，欢迎在 GitHub 点一颗 ⭐ **Star**，或在 [Issues](https://github.com/Ceph-learner/ListenScope/issues) 中提交问题与建议。
