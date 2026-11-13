# ListenScope Windows 打包与三环境隔离部署指南 (Section 21)

## 1. 为什么要拆分为 Core + AI Worker + CPU MIDI 隔离环境？

ListenScope 严格遵守“**Core 轻量常驻、AI 按需隔离、不炸内存**”架构：

- **Target PC 硬性基线**: Windows（按进程捕获需要 Build `20348` 或更高） · **NVIDIA GeForce RTX 5060 Ti (8GB VRAM)** · **16GB RAM**
- **ListenScope Core (`.venv-core` / `ListenScope.exe`, 实测 Python 3.12 x64)**:
  - 仅包含 GUI (`PySide6>=6.8.0,<6.10` + `pyqtgraph`)、WASAPI 音频捕获 (`proc-tap` + `pycaw` + `PyAudioWPatch`)、120s PCM 环形缓冲、纯 CPU WSOLA 不变调变速回放 (`audio/time_stretch.py`) 与 CPU 实时频谱/chroma/和弦/调性/BPM 分析。
  - **版本约束说明**: `PySide6` 明确锁定 `<6.10`（避免上游 `6.12.0` 信号释放崩溃风险）。
  - **禁止捆绑 CUDA / PyTorch / TensorFlow DLL**，常态主进程 RAM 目标 `< 1GB`。
- **ListenScope AI Worker (`.venv-ai`, 实测 Python 3.12.16 x64 + CUDA 12.8)**:
  - 独立 Python 虚拟环境，运行在已通过 RTX 5060 Ti (`sm_120`) 实测验证的依赖组合：
    - `torch==2.11.0` + `torchaudio==2.11.0` (`--index-url https://download.pytorch.org/whl/cu128`)
    - `onnxruntime-gpu 1.26.0`（锁定 `<1.27`，ORT 1.27+ 切换为 CUDA 13）
    - `audio-separator[gpu]>=0.48.0`、`audioread>=3.1.0`（补齐 `audio-separator` + `librosa 1.0` 加载传递依赖）、`demucs>=4.1.0`
  - **故意移出 `basic-pitch`**: `basic-pitch 0.4.0` 依赖 `tensorflow<2.15.1`（最高 Python 3.11），移出后 `.venv-ai` 可在 Python 3.12 零冲突通过 `pip check`，且 `basic-pitch` 缺失时 `gpu_ai_ready` 仍正确返回 `READY`。
  - **无需临时 `sitecustomize.py`**: Round 2 实测常规 ONNX Runtime 配置即可在 8GB VRAM / 16GB RAM 下稳定完成。
  - 仅在用户点击 `AI 2-Stem` / `AI 4-Stem`（或手动开启实验性实时分轨）时由 `AIJobManager` 作为子进程串行启动；离线默认 **`long_audio_chunk_seconds=6.0`s**、HTDemucs 默认 **`demucs_default_segment_sec=6`s**（MDX 内部 `segment_size=256` 独立），低于 `3072 MiB` 拒绝新任务、低于 `2048 MiB` 急停，任务退出后 100% 释放整颗 Worker 进程树与 RAM/VRAM。
- **ListenScope CPU MIDI (`.venv-midi`, 实测 Python 3.11 x64)**:
  - 独立 CPU 转录环境（`requirements-midi.txt`）：`basic-pitch>=0.4.0,<0.5`、`tensorflow>=2.13.0,<2.15.1`、`setuptools>=68.0,<81`（提供 `resampy` 所需 `pkg_resources`）、`numpy<2.0`、`psutil>=5.9.0`、`mido>=1.3.0`。
  - 源码版与打包版 GUI 的 **转 MIDI** 按钮统一从该独立解释器调用 `python -m analysis.midi_transcription`（在「设置 -> 独立 CPU MIDI Python 路径」配置并验证）。若未配置或缺少依赖，界面会给出明确配置方法，并在触发 `cpu_monophonic_fallback_test` 轻量回退时显式标出实际算法。

---

## 2. Windows 真机安装与打包步骤

### 一键自动化脚本

仓库 [`scripts/setup_windows.ps1`](../scripts/setup_windows.ps1) 与 [`scripts/build_windows.ps1`](../scripts/build_windows.ps1) 会自动检测 Python 3.12 x64 (Core + AI) 与可选 Python 3.11 x64 (`.venv-midi`)、安装已验证版本的 `cu128` Torch / ORT / AI / MIDI 依赖、检查 FFmpeg 查找路径并对每个环境执行 `pip check`：

```powershell
# 创建 .venv-core、.venv-ai (cu128) 与可选 .venv-midi (若系统装有 Python 3.11)，并生成 SYSTEM_REPORT.md
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1

# 也可显式指定解释器版本或跳过部分环境:
# powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -PythonExe C:\Python312\python.exe -MidiPythonExe C:\Python311\python.exe

# 构建轻量 Core 可执行目录 dist\ListenScopeCore\ListenScope.exe
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -Clean
```

若需手动逐步安装与校验，可按以下步骤执行：

### Step A: 建立 Core 环境 (Python 3.12 x64)

```powershell
py -3.12 -m venv .venv-core
.\.venv-core\Scripts\activate
pip install --upgrade pip
pip install -r requirements-windows.txt
pip check

# 1. 运行硬件探针
python scripts\check_env.py --write-report SYSTEM_REPORT.md

# 2. 验证 QQ 音乐音频捕获 (WASAPI Process Loopback)
python capture_test.py --list-procs
python capture_test.py --name QQMusic.exe --fallback-system
```

### Step B: 建立独立 RTX 5060 Ti AI Worker 环境 (`.venv-ai`, Python 3.12 x64)

