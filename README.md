# ListenScope

<p align="left">
  <a href="README.md">简体中文</a> ·
  <a href="README.en.md">English</a> ·
  <a href="README.ko.md">한국어</a> ·
  <a href="README.ja.md">日本語</a>
</p>

<p align="left">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%2F11%20(x64)-0078D4?style=flat-square" alt="Windows" />
  <img src="https://img.shields.io/badge/Release-v1.0.1-00A878?style=flat-square" alt="Release" />
  <img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" alt="License" />
</p>

**免费、离线、本地运行**的 Windows 桌面听歌分析、A/B 循环与扒谱练习工作台。

无需下载加密音乐缓存，也不必折腾虚拟声卡。在播放器或浏览器正常听歌时，ListenScope 直接通过 Windows 标准音频接口按进程捕获实时声音，提供频谱/音准分析、和弦与调性识别、120 秒回溯 A/B 慢放、本地 AI 分轨和 Cubase 兼容 MIDI 导出。

<p align="center">
  <img src="docs/images/demo.gif" alt="ListenScope 实时分析演示（模拟信号）" width="820" />
</p>

---

## 快速上手（图形界面一键配置 · 无需命令行）

1. **下载安装**：前往 [Releases](https://github.com/Ceph-learner/ListenScope/releases) 下载安装版 `ListenScope-Setup-Windows-x64.exe` 或免安装便携版 `ListenScope-Core-Windows-x64-Portable.zip`。
2. **双击启动**：运行 `ListenScope.exe`。**实时频谱、和弦/调性/BPM 识别、120 秒 A/B 慢放循环与节拍器开箱即用**，无需显卡即可运行。
3. **配置 AI 分轨与 MIDI（可选，图形界面一键完成）**：
   - 点击右上角 **`CONFIG // 设置`** → 左侧 **`AI 与 MIDI 环境`**。
   - 若本机已有 PyTorch / Conda 环境，点击 **「扫描本机 PyTorch 环境」** 自动识别；
   - 若尚未安装，点击 **「一键自动配置 AI + MIDI」** 自动下载配置独立运行环境，完成后点击重启按钮即可生效。
4. **开始使用**：在顶栏 `AUDIO_IN // 音源` 下拉框选择正在播放音乐的进程，点击 **`CAPTURE_START // 开始捕获`**。

> 配置文件（`settings.json`）、工作区缓存与导出的 WAV/MIDI 默认保存在**软件同级目录**，不向 `C:\` 盘写入冗余文件。

<p align="center">
  <img src="docs/images/settings_ai.png" alt="设置页图形化一键配置 AI 与 MIDI" width="740" />
</p>

---

## 核心功能

| 模块 | 功能说明 |
| :--- | :--- |
| **实时捕获与频谱** | Windows 进程环回捕获（Build ≥ 20348，无需虚拟声卡）或系统环回；仅通过系统标准音频接口捕获实时播放输出，不涉及绕过加密或缓存提取；提供波形、FFT / 对数频谱、基频 `F0` 与 `-50 ~ +50 cents` 音准刻度条 |
| **和弦、调性与 Capo** | 12-bin Chroma 热图、大/小三和弦与构成音识别、罗马级数、12 步和弦轨迹、纯 CPU **Capo 移调联动**、24 调和弦练习弹窗（支持本地合成试听与 `.mid` 导出） |
| **120 秒回溯与 A/B 练习** | 固定 120s 环形缓冲（`48 kHz / Stereo / float32`）、拖拽 A/B 选区、`0.5x–1.25x` 不变调变速回放、12 个练习书签、Tap 定速节拍器（含预备拍）及练习 WAV 导出 |
| **本地 AI 分轨与混音** | 独立子进程按需运行 2-Stem（人声/伴奏）或 4-Stem（人声/鼓组/贝斯/其他）分离，默认 6 秒安全分块与随时急停释放显存；支持 **`0–24 dB` 贝斯独听增益**与 FFT-YIN 贝斯最低音（低至 `B0`/`E1`）检测 |
| **MIDI 导出与 Cubase 适配** | 支持分轨后一键转 MIDI 或直接打开本地单轨 WAV 转 MIDI；所有和弦、鼓点与单轨 MIDI 均统一规范为 **Steinberg Cubase 兼容 SMF Type-0 (`480 TPB`)** |
| **主题与四语界面** | 默认 **酸性遥测（临床浅色）** 工业视觉，顶栏一键切换暗夜/浅色；内置经典、极光冰蓝、石墨靛紫、暖砂琥珀主题，支持 **中 / 英 / 韩 / 日** 实时切换与无边框圆角窗口 |

<p align="center">
  <img src="docs/images/chroma.png" alt="和弦、调性与音准分析" width="440" />
  <img src="docs/images/main_dark.png" alt="暗夜工业模式" width="440" />
</p>

---

## 硬件兼容性说明

- 目前实机主要在 **Windows 11 + NVIDIA RTX 5060 Ti (8 GB VRAM) + 16 GB RAM** 环境验证通过，默认 6 秒分块与三级内存护栏（5120 / 3072 / 2048 MiB）均按该规格保守标定。
- 其余显卡型号、核显或不同系统配置尚未全面实测；如在使用中遇到兼容或性能问题，欢迎在 [Issues](https://github.com/Ceph-learner/ListenScope/issues) 反馈硬件信息与诊断包日志。

---

## 开发者与源码运行

为保持主界面轻量流畅（无显卡也可运行全部实时分析与 A/B 练习），项目采用三环境隔离结构：

```text
ListenScope/
├── core/         # 配置与同级便携路径、多语言 (zh/en/ko/ja)、外观模型、PyTorch 扫描与资源守卫
├── audio/        # WASAPI 捕获、120s 环形缓冲、WSOLA 变速、节拍器、试听合成与四轨混音
├── analysis/     # CPU 频谱/Chroma/和弦/调性/BPM、FFT-YIN 贝斯与 Cubase SMF Type-0 MIDI 导出
├── ai/           # 分轨模型注册表、流式分块守护与独立 AI 子进程管理
├── separation/   # 2-Stem MDX-ONNX 与 4-Stem HTDemucs 后端
├── streaming/    # 实验性近实时 2-Stem 监听（默认关闭）
├── ui/           # PySide6 + PyQtGraph 桌面界面与样式引擎
├── packaging/    # PyInstaller 打包规范与环境依赖约束
├── scripts/      # Windows 一键初始化 (setup_windows.ps1)、硬件探针与 Inno Setup 脚本
└── docs/         # 架构说明、技术决策、开发指南与打包文档
```

### 从源码启动与测试

```powershell
# Windows：在短路径目录初始化 Core / GPU AI / CPU MIDI 三个环境
pwsh -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
.\.venv-core\Scripts\python.exe main.py
```

```bash
# Linux / 无声卡环境使用模拟信号与运行测试
pip install -r requirements-core.txt pytest
python main.py --simulate
QT_QPA_PLATFORM=offscreen pytest -q --tb=short
```

---

## 相关文档与开源协议

- [架构设计 (docs/ARCHITECTURE.md)](docs/ARCHITECTURE.md) · [技术决策 (docs/DECISIONS.md)](docs/DECISIONS.md) · [开发指南 (docs/DEVELOPMENT.md)](docs/DEVELOPMENT.md) · [打包文档 (docs/PACKAGING.md)](docs/PACKAGING.md) · [贡献指南 (CONTRIBUTING.md)](CONTRIBUTING.md)
- 本项目基于 [MIT License](LICENSE) 开源；所集成的第三方模型与开源库保留各自许可协议，详见 [致谢与来源 (ACKNOWLEDGMENTS.md)](ACKNOWLEDGMENTS.md)。
- ListenScope 与文中提及的任何第三方音乐播放器、DAW 或硬件厂商均无隶属或商业合作关系；各商标归其各自所有者所有。
