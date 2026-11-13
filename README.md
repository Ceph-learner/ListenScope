# ListenScope

**完全免费、离线、本地运行** 的 Windows 音乐分析、A/B 循环与扒谱辅助桌面软件。无需下载 QQ 音乐加密歌曲文件、无需解密缓存、无需绕过 DRM，即可一边在 QQ 音乐（或任意桌面应用）正常听歌，一边实时分析频谱/Chroma/和弦（含 12 步进行轨迹与一键换歌重置）/调性/BPM，使用纯 CPU **Tap 定速、检测 BPM 一键同步与变速随播练习节拍器**，在 **120 秒交互式波形时间轴**（含黄线实时播放头、最多 12 个自动防滚出 **A/B 练习书签**、单次/循环开关及 `0.5x–1.25x` 纯 CPU 不变调倍速）上拖拽选区回放或单独导出 WAV，并对历史片段进行本地 AI 分轨（2-Stem / 4-Stem）、无损流式和弦（可选 `maj7/m7/7/sus4`）/Bass/鼓组/主旋律深度分析、选中和弦片段局部循环练习、Live 当前/下一和弦 HUD、MIDI 转录、钢琴卷帘点击画面跳转、`Ctrl+Space` 全局播放/暂停以及一键导出**脱敏排障诊断包 (`.zip`)**。

---

## 硬性目标硬件规范与资源安全原则

- **目标系统**: Windows 10 / 11 (20H1+, Build >= `19041`)
- **目标 GPU**: `NVIDIA GeForce RTX 5060 Ti` (Blackwell, `sm_120`)
- **GPU 显存**: **8GB VRAM**（严格按 8GB 预算，绝非 16GB VRAM）
- **系统内存**: **16GB RAM**

核心安全准则：
1. **CPU 实时基础与练习工具**：实时波形、FFT/对数频谱、12-bin Chroma、12 大/小三和弦（有界 12 步和弦进行与一键换歌重置；离线深度分析可选 `maj7/m7/7/sus4` 扩展和弦）、调性、BPM、纯 CPU Tap 定速与练习节拍器（支持独立跟练及自动对齐 `0.5x–1.25x` 回放速度）、鼓组 Kick/Snare/Hi-Hat 16 步律动、Bass 根音、主旋律音域、`.md/.csv` 扒谱报告导出以及纯 CPU WSOLA 不变调变速回放（`0.5x–1.25x`）全部纯 CPU 运行，不依赖 PyTorch GPU 且不打断实时捕获。
2. **120 秒固定 PCM 环形缓冲、A/B 选区与有界书签**：统一 `48kHz / stereo / float32`（固定预分配 ~46.08 MB），支持流式载入本地音频前 `<=120s` 片段、底部 120s 波形总览拖拽 A/B 选区、实时黄线播放游标、最多 12 个按环形缓冲绝对帧追踪并随滑窗滚出自动清理的 A/B 练习书签、单次/循环切换及独立导出 A/B 片段 WAV；禁止无限音频队列、禁止一次性整首解码进 RAM。
3. **AI 独立子进程 + 严格串行单模型 + 防死锁 IPC**：每次最多 1 个任务、1 个模型；按需加载、流式分块推理（含声道数自动规范化与非有限值保护）；`AIJobManager` 双线程排空外部 `.venv-ai` stdout/stderr 避免阻塞并透传崩溃错误；取消/OOM 中止前优先卸载模型再采样释放后 RAM/VRAM；实时分轨检测 worker 意外退出即清理重置。
4. **明确 GPU 准入、持久化设置与一键排障**：启动、应用设置与「验证 AI 环境」同步检测驱动、NVML、`torch.cuda.is_available()`、`sm_120` 核函数、ONNX Runtime `CUDAExecutionProvider` 与 `demucs`/`audio-separator`/`basic-pitch` 可用性（外部 `.venv-ai` 检测结果实时同步主窗口 GPU 状态）；用户设置持久化保存至 `~/.listenscope/settings.json`；资源面板支持一键生成脱敏诊断包 `.zip`（不含环境变量秘密、用户目录替换为 `~`、性能日志限尾截取）。
5. **随时可用的红色「紧急停止 AI」按钮**：强制结束 worker、清理 IPC 与不完整临时输出、重采样 RAM/VRAM，主界面与实时捕获永不中断。

---

## 模块架构

```text
ListenScope/
├── core/               # 硬件探针 (Phase 0), frozen 路径解析 (paths.py), ResourceLimits, ResourceManager, PersistedSettings, PerformanceLogger, 脱敏诊断打包 (diagnostics.py)
├── audio/              # WASAPI Process/System Loopback, PCM normalize, FixedRingBuffer(120s + 波形总览 + 流式导入), WSOLA 不变调变速, Tap 定速与 CPU 节拍器 (metronome.py), 有界 A/B 书签 (bookmarks.py), HistoryABPlayer, StemMixerEngine
├── analysis/           # CPU DSP: 频谱/Chroma/12大小三和弦+可选扩展7和弦/调性/BPM(含线程安全换歌重置), 无损流式分轨深度解析 (stem_analyzer.py), Basic Pitch / 降噪单音 MIDI 转录
├── ai/                 # 模型注册表, 流式 WAV 分块守护(声道规范化与 NaN 防护), 隔离 AIWorkerProcess(中止前卸载模型), AIJobManager + 紧急停止 + 防 pipe 阻塞排空
├── separation/         # 2-Stem MDX-ONNX 后端 & 严格受限的 4-Stem HTDemucs 后端
├── streaming/          # Phase 8 实验性近实时 2-Stem 分轨 (默认关闭, 独立外部 .venv-ai 隔离、RTF 基准与 worker 意外退出检测)
├── ui/                 # PySide6 + PyQtGraph GUI (频谱, Chroma/和弦轨迹与 Tap 定速/节拍器, 120s 拖拽时间轴+书签+游标+A/B变速, 分轨混音+和弦局部循环+随播节拍器+MIDI钢琴卷帘点击跳转, 诊断导出, 资源监控)
├── packaging/          # PyInstaller Core 规范 (排除 CUDA/PyTorch 臃肿依赖, 捆绑外部 worker 所需的全部源码模块)
├── scripts/            # check_env.py 硬件/AI 包探针, setup_windows.ps1 & build_windows.ps1 (未在 Windows 真机实际验证)
├── docs/PACKAGING.md   # 双环境 Core vs AI Worker 部署与 Windows 真机清单 Test A-J
├── capture_test.py     # Phase 1 CLI 捕获 + ResourceManager PoC
└── main.py             # 桌面主程序入口
```

---

## 环境 Honest Status 说明（重要）

> [!WARNING]
> 当前代码与自动化单元测试均在 **Linux x86_64 开发沙箱（无 NVIDIA GPU / 非 Windows）** 中完成：
> - **已验证**：`SYSTEM_REPORT.md` 硬件探测与 `.venv-ai` 子进程探针、`PersistedSettings` 持久化、脱敏离线排障 `.zip` 打包（含大日志有界截取与路径脱敏）、`ResourceManager` 阈值/急停逻辑、120s 固定 `FixedRingBuffer`（包络总览、A/B 导出、流式本地截断导入与有界 `<=12` 个防滚出 A/B 书签）、纯 CPU Tap 定速与采样精确随播/独立练习节拍器、纯 CPU WSOLA 不变调变速器（`0.5x–1.25x`）、和弦局部循环与单次结束主线程安全关流、CPU DSP 换歌重置与进行轨迹、以及 `PySide6` 无头界面 (`QT_QPA_PLATFORM=offscreen`) 联调。
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
