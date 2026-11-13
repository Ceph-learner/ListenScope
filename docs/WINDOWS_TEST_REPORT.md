# ListenScope Windows 真机验收记录

日期为 2026-11-13（UTC+8）。应现场要求提前结束长测。基线为 `81c361a983266c2882031788b09a28677046eb93`。原工作目录没有 Git 仓库，使用已连接的 GitHub 账号获取私有仓库的 85 个文件，校验 blob、tree 和 commit 哈希后构建本地浅检出。初始 `git status --short --branch` 为 `## main...origin/main`，`git fsck --no-dangling` 通过。源码改动保留在工作树。

## 本机与 Core 环境

- **本机实测通过**。Windows 11 Pro Build 26300，原生 PowerShell 7.6.9。终端与 Explorer 均在会话 1。系统原有 Windows Python 3.15.2，验收使用本地安装的 x64 Python 3.12.16。RTX 5060 Ti 驱动 616.64，SM 12.0，NVML 总显存 8151 MiB。系统标称 16 GB，psutil 可见 15417 MiB，初查空闲物理内存约 4869 MiB。QQ 音乐和浏览器同时操作时曾降至约 2.4–2.8 GiB。用户关闭部分应用后恢复到约 4.3 GiB。
- 执行 `scripts\setup_windows.ps1 -SkipAI -PythonExe <Python 3.12.16>`、`.venv-core\Scripts\python.exe -m pip check`、`scripts\check_env.py --json --no-write`。Core 安装通过，`No broken requirements found`。日志在验收目录的 `work/log` 下，包括 `baseline.log`、`setup-core.log`、`pip-check-core.log`、`core-hardware-fixed.json`。
- **Windows 自动化回归通过**。使用 Core Python 执行 `-m pytest -q` 首轮 94 通过、12 失败。修正硬编码 Linux 路径、Bash 包装脚本、符号链接权限、`SIGKILL` 和测试对当前机器可用 RAM 的依赖后，`-m pytest -q --tb=short` 为 **106/106**（62.69 秒）。日志 `pytest-baseline.log`、`pytest-fixed.log`、`pytest-final.log`。
- **本机复现并修复**。GBK 环境中 `-m streaming.benchmark --use-mock-backend --json` 原先因状态符号触发编码错误。JSON 协议改为 ASCII 转义后，在 `PYTHONUTF8=0` 下可解析。系统探针原先把 Build 19045 误判为支持按进程捕获，已将报告和文档的最低 Build 修正为 20348。依据为 [Microsoft Application loopback audio capture](https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/)。

## QQ 音乐与桌面分析

