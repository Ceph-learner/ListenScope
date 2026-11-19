# ListenScope 当前状态

证据基线和检出分支记录在 [HANDOFF.md](HANDOFF.md)。功能清单见 [REQUIREMENTS](REQUIREMENTS.md)，长期约束见 [DECISIONS](DECISIONS.md)。

## 项目与已实现范围

ListenScope 是 Windows 本地音乐分析与练习工作台。入口 [main.py](../main.py) 和 [GUI](../ui/main_window.py) 连接以下模块：

- [进程音频捕获](../audio/process_loopback.py)
- [固定 PCM 环](../audio/ring_buffer.py)
- 实时 Chroma 页的「练习和弦」根据最近和弦排列本地大小调模板，支持手动选调、Capo 指型显示、旋律通道 `.mid` 导出（[`export_chord_progression_midi`](../analysis/chord_practice.py)）与本地 CPU 合成试听（[`render_chord_progression_preview`](../analysis/chord_practice.py)，复用 [`DrumPreviewPlayer`](../audio/drum_preview.py) 并与 A/B、混音、节拍器、鼓试听及系统环回/近实时互斥）。已通过自定义 `_PracticeTableDelegate` 消除 `#practiceTable` 第 0 行焦点框缩进并与表头对齐；同时为主音高增加轻量 90ms `QVariantAnimation` 准音刻度条（`TuningCentsBar`，全程零 `QGraphicsEffect`）并在复杂控件旁补充 `[?]` 悬浮/点击说明徽标（`HelpBadge`）。

- **全链路贝斯基频与转调提示**：[`analyze_bass_stem`](../analysis/stem_analyzer.py) 采用 `[28 Hz, 350 Hz]` FFT-YIN (CMNDF) + 2 倍谐波防跃变验证，精确测量低至 `B0`/`E1` 的音名、实音/移调 MIDI 编号、中心频率及时间戳，并对半程根音重心迁移给出疑似转调提示（联动混音摘要与 Chroma `key_relation_lbl` 警告色调）。

- **Cubase 兼容标准 MIDI 规范化**：和弦进行、鼓点与单轨 Basic Pitch 转录统一接入 [`analysis/midi_common.py`](../analysis/midi_common.py)，输出 SMF Type-0 (`480 TPB`)、Tick 0 英文轨名/拍号/BPM/等音映射 `key_signature`/Controller Reset (`CC 121=0`, `CC 64=0`, `pitchwheel=0`) 及 GM 音色号，并裁切重叠且确保 `note_off` 先于 `note_on`。

- A/B 历史波形支持横向缩放。停止 A/B 后可点击「贴近零点」，在每个已选边界的 ±5 ms 内查找更安静的实际播放边缘。

