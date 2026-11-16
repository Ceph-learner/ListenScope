# 最新交接

- **目标和结果**：修复离线分轨相邻推理窗口预测电平不一致时的硬切。[流式分轨写入](../ai/resource_guard.py) 保存上一块的右侧预测，与下一块同一源时间的预测交叉淡化。只写核心帧，分块大小、输出时长、模型和保护阈值沿用现有配置。
- **基线与分支**：`1905f242d77585e96948fa2ee845d8354869c649` 为前一轮 PR #4 合并后的 `main`。本轮证据提交为 `35add3ca68bd0ad7dbc7bc1e64e848711148e826`，分支 `fix/offline-stem-seams`。
- **验证**：Windows，Python 3.11.17，Core 虚拟环境位于纯 ASCII 路径，设置 `QT_QPA_PLATFORM=offscreen`。
  - `python -m pytest -q --tb=short tests/test_phase5_6_ai_worker.py -k crossfade` 在旧实现上出现 1 项预期失败，修复后 2 项通过。合成斜坡验证了接缝混合、无重叠路径、短尾块和逐帧顺序。
  - `python -m pytest -q --tb=short` 共 126 项通过，包括 30 分钟流式分轨的帧数与内存测试。
- **协作**：OpenCode Go 和 Command Code GOAT 的本轮两项排查均被本地 Bridge 初始验证启动上限拒绝，未调用模型。Codex 复现并完成修复。
- **待验证**：开发机为 RTX 4060，且没有启动 QQ 音乐。本轮按合成数据运行，目标机上真实分轨听感和耗时仍需复测。近实时系统环回可能再次捕获监听输出，后续可结合捕获模式和复现结果核查。

## Windows 目标机复测

1. 在含 `35add3c` 的提交按 [PACKAGING](PACKAGING.md) 配置 Core、AI 和 MIDI 环境，运行 `.\.venv-core\Scripts\python.exe main.py`。
2. 选一段不少于 18 秒、有稳定背景声并跨越多个 6 秒边界的 WAV。使用默认分块离线分轨，试听每条分轨第 6 秒和第 12 秒附近，并与旧版在同一 WAV、同一模型的输出比较。核对输出帧数和源文件相同。
3. 在 QQ 音乐中使用按进程环回，确认界面没有退回系统环回。近实时运行 60 秒，记下首段和暂停恢复等待、断续或重播、RTF、缓冲时长和保护原因。若只能使用系统环回，单列可能被回采的听感。
4. 顺带核对 Chroma 级数随调性更新且不受 Capo 影响。QQ 音乐切歌、暂停、恢复和拖动进度后，在诊断包 `recent_logs.txt` 核查 `SMTC automatic harmony resets: N`。复测历史 WAV 转 MIDI 同名文件哈希与另存。将实际提交和结果追加至 [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md)。
