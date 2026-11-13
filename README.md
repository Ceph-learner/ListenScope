# ListenScope

**完全免费、离线、本地运行** 的 Windows 音乐分析、A/B 循环与扒谱辅助桌面软件。无需下载 QQ 音乐加密歌曲文件、无需解密缓存、无需绕过 DRM，即可一边在 QQ 音乐（或任意桌面应用）正常听歌，一边实时分析频谱/Chroma/和弦（含音阶构成音实时拼写、12 步进行轨迹与一键换歌重置）/调性/BPM/主音高可视化音准条（`-50 ~ +50 cents`），支持 **纯 CPU Capo / 乐器移调实时联动**（自动同步实时分析、12 步和弦带、分轨深度报告、Live 和弦 HUD 与 `.md/.csv` 扒谱表并保留原始实音对照）、纯 CPU **Tap 定速、检测 BPM 一键同步、1 小节预备拍与 `0%–150%` 音量可调练习节拍器**（自动持久化 BPM/拍号/音量/预备拍/移调偏好），在 **120 秒交互式波形时间轴**（含 `A-1s/A+1s/B-1s/B+1s` 区间微调与反转归一化、黄线实时播放头、最多 12 个自动防滚出 **A/B 练习书签**、单次/循环开关及 `0.5x–1.25x` 纯 CPU 不变调倍速）上拖拽选区回放或**分块导出应用当前倍速与节拍器 Click 的 A/B / 分轨混音练习 WAV**，并对历史片段进行本地 AI 分轨（2-Stem / 4-Stem）、无损流式和弦（可选 `maj7/m7/7/sus4`）/Bass/鼓组/主旋律深度分析、选中和弦片段局部循环练习、Live 当前（含构成音）/下一和弦 HUD、MIDI 转录、钢琴卷帘点击画面跳转、`Ctrl+Space` 全局播放/暂停以及一键导出**脱敏排障诊断包 (`.zip`)**。

---

## 硬性目标硬件规范与资源安全原则

- **目标系统**: Windows 10 / 11 (20H1+, Build >= `19041`)
- **目标 GPU**: `NVIDIA GeForce RTX 5060 Ti` (Blackwell, `sm_120`)
- **GPU 显存**: **8GB VRAM**（严格按 8GB 预算，绝非 16GB VRAM）
- **系统内存**: **16GB RAM**

核心安全准则：
1. **CPU 实时基础与练习工具**：实时波形、FFT/对数频谱、12-bin Chroma、12 大/小三和弦（实时显示构成音拼写、有界 12 步进行与一键换歌重置；离线深度分析可选 `maj7/m7/7/sus4` 扩展和弦）、调性、BPM、主音高与 `-50 ~ +50c` 彩色音准指针条 (`TuningCentsBar`)、**纯 CPU Capo / 乐器移调联动**（UI 与 `.md/.csv` 扒谱表同步移调显示）、纯 CPU Tap 定速与练习节拍器（支持 `0%–150%` 音量调节、1 小节预备拍、独立跟练及自动对齐 `0.5x–1.25x` 回放速度）、鼓组 Kick/Snare/Hi-Hat 16 步律动、Bass 根音、主旋律音域、`.md/.csv` 扒谱报告原子导出以及纯 CPU WSOLA 不变调变速回放与分块练习 WAV 导出（`0.5x–1.25x` + 可选节拍器混入）全部纯 CPU 运行，不依赖 PyTorch GPU 且不打断实时捕获。
2. **120 秒固定 PCM 环形缓冲、A/B 选区与有界书签**：统一 `48kHz / stereo / float32`（固定预分配 ~46.08 MB），支持流式载入本地音频前 `<=120s` 片段（先成功解码首块后再清空旧历史，避免损坏文件抹除既有缓冲）、底部 120s 波形总览拖拽 A/B 选区、`A-1s/A+1s/B-1s/B+1s` 区间微调、实时黄线播放游标、最多 12 个按环形缓冲绝对帧追踪并随滑窗滚出自动清理的 A/B 练习书签、单次/循环切换及独立原子导出（支持带当前倍速与节拍器 Click 的练习 WAV）；禁止无限音频队列、禁止一次性整首解码进 RAM。
3. **AI 独立子进程 + 严格串行单模型 + 防死锁 IPC**：每次最多 1 个任务、1 个模型；按需加载、流式分块推理（全链路统一 `decode_wave_bytes` 字节对齐、单/多声道规范化与 NaN/Inf 清洗）；`AIJobManager` 双线程排空外部 `.venv-ai` stdout/stderr 避免阻塞并透传崩溃错误；WASAPI 设备重连自愈清理瞬态提示、PortAudio 输出流启停并发安全释放、实时分轨畸形 IPC 载荷过滤、新分轨完成递增 `_stem_generation` 自动丢弃过期异步深度分析/MIDI 结果，且取消/OOM 中止前优先卸载模型再采样释放后 RAM/VRAM。
4. **明确 GPU 准入、v2 持久化设置与一键排障**：启动、应用设置与「验证 AI 环境」同步检测驱动、NVML、`torch.cuda.is_available()`、`sm_120` 核函数、ONNX Runtime `CUDAExecutionProvider` 与 `demucs`/`audio-separator`/`basic-pitch` 可用性（外部 `.venv-ai` 检测结果实时同步主窗口 GPU 状态）；`PersistedSettings` (v2 兼容 v1) 自动记忆阈值、AI 路径与练习参数（节拍器 BPM/拍号/音量/预备拍、Capo 移调半音），打包工作路径自动解析可写用户目录 (`~/.listenscope`)；资源面板支持一键生成脱敏诊断包 `.zip`。
5. **随时可用的红色「紧急停止 AI」按钮**：强制结束 worker、清理 IPC 与不完整临时输出、重采样 RAM/VRAM，主界面与实时捕获永不中断。

