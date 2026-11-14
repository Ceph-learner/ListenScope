# ListenScope Windows 打包与三环境隔离部署指南 (Section 21)

## 1. 为什么要拆分为 Core + AI Worker + CPU MIDI 隔离环境？

ListenScope 严格遵守“**Core 轻量常驻、AI 按需隔离、不炸内存**”架构：

- **Target PC 硬性基线**: Windows（按进程捕获需要 Build `20348` 或更高） · **NVIDIA GeForce RTX 5060 Ti (8GB VRAM)** · **16GB RAM**
- **ListenScope Core (`.venv-core` / `ListenScope.exe`, 实测 Python 3.12.16 x64)**:
  - 仅包含 GUI (`PySide6>=6.8.0,<6.10` + `pyqtgraph`)、WASAPI 音频捕获 (`proc-tap` + `pycaw` + `PyAudioWPatch`)、120s PCM 环形缓冲、Windows SMTC 曲目监测可选 WinRT 绑定 (`winrt-Windows.Media.Control>=3.0`，[`core/media_session.py`](../core/media_session.py))、纯 CPU WSOLA 不变调变速回放 (`audio/time_stretch.py`) 与 CPU 实时频谱/chroma/和弦/调性/BPM 分析。
  - **版本约束说明**: `PySide6` 明确锁定 `<6.10`（避免上游 `6.12.0` 信号释放崩溃风险）。
  - **禁止捆绑 CUDA / PyTorch / TensorFlow DLL**，常态主进程 RAM 目标 `< 1GB`（30 分钟连续真机实测约 `289–362 MiB`）。
- **ListenScope AI Worker (`.venv-ai`, 实测 Python 3.12.16 x64 + CUDA 12.8)**:
  - 独立 Python 虚拟环境，运行在已通过 RTX 5060 Ti (`sm_120`) 实测验证的依赖组合：
    - `torch==2.11.0+cu128` + `torchaudio==2.11.0+cu128` + `torchvision==0.26.0+cu128`（在线 `--index-url https://download.pytorch.org/whl/cu128`，或通过 `setup_windows.ps1 -CudaWheelDir <目录>` **优先从本地官方 wheel 安装**）
    - `onnxruntime-gpu 1.26.0`（锁定 `<1.27`，ORT 1.27+ 切换为 CUDA 13）
    - `audio-separator[gpu]>=0.48.0`、`audioread>=3.1.0`（补齐 `audio-separator` + `librosa 1.0` 加载传递依赖）、`demucs>=4.1.0`
  - **cu128 依赖约束保护**（[`constraints-ai-cu128.txt`](../constraints-ai-cu128.txt) 与 [`scripts/setup_windows.ps1`](../scripts/setup_windows.ps1)）：无论走在线 `cu128` 索引还是 `-CudaWheelDir` 本地 wheel，安装脚本均会在装好 PyTorch 三件套后读取实际 `+cu128` 版本、生成 `.venv-ai\cuda-constraints.txt` 并以 `-c` / `PIP_CONSTRAINT` 安装 `requirements-ai.txt`，再校验三者版本均含 `+cu128` 与执行 `pip check`，防止 `pip` 从 PyPI 解析 `torchvision` 等传递依赖时把已安装的 `2.11.0+cu128` 替换为 PyPI 默认版本。
  - **故意移出 `basic-pitch`**: `basic-pitch 0.4.0` 依赖 `tensorflow<2.15.1`（最高 Python 3.11），移出后 `.venv-ai` 可在 Python 3.12 零冲突通过 `pip check`，且 `basic-pitch` 缺失时 `gpu_ai_ready` 仍正确返回 `READY`。
  - **无需临时 `sitecustomize.py`**: Round 2 / Round 3 / Round 4 实测常规 ONNX Runtime 配置即可在 8GB VRAM / 16GB RAM 下稳定完成（30s MDX 2-Stem 耗时 `9.47s`，30s HTDemucs 4-Stem 耗时 `4.34s`）。
  - 仅在用户点击 `AI 2-Stem` / `AI 4-Stem`（或手动开启实验性实时分轨）时由 `AIJobManager` 作为子进程串行启动；离线默认 **`long_audio_chunk_seconds=6.0`s**、HTDemucs 默认 **`demucs_default_segment_sec=6`s**（MDX 内部 `segment_size=256` 独立），低于 `3072 MiB` 拒绝新任务、低于 `2048 MiB` 急停，任务退出后 100% 释放整颗 Worker 进程树与 RAM/VRAM。
