# ListenScope

**完全免费、离线、本地运行** 的 Windows 音乐分析、A/B 循环与扒谱辅助桌面软件。无需下载 QQ 音乐加密歌曲文件、无需解密缓存、无需绕过 DRM，即可一边在 QQ 音乐（或任意桌面应用）正常听歌，一边实时分析频谱/Chroma/和弦/调性/BPM，并对最近 120 秒历史片段（或流式载入的 `<=120s` 本地音频片段）进行 A/B 循环、本地 AI 分轨（2-Stem / 4-Stem）、无损流式和弦/Bass/鼓组/主旋律深度分析、MIDI 转录及钢琴卷帘预览。

---

## 硬性目标硬件规范与资源安全原则

- **目标系统**: Windows 10 / 11 (20H1+, Build >= `19041`)
- **目标 GPU**: `NVIDIA GeForce RTX 5060 Ti` (Blackwell, `sm_120`)
- **GPU 显存**: **8GB VRAM**（严格按 8GB 预算，绝非 16GB VRAM）
- **系统内存**: **16GB RAM**

核心安全准则：
1. **CPU 实时基础与分轨深度分析**：实时波形、FFT/对数频谱、12-bin Chroma、和弦、调性、BPM 以及离线分轨深度解析（时间轴和弦进行、Bass 根音与音域、鼓组 Kick/Snare/Hi-Hat 16 步律动、主旋律音域、`.md/.csv` 扒谱报告导出）全部纯 CPU 流式运行，不依赖 PyTorch GPU 且不打断实时捕获。
2. **120 秒固定 PCM 环形缓冲**：统一 `48kHz / stereo / float32`（固定预分配 ~46.08 MB），支持流式载入本地音频前 `<=120s` 片段；禁止无限音频队列、禁止一次性整首解码进 RAM。
3. **AI 独立子进程 + 严格串行单模型**：每次最多 1 个任务、1 个模型；按需加载、流式分块推理、任务结束后释放引用并退出子进程由 OS 回收 100% RAM/VRAM。
4. **明确 GPU 准入与持久化设置**：启动与设置页「验证 AI 环境」按钮实时检测驱动、NVML、`torch.cuda.is_available()`、`sm_120` 核函数、ONNX Runtime `CUDAExecutionProvider` 与 `demucs`/`audio-separator`/`basic-pitch` 可用性；用户设置与阈值安全约束持久化保存在 `~/.listenscope/settings.json`。
5. **随时可用的红色「紧急停止 AI」按钮**：强制结束 worker、清理 IPC 与不完整临时输出、重采样 RAM/VRAM，主界面与实时捕获永不中断。

---

## 模块架构

```text
ListenScope/
├── core/               # 硬件探针 (Phase 0), ResourceLimits, ResourceManager, PersistedSettings (~/.listenscope/settings.json), PerformanceLogger
├── audio/              # WASAPI Process/System Loopback, PCM normalize, FixedRingBuffer(120s + 流式导入), HistoryABPlayer, StemMixerEngine
├── analysis/           # CPU DSP: 频谱/Chroma/和弦/调性/BPM, 无损流式分轨深度解析 (stem_analyzer.py), Basic Pitch MIDI 转录
├── ai/                 # 模型注册表, 流式 WAV 分块守护, 隔离 AIWorkerProcess, AIJobManager + 紧急停止
├── separation/         # 2-Stem MDX-ONNX 后端 & 严格受限的 4-Stem HTDemucs 后端
├── streaming/          # Phase 8 实验性近实时 2-Stem 分轨 (默认关闭, RTF 基准测试 + 超时自动急停)
├── ui/                 # PySide6 + PyQtGraph GUI (频谱, Chroma/和弦, 分轨混音+时间轴拖拽+MIDI钢琴卷帘, 资源监控, 设置诊断)
├── packaging/          # PyInstaller Core 规范 (排除 CUDA/PyTorch 臃肿依赖)
├── scripts/            # check_env.py 硬件/AI 包探针, setup_windows.ps1 & build_windows.ps1 (未在 Windows 真机实际验证)
├── docs/PACKAGING.md   # 双环境 Core vs AI Worker 部署与 Windows 真机清单 Test A-J
├── capture_test.py     # Phase 1 CLI 捕获 + ResourceManager PoC
└── main.py             # 桌面主程序入口
```

---

## 环境 Honest Status 说明（重要）

> [!WARNING]
> 当前代码与自动化单元测试均在 **Linux x86_64 开发沙箱（无 NVIDIA GPU / 非 Windows）** 中完成：
> - **已验证**：`SYSTEM_REPORT.md` 硬件探测与 `.venv-ai` 子进程探针、`PersistedSettings` 持久化与安全不变量校验、`ResourceManager` 阈值/急停逻辑、120s 固定预分配 `FixedRingBuffer` 与流式本地音频截断导入、CPU DSP 与分轨深度解析（Bass 8192-pt FFT / Drums 3 频段瞬态与 16 步律动 / 主旋律音域 / 时间轴和弦与 `.md/.csv` 报告导出）、A/B 循环与 `StemMixerEngine` 时间轴进度跳转及流式导出、真实 `spawn` 多进程 AI Worker 连续运行无泄漏/取消清理/OOM 3选1/低内存拒绝与急停/30分钟(1800s)流式分块/强杀恢复/实验性实时分轨限流、`PySide6` 无头界面 (`QT_QPA_PLATFORM=offscreen`) 与水平 MIDI 钢琴卷帘 (`BarGraphItem`) 完整联调。
> - **未在 Windows 真机验证**：Windows `WASAPI Process Loopback` 对 `QQMusic.exe` 的实际捕获、真实 RTX 5060 Ti (`8GB VRAM`, `sm_120`) 上 PyTorch `cu128`+ / ONNX Runtime `CUDAExecutionProvider` / `audio-separator` / `basic-pitch` 的实测显存峰值与延迟、`scripts\setup_windows.ps1`、`scripts\build_windows.ps1` 与 PyInstaller `.exe` 打包测试。请在真机按 [PACKAGING.md](docs/PACKAGING.md) 验证。

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

详见 [docs/PACKAGING.md](docs/PACKAGING.md) 进行双环境部署（`.venv-core` + `.venv-ai` 或使用 `scripts\setup_windows.ps1`），并先执行：

```powershell
python scripts\check_env.py --write-report
python capture_test.py --name QQMusic.exe --fallback-system
python main.py --ai-python .\.venv-ai\Scripts\python.exe
```
