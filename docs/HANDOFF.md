# 最新交接

- **目标和结果**：合并近实时输出环修复，并修复历史分轨目录内自动转录覆盖同名 MIDI 的问题。直接打开和混音器内转录共享同一入口，每次在 `work_dir/midi/` 写独立中间文件。外部解释器收到绝对输入和输出路径，用户可另存到指定位置。
- **基线与分支**：基线为 PR #2 合入 `main` 的 `42bc193fb006232c6b2a71216903e98ffd8ccfae`。MIDI 修复的代码与测试证据提交为 `607d4aa5eac99ff0e940f81cb539fdf4e5563ecb`，分支 `fix/single-stem-midi-output`。
- **改动**：[`_on_transcribe_stem_midi`](../main.py#L1298) 使用独立 UUID 文件名。[MIDI 集成测试](../tests/test_media_session_and_single_stem_midi.py) 覆盖历史作业目录和外部目录、保留原文件、重复转录、相对路径、实时捕获与另存。
- **协作**：OpenCode Go 提出统一中间路径和回归方案，Command Code GOAT 独立审查并指出外部解释器工作目录和并发写入风险。两项委派各执行一次。中间文件沿用工作区留存方式，由用户执行明确的另存操作。
- **验证**：Windows，Python 3.11.17，Core 虚拟环境位于纯 ASCII 路径，`QT_QPA_PLATFORM=offscreen`。
  - 合并前的近实时修复经 [PR #2 CI](https://github.com/Ceph-learner/ListenScope/actions/runs/43787946907) 验证，119 项通过。本地 `main` 已拉取合并提交。
  - `python -m pytest -q --tb=short tests/test_media_session_and_single_stem_midi.py -k historical-job` 在旧实现上复现失败，原 MIDI 的字节被改写。
  - `python -m pytest -q --tb=short tests/test_media_session_and_single_stem_midi.py tests/test_windows_defaults_and_midi_routing.py` 修复后 10 项通过。
  - `python -m pytest -q --tb=short` 修复后 120 项通过。
- **下一步**：为 QQ 音乐 SMTC 自动切歌重置补事件计数和测试，核实同一切歌是否重复触发。状态见 [CURRENT_STATE](CURRENT_STATE.md)。

## Windows 目标机复测

1. 在包含 `607d4aa` 的提交按 [PACKAGING](PACKAGING.md) 配置 Core、AI、MIDI 解释器，运行 `.\.venv-core\Scripts\python.exe main.py`。
2. 准备一份历史作业目录中的单轨 WAV 和同名 MIDI，先用 `Get-FileHash` 记录原 MIDI 的哈希。打开 WAV 连续转录两次，确认原 MIDI 的哈希一致，两次中间文件不同，再通过「另存 MIDI」导出并用 MIDI 编辑器打开。
3. 播放音频并启动捕获。在「5. 实验功能」开启近实时分轨，记录可用内存、首段延迟、持续输出和暂停恢复。若内存保护触发，记录停止原因并确认基础频谱继续运行。
4. 将提交、事件时间和实际结果追加至 [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md)。
