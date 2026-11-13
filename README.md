# ListenScope

**完全免费、离线、本地运行** 的 Windows 音乐分析、A/B 循环与扒谱辅助桌面软件。无需下载 QQ 音乐加密歌曲文件、无需解密缓存、无需绕过 DRM，即可一边在 QQ 音乐（或任意桌面应用）正常听歌，一边实时分析频谱/Chroma/和弦/调性/BPM，并对最近 120 秒历史片段进行 A/B 循环与本地 AI 分轨（2-Stem / 4-Stem）及单轨 MIDI 转录。

---

## 硬性目标硬件规范与资源安全原则

- **目标系统**: Windows 10 / 11 (20H1+, Build >= `19041`)
- **目标 GPU**: `NVIDIA GeForce RTX 5060 Ti` (Blackwell, `sm_120`)
- **GPU 显存**: **8GB VRAM**（严格按 8GB 预算，绝非 16GB VRAM）
- **系统内存**: **16GB RAM**

核心安全准则：
1. **CPU 实时基础分析**：波形、FFT/对数频谱、12-bin Chroma、和弦、调性、BPM 全部纯 CPU 轻量运行，默认不加载 PyTorch。
2. **120 秒固定 PCM 环形缓冲**：统一 `48kHz / stereo / float32`（固定预分配 ~46.08 MB），禁止无限音频队列、禁止保留整场历史。
3. **AI 独立子进程 + 严格串行单模型**：每次最多 1 个任务、1 个模型；按需加载、流式分块推理、任务结束后释放引用并退出子进程由 OS 回收 100% RAM/VRAM。
4. **明确 GPU 准入检查**：启动时检测驱动、NVML、`torch.cuda.is_available()`、`sm_120` 核函数、ONNX Runtime `CUDAExecutionProvider`；不满足直接阻断并提示修复，不静默伪装正常。
5. **随时可用的红色「紧急停止 AI」按钮**：强制结束 worker、清理 IPC 与不完整临时输出、重采样 RAM/VRAM，主界面与实时捕获永不中断。

---

## 模块架构

```text
ListenScope/
├── core/               # Hardware probe (Phase 0), ResourceLimits, ResourceManager, PerformanceLogger
├── audio/              # WASAPI Process/System Loopback, PCM normalize, FixedRingBuffer(120s), HistoryABPlayer, StemMixerEngine
├── analysis/           # CPU DSP: SpectrumAnalyzer, ChromaExtractor, ChordDetector, KeyDetector, TempoEstimator, PitchEstimator, Basic Pitch MIDI adapter
├── ai/                 # Model registry, chunked streaming WAV guard, isolated AIWorkerProcess, AIJobManager + Emergency Stop
├── separation/         # Genuine 2-stem MDX-ONNX backend & strict resource-capped 4-stem HTDemucs backend
├── streaming/          # Phase 8 Experimental Near-Real-Time 2-stem separator (default OFF, RTF benchmark + auto-stop)
├── ui/                 # PySide6 + PyQtGraph GUI (Spectrum, Chroma/Harmony, Mixer/MIDI, Resource Monitor, Settings, MainWindow)
├── packaging/          # PyInstaller Core spec (excludes CUDA/PyTorch bloat)
├── docs/PACKAGING.md   # Split Core vs AI Worker deployment & Windows checklist A-J
├── capture_test.py     # Phase 1 CLI Capture + ResourceManager PoC
└── main.py             # Desktop application entry point
```

---

## 环境 Honest Status 说明（重要）

> [!WARNING]
> 当前代码与自动化单元测试均在 **Linux x86_64 开发沙箱（无 NVIDIA GPU / 非 Windows）** 中完成：
> - **已验证**：`SYSTEM_REPORT.md` 硬件探测、`ResourceManager` 阈值/急停逻辑、120s 固定预分配 `FixedRingBuffer`、CPU DSP 音高/和弦/调性/BPM 准确性、A/B 循环与 `StemMixerEngine` 流式导出、真实 `spawn` 多进程 AI Worker 连续运行无泄漏/取消清理/OOM 3选1/低内存拒绝与急停/30分钟(1800s)流式分块/强杀恢复/实验性实时分轨限流与基准测试、`PySide6` 无头界面 (`QT_QPA_PLATFORM=offscreen`) 完整联调。
> - **未在 Windows 真机验证**：Windows `WASAPI Process Loopback` 对 `QQMusic.exe` 的实际捕获、真实 RTX 5060 Ti (`8GB VRAM`, `sm_120`) 上 PyTorch `cu128`+ / ONNX Runtime `CUDAExecutionProvider` / `audio-separator` / `basic-pitch` 的实测显存峰值与延迟，以及 PyInstaller `.exe` 打包测试。请在真机按 [PACKAGING.md](docs/PACKAGING.md) 验证。

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

详见 [docs/PACKAGING.md](docs/PACKAGING.md) 进行双环境部署（`.venv-core` + `.venv-ai`），并先执行：

```powershell
python scripts\check_env.py --write-report
python capture_test.py --name QQMusic.exe --fallback-system
python main.py --ai-python .\.venv-ai\Scripts\python.exe
```
