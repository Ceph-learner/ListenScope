# ListenScope

**完全免费、离线、本地运行** 的 Windows 音乐分析、A/B 循环与扒谱辅助桌面软件。无需下载 QQ 音乐加密歌曲文件、无需解密缓存、无需绕过 DRM，即可一边在 QQ 音乐（或任意桌面应用）正常听歌，一边实时分析频谱/Chroma/和弦（含音阶构成音实时拼写、12 步进行轨迹与一键换歌重置）/调性/BPM/主音高可视化音准条（`-50 ~ +50 cents`），支持 **纯 CPU Capo / 乐器移调实时联动**（自动同步实时分析、12 步和弦带、分轨深度报告、Live 和弦 HUD 与 `.md/.csv` 扒谱表并保留原始实音对照）、纯 CPU **Tap 定速、检测 BPM 一键同步、1 小节预备拍与 `0%–150%` 音量可调练习节拍器**（自动持久化 BPM/拍号/音量/预备拍/移调偏好），在 **120 秒交互式波形时间轴**（含 `A-1s/A+1s/B-1s/B+1s` 区间微调与反转归一化、黄线实时播放头、最多 12 个自动防滚出 **A/B 练习书签**、单次/循环开关及 `0.5x–1.25x` 纯 CPU 不变调倍速）上拖拽选区回放或**分块导出应用当前倍速与节拍器 Click 的 A/B / 分轨混音练习 WAV**，并对历史片段进行本地 AI 分轨（2-Stem / 4-Stem）、无损流式和弦（可选 `maj7/m7/7/sus4`）/Bass/鼓组/主旋律深度分析、选中和弦片段局部循环练习、Live 当前（含构成音）/下一和弦 HUD、MIDI 转录、钢琴卷帘点击画面跳转、`Ctrl+Space` 全局播放/暂停以及一键导出**脱敏排障诊断包 (`.zip`)**。

---

## 硬性目标硬件规范与资源安全原则

- **目标系统**: Windows（按进程捕获需要 Build `20348` 或更高）
- **目标 GPU**: `NVIDIA GeForce RTX 5060 Ti` (Blackwell, `sm_120`)
- **GPU 显存**: **8GB VRAM**（严格按 8GB 预算，绝非 16GB VRAM）
- **系统内存**: **16GB RAM**

核心安全准则：
1. **CPU 实时基础与练习工具**：实时波形、FFT/对数频谱（带横轴十倍频防重叠刻度）、12-bin Chroma、12 大/小三和弦（实时显示构成音拼写、有界 12 步进行、**手动「换歌重置」与基于 Windows SMTC 的受保护「自动切歌重置」**；离线深度分析可选 `maj7/m7/7/sus4` 扩展和弦）、调性、BPM、主音高与 `-50 ~ +50c` 彩色音准指针条 (`TuningCentsBar`)、**纯 CPU Capo / 乐器移调联动**（UI 与 `.md/.csv` 扒谱表同步移调显示）、纯 CPU Tap 定速与练习节拍器（支持 `0%–150%` 音量调节、1 小节预备拍、独立跟练及自动对齐 `0.5x–1.25x` 回放速度）、鼓组 Kick/Snare/Hi-Hat 16 步律动、Bass 根音、主旋律音域、`.md/.csv` 扒谱报告原子导出以及纯 CPU WSOLA 不变调变速回放与分块练习 WAV 导出全部纯 CPU 运行，不依赖 PyTorch GPU 且不打断实时捕获。
2. **120 秒固定 PCM 环形缓冲、A/B 选区与有界书签**：统一 `48kHz / stereo / float32`（固定预分配 ~46.08 MB），支持流式载入本地音频前 `<=120s` 片段（先成功解码首块后再清空旧历史，避免损坏文件抹除既有缓冲）、底部 120s 波形总览拖拽 A/B 选区、`A-1s/A+1s/B-1s/B+1s` 区间微调、实时黄线播放游标、最多 12 个按环形缓冲绝对帧追踪并随滑窗滚出自动清理的 A/B 练习书签、单次/循环切换及独立原子导出（支持带当前倍速与节拍器 Click 的练习 WAV）；禁止无限音频队列、禁止一次性整首解码进 RAM。
3. **三环境隔离 + 严格串行单模型 + 6 秒实测安全默认**：
   - `.venv-core`（Python 3.12 x64）：轻量桌面 GUI 与 WASAPI/DSP + 可选 Windows SMTC (`winrt-Windows.Media.Control`) 只读曲目监听，禁止混入 PyTorch/CUDA。
   - `.venv-ai`（Python 3.12 x64 + `torch/torchaudio 2.11.0+cu128` + `torchvision 0.26.0+cu128` + `constraints-ai-cu128.txt` + `onnxruntime-gpu 1.26.0` + `audio-separator 0.48.0` + `demucs 4.1.0` + `audioread 3.1.0`）：每次最多 1 个任务、1 个模型；离线默认 **6.0s 流式分块** (`long_audio_chunk_seconds=6.0`)、HTDemucs 默认 **6s 模型分段** (`demucs_default_segment_sec=6`，保留 MDX 内部 `segment_size=256` 与已保存自定义设置)；低于 **3072 MiB** 拒绝启动新任务、低于 **2048 MiB** 自动急停并清理整颗进程树与暂存；`setup_windows.ps1` 支持 `-CudaWheelDir <目录>` 优先使用已下载的官方 `+cu128` 本地 wheel（详见 [docs/PACKAGING.md](docs/PACKAGING.md) 下载停滞切换与联网边界说明）。
   - `.venv-midi`（Python 3.11 x64 + `basic-pitch>=0.4.0,<0.5` + `tensorflow<2.15.1` + `setuptools<81` + `psutil` + `mido`；Windows `LongPathsEnabled=0` 下建议使用短路径如 `E:\LS-midi`）：独立 CPU MIDI 解释器，可在「设置」选择、验证并保存；除分轨后在各单轨点击「转 MIDI」外，也可在 **3. AI 分轨混音与多轨练习** 直接点击 **「打开单轨 WAV 转 MIDI...」** 对本地任意目录已有的单轨 WAV（如 `bass.wav`）无损载入并导出可被 `mido` 解析的 `.mid`；打包版通过 `run_external_python` 自动隔离包内 Python 3.12 DLL/模块搜索路径。
