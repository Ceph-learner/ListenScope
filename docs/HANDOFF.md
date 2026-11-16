# 最新交接

- **结果**：近实时输出缓冲新增溢出丢弃帧数，区分输入跳段、输出重缓冲和声卡报告欠载。计数保留到下一次启动，停止后仍可导出。修复超长写入且两轨长度不一致时分别截尾造成的时间错位。
- **基线与分支**：PR #7 合入 `main` 的 `1f7516825098e92a298b99c7d1fabd9f354de68f`。本轮代码与测试证据为 `bbbede14fa69090d067449822a3124d0b2314ad5`，分支 `fix/live-output-overwrite-diagnostics`。
- **数据**：[`_append_output`](../streaming/live_separator.py) 以共同帧数保证人声和伴奏对齐。输出溢出发生时，只计因超出队列容量而丢弃的帧。[诊断导出](../core/diagnostics.py) 把 `output_overwritten_frames` 与其他播放指标放在 `diagnostic_summary.json` 的 `live_separation`。
- **协作**：[AI 协同报告](AI_COLLABORATION.md) 记录两家 V4.1 Flash 在同一审查任务上的结果与用量。都找到了真实错位，零重试。后续优先让 Worker 负责完整的独立模块方案和关键风险复审，同题用于模型对比。
- **验证**：Windows，Python 3.11.17，Core 环境位于纯 ASCII 路径，`QT_QPA_PLATFORM=offscreen`。旧代码在 `python -m pytest -q --tb=short tests/test_phase7_9_mixer_live_midi.py -k oversized_stems` 上复现错位。修复后 `python -m pytest -q --tb=short tests/test_phase7_9_mixer_live_midi.py tests/test_phase14_practice_tools_and_diag.py` 通过 19 项，全量 `python -m pytest -q --tb=short` 通过 132 项。
- **待验证**：目标机的真实 WASAPI 模式、GPU 模型耗时及监听听感。torch 在线下载停滞仍可用本地 wheel，根因待查。

## Windows 目标机复测

1. 用含 `bbbede1` 的提交按 [PACKAGING](PACKAGING.md) 配置 Core、AI 与 MIDI 环境，从源码运行 `.\.venv-core\Scripts\python.exe main.py`。
2. 在 QQ 音乐选择按进程环回，运行近实时监听至少 60 秒。记下首段等待、暂停和恢复以及听到断续的时刻。停止监听后立即导出诊断包，从 `diagnostic_summary.json` 的 `live_separation` 记录 RTF、缓冲、`input_drop_events`、`output_overwritten_frames`、`playback_rebuffers` 和 `device_underflows`。
3. 停止或切换捕获，确认监听关闭。切到系统环回，确认基础频谱继续，开启监听时提示使用进程环回。若保护触发，记录原因。
4. 有条件时一并验证离线分轨第 6 秒和第 12 秒的接缝、历史 MIDI 隔离、Chroma 级数及 Capo、QQ 音乐自动切歌重置计数，将提交、事件时间与结果追加至 [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md)。