- **ListenScope CPU MIDI (`.venv-midi`, 实测 Python 3.11.18 x64)**:
  - 独立 CPU 转录环境（[`requirements-midi.txt`](../requirements-midi.txt)）：`basic-pitch>=0.4.0,<0.5`、`tensorflow>=2.13.0,<2.15.1`（实测 `2.15.0`）、`setuptools>=68.0,<81`（实测 `79.0.1`，提供 `resampy` 所需 `pkg_resources`）、`numpy<2.0`（实测 `1.26.4`）、`psutil>=5.9.0`、`mido>=1.3.0`。
  - **打包版跨版本 Python 启动保护**（[`run_external_python`](../core/paths.py)）：打包版 `ListenScope.exe`（内嵌 Python 3.12 扩展与 `_internal` DLL 目录）在调用外部 Python 3.11 时，会临时调用 `SetDllDirectoryW(None)` 复原 Windows 默认 DLL 搜索顺序、从子进程 `PATH`/`PYTHONPATH` 剔除 `_internal` 目录，并通过 `sys.path.append(bundle)` 将打包内 ListenScope 源码置于外部解释器标准库与 `site-packages` **末尾**，避免加载包内 Python 3.12 的 `_socket.pyd` / `python312.dll`。
  - **单轨 WAV 直接转 MIDI 入口**：在 Tab 3 (`3. AI 分轨混音与多轨练习`) 可点击 **「打开单轨 WAV 转 MIDI...」**（或 MIDI 子页 **「打开单轨 WAV...」**），直接选择本地任意目录已有的单轨 WAV（如 `bass.wav`），在不停止实时捕获、不清空 120s 环形缓冲的前提下直接载入混音器、写入 `work_dir/midi/` 中间 `.mid`（不污染原 WAV 所在外部目录）、并走独立 Python 3.11 Basic Pitch CPU Worker 完成转录与 `.mid` 另存。
  - **TensorFlow 2.15 Windows 长路径注意事项**：当系统 `LongPathsEnabled=0` 时，在过深目录安装 `tensorflow 2.15.0` 会因深层头文件（如 `alts_grpc_integrity_only_record_protocol.h`）超过 260 字符触发 `pip` `[Errno 2]`。已验证方案：将仓库检出在短路径（如 `E:\LS-midi`），或运行 `setup_windows.ps1 -MidiVenvPath E:\LS-midi\.venv-midi` 在短路径创建 `.venv-midi`，然后在「设置 -> 独立 CPU MIDI Python 路径」中选择 `E:\LS-midi\.venv-midi\Scripts\python.exe`。

---

## 2. Windows 真机安装与打包步骤

### 一键自动化脚本（推荐使用 PowerShell 7 `pwsh` 在短路径目录执行）

仓库 [`scripts/setup_windows.ps1`](../scripts/setup_windows.ps1) 与 [`scripts/build_windows.ps1`](../scripts/build_windows.ps1) 会自动检测 Python 3.12 x64 (Core + AI) 与可选 Python 3.11 x64 (`.venv-midi`)、安装已验证版本的 `cu128` Torch 三件套 + 约束保护下的 AI 依赖 + MIDI 依赖、检查 FFmpeg 查找路径并对每个环境执行 `pip check`：

