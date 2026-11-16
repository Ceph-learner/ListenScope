# 最新交接

- **结果**：近实时监听直接填充声卡回调缓冲。回绕分段混音，非默认增益复用最多 4096 帧的工作区，避免在回调内分配整块输出或拼接双轨。FIFO、限幅、欠载静音、预缓冲、源失效保护和诊断计数保持。
- **基线与分支**：PR #8 的合并提交 `70682d98c8b229328d7fe588fca95f13a8622265`。代码与测试提交 `c7d37b4e79914b0dfee8b035cb1f245e8c86426a`，分支 `perf/live-output-callback`。
- **协作**：Command Code GOAT V4.1 Flash 先交完整文本方案，OpenCode Go V4 Pro 依赖其结果做并发复审。两项完成，无重试。采纳固定工作区和保留停止保护。详见 [AI 协同报告](AI_COLLABORATION.md)。
- **验证**：Windows Python 3.11.17，Core 环境位于 ASCII 路径，设置 `QT_QPA_PLATFORM=offscreen`。`python -m pytest -q --tb=short` 通过 133 项。最终 `python -m pytest -q --tb=short tests/test_phase7_9_mixer_live_midi.py tests/test_phase14_practice_tools_and_diag.py` 通过 20 项。
- **基准**：在本机用模拟 OutputStream、同一目的数组、48 kHz 立体声、非默认增益和固定 1024 帧回绕比较。每版测 5 组各 8000 次回调，耗时中位数 10.50→9.78 微秒。另对 40 次回调测 `tracemalloc` 峰值，50,208→1,364 字节，工作区在回调前分配。
- **待验证**：目标机真实 WASAPI、GPU 模型耗时和持续监听音质。在线 Torch wheel 停滞仍可用 `-CudaWheelDir` 绕开，根因待查。

## Windows 目标机复测

1. 用包含 `c7d37b4` 的提交按 [PACKAGING](PACKAGING.md) 配置 Core、AI 和 MIDI 环境。
2. 在 QQ 音乐按进程环回监听至少 60 秒，试默认和非默认增益，暂停、恢复并切换捕获。停止后导出诊断，在 `live_separation` 下记录 RTF、缓冲、输入跳段、输出溢出帧、重缓冲和设备欠载。系统环回应提示换回按进程捕获。
3. 用稳定背景的 18 秒以上 WAV 测离线分轨，试听 6 秒和 12 秒附近。按需并测 MIDI 隔离、Chroma 级数和 SMTC 自动重置，将实际证据追加到 [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md)。
