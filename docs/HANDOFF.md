# 最新交接

- **结果**：[近实时基准](../streaming/benchmark.py) 和[运行统计](../streaming/live_separator.py) 均以每轮新增可播放音频时长计算 RTF，重叠只用于衔接。基准使用生产块长。短测试仍至少运行一个完整生产块，默认推理次数沿用原约定。隔离基准的 JSON 字段保持，`test_duration_sec` 代表分母中的可播放时长。
- **基线与分支**：基于 PR #10 的合并提交 `29be3d4b515fb05ce56b47374cb4b0b0728eef50`；本轮代码与测试证据为 `2cffafb6dd0b3e5658cd52df2b4f9ef6285ce0c0`，分支 `fix/live-rtf-hop-timing`。
- **实测数值**：假时钟下输入窗 2.00 秒、重叠 0.25 秒、耗时 1.80 秒，旧公式 RTF 0.90，新公式 1.0286。速度准入会拒绝这一持续监听场景。它验证计算口径，尚未验证目标机是否出现相同瓶颈。
- **协作**：Command Code GOAT V4.1 Flash 出完整补丁方案，OpenCode Go V4 Pro 独立复核数值和生命周期风险。各一次完成，无重试。详细采纳和用量见 [AI 协同报告](AI_COLLABORATION.md)。
- **验证**：Windows，Python 3.11.17；Core 环境位于 ASCII 路径，`QT_QPA_PLATFORM=offscreen`。旧实现上 `python -m pytest -q --tb=short tests/test_phase7_9_mixer_live_midi.py -k 'measures_new or ignores_duplicate'` 复现 3 项失败。修复后 `python -m pytest -q --tb=short tests/test_phase7_9_mixer_live_midi.py tests/test_phase12_audit_and_features.py` 通过 25 项，全量 `python -m pytest -q --tb=short` 通过 141 项。
- **其他**：PR #10 前两次 CI 在 checkout 失败，第三次和独立手动运行通过，已合并。见 [当前状态](CURRENT_STATE.md)。

## Windows 目标机复测

1. 检出包含 `2cffafb` 的提交。按 [PACKAGING](PACKAGING.md) 准备 CUDA 和独立 AI 解释器，先用 `-CheckCudaWheels` 预检本地 wheel，实际安装后运行 `pip check`。
2. 在应用中运行近实时速度基准，记录模型、推理耗时、新增可播放时长、RTF 和是否通过。历史报告采用输入块口径，可对照原始耗时，RTF 建议重测后比较。
3. 若基准通过，用 QQ 音乐按进程环回监听 60 秒，试暂停恢复、不同增益与切换捕获。导出诊断，核查输入跳段、输出溢出、重缓冲和设备欠载，记录真实听感与保护原因。将结果写入 [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md)。
