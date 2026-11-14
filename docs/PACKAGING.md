# ListenScope Windows 打包与三环境隔离部署指南 (Section 21)

## 1. 为什么要拆分为 Core + AI Worker + CPU MIDI 隔离环境？

ListenScope 严格遵守“**Core 轻量常驻、AI 按需隔离、不炸内存**”架构：

- **Target PC 硬性基线**: Windows（按进程捕获需要 Build `20348` 或更高） · **NVIDIA GeForce RTX 5060 Ti (8GB VRAM)** · **16GB RAM**
- **ListenScope Core (`.venv-core` / `ListenScope.exe`, 实测 Python 3.12.16 x64)**:
  - 仅包含 GUI (`PySide6>=6.8.0,<6.10` + `pyqtgraph`)、WASAPI 音频捕获 (`proc-tap` + `pycaw` + `PyAudioWPatch`)、120s PCM 环形缓冲、纯 CPU WSOLA 不变调变速回放 (`audio/time_stretch.py`) 与 CPU 实时频谱/chroma/和弦/调性/BPM 分析。
  - **版本约束说明**: `PySide6` 明确锁定 `<6.10`（避免上游 `6.12.0` 信号释放崩溃风险）。
  - **禁止捆绑 CUDA / PyTorch / TensorFlow DLL**，常态主进程 RAM 目标 `< 1GB`（真机实测约 `301–391 MiB`）。
- **ListenScope AI Worker (`.venv-ai`, 实测 Python 3.12.16 x64 + CUDA 12.8)**:
  - 独立 Python 虚拟环境，运行在已通过 RTX 5060 Ti (`sm_120`) 实测验证的依赖组合：
    - `torch==2.11.0+cu128` + `torchaudio==2.11.0+cu128` + `torchvision==0.26.0+cu128` (`--index-url https://download.pytorch.org/whl/cu128`)
    - `onnxruntime-gpu 1.26.0`（锁定 `<1.27`，ORT 1.27+ 切换为 CUDA 13）
    - `audio-separator[gpu]>=0.48.0`、`audioread>=3.1.0`（补齐 `audio-separator` + `librosa 1.0` 加载传递依赖）、`demucs>=4.1.0`
  - **cu128 依赖约束保护**（[`constraints-ai-cu128.txt`](../constraints-ai-cu128.txt) 与 [`scripts/setup_windows.ps1`](../scripts/setup_windows.ps1)）：先从 PyTorch 官方 `cu128` 索引安装 `torch==2.11.0`、`torchaudio==2.11.0`、`torchvision==0.26.0`，随后在安装 `requirements-ai.txt` 时传入 `-c constraints-ai-cu128.txt`（并在脚本内动态写出精确 `+cu128` 版本约束），防止 `pip` 从 PyPI 解析 `torchvision` 等传递依赖时把已安装的 `2.11.0+cu128` 替换为 PyPI 默认版本。
  - **故意移出 `basic-pitch`**: `basic-pitch 0.4.0` 依赖 `tensorflow<2.15.1`（最高 Python 3.11），移出后 `.venv-ai` 可在 Python 3.12 零冲突通过 `pip check`，且 `basic-pitch` 缺失时 `gpu_ai_ready` 仍正确返回 `READY`。
  - **无需临时 `sitecustomize.py`**: Round 2 & Round 3 实测常规 ONNX Runtime 配置即可在 8GB VRAM / 16GB RAM 下稳定完成（30s MDX 2-Stem 耗时 `10.66s`，峰值显存 `4420 MiB`；30s HTDemucs 4-Stem 耗时 `4.92s`，峰值显存 `3532 MiB`）。
  - 仅在用户点击 `AI 2-Stem` / `AI 4-Stem`（或手动开启实验性实时分轨）时由 `AIJobManager` 作为子进程串行启动；离线默认 **`long_audio_chunk_seconds=6.0`s**、HTDemucs 默认 **`demucs_default_segment_sec=6`s**（MDX 内部 `segment_size=256` 独立），低于 `3072 MiB` 拒绝新任务、低于 `2048 MiB` 急停，任务退出后 100% 释放整颗 Worker 进程树与 RAM/VRAM。