- **本机实测通过**。使用 Core Python 执行 `capture_test.py --list-procs` 与 `capture_test.py --name QQMusic.exe --duration 30`。为优先验证捕获，首轮使用 `PYTHONPATH` 指向临时安装的 WASAPI/DSP 依赖。列表显示 QQMusic.exe PID 9708 为活跃 WASAPI 会话。播放时约 −53.5 至 −31.3 dBFS，20:33:41 至 20:34:01 的暂停/浏览器播放操作窗口连续为 −120 dBFS，20:34:02 恢复到 −32.2 dBFS。全程 `Mode=process_loopback`，48 kHz 双声道，1,440,960 帧，欠载/溢出均 0。峰值主进程 129.2 MiB，最低可用系统 RAM 2416 MiB，采样整卡显存峰值约 2755 MiB。浏览器发声由现场操作，日志没有单独同步采集浏览器的电平。
- **本机实测通过**。完整 Core 安装后执行 `capture_test.py --pid 9708 --duration 6`，播放 RMS 约 −31 至 −28 dBFS，288,000 帧，队列 0/64，无欠载或溢出。系统回环 CLI 未单独实测，进程回环无需回退。日志 `capture-qq-30s.log`、`capture-list-resumed.log`、`capture-pid-full-core.log`。
- **本机实测通过**。Core Python 执行 `..\gui_acceptance.py --duration 1800 --output ..\gui-qq-30min`，通过桌面控制器启动真实捕获和实时分析。频谱 341 bins、时频图 450×96、Chroma 450×12，和弦、调性候选随播放更新。初段 BPM 约 88，后续播放时出现不同候选，未对照曲目核验分析准确率。真实截图/界面也验证了打包版 QQ 音乐捕获。桌面端通过 A/B 导出入口生成 30.00 秒、48 kHz 双声道 WAV，供全部分轨使用。
- **本机缩短耐久测试**。第一轮至 910.14 秒，窗口关闭后采样中断。采样脚本随后补了窗口关闭处理。第二轮至 510.00 秒，按现场要求停止。两次独立运行。第一轮 1/10 分钟主进程 RSS 为 305.8/281.3 MiB，队列均 0/64。第一轮峰值 RSS 333.9 MiB，最低系统可用 RAM 1882.6 MiB，显存峰值 2821.5 MiB，欠载 3，溢出 0。第二轮第 1 分钟 RSS 312.9 MiB，结束时 286.7 MiB，峰值 334.9 MiB，最低可用 RAM 2068.4 MiB，显存峰值 5384.7 MiB（并行观察离线 Worker），欠载和溢出均 0。两次队列峰值均 1/64，环形缓冲均到达并维持 120 秒。没有 20/30 分钟样本。日志 `gui-qq-30min.jsonl`、`gui-qq-30min-retry.jsonl`。
- **模拟验证**。A/B 循环、WSOLA 不变调、回放开关流竞态、WAV 导出、设置持久化等已通过自动化。**未验证**实际 A/B 循环听感与 0.5× 音高、GUI 重启后的现场设置恢复、退出 QQ 音乐后状态、切换物理输出设备。播放过程曾有静音并恢复，专门的切歌操作与分析重置未逐项对时验证。

## AI 环境和真实分轨