```powershell
# 1. 标准在线安装（建议在短路径目录如 E:\LS 或 C:\LS 使用 PowerShell 7 执行）
pwsh -ExecutionPolicy Bypass -File scripts\setup_windows.ps1

# 2. 优先使用本地官方 cu128 wheel 安装（推荐在 2.75 GB 官方在线 wheel 下载停滞/超时时切换）
#    先确认目录内已下载官方匹配版本：
#      - torch-2.11.0+cu128-cp312-cp312-win_amd64.whl
#      - torchaudio-2.11.0+cu128-cp312-cp312-win_amd64.whl
#      - torchvision-0.26.0+cu128-cp312-cp312-win_amd64.whl
#    （注意：若浏览器下载把 "+" 存成 "%2B"，请先将文件名中的 "%2B" 重命名为 "+"）
pwsh -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -CudaWheelDir E:\cuda_wheels

# 3. 也可叠加指定解释器路径或将 .venv-midi 放在独立短路径：
pwsh -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -CudaWheelDir E:\cuda_wheels -PythonExe C:\Python312\python.exe -MidiPythonExe C:\Python311\python.exe -MidiVenvPath E:\LS-midi\.venv-midi

# 4. 构建轻量 Core 可执行目录 dist\ListenScopeCore\ListenScope.exe
pwsh -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -Clean
```

> [!WARNING]
> **在线下载停滞切换说明 & 仍需联网范围**：
> - 第四轮 Windows 验收记录中，在线默认路径在下载 2753.2 MB `torch` wheel 时约 6 分钟仍停留在 0 字节（主动停止前 pip 未给出原始异常，网络卡顿具体根因待查）。如遇同样停滞，可用浏览器/独立下载工具将上述 3 个官方 `+cu128` (`cp312-win_amd64`) wheel 预先放到同一本地目录后改传 `-CudaWheelDir <目录>`。
> - **哪些步骤仍需联网（即使传入 `-CudaWheelDir`）**：
>   1. 升级 `pip` 与安装 Core 环境 [`requirements-windows.txt`](../requirements-windows.txt)（含 `PySide6`、`proc-tap`、`winrt-Windows.Media.Control` 等）。
>   2. 若 `-CudaWheelDir` 只放了 `torch` / `torchaudio` / `torchvision` 其中 1–2 个，缺项会自动回退到 `$CudaIndexUrl` (`https://download.pytorch.org/whl/cu128`) 在线安装；`torch` 家族的纯 Python 传递依赖（如 `sympy`、`networkx`、`filelock`、`fsspec`、`jinja2`、`typing-extensions`、`numpy`、`pillow`）也会优先复用 `-CudaWheelDir`，本地未提供时按需联网获取。
>   3. 安装 [`requirements-ai.txt`](../requirements-ai.txt) 其余包（`onnxruntime-gpu 1.26.0`、`audio-separator`、`demucs`、`audioread` 等，全过程受 `cuda-constraints.txt` 保护不降级/不覆盖 `+cu128`）仍需从 PyPI 联网获取（除非自行准备全量离线 wheel 缓存）。
>   4. 安装独立 `.venv-midi` 的 [`requirements-midi.txt`](../requirements-midi.txt) 仍需联网（可加 `-SkipMidi` 跳过）。
>   5. 首次使用 AI 分轨或 Basic Pitch 若本地尚无模型缓存，下载模型权重仍需联网（已缓存后可设 `HF_HUB_OFFLINE=1`）。

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