- **ListenScope CPU MIDI (`.venv-midi`, 实测 Python 3.11.18 x64)**:
  - 独立 CPU 转录环境（[`requirements-midi.txt`](../requirements-midi.txt)）：`basic-pitch>=0.4.0,<0.5`、`tensorflow>=2.13.0,<2.15.1`（实测 `2.15.0`）、`setuptools>=68.0,<81`（实测 `79.0.1`，提供 `resampy` 所需 `pkg_resources`）、`numpy<2.0`（实测 `1.26.4`）、`psutil>=5.9.0`、`mido>=1.3.0`。
  - **打包版跨版本 Python 启动保护**（[`run_external_python`](../core/paths.py)）：打包版 `ListenScope.exe`（内嵌 Python 3.12 扩展与 `_internal` DLL 目录）在调用外部 Python 3.11 时，会临时调用 `SetDllDirectoryW(None)` 复原 Windows 默认 DLL 搜索顺序、从子进程 `PATH`/`PYTHONPATH` 剔除 `_internal` 目录，并通过 `sys.path.append(bundle)` 将打包内 ListenScope 源码置于外部解释器标准库与 `site-packages` **末尾**，避免加载包内 Python 3.12 的 `_socket.pyd` / `python312.dll`。
  - **TensorFlow 2.15 Windows 长路径注意事项**：当系统 `LongPathsEnabled=0` 时，在过深目录安装 `tensorflow 2.15.0` 会因深层头文件（如 `alts_grpc_integrity_only_record_protocol.h`）超过 260 字符触发 `pip` `[Errno 2]`。已验证方案：将仓库检出在短路径（如 `E:\LS-midi`），或运行 `setup_windows.ps1 -MidiVenvPath E:\LS-midi\.venv-midi` 在短路径创建 `.venv-midi`，然后在「设置 -> 独立 CPU MIDI Python 路径」中选择 `E:\LS-midi\.venv-midi\Scripts\python.exe`。

---

## 2. Windows 真机安装与打包步骤

### 一键自动化脚本（推荐使用 PowerShell 7 `pwsh` 在短路径目录执行）

仓库 [`scripts/setup_windows.ps1`](../scripts/setup_windows.ps1) 与 [`scripts/build_windows.ps1`](../scripts/build_windows.ps1) 会自动检测 Python 3.12 x64 (Core + AI) 与可选 Python 3.11 x64 (`.venv-midi`)、安装已验证版本的 `cu128` Torch 三件套 + 约束保护下的 AI 依赖 + MIDI 依赖、检查 FFmpeg 查找路径并对每个环境执行 `pip check`：

```powershell
# 建议在短路径目录 (如 E:\LS 或 C:\LS) 使用 PowerShell 7 (pwsh) 执行，避免 TensorFlow 2.15 长路径及 PS 5.1 编码问题
pwsh -ExecutionPolicy Bypass -File scripts\setup_windows.ps1

# 也可显式指定解释器路径或将 .venv-midi 放在独立短路径:
# pwsh -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -PythonExe C:\Python312\python.exe -MidiPythonExe C:\Python311\python.exe -MidiVenvPath E:\LS-midi\.venv-midi

# 构建轻量 Core 可执行目录 dist\ListenScopeCore\ListenScope.exe
pwsh -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -Clean
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
> 1. RTX 5060 Ti 属于 Blackwell 架构 (`sm_120`)：PyTorch 三件套（`torch==2.11.0`、`torchaudio==2.11.0`、`torchvision==0.26.0`）必须先从 `cu128` 索引安装。
> 2. 安装 `requirements-ai.txt` 时**必须附带 `-c constraints-ai-cu128.txt`**，防止 PyPI 在解析 `torchvision` 时把已装好的 `2.11.0+cu128` 替换为 PyPI 上的其他版本。
> 3. `onnxruntime-gpu` 必须锁定 `<1.27`（已验证 `1.26.0`；ORT 1.27+ 起已转向 CUDA 13）。

```powershell
py -3.12 -m venv .venv-ai
.\.venv-ai\Scripts\activate
pip install --upgrade pip

# 1. 从官方 cu128 索引安装已验证的 PyTorch + Torchaudio + Torchvision
pip install torch==2.11.0 torchaudio==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128

# 2. 带 cu128 约束安装 AI 分轨依赖 (保住 2.11.0+cu128 / 0.26.0+cu128，不含 basic-pitch)
pip install -r requirements-ai.txt -c constraints-ai-cu128.txt
pip check

# 3. 验证 GPU AI 准入状态返回 READY (basic_pitch 为 OPT 可选)
python scripts\check_env.py --json --check-ai-packages --write-report SYSTEM_REPORT.md
```

### Step C: 建立独立 CPU MIDI 环境 (`.venv-midi`, Python 3.11 x64 · 短路径方案)

> [!TIP]
> **处理 TensorFlow 长路径限制 (`LongPathsEnabled=0`)**：
> TensorFlow 2.15 含超长 C++ 头文件路径（如 `alts_grpc_integrity_only_record_protocol.h`）。若当前仓库路径较深，无需修改系统注册表，直接在盘符根部短路径（例如 `E:\LS-midi\.venv-midi`）创建虚拟环境即可：

```powershell
# 方案 1: 使用 setup_windows.ps1 指定短路径创建 .venv-midi
pwsh -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -SkipAI -MidiPythonExe C:\Python311\python.exe -MidiVenvPath E:\LS-midi\.venv-midi

# 方案 2: 手动在短路径创建 .venv-midi
py -3.11 -m venv E:\LS-midi\.venv-midi
E:\LS-midi\.venv-midi\Scripts\python.exe -m pip install --upgrade pip
E:\LS-midi\.venv-midi\Scripts\python.exe -m pip install -r requirements-midi.txt
E:\LS-midi\.venv-midi\Scripts\python.exe -m pip check

