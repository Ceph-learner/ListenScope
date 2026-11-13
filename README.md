# ListenScope

**完全免费、离线、本地运行** 的 Windows 音乐分析、A/B 循环与扒谱辅助桌面软件。无需下载 QQ 音乐加密歌曲文件、无需解密缓存、无需绕过 DRM，即可一边在 QQ 音乐（或任意桌面应用）正常听歌，一边实时分析频谱/Chroma/和弦（含音阶构成音实时拼写、12 步进行轨迹与一键换歌重置）/调性/BPM/主音高可视化音准条（`-50 ~ +50 cents`），支持 **纯 CPU Capo / 乐器移调实时联动**（自动同步实时分析、12 步和弦带、分轨深度报告、Live 和弦 HUD 与 `.md/.csv` 扒谱表并保留原始实音对照）、纯 CPU **Tap 定速、检测 BPM 一键同步、1 小节预备拍与 `0%–150%` 音量可调练习节拍器**（自动持久化 BPM/拍号/音量/预备拍/移调偏好），在 **120 秒交互式波形时间轴**（含 `A-1s/A+1s/B-1s/B+1s` 区间微调与反转归一化、黄线实时播放头、最多 12 个自动防滚出 **A/B 练习书签**、单次/循环开关及 `0.5x–1.25x` 纯 CPU 不变调倍速）上拖拽选区回放或**分块导出应用当前倍速与节拍器 Click 的 A/B / 分轨混音练习 WAV**，并对历史片段进行本地 AI 分轨（2-Stem / 4-Stem）、无损流式和弦（可选 `maj7/m7/7/sus4`）/Bass/鼓组/主旋律深度分析、选中和弦片段局部循环练习、Live 当前（含构成音）/下一和弦 HUD、MIDI 转录、钢琴卷帘点击画面跳转、`Ctrl+Space` 全局播放/暂停以及一键导出**脱敏排障诊断包 (`.zip`)**。

---

## 硬性目标硬件规范与资源安全原则

- **目标系统**: Windows（按进程捕获需要 Build `20348` 或更高）
- **目标 GPU**: `NVIDIA GeForce RTX 5060 Ti` (Blackwell, `sm_120`)
- **GPU 显存**: **8GB VRAM**（严格按 8GB 预算，绝非 16GB VRAM）
- **系统内存**: **16GB RAM**