4. **明确 GPU 准入、持久化设置与一键排障**：启动、应用设置与「验证 AI 环境」同步检测驱动、NVML、`torch.cuda.is_available()`、`sm_120` 核函数、ONNX Runtime `CUDAExecutionProvider`、`demucs`/`audio-separator`/`audioread` 与 FFmpeg 可用性（`basic-pitch` 已移出 GPU 环境，不影响 `gpu_ai_ready = READY`）；`PersistedSettings` 自动记忆阈值、`.venv-ai`/`.venv-midi` 路径、SMTC 自动切歌重置开关与练习参数；资源面板支持一键导出脱敏诊断包 `.zip`。
5. **随时可用的红色「紧急停止 AI」按钮**：强制结束 worker 进程树、清理 IPC 与任务暂存输出、重采样 RAM/VRAM，主界面与实时捕获永不中断。

---

## 模块架构

```text
ListenScope/
├── core/               # 硬件与 MIDI 探针, frozen 跨版本外部 Python 启动/FFmpeg 路径解析 (paths.py), Windows SMTC 曲目监听与防抖状态机 (media_session.py), ResourceLimits, ResourceManager, PersistedSettings, 脱敏诊断打包 (diagnostics.py)
├── audio/              # WASAPI Process Loopback (Build >= 20348)/System Loopback, decode_wave_bytes/PCM 规范化, FixedRingBuffer(120s), WSOLA 不变调变速, Tap 定速与 CPU 节拍器, 有界 A/B 书签, HistoryABPlayer/StemMixerEngine
├── analysis/           # CPU DSP(NaN/Inf 清洗): 频谱/Chroma/和弦/Capo移调/调性/BPM, 无损流式分轨深度解析 (stem_analyzer.py), Basic Pitch / 轻量单音回退 MIDI 转录 (midi_transcription.py)
├── ai/                 # 模型注册表(htdemucs_4stem 默认 6s 分段), 流式 WAV 分块守护(默认 6.0s 分块), 隔离 AIWorkerProcess, AIJobManager(进程树清理与 RAM 拒停告警)
├── separation/         # 2-Stem MDX-ONNX 后端 & 4-Stem HTDemucs 后端 (全链路 2ch float32 与任务内 tmp 隔离)
├── streaming/          # Phase 8 实验性近实时 2-Stem 分轨 (默认关闭, 独立 .venv-ai 隔离、RTF 基准与 ASCII 安全 JSON IPC)
├── ui/                 # PySide6 + PyQtGraph GUI (防重叠对数频谱刻度, Chroma/Capo/节拍器/自动切歌开关, 120s 拖拽时间轴, 分轨混音+打开单轨 WAV 转 MIDI+钢琴卷帘, AI & MIDI 独立验证设置页)
├── packaging/          # PyInstaller Core 规范 (排除 CUDA/PyTorch/TF 臃肿依赖, 附带 requirements-ai.txt / constraints-ai-cu128.txt / requirements-midi.txt、winrt 绑定与 Worker/Probe 模块)
├── scripts/            # check_env.py, probe_media_session.py (只读 SMTC 切歌信号探针), setup_windows.ps1 (支持 -CudaWheelDir 与 cu128 约束/短路径) & build_windows.ps1
├── docs/               # CURRENT_STATE/HANDOFF (AI 接手入口), REQUIREMENTS/ARCHITECTURE/DECISIONS/DEVELOPMENT, PACKAGING.md 与 WINDOWS_TEST_REPORT.md (Windows 11 + RTX 5060 Ti 真机五轮验收记录)
├── capture_test.py     # Phase 1 CLI 捕获 + ResourceManager PoC
└── main.py             # 桌面主程序入口 (单轨 WAV 转 MIDI、SMTC 监测、--ai-python 与 --midi-python 路由与偏好持久化)
```

