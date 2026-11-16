# 最新交接

- **结果**：防止近实时分轨的监听输出被系统环回再次捕获。桌面入口按捕获后端报告的实际模式判断，包括按进程捕获回退至系统环回。拒绝监听时保留当前捕获和基础分析。停止或切换捕获时，已运行或正在启动的监听会关闭。后台启动和输出回调均验证捕获源仍有效。
- **基线与分支**：基线为 PR #5 合入 `main` 的 `ceed61f20bed69ab26df8cfa29e384c40ab58ba7`。代码和测试证据为 `f1bd25fba506c4a118b7e8e074bda50b776f2702`，分支 `fix/live-loopback-feedback`。
- **改动**：[桌面控制器](../main.py)、[近实时 Worker 与输出流](../streaming/live_separator.py)、[实验功能页提示](../ui/main_window.py)。离线分轨、模拟捕获、独立 RTF 基准与程序化无声卡模拟仍可运行。
- **协作**：OpenCode Go 提出捕获源切换及延迟启动的修复方案，Command Code GOAT 独立审查输出打开与回调并发。两项文本任务各一次成功，零重试。采用现有实际模式和捕获实例身份作为开关。
- **验证**：Windows，Python 3.11.17，Core 环境位于纯 ASCII 路径，`QT_QPA_PLATFORM=offscreen`。
  - `python -m pytest -q --tb=short tests/test_phase10_gui_smoke.py -k falls_back` 在旧实现复现了系统环回状态仍调用监听启动的错误。
  - `python -m pytest -q --tb=short tests/test_phase10_gui_smoke.py tests/test_phase7_9_mixer_live_midi.py` 共 14 项通过。
  - `python -m pytest -q --tb=short` 共 130 项通过。
  - `python main.py --simulate --headless-smoke` 使用临时工作目录和设置，正常退出。
- **待验证**：目标机的实际 WASAPI 捕获模式、监听、模型耗时与听感。离线分轨接缝已在合成 WAV 中验证，真实模型听感仍待确认。torch 在线下载停滞可用本地 wheel，根因待查。

## Windows 目标机复测

1. 在含 `f1bd25f` 的提交按 [PACKAGING](PACKAGING.md) 配置 Core、AI 和 MIDI 环境，运行 `.\.venv-core\Scripts\python.exe main.py`。
2. 用 QQ 音乐按进程捕获，在页面确认实际模式为进程环回。开启近实时监听，记录首段、暂停恢复、持续 60 秒的 RTF、缓冲时长、断续或重播。若资源保护触发，记录原因并确认频谱继续。
3. 播放中停止捕获，确认监听一同关闭。再试从进程捕获切到系统环回或触发进程捕获回退。确认基础分析仍更新，重新点击近实时监听时出现切回进程环回的提示。
4. 用稳定背景的 18 秒以上 WAV 做离线分轨，试听第 6 秒、第 12 秒附近并核对源与分轨帧数。核查 Chroma 级数随调性更新，Capo 移调后保持。执行 QQ 音乐切歌、暂停、恢复、拖动进度，查看诊断包中的 `SMTC automatic harmony resets: N`。将实际提交和结果追加至 [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md)。