- **本机实测**。GPU Worker 使用独立 `.venv-ai`。按 PyTorch 官方 cu128 索引取得经过 SHA-256 验证的 `torch 2.11.0+cu128`，同套 `torchaudio 2.11.0+cu128`、`torchvision 0.26.0+cu128`。安装 `onnxruntime-gpu 1.26.0`、`audio-separator 0.48.0`、`demucs 4.1.0`、`audioread 3.1.0`，模型权重和 ffmpeg 均缓存于验收工作目录。执行 `.venv-ai\Scripts\python.exe -m pip check` 通过。`scripts\check_env.py --json --check-ai-packages --write-report ..\log\SYSTEM_REPORT.ai.md` 显示 GPU READY，Basic Pitch 在该环境缺失。`torch.arange(16,device="cuda").square().sum()` 加 CUDA 同步返回 1240，架构列表包含 `sm_120`。
- **本机复现**。仓库原始 `pip install --dry-run -r requirements-ai.txt` 在 Python 3.12 无解，Basic Pitch 0.4.0 要求 `tensorflow<2.15.1`。使用单独的 Python 3.11 环境安装 Basic Pitch 0.4.0 与 TensorFlow 2.15.0，`pip check` 通过，未执行真实 MIDI。PyPI 默认 ONNX Runtime 1.27 起改用 CUDA 13，现场为 PyTorch cu128 选用 ORT 1.26。已复现 `audio_separator` 在 librosa 1.0.1 环境中导入缺少 `audioread`，补装并复测导入成功，已把缺失项加入仓库依赖。Windows 一键 AI 初始化的 Basic Pitch 与 CUDA 版本选择仍待整合。参考 [Spotify Basic Pitch 依赖](https://github.com/spotify/basic-pitch/blob/main/pyproject.toml) 和 [ONNX Runtime CUDA 兼容表](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html#requirements)。
- **本机实测通过**。ORT 的独立 MatMul 探针得到 32.0，并在节点 profile 中确认 CUDA。真实 `UVR-MDX-NET-Inst_HQ_3.onnx` 的一次完整 30 秒处理得到 2670 条 `CUDAExecutionProvider` 节点执行事件，无 CPU 节点事件。模型权重从发布源获取，真实 ONNX 输入形状为动态 batch × 4 × 3072 × 256。
- 以下由 `.venv-core\Scripts\python.exe ..\ai_acceptance.py` 启动正常 `AIJobManager` 与外部 Worker。所有任务串行，使用同一个 GUI 导出的 `sample30.wav`。主进程列为验收驱动 RSS，GUI 的 RSS 单独在上文记录。Worker RSS 列含 Python venv 启动器和子进程，显存为整卡采样值。两次成功的六个 WAV 都验证为 1,440,000 帧、48 kHz 双声道，输出分离质量未试听。

| 命令参数和结果 | 主进程峰值 | Worker 峰值 | 整卡显存峰值 | 最低可用 RAM | 耗时及退出后 |
| --- | ---: | ---: | ---: | ---: | --- |
| `mdx mdx30-first`，导入缺 audioread | 122.6 MiB | 812.4 MiB | 2512.0 MiB | 3417.1 MiB | 墙钟 12.0 秒，Worker 退出 |
| `mdx mdx30-fixed`，20 秒分块触发 RAM 急停 | 122.5 MiB | 2403.8 MiB | 4833.8 MiB | 1929.0 MiB | 墙钟 18.9 秒，RAM/显存回到 4356/2370 MiB |
| `mdx mdx30-chunk6 --chunk 6`，6 秒分块仍触发急停 | 122.8 MiB | 2353.1 MiB | 4761.9 MiB | 2039.8 MiB | 墙钟 9.6 秒，RAM/显存回到 4407/2371 MiB |
| `demucs demucs30-chunk6 --chunk 6 --segment 6`，真实 GPU 四轨完成 | 123.4 MiB | 1578.5 MiB | 3488.8 MiB | 2784.6 MiB | Worker 53.95 秒（含加载），退出后 RAM/显存回到 4388/2368 MiB |
| `mdx mdx30-ort-workspace --chunk 6`，真实 GPU 二轨完成，使用验收探针配置 ORT | 123.3 MiB | 2530.5 MiB | 5500.3 MiB | 2063.2 MiB | Worker 39.27 秒，退出后 RAM/显存回到 4510/2351 MiB |

MDX 成功时由工作目录的 `mdx-profile/sitecustomize.py` 给真实 ONNX 会话设置 `cudnn_conv_algo_search=HEURISTIC`、`cudnn_conv_use_max_workspace=0`、`arena_extend_strategy=kSameAsRequested`、单 intra-op 线程，并采集 profile。该配置仅用于验收，尚未合入生产代码。成功时最低可用 RAM 仅比 2048 MiB 急停线高 15 MiB。没有手工填满 RAM 或显存，也没有下调保护阈值。两次实际内存急停与两次成功均观察到 Worker 树消失。AI 原始日志为 `ai-mdx30-*.log`、`ai-demucs30-chunk6.log`、`ort-kernel.log`、`mdx-real-profile_*.json`。

- **模拟验证通过**。仓库 Windows 测试覆盖重复 Mock 分轨、LoadingModel/Inferring/Writing 取消、三选项 OOM、低 RAM 拒绝与急停、30 分钟长 WAV 流式处理、Worker 强杀与主分析继续、手动紧急停止、Mock 近实时基准与轻量 MIDI。**未验证**两模型各五次真实重复、真实 GPU 取消/手动急停/强杀、真实 30 分钟长 WAV 分轨、真实近实时基准和真实 MIDI 转录。30 秒离线分轨耗时不能替代近实时基准。

## 打包

- **本机实测通过**。`scripts\build_windows.ps1` 成功生成 `dist\ListenScopeCore\ListenScope.exe`，实际启动并用 `--headless-smoke` 正常退出，退出码 0。打包版 GUI 选择 QQMusic.exe PID 9708 并开始捕获，确认 `process_loopback`、约 −37.6 dBFS、缓冲 5.7 秒，无欠载与溢出。打包日志 `build-initial.log`、`build-final.log`。
- **本机实测通过，限打包模块的外部探针**。`..\ai_acceptance.py probe pack-probe --bundle` 从生成物的 `_internal` 调用附带的探针模块，独立 `.venv-ai` 返回 READY。此项通过命令行调用打包目录，打包 GUI 内设置保存和启动一次真实分轨尚未验收。界面自动化因现场按 Esc 停止。

## 结论

本机已验证 QQ 音乐边听边分析、短时到约 15 分钟的捕获与 WAV 导出，以及 GPU 四轨在短分段下完成一次。GPU 二轨通过带 ORT 参数的验收探针完成一次，默认配置两次触发 RAM 急停。A/B 回放听感、完整 30 分钟稳定性、真实重复分轨和打包端到端分轨仍有验收缺口。当前证据不足以给出四项全部稳定可用的结论。

## 第二轮补验

以下结果更新首轮对应的未验证项。验收在同一台 Windows 本机及同一 Git 工作树进行，全部真实分轨任务串行运行。RAM 与显存均以 MiB 记录。

### 桌面与打包版

- **本机实测通过**。执行 Core Python `..\practice_acceptance.py play`。桌面 A/B 入口将 1.8 秒测试音以 0.5× 在 XIBERIA K03S Wireless 7.1 的真实 PortAudio 流播放。按进程 WASAPI 回采主频 439.98 Hz（输入 440 Hz），RMS 0.05077，有多次播放头回绕；停止后流关闭。导出为 3.60 秒、48 kHz 双声道 WAV。用户又在打包版播放实际 QQ 音乐片段，确认循环和音高正常。第二个桌面进程运行 `..\practice_acceptance.py restore` 后恢复节拍器至 96.5 BPM。日志 `practice-native.log`、`practice-native-restore.log`。
- **本机实测通过**。通过 `Start-Process ...\ListenScope.exe --settings <pack-verification.json>` 启动，GUI 确认外部 AI 环境通过 CUDA/ONNX 探针。导入同一 30 秒 WAV，点击 GPU 二轨按钮。GUI 显示 `Completed | GPU-CUDA | 8.28s`，混音页显示两轨，输出 WAV 每轨 5,760,044 字节。测试设置使用 6 秒分块。外部采样主进程峰值 366.4、Worker 树峰值 1839.0、整卡显存峰值 4605.5、最低可用 RAM 2877.7；退出后 Worker 0、显存约 2144、可用 RAM 4738。日志 `pack-gpu-monitor.csv`，应用任务号 `job_0f08332e`。
- **本机实测通过**。用户在打包捕获运行时把 XIBERIA K03S 切到 KATANA:GO，新设备能听到 QQ 音乐。GUI 曾短时显示静音，随后恢复为 `process_loopback | QQMusic.exe | RMS -35.7 dBFS` 并继续更新频谱。切换后另运行 `capture_test.py --name QQMusic.exe --duration 5`，RMS 约 −36 至 −34 dBFS，欠载/溢出均 0。随后用户从 QQ 音乐托盘退出，GUI 显示「目标进程已退出，已安全停止捕获」，按钮恢复可开始状态，120 秒历史保留，进程仍响应。日志 `endpoint-switch-qq.log`。
- **本机复现并修复**。用户截图显示 FFT 对数轴在 40–100 Hz 等区域标签相互覆盖。自定义该轴的刻度密度，缩窄视图时优先保留整十倍频标签，使用 `100`、`1k`、`10k` 等 Hz 标注。Windows 取图检查了 1360/760 逻辑像素宽度和深度缩放 315–340 Hz，标签未重叠。`scripts\build_windows.ps1` 重新打包并实际启动新 exe，核对修改后的 FFT 刻度。重跑 `python -m pytest -q --tb=short`，106 通过（52.22 秒）。日志 `fft-visual-check.log`、`fft-*.png`、`build-fft-final.log`、`pytest-final-round2.log`。

### 真实 GPU 和 MIDI

- **本机实测通过**。正常 ONNX 配置下，运行 `..\ai_acceptance.py mdx mdx30-stock-retest --chunk 6`，初始可用 RAM 4972，30 秒二轨用时 7.78 秒，峰值主进程/Worker/显存为 122.7/1841.7/4746.6，最低可用 RAM 3108.6，回落至可用 RAM 4981.5、显存 2284.5。未使用首轮临时 ORT 参数。首轮较低可用 RAM 时的急停仍计入结果。
- **本机实测通过**。同样输入连续分别运行二轨与四轨五次。`..\ai_acceptance.py mdx repeat-mdx-N --chunk 6` 每次 8.47–9.12 秒，Worker 树峰值 1849.5，整卡峰值 4712.6，最低可用 RAM 2601.7。四轨 `..\ai_acceptance.py demucs repeat-demucs-N --chunk 6 --segment 6` 每次 4.14–4.42 秒，Worker 树峰值约 1530，整卡峰值约 3732，最低可用 RAM 2860。各轮 Worker 退出后资源没有逐次累积。`HF_HUB_OFFLINE=1` 且模型已缓存。日志 `repeat-mdx-*.log`、`repeat-demucs-*.log`。
- **本机实测，含故障注入**。真实 MDX 在 LoadingModel 与 Inferring 阶段取消，分别约 1.45/1.47 秒返回，任务暂存和 Worker 都已清除。Writing 阶段使用仓库现有的 350 ms 测试延迟留出注入窗口，真实推理完成后取消写入，约 0.58 秒。真实 Worker 强杀后约 0.20 秒报告失败，手动急停调用约 0.75 秒。首轮强杀复现了系统临时目录残留，已将 MDX 和 Demucs 回退的中间目录放在任务暂存目录。重测强杀和急停确认路径位于任务暂存目录，退出后暂存、进程树均清理。日志 `real-*.log`、`staging-fixed-*.log`。
- **本机实测通过**。执行 AI Python `-m streaming.benchmark --model-id mdx_low_vram_2stem --test-duration-sec 4 --json`。真实 MDX CUDA 在内置 4 秒合成信号上推理 1.92 秒，RTF 0.4805。此结果是基准性能，持续近实时播放尚未验收。日志 `near-live-native.json`。
- **本机实测通过**。将同一真实 30 秒 QQ 音乐片段在磁盘上重复 60 次生成 1800 秒 WAV。执行 `..\ai_acceptance.py demucs demucs-long30 --chunk 6 --segment 6 --input <long-qq-repeat-30min.wav>`，完成 300 个分块，耗时 101.14 秒。峰值主进程/Worker 树/整卡显存为 124.0/1531.8/3518.8，最低可用 RAM 3057.0，退出后可用 RAM 4808.3、显存 2306.0。四个输出分别核对为 86,400,000 帧、48 kHz 双声道。日志 `demucs-long30.log`。
- **本机实测通过，独立 CPU 环境**。Python 3.11 执行 `-m analysis.midi_transcription --audio <真实 HTDemucs bass.wav> --output-midi <bass.mid> --stem-name bass --json`。补装 psutil，并用 `setuptools<81` 恢复旧版 resampy 需要的 `pkg_resources` 后通过。Basic Pitch 0.4.0 使用 TensorFlow 2.15 CPU，得到 141 个候选音符。当前打包界面的 MIDI 仍指向 GPU Worker 环境，此环境内没有 Basic Pitch。日志 `midi-real-fixed.json`、`midi-real-fixed.stderr`。

四项核心用途均已在本机跑通。短片段 GPU 二轨与四轨的重复测试使用 6 秒分块，运行时起始可用内存约 4.3–4.9 GiB。较低可用内存时 MDX 可触发保护。仍未覆盖完整 30 分钟 QQ 音乐连续捕获、近实时长期播放、逐项对时的切歌重置和打包版 MIDI。