> [!IMPORTANT]
> RTX 5060 Ti 属于 Blackwell 架构 (`sm_120`)：PyTorch 必须从 `cu128` 索引安装（已验证 `2.11.0+cu128`），且 `onnxruntime-gpu` 必须锁定 `<1.27`（已验证 `1.26.0`；ORT 1.27+ 起已转向 CUDA 13）。

```powershell
py -3.12 -m venv .venv-ai
.\.venv-ai\Scripts\activate
pip install --upgrade pip

# 1. 安装已验证的 PyTorch cu128 构建
pip install torch==2.11.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu128

# 2. 安装 AI 分轨依赖 (不含 basic-pitch)
pip install -r requirements-ai.txt
pip check

# 3. 验证 GPU AI 准入状态返回 READY (basic_pitch 为 OPT 可选)
python scripts\check_env.py --json --check-ai-packages --write-report SYSTEM_REPORT.md
```

### Step C: 建立独立 CPU MIDI 环境 (`.venv-midi`, Python 3.11 x64)

```powershell
py -3.11 -m venv .venv-midi
.\.venv-midi\Scripts\activate
pip install --upgrade pip
pip install -r requirements-midi.txt
pip check

# 验证 Basic Pitch / TensorFlow / pkg_resources / mido 探针
python scripts\check_env.py --json --check-midi-packages --no-write
```

### Step D: FFmpeg 查找规则与打包启动

- **FFmpeg 查找顺序**（[`core/paths.py`](../core/paths.py)）: 系统 `PATH` -> 当前工作目录 -> 可执行文件目录 / Bundle 根目录 -> `ffmpeg/`、`ffmpeg/bin/`、`tools/ffmpeg/bin/`、`../tools/ffmpeg/bin/`；主进程会在启动 AI/MIDI/Benchmark 子进程前自动把命中的 FFmpeg 目录注入子进程 `PATH`。WAV 可直走 `soundfile`，但部分模型加载和封装格式需要 `ffmpeg.exe`。
- **源码运行**:
  ```powershell
  .\.venv-core\Scripts\python.exe main.py --ai-python .\.venv-ai\Scripts\python.exe --midi-python .\.venv-midi\Scripts\python.exe
  ```
- **打包目录运行**: `dist\ListenScopeCore\ListenScope.exe`（[`listenscope_core.spec`](../packaging/listenscope_core.spec) 已同步打包 `requirements-ai.txt`、`requirements-midi.txt` 与全部 Worker 模块）。首次运行可通过 `--ai-python` / `--midi-python` 传入，或在 **设置 -> 资源安全阈值 & AI 配置** 页面浏览、验证并保存至 `~/.listenscope/settings.json`。

### Windows 真机音频设备与现场排障说明

- **44.1kHz / 96kHz 声卡或蓝牙耳机静音启动问题（上游 `proctap 1.1.1` 特性）**:
  - 推荐在 Windows「声音设置 -> 默认格式」保持 **48000 Hz**；若使用其他采样率设备，先让 QQ 音乐开始出声再点击「开始捕获」。如仍受限可切换 `[兜底] 系统 WASAPI Loopback`。
- **一键导出脱敏诊断包 (`.zip`)**:
  - 在 **4. 系统资源 & 性能日志** 页点击 **「导出诊断包 (.zip)」**，导出 `SYSTEM_REPORT.md`、硬件摘要（含 AI/MIDI 路径及 FFmpeg 探测路径）、最近 500 条日志、最新性能日志尾部及脱敏设置。

---

## 3. Windows 真机实测状态与待完成验证项

### 已在 Windows 11 真机（RTX 5060 Ti 8GB VRAM / 16GB RAM）实测通过（详见 [WINDOWS_TEST_REPORT.md](WINDOWS_TEST_REPORT.md)）

- Core 与 Windows 单元测试全通、PyInstaller 构建 `ListenScope.exe` 及外部探针就绪检查
- `QQMusic.exe` 按进程捕获、输出设备热切换重连、目标进程退出安全停止、0.5× WSOLA A/B 循环回放及配置恢复
- FFT 对数频谱横轴防重叠刻度修复（重打包后视觉复核通过）
- 正常 ORT (`1.26.0`) 配置下连续 5 次 30s GPU 2-Stem (`6s` chunk) 与 4-Stem (`6s` chunk / `6s` segment)、30 分钟长 WAV 4-Stem 分块完成，任务取消/强杀/手动急停下 Worker 进程树与暂存全部清除
- 独立 Python 3.11 CPU 环境执行 `analysis.midi_transcription` 转录真实 `bass.wav` -> `.mid` (141 音符)

### 仍需在本机复测 / 待验收项

1. **新脚本全新安装复测**: 按本版 `scripts\setup_windows.ps1` 与 `requirements-ai.txt` / `requirements-midi.txt` 完成 `.venv-core` / `.venv-ai` / `.venv-midi` 安装、`pip check` 与 CUDA 实算校验。
2. **默认 GUI / 打包版端到端分轨与 MIDI 复测**: 不依赖首轮临时 `sitecustomize.py`，用默认设置对同一 30 秒片段在打包版 `ListenScope.exe` 完成 2-Stem 与 4-Stem（记录设备/峰值 RAM 与 VRAM/最低可用 RAM/退出后回落）及 `bass` 轨导出 `.mid`。
3. **长期耐久待验收项**: 完整 **30 分钟 QQ 音乐连续捕获**、逐项对时的 **切歌重置**、以及真实 GPU 下 **持续近实时播放**（除已验证的 RTF 0.4805 基准外）。