---

## 模块架构

```text
ListenScope/
├── core/               # 硬件探针 (Phase 0), frozen/只读可写路径解析 (paths.py), ResourceLimits, ResourceManager, PersistedSettings v2 (含练习偏好), PerformanceLogger, 脱敏诊断打包 (diagnostics.py)
├── audio/              # WASAPI Process/System Loopback(含设备切换重连自愈), decode_wave_bytes/PCM 规范化, FixedRingBuffer(120s + 波形总览 + 安全流式导入), WSOLA 不变调变速, Tap 定速与 CPU 节拍器/1小节预备拍, 有界 A/B 书签, HistoryABPlayer/StemMixerEngine (含变速+节拍器分块实践 WAV 导出与启停并发锁保护)
├── analysis/           # CPU DSP(NaN/Inf 清洗): 频谱/Chroma/12大小三和弦+可选扩展7和弦/Capo移调拼写/调性/BPM(含换歌重置), 无损流式分轨深度解析与移调/原子报告导出 (stem_analyzer.py), Basic Pitch / 降噪单音 MIDI 转录
├── ai/                 # 模型注册表, 流式 WAV 分块守护(统一解码/声道规范化与 NaN 防护), 隔离 AIWorkerProcess(中止前卸载模型), AIJobManager + 紧急停止 + 防 pipe 阻塞排空
├── separation/         # 2-Stem MDX-ONNX 后端 & 严格受限的 4-Stem HTDemucs 后端 (全链路 2ch float32 与非有限值清洗)
├── streaming/          # Phase 8 实验性近实时 2-Stem 分轨 (默认关闭, 独立外部 .venv-ai 隔离、RTF 基准、IPC 畸形包校验与 worker 意外退出防护)
├── ui/                 # PySide6 + PyQtGraph GUI (频谱, Chroma/和弦构成音+Capo移调联动+TuningCentsBar+预备拍/音量节拍器, 120s 拖拽时间轴+A/B微调+书签+游标+A/B变速, 分轨混音+和弦局部循环+Live和弦HUD+MIDI钢琴卷帘跳转, 诊断导出, 资源监控)
├── packaging/          # PyInstaller Core 规范 (排除 CUDA/PyTorch 臃肿依赖, 捆绑外部 worker 所需的全部源码模块)
├── scripts/            # check_env.py 硬件/AI 包探针, setup_windows.ps1 & build_windows.ps1 (未在 Windows 真机实际验证)
├── docs/PACKAGING.md   # 双环境 Core vs AI Worker 部署与 Windows 真机清单 Test A-J
├── capture_test.py     # Phase 1 CLI 捕获 + ResourceManager PoC
└── main.py             # 桌面主程序入口 (含 _stem_generation 过期结果隔离与 v2 练习参数持久化)
```

---

## 环境 Honest Status 说明（重要）

> [!WARNING]
> 当前代码与自动化单元测试均在 **Linux x86_64 开发沙箱（无 NVIDIA GPU / 非 Windows）** 中完成：
> - **已验证**：`SYSTEM_REPORT.md` 硬件探测与 `.venv-ai` 子进程探针、打包只读环境可写路径回退、`PersistedSettings` v2 持久化与 v1 兼容、脱敏离线排障 `.zip` 打包、`ResourceManager` 阈值/急停逻辑、120s 固定 `FixedRingBuffer`（`decode_wave_bytes` 全宽对齐/损坏导入保护/NaN 防护、包络总览、原子 A/B 与混合带速+节拍器流式导出、流式本地截断导入与有界 `<=12` 个防滚出 A/B 书签）、纯 CPU Capo/乐器移调联动与 `.md/.csv` 同步移调导出、纯 CPU Tap 定速与采样精确随播/独立/1 小节预备拍及音量可调练习节拍器、纯 CPU WSOLA 不变调变速器（`0.5x–1.25x`）、和弦构成音拼写与 `TuningCentsBar` 音准偏离条、A/B 区间微调与反转规范化、和弦局部循环与 PortAudio 启停并发安全关流、CPU DSP 换歌重置与进行轨迹、分轨代际过期结果丢弃、实时分轨畸形 IPC 过滤，以及 `PySide6` 无头界面 (`QT_QPA_PLATFORM=offscreen`) 联调。
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
