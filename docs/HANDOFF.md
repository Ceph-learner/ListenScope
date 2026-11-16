# 最新交接

- **基线与分支**：`main` 的 `7a57139a5fc161b1a49907f3de4efe7917c7ccaf` 已合入历史目录 MIDI 输出修复。此轮代码和测试证据为 `ea85d23742d9cd0d5ffd20359423790a6209ae0a`，分支 `fix/live-practice-reliability`。
- **近实时播放**：[`live_separator.py`](../streaming/live_separator.py) 丢弃重复或过期回包，仅对相邻结果做交叠。播放启动和欠载恢复时有界预缓冲。默认步长 1.75 秒，常规启动需要两批结果，因此首段和欠载恢复会晚约一个步长。保留既有 Worker、队列容量和内存保护。
- **和声练习**：[`chords.py`](../analysis/chords.py) 按调性和和弦性质计算罗马数字。Chroma 页显示当前和弦级数，小调按自然小调，Capo 移调保持级数，热图纵轴音名改用较小字体。
- **SMTC**：只有实际执行自动重置才会写一条 `SMTC automatic harmony resets: N`，从应用启动累计。消息只含计数，可在诊断包 `recent_logs.txt` 核对，手动重置不计数。
- **仓库资料**：[致谢与来源](../ACKNOWLEDGMENTS.md) 列明上游工具、模型、论文和体验参考。README 有致谢入口，GitHub 仓库简介及六个主题已更新。
- **协作**：OpenCode Go 分析分轨断续和重复输出，Command Code GOAT 提供级数与 SMTC 计数方案。各执行一次文本任务，零重试。代码保留既有 IPC 字段，通过跳号标记输入不相邻。
- **验证**：Windows，Python 3.11.17，Core 环境位于纯 ASCII 路径，`QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short` 共 124 项通过。覆盖重复与乱序回包、跳段交叠、欠载恢复、级数与 Capo、SMTC 单次计数和原有资源停止行为。
- **待验证**：真实 WAV/GPU/声卡链路的听感、首段与恢复延迟，实际 QQ 音乐 SMTC 事件以及 Chroma 的 Windows 显示效果。torch 在线下载停滞仍可用本地 wheel 路线绕开，根因待查。

## Windows 目标机复测

1. 在含 `ea85d23` 的提交按 [PACKAGING](PACKAGING.md) 配置三个环境，运行 `.\.venv-core\Scripts\python.exe main.py`。
2. 用明确有节拍的片段，选择按进程捕获，并在界面确认显示为进程环回。启动近实时分轨，记录首段与暂停恢复的等待、连续 60 秒内的断续或重播、RTF 和缓冲时长。若实际为系统环回，单列结果，因为系统环回可能将 ListenScope 播放的输出再次捕获。若触发保护，记录停止原因并确认基础频谱继续运行。
3. 用 C 大调中含 Am 的片段核对 `vi`，切换 Capo 后核对级数保持不变。检查热图音名在常用窗口尺寸和缩放比例下是否清晰。
4. 在 QQ 音乐中切歌、暂停、恢复和拖动进度，导出诊断包。核对每次实际切歌是否只有一条自动重置计数，其他操作和手动重置是否未增加计数。
5. 对历史作业目录中的 WAV 重复转录，核对同名 MIDI 的 `Get-FileHash` 值与转录前一致，另存的 MIDI 可正确打开。将各项实际测试提交和结果追加至 [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md)。