核心安全准则：
1. **CPU 实时基础与练习工具**：实时波形、FFT/对数频谱（带横轴十倍频防重叠刻度）、12-bin Chroma、12 大/小三和弦（实时显示构成音拼写、有界 12 步进行与一键换歌重置；离线深度分析可选 `maj7/m7/7/sus4` 扩展和弦）、调性、BPM、主音高与 `-50 ~ +50c` 彩色音准指针条 (`TuningCentsBar`)、**纯 CPU Capo / 乐器移调联动**（UI 与 `.md/.csv` 扒谱表同步移调显示）、纯 CPU Tap 定速与练习节拍器（支持 `0%–150%` 音量调节、1 小节预备拍、独立跟练及自动对齐 `0.5x–1.25x` 回放速度）、鼓组 Kick/Snare/Hi-Hat 16 步律动、Bass 根音、主旋律音域、`.md/.csv` 扒谱报告原子导出以及纯 CPU WSOLA 不变调变速回放与分块练习 WAV 导出全部纯 CPU 运行，不依赖 PyTorch GPU 且不打断实时捕获。
2. **120 秒固定 PCM 环形缓冲、A/B 选区与有界书签**：统一 `48kHz / stereo / float32`（固定预分配 ~46.08 MB），支持流式载入本地音频前 `<=120s` 片段（先成功解码首块后再清空旧历史，避免损坏文件抹除既有缓冲）、底部 120s 波形总览拖拽 A/B 选区、`A-1s/A+1s/B-1s/B+1s` 区间微调、实时黄线播放游标、最多 12 个按环形缓冲绝对帧追踪并随滑窗滚出自动清理的 A/B 练习书签、单次/循环切换及独立原子导出（支持带当前倍速与节拍器 Click 的练习 WAV）；禁止无限音频队列、禁止一次性整首解码进 RAM。
3. **三环境隔离 + 严格串行单模型 + 6 秒实测安全默认**：
   - `.venv-core`（Python 3.12 x64）：轻量桌面 GUI 与 WASAPI/DSP，禁止混入 PyTorch/CUDA。
   - `.venv-ai`（Python 3.12 x64 + `torch/torchaudio 2.11.0+cu128` + `onnxruntime-gpu 1.26.0` + `audio-separator 0.48.0` + `demucs 4.1.0` + `audioread 3.1.0`）：每次最多 1 个任务、1 个模型；离线默认 **6.0s 流式分块** (`long_audio_chunk_seconds=6.0`)、HTDemucs 默认 **6s 模型分段** (`demucs_default_segment_sec=6`，保留 MDX 内部 `segment_size=256` 与已保存自定义设置)；低于 **3072 MiB** 拒绝启动新任务、低于 **2048 MiB** 自动急停并清理整颗进程树与暂存；任务拒绝/异常会在界面直接展示当前可用 RAM 与失败原因。
   - `.venv-midi`（Python 3.11 x64 + `basic-pitch>=0.4.0,<0.5` + `tensorflow<2.15.1` + `setuptools<81` + `psutil` + `mido`）：独立 CPU MIDI 解释器，可在「设置」选择、验证并保存；环境缺失时展示配置说明，并在回退至 `cpu_monophonic_fallback_test` 时明确标识实际算法。
4. **明确 GPU 准入、v2 持久化设置与一键排障**：启动、应用设置与「验证 AI 环境」同步检测驱动、NVML、`torch.cuda.is_available()`、`sm_120` 核函数、ONNX Runtime `CUDAExecutionProvider`、`demucs`/`audio-separator`/`audioread` 与 FFmpeg 可用性（`basic-pitch` 已移出 GPU 环境，不影响 `gpu_ai_ready = READY`）；`PersistedSettings` (v2 兼容 v1) 自动记忆阈值、`.venv-ai`/`.venv-midi` 路径与练习参数；资源面板支持一键导出脱敏诊断包 `.zip`。
5. **随时可用的红色「紧急停止 AI」按钮**：强制结束 worker 进程树、清理 IPC 与任务暂存输出、重采样 RAM/VRAM，主界面与实时捕获永不中断。

---

## 模块架构

```text
ListenScope/
├── core/               # 硬件与 MIDI 探针 (Phase 0), frozen/FFmpeg/只读可写路径解析 (paths.py), ResourceLimits, ResourceManager, PersistedSettings v2, PerformanceLogger, 脱敏诊断打包 (diagnostics.py)
├── audio/              # WASAPI Process Loopback (Build >= 20348)/System Loopback, decode_wave_bytes/PCM 规范化, FixedRingBuffer(120s), WSOLA 不变调变速, Tap 定速与 CPU 节拍器, 有界 A/B 书签, HistoryABPlayer/StemMixerEngine
├── analysis/           # CPU DSP(NaN/Inf 清洗): 频谱/Chroma/和弦/Capo移调/调性/BPM, 无损流式分轨深度解析 (stem_analyzer.py), Basic Pitch / 轻量单音回退 MIDI 转录 (midi_transcription.py)
├── ai/                 # 模型注册表(htdemucs_4stem 默认 6s 分段), 流式 WAV 分块守护(默认 6.0s 分块), 隔离 AIWorkerProcess, AIJobManager(进程树清理与 RAM 拒停告警)
├── separation/         # 2-Stem MDX-ONNX 后端 & 4-Stem HTDemucs 后端 (全链路 2ch float32 与任务内 tmp 隔离)
├── streaming/          # Phase 8 实验性近实时 2-Stem 分轨 (默认关闭, 独立 .venv-ai 隔离、RTF 基准与 ASCII 安全 JSON IPC)
├── ui/                 # PySide6 + PyQtGraph GUI (防重叠对数频谱刻度, Chroma/Capo/节拍器, 120s 拖拽时间轴, 分轨混音与算法可见 MIDI 钢琴卷帘, AI & MIDI 独立验证设置页)
├── packaging/          # PyInstaller Core 规范 (排除 CUDA/PyTorch/TF 臃肿依赖, 附带 requirements-ai.txt / requirements-midi.txt 及 Worker 模块)
├── scripts/            # check_env.py (--check-ai-packages / --check-midi-packages / FFmpeg 探针), setup_windows.ps1 & build_windows.ps1
├── docs/               # PACKAGING.md 与 WINDOWS_TEST_REPORT.md (Windows 11 + RTX 5060 Ti 真机两轮验收记录)
├── capture_test.py     # Phase 1 CLI 捕获 + ResourceManager PoC
└── main.py             # 桌面主程序入口 (分离 --ai-python 与 --midi-python 路由与偏好持久化)
```