---

## 环境 Honest Status 说明（重要）

> [!NOTE]
> 以下区分 **云端 Linux 自动化验证**、**Windows 真机实测已通过项** 与 **待真机补验项**（详情见 [docs/WINDOWS_TEST_REPORT.md](docs/WINDOWS_TEST_REPORT.md)）：
> - **Windows 11 + RTX 5060 Ti (8GB VRAM, 16GB RAM) 已实测通过（含第四轮 `873db544`）**：Core / GPU AI / CPU MIDI 三环境 `pip check` 与 Windows `pytest` 112/112；**30 分钟 `QQMusic.exe` `process_loopback` 连续捕获**（主进程 `289–362 MiB`、队列 `0/64`、累计溢出/欠载 `0/0`）与**手动点击「换歌重置」**立即清空 12 步历史；打包版默认 `6.0s` 分块下真实 30s GPU 二轨 (`9.469s`，2,670 个 CUDA 节点事件) 与四轨 (`4.344s`) 分离及显存/子树完全回落；打包版调用独立 Python 3.11 CPU 环境导出 `bass` 的 **Spotify Basic Pitch CPU (`basic-pitch`)** `.mid`（`120` 音符，与 CLI 逐字节同源 SHA-256），且重启 `exe` 后保留设置。第四轮报告同步确认：默认在线下载 2.75 GB `torch` wheel 时曾出现 0 字节停滞（未获原始 pip 异常，根因待定位），使用本地官方 wheel + `cu128` 约束路径通过。
> - **云端 Linux 沙箱已验证（无 Windows 声卡 / 无 WinRT SMTC / 无 NVIDIA GPU）**：`setup_windows.ps1 -CudaWheelDir` 参数与错误校验、`打开单轨 WAV...` 直转 MIDI 流程（不中断捕获、不清空 120s 缓冲、不污染源目录）、SMTC `TrackChangeTracker` 防抖状态机与只读探针 `--self-test-mock`（模拟播放/暂停/恢复/拖动进度/闪烁/无关应用无误重置 & 连续两次新曲确认后触发 `reset_harmony()` + 设置开关持久化）、以及完整 headless PySide6 + pytest 自动化回归。
> - **最新状态见 [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md)**。第五轮（`f03dbf1`）在目标机验证了 `-CudaWheelDir` 本地 wheel 安装与单轨 WAV 转 MIDI。历史目录同名 MIDI 覆盖和近实时输出环重复读取均已修复，待目标机复测。QQ 音乐 SMTC 自动重置是否重复触发仍待确认。

---

## 快速运行

### 1. 运行自动化测试套件

```bash
pytest -v
```

### 2. 非 Windows 合成测试信号启动桌面 UI / SMTC 模拟探针

```bash
python main.py --simulate
python scripts/probe_media_session.py --self-test-mock --json
```

### 3. Windows 真机安装与运行

详见 [docs/PACKAGING.md](docs/PACKAGING.md)，建议使用 PowerShell 7 (`pwsh`) 在短路径目录（如 `E:\LS`）初始化 `.venv-core` / `.venv-ai` / `.venv-midi`（若在线下载 2.75 GB `cu128` Torch wheel 停滞，可附加 `-CudaWheelDir E:\cuda_wheels`）：

```powershell
pwsh -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
.\.venv-core\Scripts\python.exe scripts\check_env.py --write-report SYSTEM_REPORT.md
.\.venv-core\Scripts\python.exe scripts\probe_media_session.py --process QQMusic.exe --duration 30
.\.venv-core\Scripts\python.exe capture_test.py --name QQMusic.exe --fallback-system
.\.venv-core\Scripts\python.exe main.py --ai-python .\.venv-ai\Scripts\python.exe --midi-python .\.venv-midi\Scripts\python.exe
```