- 深度分轨的「鼓点」页支持导出独立鼓 MIDI，以及最多 8 秒合成试听。沿用检测的击打时间，可在 DAW 中选择鼓音源；映射见 [MIDI Association 打击乐说明](https://midi.org/general-midi-lite)。

- CPU 分析：频谱、Chroma、和弦与 BPM；高频标签、x 轴缓冲与性能表格通过缓存与签名去重降低内存波动与重绘开销。
- **外观、主题、字体、四语本地化与同级便携存储**：默认启用 **「酸性遥测 (`Acid Telemetry v2`, 预设 ID `acid_telemetry`, 默认 `theme_mode="light"` 临床浅色)」** 双模工业预设（[`ui/acid_style.py`](../ui/acid_style.py)、`ui/assets/acid_*.svg`、全新酸性几何图标 `ui/assets/listenscope.svg` / `listenscope.ico` 与 [`packaging/listenscope_core.spec`](../packaging/listenscope_core.spec) 打包绑定），含 `CLINICAL_LIGHT` 临床浅色（`#EEF2F6` / `#00A878`）与 `ACID & VOID` 暗夜（`#0B0D0F` / `#CEFF18` / `#2211FF`）顶栏快切持久化；在酸性遥测主题下**自动锁定字体家族、自定义三色、液态玻璃光学与自定义背景壁纸**（仅保留 `11–20 px` 字号、白天/黑夜/跟随系统模式、语言、无边框圆角与工作区布局可调），而在非酸性主题（`经典`/`Lenso`/`Codex`/`Claude Code`）下开放本机字体扫描实时预览、自定义颜色与**自定义背景图片上传（带可读性遮罩）**。支持 **中 (`zh`) / 英 (`en`) / 韩 (`ko`) / 日 (`ja`) 四语切换**（[`core/i18n.py`](../core/i18n.py)：内置英文遥测代号固定，仅替换中文文案，英文模式下仅显示英文且绝不重复显示两次）、默认**无边框圆角窗口（`frameless=True`，10px 圆角、顶栏拖拽移动与最小化/最大化/关闭按钮、启动自动适配屏幕分辨率并居中、切换选项锁定几何位置不跳动）**、单行紧凑不换行的最近和弦带（`Am[vi] → F[IV] → C[I] → G[V]`）、可调 `0–24 dB` 贝斯独听增益（默认 `+12 dB`，`>12 dB` 护耳警告，可选写入导出 WAV）、本机 PyTorch 自动扫描器（[`scan_local_pytorch_installations`](../core/system_probe.py)）与官方下载链接指引、设置页 GitHub 仓库/Star/Issues 反馈入口以及全界面 `[?]` 悬浮/点击说明徽标（[`HelpBadge`](../ui/help_badge.py)）。配置与导出（[`core/paths.py`](../core/paths.py)）优先保存在程序同级目录（不写 `C:\`），仅在只读目录回退用户目录。

GPU 分轨和 CPU MIDI 各用独立环境（Core 仍保持零 Torch/CUDA/TF，面向目标基线 Windows 11 · RTX 5060 Ti 8GB VRAM · 16GB RAM）。实验性近实时分轨位于 [streaming](../streaming)，默认关闭。软件版本 `0.2.4`（[pyproject.toml](../pyproject.toml)、[installer.iss](../scripts/installer.iss)）。

## 当前验证基线

- **PR #28 收口修复基线（分支 `fix/help-hover-startup-flash-and-bootstrap` · 代码证据 `fce0d80` · 尚未合并 `main`，未打新 Release 标签）**：
  - 针对 `v0.2.2` 首轮实机反馈修复三类问题：
    1. **严格仅 `[?]` 触发说明**：新增应用级 [`install_tooltip_guard`](../ui/help_badge.py)（`_TooltipOnlyOnHelpBadgeFilter`）在 `QEvent.Type.ToolTip` 拦截并抑制所有非 `HelpBadge` 控件原生弹窗，同步清理 [`ui/main_window.py`](../ui/main_window.py)、[`ui/settings_dialog.py`](../ui/settings_dialog.py)、[`ui/mixer_widget.py`](../ui/mixer_widget.py)、[`ui/resource_widget.py`](../ui/resource_widget.py)、[`ui/appearance.py`](../ui/appearance.py)、[`ui/chord_practice.py`](../ui/chord_practice.py)、[`ui/acid_style.py`](../ui/acid_style.py) 与 [`ui/chroma_widget.py`](../ui/chroma_widget.py) 冗余 `.setToolTip(...)`（保留 `chord_progression_lbl` 内部契约文本但运行时完全屏蔽弹出）；
    2. **消除启动与打开「设置」时小窗/图标闪烁及卡顿**：[`HelpBadge._sync_help_mode`](../ui/help_badge.py) 限制在拥有 `parentWidget()` 后才允许显示（监听 `ParentChange`），避免未入布局的 `22×22` 控件实例化为独立带应用图标的顶层窗口闪现；收敛 [`FocusRingAnimator`](../ui/help_badge.py) 预显示/重排/窗口激活触发，去除 [`SettingsDialog`](../ui/settings_dialog.py) 构造期重复图标渲染、`translate_widget_tree` 与预设焦点；将 [`main.py`](../main.py) 耗时宽范围本机 PyTorch 扫描改为后台线程 `ListenScope-StartupPyTorchScan` 异步发现并在 `_on_ui_tick` 回填；为 [`query_smtc_via_powershell`](../core/media_session.py) 与 [`subprocess_no_window_kwargs`](../core/paths.py)（含 `os.name == "nt"` 校验）统一消除 Windows 控制台闪烁；
    3. **Windows 一键配置脚本与日志可读性修复**：[`scripts/setup_windows.ps1`](../scripts/setup_windows.ps1) 新增 `$ErrorView = "NormalView"`、`$PSStyle.OutputRendering = "PlainText"`、UTF-8 控制台编码、多源 `Resolve-LauncherPython`（`py -0p` / 注册表 / `Programs\Python` / `pythoncore-*` / `Python\bin` / `uv` / Conda / 盘符根路径）与 `-AutoInstallPython`（缺少 Python `3.12`/`3.11` 时通过 `winget` 自动安装）；[`SettingsDialog`](../ui/settings_dialog.py) 新增「Python 3.12 官方下载」直链与默认开启的 `winget` 自动补装开关（同步补充 [`core/i18n_catalog.py`](../core/i18n_catalog.py) EN/KO/JA 翻译，保持 EN/KO 零中文泄漏），用 UTF-8 → CP936/GBK 解码并清洗 ANSI 转义与 `| ~~~` 诊断噪音，且支持只读安装目录回退 `~/.listenscope` 的自动发现；同步修复冻结版 Windows [`run_external_python`](../core/paths.py) 的 `capture_output`/`PYTHONHOME`/隔离传参，并在 [`scan_local_pytorch_installations`](../core/system_probe.py) 排除冻结版 `sys.executable`。
  - **云端 Linux 本地（Debian 12 · Python 3.11.2 · PySide6 6.9.3 · `QT_QPA_PLATFORM=offscreen` · `fce0d80`）**：`QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short` 共 **`200 passed, 6 skipped in 79.10s`**（6 项为 Windows 专属 PowerShell/WinRT 跳过）；无硬件 `main.py --simulate --headless-smoke`、`scripts/check_env.py --no-write` 与 `scripts/probe_media_session.py --self-test-mock --json` 通过。
  - **GitHub Ubuntu 24.04 PR CI（`tests.yml` Run `44539768467` · PR #28 @ `fce0d80`）**：**`206 passed in 77.98s`**（含 Ubuntu 预装 `pwsh` 下 PowerShell wheel 预检 6 项）。
  - **未验证**：Windows 11 + RTX 5060 Ti 真机实测（启动/设置零闪烁体感、仅 `[?]` 悬浮卡触发、`setup_windows.ps1 -AutoInstallPython` 补装 Python 3.12/3.11 与 `cu128` 分轨、WASAPI 捕获与 `.exe` 重打包）。

- **`v0.2.2` 发布验证基线（PR #27 `b89cf2e` + CI 收口 `8ef17c3`，基于 `main` `67b1b8b` · Tag `v0.2.2`）**：
  - 默认主题切换为 `preset="acid_telemetry", theme_mode="light"`（临床浅色），并在酸性主题下锁定字体家族/颜色/背景图（字号 `11–20 px` 可调），非酸性主题新增自定义背景壁纸上传；
  - 新增 [`core/i18n.py`](../core/i18n.py) 与 [`core/i18n_catalog.py`](../core/i18n_catalog.py) 中/英/韩/日四语引擎（英文模式零重复、EN/KO 四窗零残留中文）、无边框 10px 圆角窗口 + 启动屏幕居中 + 切换选项几何锁定、全新酸性几何图标 `listenscope.svg` / `listenscope.ico`；
  - 新增 [`scan_local_pytorch_installations`](../core/system_probe.py) 本机 PyTorch 扫描器与官方下载直链、设置页开源项目 Star / Issues 反馈卡片、自绘 `22×22` 悬浮 [`HelpBadge`](../ui/help_badge.py) + 全局「说明模式」与零 `QGraphicsEffect`「交互聚焦动画」开关、分轨行固定 96px 标签列对齐 `M`/`S` 按钮、最近和弦单行 `Name[Degree]`、`0–24 dB` 贝斯独听自定义分贝输入（`>12 dB` 护耳警告 + 导出可选应用）、以及设置页可选 **集显 + 独显异构协同加速（方案 A：核显 DirectML 接管轻量 2-Stem ONNX；方案 B：GUI 核显卸载 + AI 子进程锁定 `CUDA_VISIBLE_DEVICES=0` + Windows 图形设置直达）**；
  - **云端 Linux 本地（Debian 12 · Python 3.11.2 · PySide6 6.9.3 · offscreen）**：全量 **`192 passed, 6 skipped in 61.25s`**；已完成 `1360×860` 四语几何锁定与 `ResourceMonitorBar` 离屏截图目检。
  - **GitHub Actions 双端 CI（均运行于 `8ef17c3`）**：Ubuntu 24.04 `tests.yml`（Run `44525780384`）**`198 passed in 80.15s`**；`windows-latest` `release-windows.yml`（Run `44525789042`，Tag `v0.2.2`）**`198 passed in 104.57s`**，PyInstaller 打包与 8 项 UI 资产核验通过、重定位 `ListenScope.exe --simulate --headless-smoke` 返回 `ExitCode=0`，已正式发布 [GitHub Release `v0.2.2`](https://github.com/Ceph-learner/ListenScope/releases/tag/v0.2.2)（`ListenScope-Setup-Windows-x64.exe`、`ListenScope-Core-Windows-x64-Portable.zip`、`SHA256SUMS.txt`）。真机 Windows 11 音频/GPU/核显 DirectML/DAW/高 DPI 验收待目标机按 [HANDOFF](HANDOFF.md) 补测。
  - [README.md](../README.md) 重构为简洁自然的开源项目介绍，详细工程交接状态统一归档至本文档与 [HANDOFF.md](HANDOFF.md)。
- **PR #26 预发布验证基线（`fix/settings-dialog-compact-width` · `9bf7a43`，基于 PR #25 `f22ae12`）**：
  - 修复 [`TelemetryHeader`](../ui/acid_style.py) 与 [`SettingsDialog`](../ui/settings_dialog.py) 标题标签在 Windows 离屏等宽回退字体下撑宽至 `708px` 的问题，确保 `560×500` 紧凑窗口与 Acid Dark/Classic 切换正常。
  - **云端 Linux 本地（Debian 12 · Python 3.11.2 · PySide6 6.8.3 · offscreen）**：全量 **`189 passed, 6 skipped`**；已完成 `Acid Telemetry v2` 14 张及 `560×500` 等宽回退窄窗离屏截图目检，全仓库商标词正则扫描仅命中合法迁移别名与测试断言。
  - **GitHub Actions 双端 CI（均运行于 `9bf7a43`）**：Ubuntu 24.04 `tests.yml`（Run `44339863394`）**`195 passed`**；`windows-latest` `release-windows.yml`（Run `44339675131`）**`195 passed`**，PyInstaller 随包 `acid_*.svg` 资产校验通过、重定位 `ListenScope.exe --simulate --headless-smoke` 返回 `ExitCode=0`、`ListenScope-Core-Windows-x64-Portable.zip` 与 `ISCC.exe` 安装包 `ListenScope-Setup-Windows-x64.exe` 生成及 `SHA256SUMS.txt` 校验完成。真机 Windows 11 音频/GPU/DAW/高 DPI 验收待目标机按 [HANDOFF](HANDOFF.md) 补测。
- **PR #24 合入基线（历史档案）**：PR #24 完成第 5 档双模工业主题首次集成与隔离扁平控件重塑（`189 passed, 6 skipped`）。
- **PR #23 合并前云端基线（`2a9c335`，历史参照）**：`QT_QPA_PLATFORM=offscreen pytest -q --tb=short` 共 `188 passed, 6 skipped`。

- **四轨监听复测**：Windows 现场 10 秒 GPU 四轨完成。贝斯独听默认 +12 dB，可关闭，原始 WAV 和导出保持原音量。混音页禁用缺轨独听，复选框选中态更清楚。Windows pytest 165 项通过。见 [Windows 验收报告](WINDOWS_TEST_REPORT.md)。

- **目标机第六轮**：`b58c758` 源码快照通过 164 项 Windows pytest。打包、44.1 kHz 导入与 A/B 导出、三档外观捕获、自然切歌和相对和弦级数已复测。普通窗口 Chroma 热图纵轴仍重叠，AI 分轨受 RAM 门槛限制未复测。详见 [Windows 验收报告](WINDOWS_TEST_REPORT.md)。

- **目标机**：[Windows 验收](WINDOWS_TEST_REPORT.md) 第五轮对应 `f03dbf1`。
  - Windows pytest 115 项通过。
  - 打包、短段离线 MDX、直接打开 WAV 转 MIDI 已验证。
  - QQ Music 暂停、恢复、切歌时捕获基本正常。后续版本已在诊断日志加入自动重置计数，待目标机复核。
  - 目标机尚未复测后续的分轨接缝、近实时播放、和弦级数与历史目录 MIDI 输出修复。
- **云端 Linux（历史基线）**：2026-11-15 在 `6d9ade0` 上运行 `QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short`，115 passed。环境为 Debian 12、Python 3.11.2。仅安装 [requirements-core.txt](../requirements-core.txt) 和 pytest 的全新 venv 结果相同。
- 该报告与 [README](../README.md) 的历史说明写于不同时间，有出入时以对应 SHA 和证据为准。
- **GitHub**：2026-11-16，CUDA wheel 预检经 [PR #10](https://github.com/Ceph-learner/ListenScope/pull/10) 合入 `main`（`29be3d4`）。前两次 CI 在 checkout 失败，第三次 [CI](https://github.com/Ceph-learner/ListenScope/actions/runs/43799776097/attempts/3) 通过 139 项。`*-backup` 标签和 `backup/*` 分支是早期阶段的快照。

## 已知问题与下一步

1. **近实时**：在目标机上启动即触发内存保护，没有听到首段，真实延迟和长期是否累积未知。
   - `bb3e588` 已修复 [`pull_mixed_block`](../streaming/live_separator.py#L810-L836)。输出按未读顺序消费，欠载时在末尾补静音，溢出时保留缓冲容量内最新的帧。UI 的输出缓冲时长按剩余未读帧计算。
   - `ea85d23` 增加回包序号检查，跳号时清空旧交叠尾部。真实播放启动及欠载恢复时先预缓冲到最多两个步长，受原有容量限制。等待会增加首段和恢复延迟，模型长期跑不过实时仍会出现静音。
   - `f1bd25f` 按捕获实际模式拒绝系统环回下的近实时监听，包括进程捕获退回系统环回。停止或切换捕获时自动关闭监听，基础捕获及分析仍可用。
   - 实验页与诊断摘要分别提供输入跳段、输出重缓冲和声卡报告欠载的次数，以及输出缓冲溢出丢弃的帧数。已播放的帧与捕获源失效时的主动清空不计入输出溢出。超长批次按两条轨的共同帧位置取尾段，避免错位。
   - `c7d37b4` 在声卡回调中直接写输出缓冲，回绕时分段读取。非默认增益复用至多 32 KiB 的工作区。本机合成回调验证了帧序、补静音和临时分配改善，真实设备听感待复测。
   - 速度基准和运行 RTF 都按新增可播放音频时长计算，重叠部分不会重复计入。短基准沿用生产块长。旧报告的 RTF 数值采用旧口径，需在目标机重跑才能直接对照。
   - 推断（待目标机确认）：主循环在资源状态为 WARNING 时就会自动停止（[live_separator.py](../streaming/live_separator.py#L843-L850)），WARNING 包括可用内存低于 5120 MiB（[resource_manager.py](../core/resource_manager.py)）。这可能是 16 GB 机器上触发保护的原因。
   - 下一步按 [HANDOFF](HANDOFF.md) 复测实际输出和资源保护。
2. **单轨 MIDI 输出隔离**：`607d4aa` 修复了从历史分轨作业目录打开 WAV 时覆盖同名 MIDI 的问题。直接打开和混音器内转录均经 [`_on_transcribe_stem_midi`](../main.py#L1298) 写入 `work_dir/midi/`，每次生成独立中间文件。专项测试验证重复转换与手动另存，目标机独立 MIDI 环境待复测。
3. **和弦级数与 SMTC**：Chroma 页显示当前和弦相对检测调性的罗马数字级数，Capo 同时移调后级数不变。热图纵轴使用较小的音名标签。SMTC 每次实际自动重置写一条含累计次数的日志，可在诊断包中排查同一切歌是否重复触发。
4. 在线下载 Torch wheel 停滞的根因未定位。本地 wheel 路线可用，`804a2a7` 增加 `-CheckCudaWheels` 文件名预检及安装前验证。见 [PACKAGING](PACKAGING.md)。
5. **离线分轨接缝**：`35add3c` 将相邻推理窗口在同一源帧位置的预测淡入淡出，输出帧数和既有分块参数保持。合成信号验证帧序和短尾块，真实模型听感待目标机复测。
6. **A/B 历史缓冲**：原速回放按缓冲实际返回的帧位置推进。导出保留已完成 WAV，遇到尚未读取的源帧被覆盖或历史重置时，报错并清理临时文件。音高搜索边缘采用两侧真实谱值插值，BPM 识别计入从静音开始的有效瞬态。
7. **本地音频导入**：分块重采样共用从文件起点计算的输出相位，并保留滤波器所需的边界样本。主解码器和 WAV 回退均顺序读取；解码中途回退成功时重新写入历史缓冲。

## 测试

见 [DEVELOPMENT](DEVELOPMENT.md)。在 Core 环境下运行 `python -m pytest -q --tb=short`，窗口测试设置 `QT_QPA_PLATFORM=offscreen`。安装、打包和三个环境的约束见 [PACKAGING](PACKAGING.md)。真实 QQ Music、GPU 和近实时功能要在目标机上分别验证。
