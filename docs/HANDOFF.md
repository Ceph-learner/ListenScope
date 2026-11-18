# 最新交接

## 「马拉松 (`Marathon`)」工业临床主题集成与隔离式扁平控件（`design/marathon-ui-preview` · 提交 PR 合入 `main`）

- **目标与状态**：基于远端 `main` (`2a9c335`, PR #23) 检出 `design/marathon-ui-preview`，将已确认的「马拉松」工业临床双模视觉方案正式接入 **设置 / 外观主题** 预设体系（第 5 档 `marathon`，与 `classic` / `lenso` / `codex` / `claude` 并列，支持 **黑夜 / 白天 / 跟随系统**、`AppearanceDialog` 实时预览与取消回退、顶栏快切胶囊持久化）；随后按用户视觉反馈在完全隔离于 `ui/marathon_style.py` + `ui/assets/marathon_*.svg` 的前提下消除 Qt Fusion 原生 3D 凸起（`QComboBox` 下拉盖板、`QSpinBox`/`QDoubleSpinBox` 步进钮、`QGroupBox` 抬升框、`QSlider`、`QCheckBox`、`QRadioButton`、`QScrollArea` 与 `QPushButton`），不影响 `经典` 等现有预设。核心代码及测试证据提交：`549aecf6986c03039ebc7211ecbed496234ac305`。
- **关键改动路径**：
  - 主题配置与独立视觉引擎：[`core/appearance.py`](../core/appearance.py)、[`ui/marathon_style.py`](../ui/marathon_style.py)（`is_marathon_eligible`、`resolve_marathon_variant`、`marathon_stylesheet`、`apply_marathon_plot_theme`、`marathon_colormap_lut`、`ChamferBadge`、`TelemetryHeader` 与隔离扁平控件生成函数 `_marathon_controls_qss`）、[`ui/appearance.py`](../ui/appearance.py)（接入 `AppearanceDialog` 第 5 档预设并提供切回 `经典`/`Lenso` 时的顶栏与遥测卡片完整回退 CSS）。
  - 随包 SVG 矢量化图标与 PyInstaller 打包清单：`ui/assets/marathon_check.svg`、`ui/assets/marathon_chevron_{up,down}_{light,dark}.svg` 及 [`packaging/listenscope_core.spec`](../packaging/listenscope_core.spec) `datas`。
  - 窗口与子模块联动：[`ui/main_window.py`](../ui/main_window.py)（顶栏双模快切 `MARATHON // CLINICAL` 与 `OBSIDIAN` 持久化回调 `set_marathon_skin`、切离自动隐藏）、[`ui/settings_dialog.py`](../ui/settings_dialog.py)（左侧导航动态着色与主题摘要同步）、[`ui/mixer_widget.py`](../ui/mixer_widget.py)、[`ui/chord_practice.py`](../ui/chord_practice.py)、[`ui/chroma_widget.py`](../ui/chroma_widget.py)、[`ui/spectrum_widget.py`](../ui/spectrum_widget.py)、[`ui/resource_widget.py`](../ui/resource_widget.py)。
  - 回归测试：[`tests/test_turnkey_cubase_bass_theme.py`](../tests/test_turnkey_cubase_bass_theme.py)（`test_marathon_preset_integration_topbar_sync_persistence_and_packaging`）。
- **已验证（云端 Linux · Debian 12 · Python 3.11.2 · PySide6 6.8.3 · `QT_QPA_PLATFORM=offscreen`）**：
  - 专项：`QT_QPA_PLATFORM=offscreen /home/antigravity/.venv_test/bin/python -m pytest tests/test_turnkey_cubase_bass_theme.py tests/test_appearance.py -q --tb=short` -> **`12 passed in 3.21s`**
  - 全量（基于代码提交 `549aecf`）：`QT_QPA_PLATFORM=offscreen /home/antigravity/.venv_test/bin/python -m pytest -q --tb=short` -> **`189 passed, 6 skipped in 63.68s`**（6 项 Windows WASAPI / WinRT / PowerShell 专属测试在 Linux 跳过）。
  - 离屏视觉截图检查与顺带修复：生成并逐一核对 10 张真实 `PySide6` offscreen 截图（临床冷白 Tab 1–3、暗夜遥测 Tab 4、1280×800 窄窗、设置弹窗、外观弹窗、和弦练习弹窗及 `经典` 暗黑回退对照）；除消除 `QComboBox`/`QSpinBox`/`QGroupBox` 3D 凸起外，同步在 `ui/mixer_widget.py` 收紧子页内距与设置 `chord_timeline_table.setMinimumHeight(48)` 解决 870px 高度下 `deep_summary_lbl`（`Melody (vocals)` 行）底部 3–6px 裁切问题。
- **尚未验证（需 Windows 11 目标机复测）**：
  1. PyInstaller 打包产物 `dist\ListenScopeCore\ListenScope.exe` 下 [`_marathon_asset_url`](../ui/marathon_style.py#L335-L340) 加载 `ui/assets/marathon_*.svg`（确认下拉箭头、微调上下三角与复选框对勾正常渲染）。
  2. Windows 11 实机 `100% / 125% / 150%` 系统 DPI 缩放与字体渲染、系统深浅色切换联动「跟随系统」以及在 **马拉松 临床冷白 / 暗夜遥测 / 经典 / Lenso** 间反复切换。
  3. 延续 PR #23 待真机复测项：`ISCC.exe` 编译单文件安装包（`build_windows.ps1 -Clean -BundleRuntimes -BundleFfmpeg -BuildInstaller`）与非 C 盘零配置安装、三类 Cubase `.mid` 导入验证、WASAPI 实声卡试听及 RTX 5060 Ti 8GB / 16GB RAM 下真实曲目四轨与近实时播放。
- **Windows 本机复测命令**：
  ```powershell
  $env:PYTHONUTF8 = "1"; $env:QT_QPA_PLATFORM = "offscreen"
  .\.venv-core\Scripts\python.exe -m pytest tests/test_turnkey_cubase_bass_theme.py tests/test_appearance.py tests/test_chord_practice.py -q --tb=short
  .\.venv-core\Scripts\python.exe -m pytest -q --tb=short
  # PyInstaller + Inno Setup 安装包验证（Windows 目标机）：
  pwsh -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -Clean -BundleRuntimes -BundleFfmpeg -BuildInstaller
  ```

---

## 更早交接（PR #23 基线 · `2a9c335`）

- **基线与状态**：从远端 `main` (`426a6f476d24f6903de6f4f7f280521461a8c769`, PR #22) 检出本地分支 `feature/chord-practice-midi-audition`，已通过 PR #23 合入 `main` (`2a9c335`)。目标机硬件基线保持 **Windows 11 (Build >= 20348) · NVIDIA GeForce RTX 5060 Ti 8GB VRAM · 16GB RAM**（Core 仍零捆绑 PyTorch/CUDA/ORT/TF，安装包版本与 `pyproject.toml` 同步为 `0.2.0`）。
- **核心改动**：
  1. **练习和弦弹窗 Row 0 对齐与试听/导出**（[`ui/chord_practice.py`](../ui/chord_practice.py)、[`analysis/chord_practice.py`](../analysis/chord_practice.py)）：新增 `_PracticeTableDelegate` 清除第 0 行 `State_HasFocus` 焦点矩形导致的左缩进并统一罗马级数/和弦左对齐与匹配列居中（对齐表头）；支持 24 调模板、Capo 移调指型/实音双重口径换算、本地合成试听（复用共享 `DrumPreviewPlayer` 且与 A/B、混音、节拍器、鼓试听严格互斥）与 `.mid` 导出。
  2. **贝斯最低音 MIDI、具体音名与转调预警**（[`analysis/stem_analyzer.py`](../analysis/stem_analyzer.py)、[`ui/chroma_widget.py`](../ui/chroma_widget.py)、[`ui/mixer_widget.py`](../ui/mixer_widget.py)）：在 `[28 Hz, 350 Hz]` 实现 FFT 加速 YIN (CMNDF) + 2 倍谐波防 8 度跃变 + 3 帧中值滤波，支持低至 `B0` (`30.87 Hz`)/`E1` (`41.20 Hz`, MIDI `28`)；对比前半段/后半段音级权重并在混音摘要、`export_transcription_sheet` Markdown 报告及 Chroma 页呈现转调警告（`tone="warn"`）。
  3. **轻量化微动画 & `[?]` 悬浮/点击说明徽标**（[`ui/help_badge.py`](../ui/help_badge.py)、[`ui/chroma_widget.py`](../ui/chroma_widget.py)）：全程禁用 `QGraphicsEffect`；主音高旁加入平滑 `90 ms OutCubic` `QVariantAnimation` 准音刻度条（`TuningCentsBar`）；关键控件旁加入支持悬停、点击弹出与键盘 `TabFocus` 的 `HelpBadge`（`wrap_with_help`）。
  4. **Cubase 兼容标准 MIDI 规范化**（[`analysis/midi_common.py`](../analysis/midi_common.py)、[`analysis/drum_midi.py`](../analysis/drum_midi.py)、[`analysis/midi_transcription.py`](../analysis/midi_transcription.py)）：和弦进行、鼓点（GM 通道 9）及单轨 Basic Pitch / CPU 回退全部规范为 SMF Type-0 (`480 TPB`)，Tick 0 写入 ASCII 轨名、`time_signature`、`set_tempo`、合法规范 `key_signature`（自动等音映射如 `G# major -> Ab`）、Controller Reset (`CC 121=0`, `CC 64=0`, `pitchwheel=0`) 与 GM 音色号，修剪同通道同音高重叠并保证 `note_off` 先于同 Tick `note_on`。
  5. **黑夜 / 白天 / 跟随系统主题 + 扫描电脑字体 + 实时预览 + 恢复默认**（[`core/appearance.py`](../core/appearance.py)、[`ui/appearance.py`](../ui/appearance.py)、[`ui/spectrum_widget.py`](../ui/spectrum_widget.py)、[`ui/main_window.py`](../ui/main_window.py)、[`ui/settings_dialog.py`](../ui/settings_dialog.py)）：基于 Qt 6.8 `styleHints().colorScheme()` 实时响应系统深浅色切换；扫描本机已安装字体（`11–20 px`）并支持主界面**实时预览**与取消回退；新增「**恢复默认**」一键还原出厂配置；`PlotWidget` 与波形曲线、A/B 选区/游标及全部语义色调（`[tone=...]`）在黑夜/白天模式下均保持高对比度。
  6. **同级目录存储、零配置运行时发现与 Inno Setup 一键安装包**（[`core/paths.py`](../core/paths.py)、[`core/settings_store.py`](../core/settings_store.py)、[`main.py`](../main.py)、[`ui/settings_dialog.py`](../ui/settings_dialog.py)、[`scripts/installer.iss`](../scripts/installer.iss)、[`scripts/setup_windows.ps1`](../scripts/setup_windows.ps1)、[`scripts/build_windows.ps1`](../scripts/build_windows.ps1)）：优先把 `settings.json`、`workspace_outputs/` 与 `exports/` 保存在程序同级目录（不写 `C:\`）；启动与设置页自动发现随包 `runtime/ai`、短路径 `m`、`.venv-*` 及 `LS-midi` 短盘环境，并支持设置内一键触发 `setup_windows.ps1 -SkipCore` 自动装好 AI/MIDI；`build_windows.ps1` 支持 `-BundleRuntimes -BundleFfmpeg -BuildInstaller`（内置 `Assert-PortableRuntime` 校验禁止打包绑定本机的 `pyvenv.cfg`），`installer.iss` 默认免管理员且智能选非 `C:\`（`D:\ListenScope` / `E:\ListenScope`）。
  7. **导航流畅度与内存稳定优化**：在 [`ui/spectrum_widget.py`](../ui/spectrum_widget.py)、[`ui/chroma_widget.py`](../ui/chroma_widget.py)、[`ui/mixer_widget.py`](../ui/mixer_widget.py)、[`ui/resource_widget.py`](../ui/resource_widget.py) 与 [`main.py`](../main.py) 为高频标签、工作区缓存文本与曲线 X 轴缓冲加入去重缓存；统一收口 `set_widget_tone()` 仅在属性变化时触发 `unpolish/polish`；消除顶部状态栏截断、Tab 标题 `&` 误下划线及 MIDI 表格横向溢出。
- **云端 Linux 离屏验证**：
  - 全量 `QT_QPA_PLATFORM=offscreen /home/antigravity/.venv_test/bin/python -m pytest -q --tb=short` 运行 **`188 passed, 6 skipped`**（6 项 Windows 专属 WinRT / PowerShell 脚本在 Linux 跳过），含新增 [`tests/test_turnkey_cubase_bass_theme.py`](../tests/test_turnkey_cubase_bass_theme.py) 全项测试。
  - 无硬件命令行自检：`python scripts/check_env.py --no-write` 与 `python scripts/probe_media_session.py --self-test-mock --json` 通过；原生 PySide6 离屏截图已核对（`ChordPracticeDialog` Row 0 对齐、白天模式 `AppearanceDialog`、Light Lenso Chroma 无裁剪、Dark Classic Mixer 贝斯 FFT-YIN 最低 `E1` / `MIDI 28` / 转调 warning 横幅及 MIDI 表格预览）。
- **尚未验证（需 Windows 11 目标机复测）**：
  1. `ISCC.exe` 编译单文件安装程序（`build_windows.ps1 -Clean -BundleRuntimes -BundleFfmpeg -BuildInstaller`）及干净目录一键安装体验（含核验免手工配置识别同级 `runtime\ai` 与 `m`、设置/导出落在 `D:\ListenScope` 而非 `C:\`）。
  2. 将三类导出的 `.mid`（和弦进行、鼓点、单轨转录）实际拖入 Steinberg Cubase 验证轨道、拍号、BPM、调号与音符不粘连。
  3. Windows 11 系统深浅色切换时「跟随系统」实时刷新、`125% / 150%` 系统缩放 DPI、真实本地字体显示效果与 WASAPI 声卡试听。
  4. RTX 5060 Ti 8GB / 16GB RAM 下真实曲目贝斯/四轨分析、SMTC 切歌与持续近实时播放。
- **Windows 本机复测命令**：
  ```powershell
  $env:PYTHONUTF8 = "1"; $env:QT_QPA_PLATFORM = "offscreen"
  .\.venv-core\Scripts\python.exe -m pytest tests/test_turnkey_cubase_bass_theme.py tests/test_chord_practice.py tests/test_drum_preview.py tests/test_appearance.py -q --tb=short
  .\.venv-core\Scripts\python.exe -m pytest -q --tb=short
  # 构建与安装包测试（需安装 Inno Setup 6，建议配合可迁移便携运行时）：
  pwsh -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -Clean -BundleRuntimes -BundleFfmpeg -BuildInstaller
  ```

---

## 更早交接（PR #22 基线）

- 新增实时 Chroma 页的「练习和弦」，代码证据 `877ebe48ead6e85096dbcd708847e133a6bbeabe`。根据打开窗口时的最近和弦与稳定调性预选练习调，或手选 24 个大小调。显示罗马级数、保留常用升降号拼写的和弦和连续匹配步数。按最近和弦的连续后缀与练习模板开头匹配，平手保留内置顺序。模板为项目内置通用练习，原曲检测状态独立。
- Windows Core 离屏 `python -m pytest tests/test_chord_practice.py -q --tb=short` 三项通过，覆盖大调七和弦归类、自然小调、24 调、非调内和弦中断、Capo 偏移与手选调。原生截图使用合成和弦历史。实机可在 Chroma 页先核对手选调，再用有稳定调性的片段检查自动预选。后续可扩展练习模板的试听与 MIDI。

- 「分轨混音 & MIDI 扒谱 → 鼓点」加入「试听鼓点」，代码证据 `9ee45225611aaf73d970143046e5d0d3996068a3`。从第一个检测到的击打起保留间距，用本地程序合成底鼓、军鼓和踩镲，最长 8 秒。试听独占应用输出，启动 A/B、混音、节拍器或近实时监听时停掉试听；清除结果、替换分析和关闭应用同样释放试听流。系统环回正在捕获时禁止试听，避免录入环形缓冲。
- Windows 离屏 `python -m pytest tests/test_drum_preview.py -q --tb=short` 3 项通过。用模拟声卡验证自然结束、切换到混音、清除结果和设备启动失败。原生界面截图与生成 PCM 的 WAV 样例已放入交付包。目标机复测：对四轨结果运行「分析和弦与节奏」，点「鼓点 → 试听鼓点」，分别等待自然结束、点击停止、切到 A/B 和清除分轨结果。真实声卡与听感待验收。下一步可做常见和弦进行的本地练习推荐。

- 鼓点 MIDI 导出已在 `feature/drum-midi-export` 实现，代码证据 `72665d55937b0d4988a6e2c937c7d5a9bb12e3f6`。在「分轨混音 & MIDI 扒谱 → 分析和弦与节奏 → 鼓点」点击「导出鼓点 MIDI」。文件保留片段内的底鼓、军鼓和踩镲起始时间，用标准鼓通道、固定力度和短音符；速度未知时写 120 BPM，同时按该速度换算时间，实际击打秒数仍对齐原片段。
- Windows Core 专项用 `QT_QPA_PLATFORM=offscreen`、显式依赖路径执行 `python -m pytest tests/test_phase11_workstation.py -k drum_midi -q --tb=short`，3 项通过。原生 UI 合成样例通过按钮导出 26 次击打，由 mido 回读。真实 DAW 鼓音源映射和听感待验收；可将样例文件拖入使用 GM 鼓组的轨道试听。下一步是鼓点试听。

- 本轮在 `feature/ab-zero-crossing` 上加入 A/B「贴近零点」，代码证据为 `ac61cab13a4a952a4f237f52c7298cb78d1a44c7`。播放停止后，按钮只扫描两个边界各 ±5 ms 的原始 PCM；仅当实际会播放的边缘样本在各声道中的最大振幅变小时才移动边界。超时或被覆盖的选区需要重选；拖动、缩放和实时刷新沿用原逻辑。
- 原生 Qt 离屏预览使用合成反相立体声，验证了按钮入口、两个绝对帧各左移 1 ms、波形选区同步，以及循环读取的半开边界。Windows 复测用 `QT_QPA_PLATFORM=offscreen` 和当前环境的依赖路径，再运行 `python -m pytest -q --tb=short`。目标机听感待验收：导入有声素材、缩放历史波形、选一段并试听，再停止点「贴近零点」后比较接缝。后续可做鼓点试听与独立鼓 MIDI。

- 实时分析评审分支提供三个原生布局「实时监听」「频率诊断」「时频追踪」。右上方切换，保留图表对象、已更新数据和频率图缩放。频带图使用实测频率坐标。随评审包提供原生 Qt 合成信号预览，默认「实时监听」；可在设置的外观主题中选其余布局，实时分析页右上角也可切换，两处同步并自动保存。

- 设置最终采用 A「左侧导航」方案，外观、资源保护、AI 与 MIDI、系统诊断常驻左侧。使用原生 Qt 控件和随包分发的 Lucide 图标。切页保留编辑值，MIDI 快捷入口直达路径输入。

- A/B 启动前区分全零选区、过期和已重置的音频历史，保留微弱有效信号。回放过程中发现历史重置便停止。Windows 图标已接入 Qt、任务栏分组及 PyInstaller，实际打包图标和目标机固定图标待验收。
- 换歌重置与 DSP 更新互斥，重置后的和弦分析从新采集帧开始。主动导入已解码文件仍可立即分析，旧缓冲继续可用于 A/B。
- 现有设置表单可以在较低窗口滚动，MIDI 快捷入口会把解释器字段滚动到视口。三种设置重排方案在浏览器原型中供评审，选定后再重排原生设置结构。

- 原生 Qt 已集成 A 工作台、B 双栏扒谱（默认）和 C 练习优先。设置入口为「外观主题 → 界面布局」。切换复用混音和波形实例，保留 A/B 状态。横轴可用滚轮、放大缩小按钮和总览控制。

## 分轨分析与练习界面预览（2026-11-17）

- 基于实机反馈提交 `8de56f4622074d25aa2c174087fafcbeb85b57c1`。公司机使用原生 Qt 离屏窗口与合成素材。实际目标机音频设备、DPI、分轨和独立 MIDI 环境需另行验收。
- 弱信号分析使用已有分析配置的 −60 dBFS 静音门限，保留原频谱置信度检查。合成弱贝斯、弱和弦、全零和低电平噪声均有回归。混音页分别提示缺轨、低于静音门限、无稳定音符；MIDI 页可直接定位解释器设置。
- 新增分轨结果清除、局部 A/B 波形缩放与总览、设备打开失败提示、最近和弦名与级数切换、Chroma 刻度抽样、16 步鼓点查看。清除保留源 WAV 与历史缓冲，过滤被清除任务的晚到结果。
- Windows Core 离屏全量 169 项通过。原生 Qt 预览取 1280 × 920。额外检查确认 MIDI 设置进入正确页签，键盘焦点定位到解释器输入框。请求 1200 × 800 时，离屏窗口的实际高度被布局撑到 888。
- 待处理：A/B 纯静音及换设备场景的实机复现，缩放后的零交叉吸附，鼓点试听和 MIDI 导出，独立吉他分轨的资源与音色实测，本地练习和弦推荐。保留下文的现场复现和期望作为原始依据。

## 分轨深度分析与练习功能待办（2026-11-16）

记录于 2026-11-16。证据基线：`main` 上的 `aa1054af5a5c890d26c0dd4626bbebbd1f86137b`（贝斯独听与界面修订）。Windows 11，RTX 5060 Ti 8 GB，16 GB RAM。本轮只做只读复现及文档交接；未改源码、未重打包，未重跑全量 pytest。

### 已复现与接手起点

在同一台 Windows 机对现场 10 秒四轨的原始 WAV 调用 analyze_stems_offline。返回和声源 other + bass、调性 Unknown、和弦只有一段 N（静音）、Bass 音符 0；鼓检测返回 Kick 32 / Snare 38 / Hi-Hat 9 个候选。此前确认原贝斯轨约 −45.0 dBFS RMS 且能听到。这个最小复现不用再捕获或跑 GPU，适合下一轮先定位分析门槛；鼓候选数量未做人工标注对照。

---
name: project-continuity
description: Recover development context from repository instructions, Git, and handoff notes before beginning or resuming software work.
---

1. Read root and applicable nested AGENTS.md. Check git status --short --branch, git rev-parse HEAD, and recent commits. Identify the caller's branch, local edits and their relation to the requested work.
2. Read the project overview, current state and latest handoff using the links in AGENTS.md. Follow architecture, requirements, decisions and development links when relevant.
3. Treat handoff claims as leads. Verify the recorded baseline, changed paths, tests and constraints against the current tree, history and available CI evidence. Inspect commits since the recorded baseline. Label checkout, remote and historical release state separately.
4. Identify implemented scope, unresolved work and known risks. Preserve existing edits and respect the current request when choosing the next action. Continue with the requested work.

公司电脑没有原 WAV 时，可以先用任意合法测试素材完成四轨，保留原混音和各轨 WAV；然后在 Windows Core 环境对这些 WAV 调用 [`analysis/stem_analyzer.py`](../analysis/stem_analyzer.py) 的 `analyze_stems_offline`。同一组输入对照原增益、诊断性增益及真正的全零信号。记录 RMS、每帧门限判定、有效帧、调性、和弦段与 Bass 音符；优先区分真实静音与有声但无法识别的片段。现场 WAV 不入库。修复后按 [开发文档](DEVELOPMENT.md) 跑专项回归与 Windows 全量测试，再用 GUI 复测。

### 按顺序处理

| 顺序 | 反馈 | 第一轮验证及完成条件 |
| --- | --- | --- |
| 1 | 深度分析的和弦候选显示静音，调性未知，Bass 无结果；MIDI 页空 | 用现场同一组 WAV 直接调用分析器，记录分析源、原混音及各轨的窗口电平、静音判定、有效帧和音符数。现有四轨和声分析使用 65% other + 35% bass；检查弱信号是否被判为静音、调性是否因有效帧不足。对比原音量与诊断性增益的同一输入，再补弱音及真静音回归。输出区分“缺轨”“确实静音”“信号弱或置信度不足”“尚未转录”，并显示分析源。 |
| 2 | MIDI 提示缺 Python，深度分析和 MIDI 的关系不清楚 | MIDI 转录需单独点轨道的「转 MIDI」。本机已存在独立 Python 3.11 环境，在正在使用的 exe 中选该解释器并验证。复测 Bass 的 MIDI 钢琴卷帘、有效音符与重启恢复。应用提示应能直接带用户到设置。鼓点 MIDI 与有音高单轨转录应分开实现。 |
| 3 | 底部 A/B 有时按播放无声 | 分别复现暂停后选进纯静音、书签被 120 秒环形缓冲覆盖、正在捕获时回放旧区间、输出设备切换。记录实际 A/B 时间、绝对帧范围、选区电平、播放游标、设备及错误。预期有音有声，无法播放则明确提示原因。 |
| 4 | 分轨后缺少清除结果 | 加「清除分轨结果」的设计。清除本次轨道、分析、MIDI 预览和播放状态，阻止旧后台任务结果回填；保留原 WAV、已导出文件和 120 秒捕获缓冲。 |
| 5 | A/B 横轴需要精确缩放 | 当前历史波形关闭了鼠标缩放。用 pyqtgraph 的 ViewBox 做横轴缩放和平移、回到 120 秒总览，缩放时按可见范围重采样峰谷包络，保留 A/B 拖选。支持时间标签、A/B 标记和小步进。极近时再考虑波形采样点、峰谷或零交叉吸附。附查普通窗口 Chroma 热图音名重叠。 |
| 6 | 最近和弦进行可用级数显示 | 设置选择「和弦名 / 罗马数字 / 两者」。沿用已有级数计算，明确按当前有效调性显示，遇到未知调性保留和弦名；检验切歌、调性候选和 Capo 移调。 |
| 7 | 鼓的展示再直观些，吉他轨和节奏推荐 | 把已有 Kick / Snare / Hi-Hat 事件画成 16 步三行网格，支持按需试听和导出独立鼓 MIDI。将吉他分轨、从吉他轨估计节奏、按 BPM/拍号推荐扫弦或分解节奏拆为独立任务。现有四轨的「其他」可能含吉他，不能当成独立吉他。仅把六轨 htdemucs_6s 做候选，先测目标机内存/显存、串音与音色。 |
| 8 | 推荐常见和弦进行，或给出与片段搭配的几个候选 | 先做随软件分发的本地罗马数字模板库，从调性、已识别和弦前缀、拍号与节奏筛选，再转成当前调的和弦、试听和导出 MIDI。区分「原曲检测」「可能的延续」「练习推荐」，不确定时显示依据。可借鉴公开统计接口的排序思路；仅将来源与可再分发授权明确的数据纳入内置库。 |

### 已核对的说明

- Demucs seg 是四轨模型单次推理使用的时间窗口，默认 6 秒，不是 A/B 长度或最后导出时长。更短通常有助于降低显存负担，暂保留已实测默认值。
- 两条 proctap INFO 是两次捕获初始化时确认音频已是 48 kHz / float32，因此跳过格式转换。它们没有报错，也不足以判定选区播放或深度分析是否正常。
- MIDI 使用独立的 Python 3.11 环境，按 [安装说明](PACKAGING.md) 准备后，在「设置 / 系统状态 → 资源安全阈值与 AI 配置 → 独立 CPU MIDI Python 路径」选择 `.venv-midi\Scripts\python.exe`，再点「验证 MIDI 环境」。

### 初步参考

- [Demucs 官方仓库](https://github.com/facebookresearch/demucs) 与 [六轨发布说明](https://github.com/facebookresearch/demucs/blob/main/docs/release.md)
- [Spotify Basic Pitch](https://basicpitch.spotify.com/about)
- [pyqtgraph ViewBox](https://pyqtgraph.readthedocs.io/en/latest/api_reference/graphicsItems/viewbox.html)
- [Hooktheory 的和弦转移 API](https://www.hooktheory.com/api/trends/docs)

## 贝斯独听和界面复测（2026-11-16）

- 基线为 `218e2c9e03702a944476551a1bf158e7d2e04a7b`。`audio/playback.py` 只在贝斯独自出声时给监听 +12 dB，并平滑限制接近满幅的峰值。`ui/mixer_widget.py` 提供开关，缺轨时禁用相应独听。`ui/main_window.py` 强化复选框选中态，提示 GPU 是否就绪。
- 在 Windows Core 设置 `QT_QPA_PLATFORM=offscreen`、`PYTHONUTF8=1`，运行 `python -m pytest -q --tb=short`，165 项通过。新 PyInstaller 包短时启动正常。现场 10 秒 HTDemucs GPU 四轨和贝斯原音量及 +12 dB 对照详见 [Windows 验收报告](WINDOWS_TEST_REPORT.md)。
- 后续复测普通窗口 Chroma 纵轴、较长片段的离线分轨接缝和有足够 RAM 时的持续近实时播放。

## 上一次交接

## 最新本机验收（2026-11-16）

- 目标源码 `b58c758d38d13e6bb58504b3f6e874994cf6e3c4`。Git 直连超时，本机使用 `f03dbf1` 和逐项核对 Git blob SHA 的 51 个变更文件重建测试目录。
- Windows Core 以 `PYTHONUTF8=1`、`QT_QPA_PLATFORM=offscreen` 运行 `python -m pytest -q --tb=short`，164 项通过。打包启动、44.1 kHz 导入与原速导出逐样本比对、半速导出、原速试听与三档外观各 60 秒捕获已验证。详见 [Windows 验收报告](WINDOWS_TEST_REPORT.md#第六轮-windows-首轮复测--b58c758--2026-11-16)。
- 已观察到和弦相对级数及一次自然切歌的一次重置日志。普通窗口 Chroma 热图纵轴仍重叠。下一轮先复查小窗口和 DPI，然后在可用 RAM 足够时复测真实离线与近实时分轨。继续检查录制时回放旧片段、累计溢出和 MIDI 路径隔离。

## 上一轮开发交接

- **结果**：本地音频导入使用固定输出采样网格，块边保留滤波所需的源样本，消除每块独立补零和独立向上取整。SoundFile 与 WAV 回退复用连续重采样路径，按顺序解码。WAV 回退成功时重写历史缓冲，避免保留主解码器已经写过的前段。[实现](../audio/ring_buffer.py)
- **证据**：基于 PR #13 合并提交 `6bd60e9a3cf7ae066332f80d2ee92a14e231014b`。分支 `fix/continuous-import-resampling`，代码证据 `9e827101883dc69541cf1cf061f07f694d1d9729`。两位 Worker 的建议和用量见 [协同报告](AI_COLLABORATION.md)。
- **专项验证**：Windows Core 中 `python -m pytest -q --tb=short tests/test_phase2_ring_buffer.py tests/test_audit4_regressions.py -k 'continuous or short_read'` 通过 13 项。另对 8–192 kHz 的 27 组输入逐样本比对，最大差值为 0。

## Windows 目标机复测

1. 按 [PACKAGING](PACKAGING.md) 将 Core 应用运行在目标机上，分别测光学效果关闭、小件和全部面板。每档用相同的音频源连续播放至少 60 秒，并切换频谱、和弦、混音和设置页面。记录 RAM、捕获溢出和实际听感。
2. 选择预设后修改字号和颜色，验证取消和重启恢复。用 100% 和常用缩放检查工具栏、紧急停止和 A/B 控件。
3. 近实时音频的目标机验收继续按 [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md) 进行。速度基准与运行统计按可播放步长计算 RTF（合并提交 `01dd09f`）。
4. 分别测试播放中 A/B 旧片段的原速回放、原速和慢速导出、离线分轨接缝。合成回放已验证其中一条重复帧路径，离线模型和声卡听感仍待记录。
5. 导入一段 44.1 kHz 音频，检查 A/B 跨整数秒边界的实际听感。当前仅完成合成文件与离屏测试。
