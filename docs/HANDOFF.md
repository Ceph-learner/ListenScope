# 最新交接

- **目标和结果**：修复实验性近实时分轨的输出回调重复播放尾帧。输出按未读顺序消费，欠载时在块尾补静音，溢出时保留最新帧。输出缓冲时长随消费下降。内存阈值、自动停止和 Worker 生命周期沿用原逻辑。
- **基线与分支**：`main` 在 PR #1 合并后为 `e4e91b05e8b63e8c99c508b80ce21a58283b50bd`。代码与测试证据提交为 `bb3e58836a10e1b74edafe7d29e4a2804d667c51`，分支 `fix/live-output-ring`。可用 `git ls-remote --heads origin refs/heads/fix/live-output-ring` 核对远端分支。
- **改动**：[live_separator.py](../streaming/live_separator.py#L810-L836) 用写入位置和未读帧数定位最早未读帧。[专项测试](../tests/test_phase7_9_mixer_live_midi.py) 覆盖顺序消费、回绕、欠载、重新写入、增益、限幅和容量边界。
- **协作**：OpenCode Go 提出 FIFO 修复和用例。Command Code GOAT 独立审查读写和溢出。采用现有写入位置与未读帧数，省去额外状态。两项委派各执行一次。
- **验证**：Windows，Python 3.11.17，Core 依赖及 pytest，`QT_QPA_PLATFORM=offscreen`。
  - `python -m pytest -q --tb=short tests/test_phase7_9_mixer_live_midi.py -k live_output` 在旧实现上出现 4 项预期失败。
  - `python -m pytest -q --tb=short tests/test_phase7_9_mixer_live_midi.py` 在修复后 7 项通过，含资源 WARNING 自动停止用例。
  - `python -m pytest -q --tb=short` 从纯 ASCII 路径下的 Core 虚拟环境运行，119 项通过。仓库内中文路径下的虚拟环境在基线和修复后均出现两项外部解释器测试找不到 NumPy，换用 ASCII 路径后通过。
- **待验证**：Windows 目标机的真实声卡输出、持续播放和启动时内存保护。历史目标机结果见 [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md)。单轨 MIDI 同名覆盖、SMTC 重复重置和 torch 下载停滞见 [CURRENT_STATE](CURRENT_STATE.md)。

## Windows 目标机复测

1. 在 `fix/live-output-ring` 分支按 [PACKAGING](PACKAGING.md) 配置 Core 和 AI 解释器，运行 `.\.venv-core\Scripts\python.exe main.py`。
2. 正常播放一段音频并启动捕获。在「5. 实验功能」选择「开启实验性近实时分轨」，记录启动时可用内存和状态消息。
3. 若有非静音输出，记录首段延迟，听取多个输出块，确认尾段没有循环重播。可短暂停止音源并恢复，记录欠载、恢复和缓冲时长。若保护先触发，记录停止原因，并确认基础频谱继续运行。
4. 将对应提交、事件时间、结果追加至 [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md)。随后处理历史作业目录内单轨 MIDI 的同名覆盖。
