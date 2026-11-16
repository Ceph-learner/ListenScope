# 最新交接

- **结果**：新增外观主题窗口、经典 / Lenso / Codex / Claude Code 预设、字号、背景色、强调色和字色。滑杆仅更新样区，点击保存才更新全窗和本地设置。外观随 settings schema 2 写入。[外观数据](../core/appearance.py) · [Qt 实现](../ui/appearance.py)
- **性能约束**：玻璃观感使用 Qt 渐变。范围可选仅小面积控件、全部面板或关闭，无实时背景抓取。捕获状态短摘要留在工具栏，音频源详情和溢出计数在悬停提示中。主题变化不执行 AI 或 MIDI 环境探测。
- **证据**：分支 `feature/appearance-presets`，代码 `cf3c702ab97ba606a0137e73c5c89bdf8821aeb8`，基于 `01dd09f6a48906415aeb06e4a61bfb1fdc95f273`。两位 Worker 的用量、短测数据及旧 MCP 初始上限拦截见 [AI 协同报告](AI_COLLABORATION.md)。
- **验证**：Windows 3.11 Core，`QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short` 通过 143 项。合成音频实时刷新短测持续产生分析快照并写入环形缓冲，目标机实际使用和听感待复测。

## Windows 目标机复测

1. 按 [PACKAGING](PACKAGING.md) 将 Core 应用运行在目标机上，分别测光学效果关闭、小件和全部面板。每档用相同的音频源连续播放至少 60 秒，并切换频谱、和弦、混音和设置页面。记录 RAM、捕获溢出和实际听感。
2. 选择预设后修改字号和颜色，验证取消和重启恢复。用 100% 和常用缩放检查工具栏、紧急停止和 A/B 控件。
3. 近实时音频的目标机验收继续按 [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md) 进行。速度基准与运行统计按可播放步长计算 RTF（合并提交 `01dd09f`）。
