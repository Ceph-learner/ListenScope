# ListenScope Windows 打包与双环境部署指南 (Section 21)

## 1. 为什么要拆分为 Core + AI Worker 双环境？

ListenScope 严格遵守“**Core 轻量常驻、AI 按需隔离、不炸内存**”架构：

- **Target PC 硬性基线**: Windows 10/11 (Build >= `19041`) · **NVIDIA GeForce RTX 5060 Ti (8GB VRAM，非 16GB)** · **16GB RAM**
- **ListenScope Core (`.venv-core` / `ListenScopeCore.exe`)**:
  - 仅包含 GUI (`PySide6>=6.8.0,<6.10` + `pyqtgraph`)、WASAPI 音频捕获 (`proc-tap` + `pycaw` + `PyAudioWPatch`)、120s PCM 环形缓冲与 CPU 实时频谱/chroma/和弦/调性/BPM 分析。
  - **版本约束说明**: `PySide6` 明确锁定 `<6.10`（实测 `6.8.3 LTS` 连续刷新零引用计数异常；已验证上游 `6.12.0` 存在 `Signal.emit` 导致 `bool_dealloc`/`none_dealloc` 崩溃的风险）。
  - **禁止捆绑 CUDA / PyTorch DLL**，常态主进程 RAM 目标 `< 1GB`。
- **ListenScope AI Worker (`.venv-ai`)**:
  - 独立 Python 虚拟环境，包含支持 **Blackwell (`sm_120`)** 的 PyTorch (`>= 2.7.0`, CUDA `>= 12.8`)、`onnxruntime-gpu` (`CUDAExecutionProvider`)、`audio-separator`、`demucs`、`basic-pitch`。
  - 仅在用户点击 `AI 2-Stem` / `AI 4-Stem`（或手动开启实验性实时分轨）时由 `AIJobManager` 作为子进程启动，任务完成/取消/紧急停止后进程退出，100% 归还 RAM 与 8GB VRAM 给操作系统。

---

## 2. Windows 真机安装与打包步骤

### Step A: 建立 Core 环境并验证 Phase 0 & Phase 1

```powershell
python -m venv .venv-core
.\.venv-core\Scripts\activate
pip install --upgrade pip
pip install -r requirements-windows.txt

# 1. 运行硬件与 CUDA 探针
python scripts\check_env.py --write-report

# 2. 验证 QQ 音乐音频捕获 (WASAPI Process Loopback)
python capture_test.py --list-procs
python capture_test.py --name QQMusic.exe --fallback-system
```

### Step B: 建立独立 RTX 5060 Ti AI Worker 环境 (`.venv-ai`)

> [!IMPORTANT]
> RTX 5060 Ti 属于 Blackwell 架构 (`sm_120`)，旧版 CUDA 11.x / 12.1 PyTorch 会报错 `no kernel image is available for execution on the device` 或静默失败。必须安装 **CUDA >= 12.8** 构建的 PyTorch (`>= 2.7.0`) 与匹配版本的 `onnxruntime-gpu` + cuDNN 9.x。

```powershell
python -m venv .venv-ai
.\.venv-ai\Scripts\activate
pip install --upgrade pip

# 1. 安装适配 RTX 5060 Ti (sm_120) 的 PyTorch CUDA 构建
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128

# 2. 安装其余 AI 分轨与 MIDI 依赖
pip install -r requirements-ai.txt

# 3. 验证 GPU AI 准入状态必须返回 gpu_ai_ready = READY
python scripts\check_env.py --write-report
```

### Step C: 启动桌面端或使用 PyInstaller 打包 Core

直接源码运行（Core 自动探测同目录 `.venv-ai\Scripts\python.exe`）：

```powershell
.\.venv-core\Scripts\activate
python main.py --ai-python .\.venv-ai\Scripts\python.exe
```

使用 PyInstaller 打包独立 Core 可执行目录（**未在 Windows 真机实际编译打包，需在真机执行**）：

```powershell
.\.venv-core\Scripts\activate
pip install pyinstaller
pyinstaller packaging\listenscope_core.spec --noconfirm
```