# 3. 只读探测 QQ 音乐 Windows 媒体会话 (SMTC) 切歌信号（可选加 --json）
python scripts\probe_media_session.py --process QQMusic.exe --duration 30
```

### Step B: 建立独立 RTX 5060 Ti AI Worker 环境 (`.venv-ai`, Python 3.12 x64)

> [!IMPORTANT]
> 1. RTX 5060 Ti 属于 Blackwell 架构 (`sm_120`)：PyTorch 三件套（`torch==2.11.0`、`torchaudio==2.11.0`、`torchvision==0.26.0`）必须从官方 `cu128` 索引（或本地下载的对应 `+cu128` wheel）安装。
> 2. 安装 `requirements-ai.txt` 时**必须附带 `-c constraints-ai-cu128.txt`**，防止 PyPI 在解析 `torchvision` 时把已装好的 `2.11.0+cu128` 替换为 PyPI 上的其他版本。
> 3. `onnxruntime-gpu` 必须锁定 `<1.27`（已验证 `1.26.0`；ORT 1.27+ 起已转向 CUDA 13）。

```powershell
py -3.12 -m venv .venv-ai
.\.venv-ai\Scripts\activate
pip install --upgrade pip

# 1A. 在线从官方 cu128 索引安装已验证的 PyTorch + Torchaudio + Torchvision
pip install torch==2.11.0 torchaudio==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
# 1B. 若在线下载 2.75 GB wheel 停滞，改为先指向本地官方 cu128 wheel 目录：
# pip install --find-links E:\cuda_wheels E:\cuda_wheels\torch-2.11.0+cu128-cp312-cp312-win_amd64.whl E:\cuda_wheels\torchaudio-2.11.0+cu128-cp312-cp312-win_amd64.whl E:\cuda_wheels\torchvision-0.26.0+cu128-cp312-cp312-win_amd64.whl

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

### Step D: FFmpeg 查找规则、SMTC 自动切歌与打包启动

- **FFmpeg 查找顺序**（[`core/paths.py`](../core/paths.py)）: 系统 `PATH` -> 当前工作目录 -> 可执行文件目录 / Bundle 根目录 -> `ffmpeg/`、`ffmpeg/bin/`、`tools/ffmpeg/bin/`、`../tools/ffmpeg/bin/`；主进程会在启动 AI/MIDI/Benchmark 子进程前自动把命中的 FFmpeg 目录注入子进程 `PATH`。WAV 可直走 `soundfile`，但部分模型加载和封装格式需要 `ffmpeg.exe`。
- **SMTC 自动切歌重置 (`自动切歌重置` 开关 + 手动「换歌重置」保底)**: Core 环境可选安装 `winrt-Windows.Media.Control` 后，按进程捕获期间会在后台以只读模式查询目标进程（如 `QQMusic.exe`）的 Windows SMTC 会话；同一首歌暂停/恢复/快进快退/瞬态空标题/浏览器无关会话不会误清空历史，仅在连续 2 次轮询确认新曲目后调用既有 `reset_harmony()` + 清空最近 12 步和弦带并保持捕获不断。如目标机未启用 SMTC 或尚未验证 QQ 音乐兼容细节，可先运行只读探针 `scripts\probe_media_session.py --process QQMusic.exe --duration 30` 确认，并随时使用手动「换歌重置 (和弦/调性/BPM)」按钮。
- **源码运行**:
  ```powershell
  .\.venv-core\Scripts\python.exe main.py --ai-python .\.venv-ai\Scripts\python.exe --midi-python E:\LS-midi\.venv-midi\Scripts\python.exe
  ```
- **打包目录运行**: `dist\ListenScopeCore\ListenScope.exe`（[`listenscope_core.spec`](../packaging/listenscope_core.spec) 已同步打包 `requirements-ai.txt`、`constraints-ai-cu128.txt`、`requirements-midi.txt`、`winrt` 运行时与全部 Worker/Probe 模块）。首次运行可通过 `--ai-python` / `--midi-python` 传入，或在 **设置 -> 资源安全阈值 & AI 配置** 页面浏览、验证并保存至 `~/.listenscope/settings.json`（重启 `ListenScope.exe` 后自动保留）。

### Windows 真机音频设备与现场排障说明

