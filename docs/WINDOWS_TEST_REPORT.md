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

## 第三轮 · Windows 11 交付提交复测（2026-11-14）

- **基线与隔离**：`51f4554f9b70bc795dcf965a590251da694ec621`，独立检出 `work\ListenScope-51f4554`。Windows Build 26300、NVIDIA 616.64、RTX 5060 Ti（NVML 8151 MiB）、16 GB 系统内存。原工作树、虚拟环境和旧 exe 保留。本轮单独设置文件为 `work\round3-log\clean-settings.json`，首次启动前不存在。已缓存模型用于复测，设置 `HF_HUB_OFFLINE=1`。
- **全新安装的首个阻塞点**：使用 PowerShell 7 运行 `& .\scripts\setup_windows.ps1 -PythonExe $p -MidiPythonExe $m`，其中 `$p` 为 Python 3.12.16 x64，`$m` 为 3.11.18 x64。脚本后半段 `pip install -r requirements-ai.txt` 从 PyPI 解析 torchvision 时要求替换已装的 CUDA PyTorch 为 2.15.0，停止该次安装。用 `-TorchSpec` 指向核验过的官方 cu128 wheel，并设置 `PIP_CONSTRAINT=../round3-log/cuda-constraints.txt`，固定 torch/torchaudio 2.11.0+cu128，指定官方 torchvision 0.26.0+cu128 wheel 后重跑。提交中的安装脚本仍需处理此依赖解析问题。
- **Core / GPU 本机实测**：`.\.venv-core\Scripts\python.exe -m pip check`、`.\.venv-ai\Scripts\python.exe -m pip check` 均返回 `No broken requirements found`。Core 为 PySide6 6.9.3、NumPy 2.5.4、SciPy 1.18.1、proc-tap 1.1.1。AI 为 torch/torchaudio 2.11.0+cu128、torchvision 0.26.0+cu128、ORT GPU 1.26.0、audio-separator 0.48.0、Demucs 4.1.0、audioread 3.1.0。FFmpeg 位于 `work\bin\ffmpeg.exe`，版本 9.0.2 essentials。实跑 `torch.arange(16,device='cuda').square().sum()` 加 `torch.cuda.synchronize()`，返回 1240，CUDA 12.8、设备能力 (12,0)、编译架构包含 sm_120。日志 `setup-final.log`、`cuda.log`。
- **Windows pytest 本机实测**：Core 环境运行 `python -m pytest -q --tb=short`，原提交 110 通过、1 失败。失败项目 `test_p1_midi_probe_discovery_settings_and_standalone_routing` 直接执行 POSIX shebang 夹具，Windows 无法像 POSIX 一样启动。仅本检出修改测试夹具，通过 `sys.executable` 运行相同脚本，完整重跑 111 通过（60.61 s）。日志 `pytest.log`、`pytest-fixed.log`。
- **打包版 QQ 捕获本机实测**：`& .\scripts\build_windows.ps1` 成功，启动 `dist\ListenScopeCore\ListenScope.exe --settings <clean-settings.json>`。从进程下拉框选择 QQMusic.exe PID 12336，看到 `process_loopback`，播放中采样约 −42 至 −34 dBFS，截图样本无丢帧或欠载。捕获历史中选择「选最近 30s」后停止捕获，以同一选择串行跑两模型。两份 `excerpt_input.wav` SHA-256 相同（`A11F185A449158F427AF46DB168892BD2B79215A46F59B65EDBDFE68921D641B`）。
- **打包版默认 GPU 分轨本机实测**：项目日志两个作业均 `Completed`、`GPU-CUDA`、`oom_occurred=false`、`fallback_used=false`。二轨 MDX `job_3f80a745`，6.0 s 分块、MDX segment 256，耗时 10.656 s，生成 vocals/instrumental。临时 ORT profiling 捕获 2,670 条 CUDAExecutionProvider Node 事件，此次 profile 无 CPU Node 事件。四轨 `job_cf9a04ab`，6.0 s 分块、HTDemucs segment 6 s，耗时 4.921 s，输出 vocals/drums/bass/other。低内存门槛保持 5120/3072/2048 MiB，两次运行均未触发急停。profile 只启用记录，未修改执行提供程序。
- **资源实测**（MiB，NVML 整卡和进程树约每 150 ms 采一次；系统可用 RAM 含其他应用的波动）：