---

## 环境 Honest Status 说明（重要）

> [!NOTE]
> 以下区分 **云端 Linux 自动化验证**、**Windows 真机实测已通过项** 与 **待真机补验项**（详情见 [docs/WINDOWS_TEST_REPORT.md](docs/WINDOWS_TEST_REPORT.md)）：
> - **Windows 11 + RTX 5060 Ti (8GB VRAM, 16GB RAM) 已实测通过**：Core 依赖安装与 Windows 测试回归、Build `20348+` 按进程 QQ 音乐捕获、输出设备热切换、QQ 音乐退出保护、0.5× WSOLA A/B 循环与节拍器持久化、FFT 对数刻度防重叠修复、`torch 2.11.0+cu128` + `onnxruntime-gpu 1.26.0` + `audio-separator 0.48.0` + `demucs 4.1.0` + `audioread 3.1.0` 下连续 5 次 30s GPU 二轨/四轨（6s 分块 & 6s 分段，无需临时 `sitecustomize.py`）、30 分钟 WAV 4-Stem 流式分块、Worker 取消/强杀/手动急停暂存与进程树清理，以及 Python 3.11 CPU 下 Basic Pitch (`141` 音符) 转录。
> - **云端 Linux 沙箱已验证（无 Windows 声卡 / 无 NVIDIA GPU）**：安装脚本/依赖校验、6s 默认配置与旧 `settings.json` 迁移兼容、低 RAM 拒绝/急停文案展示、`--midi-python` 独立进程路由与回退算法 UI 提示、以及完整 headless PySide6 + pytest 自动化回归。
> - **仍待 Windows 本机复测/验收**：使用最新版 `scripts\setup_windows.ps1` 全新部署 `.venv-core`/`.venv-ai`/`.venv-midi` 与 `pip check`、最新打包版 `ListenScope.exe` 下 QQ 音乐捕获 + 默认 30s 二轨/四轨 + 贝斯 `.mid` 导出，以及完整 **30 分钟 QQ 音乐连续捕获**、**逐项对时切歌重置**与**持续近实时播放**。

---

## 快速运行

### 1. 运行自动化测试套件

```bash
pytest -v
```

### 2. 非 Windows 合成测试信号启动桌面 UI（演示 / 调试）

```bash
python main.py --simulate
```

### 3. Windows 真机安装与运行

详见 [docs/PACKAGING.md](docs/PACKAGING.md)，一键初始化 `.venv-core` / `.venv-ai` / `.venv-midi` 并运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
.\.venv-core\Scripts\python.exe scripts\check_env.py --write-report SYSTEM_REPORT.md
.\.venv-core\Scripts\python.exe capture_test.py --name QQMusic.exe --fallback-system
.\.venv-core\Scripts\python.exe main.py --ai-python .\.venv-ai\Scripts\python.exe --midi-python .\.venv-midi\Scripts\python.exe
```
