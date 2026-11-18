# ListenScope 界面规范

ListenScope 是安静、紧凑、精确的 Windows 音频工作台。分轨页面先让用户确认听到哪几轨，再区分和弦与节奏分析、单轨 MIDI 转录及各自的导出。

- **字形**：支持扫描本机已安装字体（默认沿用系统 Segoe UI 与微软雅黑）与 `11–20 px` 字号实时预览，并在外觀弹窗提供「恢复默认」与「保存 / 取消」回退。区块标题半粗体，读数使用稳定小数位与同宽缓存更新。短窗口减少热图刻度数量，使保留音名对准实际音级。
- **颜色与明暗主题（含「马拉松」工业临床预设）**：支持 **黑夜 / 白天 / 跟随系统** 三种模式（依托 Qt 6.8 `styleHints().colorScheme()` 实时响应系统切换）。预设包含 `经典`、`Lenso`、`Codex`、`Claude Code` 与新增第 5 档 **「马拉松 (`Marathon`)」**（[`core/appearance.py`](core/appearance.py)、[`ui/marathon_style.py`](ui/marathon_style.py)）：在「马拉松」模式下，默认呈现 **临床冷白 (`MARATHON // CLINICAL`, `#EEF2F6` / `#FFFFFF`)** 与 **暗夜遥测 (`MARATHON // OBSIDIAN`, `#0B1016` / `#121923`)**，严格禁用暖黄/琥珀色串色，结合 45° 切角铭牌 [`ChamferBadge`](ui/marathon_style.py#L223-L278)、双语等宽遥测头 [`TelemetryHeader`](ui/marathon_style.py#L281-L332)、1px 瑞士精密边线、顶栏快切胶囊（持久化回写 `settings.json`）与冷青蓝时频 LUT，并把扁平化 `QPushButton`、`QComboBox` 下拉矢量化箭头、`QSpinBox`/`QDoubleSpinBox` 微调按钮、`QSlider`、`QCheckBox`/`QRadioButton`、`QScrollArea` 及 `QScrollBar` 完全隔离在 [`_marathon_controls_qss`](ui/marathon_style.py) 与随包 SVG 资产（`ui/assets/marathon_*.svg`）中，彻底消除 Fusion 原生 3D 凸起斜角且不影响其他预设；切换回 `经典`/`Lenso` 等预设时，[`appearance_stylesheet`](ui/appearance.py#L113) 提供完整回退规则以保证无残缺边框，所有语义色调统一收口于动态 `[tone=...]` QSS 令牌。
- **布局与微交互**：采用 6–8 px 组内间距与无 `QGraphicsEffect` 原则。顶部状态条保持固定尺寸策略避免窄窗截断；主音高新增平滑 90ms `QVariantAnimation` 准音刻度条（`TuningCentsBar`）；复杂选项旁附紧凑型 `[?]` `HelpBadge`（支持悬停、点击弹窗与 `TabFocus`）。播放、监听预设和整轨分析各有一行，高频标签、x 轴缓冲与性能表格采用签名/文本缓存跳过冗余重绘。
- **设置与同级存储**：左侧常驻图标与文字导航，右侧显示当前页面。外观卡片汇总模式/主题/字体并可直达便携存储路径：只要软件目录可写，配置（`settings.json`）、离线缓存与 WAV/MIDI 导出均优先落盘在程序同级目录（不写 `C:\` 系统目录）；AI 与 CPU MIDI 在设置同页分块提供零配置扫描与一键安装入口。
- **工作区**：外观主题内可选择 A 工作台、B 双栏扒谱、C 练习优先。B 是新设置和旧设置缺省值。切换工作区保留主题、A/B 选区、缩放和当前分析页签。历史波形支持滚轮横向缩放、平移、放大缩小按钮和 120 秒总览。
- **状态与混音分析**：空状态给出下一步，转录缺少环境时提供直达设置的入口；贝斯分析以 FFT-YIN 展示最低音名（含 8 度防跃变与半程转调警告）、实音/移调 MIDI 编号及起止频率/时间戳。按钮保留键盘焦点与禁用态，不使用像素阴影或背景采样。
- **实时分析**：音高、电平、峰值和缓存时长集中在固定顶部区域，图名置于图框左上，单位与轴刻度降为辅助层级。三种布局分别突出波形、FFT 和时频图。参考 [Logic Pro 控制栏](https://help.apple.com/logicpro/mac/10.1/en.lproj/lgcp2a07a994.html)、[Fluent 2 布局](https://fluent2.microsoft.design/layout)与 [Audacity 时频图](https://manual.audacityteam.org/man/spectrogram_view.html)。切换重用图表、数据和缩放，继续使用原生 Qt 绘制。

- **参考**：从[用户 UI 收藏](https://github.com/stars/Ceph-learner/lists/ui)核实 Lenso UI，延续当前主题的材质分层。从[Linear 视觉分析](https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/linear.app/DESIGN.md)借鉴克制的强调色和紧凑工具表面。视觉参考只取结构原则，代码和素材均沿用原生 Qt 项目已有实现。
- **练习和弦与 Chroma 卡片**：Chroma 顶部三张卡片（和弦、调性、BPM/主音高/节拍器）使用统一的 Hero 主读数 + 辅助元数据层级，避免狭长卡片标题与 BPM 大字号截断；「练习和弦」弹窗区分原曲快照卡片、练习选调/速度栏、模板表与底部实音/指型口径条、反馈提示与主操作按钮，并通过 `_PracticeTableDelegate` 消除第 0 行焦点缩进确保罗马级数列与表头左对齐一致。颜色、高亮与焦点状态复用主题预设标记。
- **预览**：使用实际 PySide6 窗口和合成轨道抓图（Marathon 临床冷白 / 暗夜遥测、1280×800 窄窗、设置与外观弹窗、练习和弦、混音贝斯与 MIDI 表，以及经典暗黑回退对照图），核对文字不截断、下拉与微调扁平无 3D 凸起、图表对比度与无滚动条溢出。目标机 DPI、声卡试听、Cubase MIDI 导入、Inno Setup 安装包与真机分轨验收单独记录。