打包输出位于 `dist\ListenScopeCore\ListenScope.exe`。打包规范（[`listenscope_core.spec`](../packaging/listenscope_core.spec)）会自动打包 `proctap` / `soundfile` 原生库并附带 `ai/`、`separation/`、`core/`、`analysis/` 纯 Python 模块，以便外部 `.venv-ai\Scripts\python.exe` 同时执行音轨分离（`python -m ai.worker`）与 Basic Pitch MIDI 转录（`python -m analysis.midi_transcription`）。运行后可在 **设置 -> 资源安全阈值 & AI 配置 -> 独立 AI Worker Python 路径** 指向 `.venv-ai\Scripts\python.exe`。

### Windows 真机音频设备排障说明（捕获前必看）

- **44.1kHz / 96kHz 声卡或蓝牙耳机静音启动变音问题（上游 `proctap 1.1.1` 已知特性）**：
  - 上游 `proc-tap` 在非 48kHz 采样率设备上会进入自检分支；若启动捕获瞬间目标播放器恰好处于纯静音，格式自检可能暂落回 INT16。
  - **推荐做法**：在 Windows「声音设置 -> 扬声器/耳机属性 -> 高级 -> 默认格式」保持 **24位/16位 48000 Hz（推荐）**；若使用 44.1kHz / 96kHz 外置声卡，先让 QQ 音乐开始出声再点击 ListenScope「开始捕获」。如仍受设备限制，可切换至 `[兜底] 系统 WASAPI Loopback`。

---

## 3. Windows 真机必须执行的 10 项验收测试 (Test A - J)

在真实 Windows 10/11 + QQ 音乐 + RTX 5060 Ti (8GB VRAM) + 16GB RAM 机器上依次验证（当前仅在 Linux 通过等价非 GPU/合成自动化验证，**以下真机项待实地确认**）：

1. **Test A (30 分钟 QQ 音乐连续捕获)**: 实时波形/频谱/chroma/和弦/调性/BPM 运行 30 分钟，主进程 RAM、环形缓冲与队列长度无持续线性增长。
2. **Test B (关闭 QQ 音乐测试)**: 捕获中途直接关闭 `QQMusic.exe`，ListenScope 优雅停止捕获、不崩溃、不锁死音频资源。
3. **Test C (切换输出设备测试)**: 播放过程中切换耳机/音响/蓝牙，系统不崩溃并自动重连或安全提示。
4. **Test D (连续 5 次 AI 分轨泄露测试)**: 对同一段 30 秒片段连续执行 5 次 2-Stem MDX 与 4-Stem HTDemucs 分轨，检查第 5 次结束后 RAM / 8GB VRAM 恢复至初始基准。
5. **Test E (取消任务测试)**: 分别在 `LoadingModel`、`Inferring`、`Writing` 阶段点击取消，确认进程干净退出且 `workspace_outputs/stems/` 无残留临时目录。
6. **Test F (RTX 5060 Ti OOM 模拟/高压测试)**: 降低 `segment` 或触发 OOM 时弹出 3 选 1 恢复方案（降 segment / 换轻量模型 / 切 CPU fallback），无无限重试。
7. **Test G (低可用 RAM 保护测试)**: 后台打开浏览器/DAW 将可用 RAM 压到 `< 3GB`，确认系统拒绝启动新 AI 任务；压到 `< 2GB` 时自动触发紧急停止。
8. **Test H (30 分钟长音频流式分轨测试)**: 输入 30 分钟 WAV，验证流式分块读写下峰值 RAM 与 VRAM 保持低位，不一次性解码进 RAM。
9. **Test I (强杀 Worker 进程容错测试)**: 任务 Manager 强行结束 `ListenScope-AIWorker`，主程序与 QQ 音乐实时频谱继续正常运行。
10. **Test J (紧急停止 AI 按钮测试)**: 分轨中途点击顶部红色 **"紧急停止 AI"**，1 秒内释放 worker/临时文件并重新采样 RAM/VRAM，主界面正常继续。
