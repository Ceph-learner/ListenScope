# 最新交接

- **结果**：近实时分轨界面与诊断摘要区分输入跳段、应用输出重缓冲和声卡报告的欠载。初次预缓冲、等待重新缓冲期间的空回调，以及捕获源失效后的静音不额外计入重缓冲。实际设备通知按报告的回调次数计。
- **基线与分支**：基线为 PR #6 合入 `main` 的 `7cc321e63beec9bef508e49673c854996f8f6068`。代码与测试证据为 `4e4c79044ed2ed91c17a91429a1f6a09c8a1742a`，分支 `feature/live-playback-diagnostics`。
- **数据**：[实时分轨](../streaming/live_separator.py) 保存本次或最近一次会话的计数，新一轮实际启动时复位。[诊断导出](../core/diagnostics.py) 只选择 `diagnostic_summary.json` 中的数值字段和运行状态，避免将自由文本状态写入新指标。
- **协作**：[AI 协同报告](AI_COLLABORATION.md) 记录本轮派工、使用模型、验收采纳、误报和下一轮对比办法。共四项文本任务，三项完成，V4 Pro 一项超时，均无重试。
- **验证**：Windows，Python 3.11.17，Core 环境位于纯 ASCII 路径，`QT_QPA_PLATFORM=offscreen`。`python -m pytest -q --tb=short` 共 130 项通过。`python -m pytest -q --tb=short tests/test_phase7_9_mixer_live_midi.py tests/test_phase14_practice_tools_and_diag.py` 在最终界面与导出改动后 17 项通过。
- **待验证**：目标机的真实 WASAPI 模式、GPU 模型耗时及监听听感。声卡报告欠载为零只说明驱动没有报告这类标志。torch 在线下载停滞仍可用本地 wheel，根因待查。

## Windows 目标机复测

1. 用含 `4e4c790` 的提交按 [PACKAGING](PACKAGING.md) 配置 Core、AI 与 MIDI 环境，从源码运行 `.\.venv-core\Scripts\python.exe main.py`。
2. 在 QQ 音乐选择按进程环回，运行近实时监听至少 60 秒。记下首段等待、暂停和恢复时刻以及听到断续的时刻。停止监听后立即导出诊断包，在 `diagnostic_summary.json` 的 `live_separation` 节点记录 RTF、缓冲、`input_drop_events`、`playback_rebuffers` 和 `device_underflows`。
3. 播放中停止或切换捕获，确认监听关闭。切到系统环回，确认基础频谱继续更新，开启监听时有切回进程环回的提示。若触发资源保护，记录具体原因。
4. 有条件时一并验证离线分轨第 6 秒和第 12 秒的接缝、历史 MIDI 隔离、Chroma 级数及 Capo、QQ 音乐自动切歌重置计数，并将提交、事件时间与结果追加至 [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md)。