# 验证 Basic Pitch / TensorFlow / pkg_resources / psutil / mido 探针
E:\LS-midi\.venv-midi\Scripts\python.exe scripts\check_env.py --json --check-midi-packages --no-write
```

### Step D: FFmpeg 查找规则与打包启动

- **FFmpeg 查找顺序**（[`core/paths.py`](../core/paths.py)）: 系统 `PATH` -> 当前工作目录 -> 可执行文件目录 / Bundle 根目录 -> `ffmpeg/`、`ffmpeg/bin/`、`tools/ffmpeg/bin/`、`../tools/ffmpeg/bin/`；主进程会在启动 AI/MIDI/Benchmark 子进程前自动把命中的 FFmpeg 目录注入子进程 `PATH`。WAV 可直走 `soundfile`，但部分模型加载和封装格式需要 `ffmpeg.exe`。
- **源码运行**:
  ```powershell
  .\.venv-core\Scripts\python.exe main.py --ai-python .\.venv-ai\Scripts\python.exe --midi-python E:\LS-midi\.venv-midi\Scripts\python.exe
  ```
- **打包目录运行**: `dist\ListenScopeCore\ListenScope.exe`（[`listenscope_core.spec`](../packaging/listenscope_core.spec) 已同步打包 `requirements-ai.txt`、`constraints-ai-cu128.txt`、`requirements-midi.txt` 与全部 Worker 模块）。首次运行可通过 `--ai-python` / `--midi-python` 传入，或在 **设置 -> 资源安全阈值 & AI 配置** 页面浏览、验证并保存至 `~/.listenscope/settings.json`（重启 `ListenScope.exe` 后自动保留）。

### Windows 真机音频设备与现场排障说明

- **44.1kHz / 96kHz 声卡或蓝牙耳机静音启动问题（上游 `proctap 1.1.1` 特性）**:
  - 推荐在 Windows「声音设置 -> 默认格式」保持 **48000 Hz**；若使用其他采样率设备，先让 QQ 音乐开始出声再点击「开始捕获」。如仍受限可切换 `[兜底] 系统 WASAPI Loopback`。
- **一键导出脱敏诊断包 (`.zip`)**:
  - 在 **4. 系统资源 & 性能日志** 页点击 **「导出诊断包 (.zip)」**，导出 `SYSTEM_REPORT.md`、硬件摘要（含 AI/MIDI 路径及 FFmpeg 探测路径）、最近 500 条日志、最新性能日志尾部及脱敏设置。

---

## 3. Windows 真机实测状态与待完成验证项

### 已在 Windows 11 真机（RTX 5060 Ti 8GB VRAM / 16GB RAM）实测通过（详见 [WINDOWS_TEST_REPORT.md](WINDOWS_TEST_REPORT.md)）

- Core、GPU AI 与独立 CPU MIDI 三个环境均通过 `pip check`，Windows `pytest` **111/111** 全通
- 打包版 `ListenScope.exe` 下 `QQMusic.exe` 按进程捕获（播放 `~-34 dBFS`、暂停 `-120 dBFS`、恢复 `~-35 dBFS`）、输出设备热切换重连、目标进程退出安全停止、0.5× WSOLA A/B 循环回放及配置恢复
- 打包版默认配置（`6.0s` 分块 / HTDemucs `6s` 分段 / MDX `256`）下同一 30 秒音频完成 GPU 2-Stem（`10.66s`，峰值显存 `4420 MiB`，最低可用 RAM `2425 MiB`）与 GPU 4-Stem（`4.92s`，峰值显存 `3532 MiB`，最低可用 RAM `2811 MiB`），退出后显存回落至 `~1950 MiB`、Worker 子树清零
- 打包版 `ListenScope.exe` 调用独立 Python 3.11 `.venv-midi`（`run_external_python` 隔离 `python312.dll`）完成四轨 `bass` 的 **Spotify Basic Pitch CPU (`basic-pitch`)** 转录与 `.mid` 导出（`120` 音符），重启 `exe` 后 MIDI 路径持久化保留

### 仍需在本机复测 / 待验收项

1. **正式安装脚本短路径全新安装 + 新打包版 MIDI 复验**: 在独立短路径目录直接运行更新后的 `scripts\setup_windows.ps1`（验证内置 `cu128` 约束无需手工干预完成安装），并从新打包版导出真实贝斯轨 `.mid` 确认显示 **Spotify Basic Pitch CPU**。
2. **30 分钟 QQ 音乐连续捕获与主动切歌重置验收**: 实测完整 **30 分钟 QQ 音乐连续捕获** 与 **主动切歌时分析状态（和弦进行、调性、BPM 等）是否正确重置**，记录内存、队列、捕获中断与切歌前后状态。
3. **持续近实时播放（留待下一轮单独测试）**: 在本机单独测试实验性近实时分轨持续播放的延迟、掉块与资源占用。