- **44.1kHz / 96kHz 声卡或蓝牙耳机静音启动问题（上游 `proctap 1.1.1` 特性）**:
  - 推荐在 Windows「声音设置 -> 默认格式」保持 **48000 Hz**；若使用其他采样率设备，先让 QQ 音乐开始出声再点击「开始捕获」。如仍受限可切换 `[兜底] 系统 WASAPI Loopback`。
- **一键导出脱敏诊断包 (`.zip`)**:
  - 在 **4. 系统资源 & 性能日志** 页点击 **「导出诊断包 (.zip)」**，导出 `SYSTEM_REPORT.md`、硬件摘要（含 AI/MIDI 路径及 FFmpeg 探测路径）、最近 500 条日志、最新性能日志尾部及脱敏设置。

---

## 3. Windows 真机实测状态与待完成验证项

### 已在 Windows 11 真机（RTX 5060 Ti 8GB VRAM / 16GB RAM）实测通过（详见 [WINDOWS_TEST_REPORT.md](WINDOWS_TEST_REPORT.md)）

- Core、GPU AI 与独立 CPU MIDI 三个环境均通过 `pip check`，Windows `pytest` **112/112** 全通（第四轮），本地核验 wheel + 自动生成 `cu128` 约束通过 CUDA 执行
- **30 分钟 QQ 音乐按进程连续捕获通过（第四轮）**：`process_loopback` 连续运行满 30 分钟，主进程 RSS `289–362 MiB`、队列始终 `0/64`、累计溢出/欠载 `0/0`，以及**手动点击「换歌重置」**立即清空 12 步和弦/BPM/调性而不中断捕获
- 打包版 `ListenScope.exe` 输出设备热切换重连、目标进程退出安全停止、0.5× WSOLA A/B 循环回放及配置重启保留（含 `midi_python`、分块 6s、Demucs 6s 与 GPU 解锁状态）
- 打包版默认配置（`6.0s` 分块 / HTDemucs `6s` 分段 / MDX `256`）下第四轮实测 GPU 2-Stem（`9.469s`，2,670 个 CUDA 节点事件，峰值显存 `4631 MiB`，最低可用 RAM `3181 MiB`）与 GPU 4-Stem（`4.344s`，峰值显存 `3209 MiB`，最低可用 RAM `3503 MiB`），退出后 Worker 子树归零、显存回落至 `~2087–2102 MiB`
- 打包版 `ListenScope.exe` 调用独立 Python 3.11 `.venv-midi` 完成 `bass` 的 **Spotify Basic Pitch CPU (`basic-pitch`)** 转录与 `.mid` 导出（`120` 音符，与 CLI 诊断 SHA-256 逐字节一致），重启 `exe` 后 MIDI 路径持久化保留

### 仍需在本机复测 / 待验收项

1. **`-CudaWheelDir` 安装路径与单轨 WAV 直接转 MIDI GUI 入口真机复验**: 在干净目录实测 `scripts\setup_windows.ps1 -CudaWheelDir <本地wheel目录>` 全流程、`pip check`、重打包 `ListenScope.exe` 并从 GUI 直接打开上一轮 `bass.wav`（不重新分轨、不清空捕获缓冲）验证 **Spotify Basic Pitch CPU (`basic-pitch`)** 预览与可用 `mido` 解析的 `.mid` 导出。
2. **QQ 音乐 Windows SMTC 只读探针与自动切歌重置实测**: 在 Windows 11 本机运行 `scripts\probe_media_session.py --process QQMusic.exe --duration 30` 检查 QQ 音乐是否稳定暴露 SMTC 曲目元信息，并在新打包 GUI 验证 **同曲暂停 / 恢复 / 拖动进度条不误清历史** 与 **真实切换歌曲 A -> B 自动重置**（以及关闭开关仅用手动重置）。
3. **持续近实时播放（继续标为待验收）**: 在本机单独测试实验性近实时分轨持续播放的延迟、掉块与资源占用。