| 作业 | 主进程峰值 | Worker 自报峰值 | Python 子树峰值 | 最低系统可用 RAM | 整卡显存，启动前 → 峰值 → Worker 退出后 | 退出后系统可用 RAM |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| MDX 二轨 | 301 | 1819 | 1846 | 2425 | 1952 → 4420 → 1948 | 4290 |
| HTDemucs 四轨 | 305 | 1489 | 1505 | 2811 | 1965 → 3532 → 1952 | 4360 |

两次退出后 Python 子树均为 0 MiB。资源原始采样 `resources.csv`，ORT 文件 `ort-mdx_2026-11-14_10-34-46_686.json`，项目任务日志 `ai_perf_20261114.jsonl`。

- **MIDI 安装本机复现**：初次在深目录安装 TensorFlow 2.15，pip 以 `[Errno 2]` 报错，目标头文件为 `alts_grpc_integrity_only_record_protocol.h`。本机 `LongPathsEnabled=0`。未修改系统选项，改在 `E:\LS51f4554-midi` 的同提交 worktree 运行 `& .\scripts\setup_windows.ps1 -PythonExe $p -MidiPythonExe $m -SkipAI`。Windows PowerShell 5.1 直接读取 UTF-8 无 BOM 脚本出现中文解析错误，实际复跑使用 PowerShell 7。日志 `setup-final.log`、`setup-midi-short.log`。

- **暂停和恢复本机实测通过**：同一次打包版捕获，播放约 −33.7 dBFS，暂停为 −120.0 dBFS，恢复后前台画面为 −35.0 至 −35.5 dBFS，全程显示 `process_loopback`。应用被遮挡期间，读取的可访问性标签短时仍显示暂停值。交叉验证运行 `.\.venv-core\Scripts\python.exe capture_test.py --pid 12336 --duration 5`，恢复后同 PID 约 −33.7 至 −35.8 dBFS、零欠载/过载，保存为 `qq-resume-cli.log`。在 GPU 作业全部结束后，操作设置时误点了一次手动急停，GUI 当时显示可用 RAM 4431 MiB、无活跃 Worker。两次 GPU 作业均未触发资源急停。


- **独立 MIDI 环境本机实测通过**。短路径脚本顺利完成，`E:\LS51f4554-midi\.venv-midi\Scripts\python.exe -m pip check` 返回 `No broken requirements found`。实际安装 Basic Pitch 0.4.0、TensorFlow / tensorflow-intel 2.15.0、NumPy 1.26.4、setuptools 79.0.1、mido 1.3.3。TensorFlow `list_physical_devices()` 只报告 CPU:0。相同四轨 bass 的源码 CLI 诊断返回 `backend_used=basic-pitch`。
- **提交原样打包版 MIDI 阻塞**。在设置页填写独立 Python 3.11 并点击「验证 MIDI 环境」，报 `ImportError: Module use of python312.dll conflicts with this version of Python`，出现在标准库 `import _socket`。PyInstaller 包内 DLL 搜索路径会被子进程继承，初次仅清除该 DLL 目录后仍可复现，因为工作目录和 `PYTHONPATH` 依旧把包内扩展放在外部 3.11 的标准库前。本地修复在启动外部解释器时临时复原 Windows DLL 默认搜索路径，并将打包源码置于外部解释器模块搜索路径末尾，覆盖环境验证及 MIDI 转录。再次运行 `scripts\build_windows.ps1`。日志 `build-midi-fixed.log`、`build-midi-fixed2.log`。参考 [PyInstaller 外部程序启动文档](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#launching-external-programs)。


- **本地修复版 MIDI 本机实测通过**。重建 exe 后，设置页显示 Python 3.11.18、`Basic Pitch CPU 准入: READY`。在 GUI 重新导入原 30 秒 WAV 并重跑 CUDA 四轨 `job_eda7491a`，耗时 4.844 s。导入再导出的 PCM 与首测同为 48 kHz 双声道、1,440,000 帧，峰值差为 1 个 int16 量化单位。点击 BASS 行的「转 MIDI」，GUI 显示 `实际算法: Spotify Basic Pitch CPU (basic-pitch)`、120 个音符。点击「另存 MIDI (.mid)」写入 `outputs\ListenScope-51f4554-bass.mid`，由独立 MIDI Python 的 `mido.MidiFile` 解析为 type 1、2 个轨道、120 个速度大于零的 Note On、29.80 s。转录期主进程峰值 391 MiB、Python 子树峰值 520 MiB、最低系统可用 RAM 5065 MiB、整卡显存峰值 2134 MiB，退出后 Python 子树回到 0 MiB。关闭 exe 并以同一 `--settings` 参数重启，GUI 保留完整 MIDI 路径 `E:\LS51f4554-midi\.venv-midi\Scripts\python.exe`。
- **最终 Windows 回归**：设置 `QT_QPA_PLATFORM=offscreen` 和 `PYTHONUTF8=1` 后，Core 执行 `python -m pytest -q --tb=short`，111 通过（56.86 s）。在未设 UTF-8 的一次运行中，Windows GBK 重定向无法编码 `capture_test.py` 的 emoji，导致 1 项 CLI 测试失败。修复及测试变更保留在独立检出，安装的依赖约束和短路径是本地绕过方案。
- **留待下一轮**：完整 30 分钟连续捕获、切歌重置和持续近实时播放。本轮没有对这些项目作出通过结论。

## 第四轮 · 873db544 Windows 11 复测（2026-11-14）

- 独立短路径 worktree E:/LS873db54，HEAD 873db5440b96e31e799a76fc71d97dabbf24da68。Windows 11 Build 26300，RTX 5060 Ti，驱动 616.64，NVML 8151 MiB，16 GB 系统内存。
- 正式命令为 PowerShell 7 的 `& .\scripts\setup_windows.ps1 -PythonExe $p -MidiPythonExe $m`，解释器实际为 3.12.16 x64 / 3.11.18 x64。Core pip check 通过。默认在线安装停在下载 2753.2 MB 的 Torch wheel，约六分钟后当前临时 wheel 仍为 0 字节。主动停止前 pip 无原始异常。日志 setup-official.log。后续使用脚本 -TorchSpec 指向上轮已核验官方 wheel，单独记为诊断。脚本自行生成了 torch==2.11.0+cu128、torchaudio==2.11.0+cu128、torchvision==0.26.0+cu128 和 ORT <1.27 的约束。
- 用同一项目脚本加 -SkipAI 独立安装 MIDI，通过 pip check。Basic Pitch 0.4.0、TensorFlow 2.15.0、setuptools 79.0.1、mido 1.3.3。Core pytest（PYTHONUTF8=1、QT_QPA_PLATFORM=offscreen，`python -m pytest -q --tb=short`）112 项通过（57.77 秒）。`scripts/build_windows.ps1` 打包成功，新 exe SHA-256 AF1821D93D052D4088F8B50851AFBA138E26C984913885F8A08E6065B8C6DCFC。
- 原始 bass 文件来自 job_eda7491a，SHA-256 F13EC3BECC9D4EC6920EBE916F9C3FB9EB2B0554925BD2BE4A812627FF3869FF。命令行诊断 `python -m analysis.midi_transcription --audio <原始bass.wav> --output-midi <输出.mid> --stem-name bass --json` 返回 basic-pitch。mido 验证 2 轨、120 个 Note On、29.80 秒，与上轮一致。GUI 缺少将已有单轨 WAV 直接载入混音器的入口。
- GUI 连续捕获开始采样时间为北京时间 22:44:50，QQMusic.exe PID 4728。起点为 313 MiB RSS、4781 MiB 可用、队列 0/64、溢出/欠载 0/0。22:50:06 样本为 340 MiB RSS、3965 MiB 可用、队列 0/64、溢出/欠载 0/0，仍在 process_loopback。
- 自动切歌：源码未找到曲目切换事件接入。22:45:07 记录 A 曲和弦历史有 12 项，22:45:24 观察到 QQ 窗口已换歌，22:45:29 捕获仍连续且历史仍为 12 项，分析继续滚动。没有观测到自动清空。人工切歌准确秒数与旧曲条目最后退出时间未采到。
- 手动重置：22:45:45 在 Chroma 页点「换歌重置」。原 12 项历史清掉，随后出现 G#m 单项，BPM 暂为 Unknown；22:46:21 已重新累积 12 项，BPM 90.8。捕获未停止，溢出/欠载仍为 0/0。
### 分轨与 MIDI：打包版真机实测

- 新 exe：`E:\LS873db54\dist\ListenScopeCore\ListenScope.exe --settings "<本轮日志目录>\settings.json"`。使用新的设置文件及已有模型缓存；Core、AI、MIDI venv 均为本轮新建。FFmpeg 9.0.2，路径为工作区 `work\bin\ffmpeg.exe`。三个 venv 各以自己的 `Scripts\python.exe -m pip check` 运行并通过。AI 环境实际为 Torch / torchaudio 2.11.0+cu128、torchvision 0.26.0+cu128、ORT GPU 1.26.0、audio-separator 0.48.0、Demucs 4.1.0。PyTorch 在设备能力 (12, 0) 上实际执行 `torch.arange(16, device="cuda").square().sum().item()`，得到 1240。
- 点击「选最近 30s」→「AI 2-Stem 分轨」。`job_e2c2e1ee`，30.0 秒，6.0 秒分块，MDX 模型 segment 256，GPU-CUDA，耗时 9.469 秒，无出错、回退或急停。为核实节点设备，仅在本轮新 AI 环境挂载临时 ORT profiling，未改 Provider 或资源门槛，测试后已移除。profile 共记录 2,670 个 Node 事件，全部为 CUDAExecutionProvider，含 600 次 Conv 和 330 次 MatMul。
- 随后串行用 GUI 生成临时四轨作业 `job_5ba834ec` 以得到 BASS 行。该作业 30.0 秒，HTDemucs 6 秒分块、模型 segment 6 秒，GPU-CUDA，耗时 4.344 秒，无回退、OOM 或急停。这次四轨用于验证 MIDI 入口，和前一二轨并非同一段取样。
- 在设置页指定 `E:\LS873db54\.venv-midi\Scripts\python.exe`，验证显示 Basic Pitch CPU 准入 READY。为用上轮逐字节相同的 bass 输入，没有改源码或旧文件：在本轮临时四轨作业目录中将新生成的 bass 文件替换为上一轮 bass 的拷贝，并核对相同 SHA-256。Windows 拒绝移动正在被混音器使用的新 bass 路径，但允许写入副本；本轮生成的 bass 没有保留。原始上轮 WAV 保留未动。原版 GUI 缺少直接将已有单轨 WAV 载入混音器的入口，此步骤是同输入诊断的准备，后续是打包版实际 GUI。
- 点击 BASS 行「转 MIDI」。状态栏确认由独立解释器启动，结果为 `Spotify Basic Pitch CPU (basic-pitch)`、120 音符。用「另存 MIDI (.mid)」导出 `outputs\ListenScope-873db544-bass.mid`。独立 MIDI Python 的 `mido.MidiFile` 读出 type 1、2 条 MIDI 轨、120 个速度大于 0 的 Note On、29.80 秒。SHA-256 C066A05976940CAC09B50DF2E8A3EB738019CAFE9946F8227C78271E82EDB4CB，与同输入 CLI 诊断的 MIDI 文件逐字节一致。

| GUI 任务 | Worker 自报峰值 RAM | 外部采样 Python 子树峰值 | 最低系统可用 RAM | 整卡显存启动前 → 峰值 → 退出后 | 退出后可用 RAM |
| --- | ---: | ---: | ---: | --- | ---: |
| MDX 二轨 | 1818 | 1845 | 3181 | 2090 → 4631 → 2087 | 5078 |
| HTDemucs 四轨 | 1442 | 1458 | 3503 | 2168 → 3209 → 2102 | 4996 |
| Basic Pitch CPU | — | 524 | 4409 | 2107 → 2107 → 2106 | 4934 |

单位 MiB。外部用 psutil / NVML 约每 150 ms 采样，Worker 退出后三次 Python 子树均回到 0 MiB。证据：`work\round4-log` 下的 `ort-mdx_*.json`、`ai-perf-round4.jsonl`、`sample-resources.csv` 和 `sample-continued.csv`。默认内存保护维持原值。

### 连续捕获采样：北京时间

| 目标采样点 | 实际时间 | 主进程 RSS (MiB) | 系统可用 (MiB) | 队列 | 溢出/欠载 | 状态 |
| --- | --- | ---: | ---: | --- | --- | --- |
| 0 分钟 | 22:44:50 | 313 | 4781 | 0/64 | 0/0 | process_loopback，有信号 |
| 5 分钟 | 22:50:06 | 340 | 3965 | 0/64 | 0/0 | process_loopback，有信号 |
| 10 分钟 | 22:54:50 | 319 | 4453 | 0/64 | 0/0 | process_loopback，有信号，MIDI 子进程转录期间 |
| 15 分钟 | 22:59:57 | 350 | 4902 | 0/64 | 0/0 | process_loopback，有信号 |
| 20 分钟 | 23:04:52 | 349 | 5181 | 0/64 | 0/0 | process_loopback，有信号 |
| 25 分钟 | 23:10:23 | 325 | 5394 | 0/64 | 0/0 | process_loopback，有信号 |
| 30 分钟 | 23:14:53 | 289 | 5906 | 0/64 | 0/0 | process_loopback，有信号（−64.3 dBFS） |

本机从 22:44:50 至 23:14:53 连续捕获满 30 分钟。所有采样点队列均为 0/64、累计溢出/欠载均为 0，没有观测到中断或切到系统捕获。外部采样中 MIDI 导出后主进程短时达 362 MiB，随后经约 349 MiB 平台回落至 289 MiB，未见持续增长。队列为各时点的观测值，无法排除采样点间瞬间非零。

采完后正常关闭本轮 exe（PID 15124），以同一 `--settings` 参数重开（PID 29780）。设置页仍显示 `E:\LS873db54\.venv-midi\Scripts\python.exe`，GPU 已解锁，分块与 Demucs 分段均仍为 6 秒。Core 环境主要版本：PySide6 6.9.3、pyqtgraph 0.14.0、NumPy 2.5.4、sounddevice 0.5.6、psutil 7.2.2、PyInstaller 6.22.3。三套完整版本保存在 `work\round4-log\pip-freeze-*.txt`。

### 回传 Gemini 的问题

1. 默认正式安装首个阻塞点为官方 2.75 GB Torch 下载停滞，未得到原始 pip 异常；在线默认路径尚未通过。短路径加已核验本地 wheel 的诊断路径验证了 cu128 约束正常工作。建议为大 wheel 下载提供本地缓存提示或超时及重试说明。
2. 当前未实现 QQ 音乐曲目识别与自动重置。切歌后历史留在滚动窗口，手动「换歌重置」通过。
3. 建议允许把已有单轨 WAV 直接交给 MIDI，以便从先前分轨结果重做转录或复现实验。独立 Python 3.11 的打包版转录与重启保留已通过，此前 DLL 冲突未重现。

持续近实时分轨按要求未测。源码无修改，旧 worktree、旧虚拟环境与旧 exe 保留。

## 第五轮 Windows 验收（2026-11-15，f03dbf1）

以下摘自该提交的本机第五轮报告与测试日志。测试环境为 Windows 11，RTX 5060 Ti 8 GB，16 GB RAM。30 分钟捕获沿用第四轮基线。

- Core Python 3.12，QT_QPA_PLATFORM=offscreen。执行 python -m pytest -q --tb=short，115 passed in 64.60s。三个环境 pip check、Windows 打包和启动通过。本地 cu128 wheel 优先安装完成。
- QQ Music 暂停、恢复、跳转和切歌时捕获保持，识别到自动重置横幅。因缺少逐次事件日志，无法排除重复重置。
- 独立 CPU MIDI 环境从 WAV 生成可解析的 MIDI（120 个有效 Note On）。从历史作业目录读取时覆盖了已有同名 MIDI，源目录隔离不通过。
- 10 秒离线 MDX 在 6 秒分块下约 7.63 秒，抽样确认 CUDA 节点运行。近实时启动则触发 RAM 保护，未听到非静音输出，首段等待与长期延迟未知。
- 输出环独立样本写八帧，连续三次读四帧均返回同一组尾帧，且剩余帧数未减少。下一步覆盖持续按序消费，再检查真实输出与资源保护。
- UI 待办是 Chroma 纵轴拥挤和相对于调性的和弦级数显示。
