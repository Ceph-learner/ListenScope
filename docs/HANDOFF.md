# 最新交接

## `v0.2.5` 发布交接：合并 PR #29、双端 CI 全绿、Windows 冻结包冒烟与 Release 发布（分支 `main` · 证据基线 `f3e6c2d45209e8f4c6e0f6ac8d0c01a84c11abf7` · Tag `v0.2.5`）

- **目标与结果**：完成实机反馈全部 19 项用户体验、一键安装、托盘缩放、日志与遥测动画升级并合并 [PR #29](https://github.com/Ceph-learner/ListenScope/pull/29)（`f3e6c2d`）；Ubuntu CI、Windows offscreen CI、PyInstaller 打包、冻结 `ListenScope.exe --simulate --headless-smoke`、便携 ZIP 与 Inno Setup 安装包均一次构建成功并发布 [GitHub Release `v0.2.5`](https://github.com/Ceph-learner/ListenScope/releases/tag/v0.2.5)。
- **关键改动文件**：
  - 安装持久化、取消与多源切换：[core/bootstrap_manager.py](../core/bootstrap_manager.py)、[scripts/mirror_wheel_fetch.py](../scripts/mirror_wheel_fetch.py)、[scripts/setup_windows.ps1](../scripts/setup_windows.ps1)、[ui/settings_dialog.py](../ui/settings_dialog.py)、[main.py](../main.py)
  - 外观字段（Schema 2 保持兼容）、质感/聚焦/动画控制与四语词典：[core/appearance.py](../core/appearance.py)、[ui/appearance.py](../ui/appearance.py)、[ui/acid_style.py](../ui/acid_style.py)、[ui/help_badge.py](../ui/help_badge.py)、[core/i18n.py](../core/i18n.py)、[core/i18n_catalog.py](../core/i18n_catalog.py)
  - 托盘/任务栏图标、8 边缩放、可关闭通知、跑马灯、隐藏 `[A]` 与微动画联动：[ui/main_window.py](../ui/main_window.py)、[ui/spectrum_widget.py](../ui/spectrum_widget.py)、[ui/chroma_widget.py](../ui/chroma_widget.py)、[ui/mixer_widget.py](../ui/mixer_widget.py)、[ui/resource_widget.py](../ui/resource_widget.py)
  - 磁盘滚动日志与版本配置：[core/logging.py](../core/logging.py)、[pyproject.toml](../pyproject.toml)、[scripts/installer.iss](../scripts/installer.iss)
  - 自动化回归测试：[tests/test_ux_polish_bootstrap_tray_marquee.py](../tests/test_ux_polish_bootstrap_tray_marquee.py)、[tests/test_startup_help_bootstrap_fixes.py](../tests/test_startup_help_bootstrap_fixes.py)
- **分支与远端状态**：当前位于 `main`（合并基线 `f3e6c2d`；特性分支 `feat/v0.2.5-ux-bootstrap-tray-marquee` 已在合并时删除；`v0.2.5` Tag 与 Release 已同步至 GitHub）；未触碰 `backup/*` 分支及 `*-backup` 标签。
- **已验证命令与实测结果**：
  - 本地 Linux offscreen：`QT_QPA_PLATFORM=offscreen pytest -q --tb=short` → **`205 passed, 6 skipped in 81.45s`**（零 warning）；`main.py --simulate --headless-smoke`、`scripts/check_env.py --no-write`、`scripts/probe_media_session.py --self-test-mock --json` 均通过（exit 0）。
  - GitHub Actions Ubuntu 24.04（`tests.yml` Run `44583969990` / `main` `f3e6c2d` Run `44584898370`）：**`211 passed in 75.69s`**（在解决 `SettingsDialog` EN/KO `简体中文 (ZH)` 残留及 Run `44581239077` `deleteLater()`/`processEvents()` C++ 析构段错误后全绿）。
  - GitHub Actions Windows（`release-windows.yml` Tag `v0.2.5` Run `44584919344`）：Windows offscreen pytest **`211 passed in 119.53s`**；PyInstaller Core 打包 + 迁移目录 `ListenScope.exe --simulate --headless-smoke` **ExitCode=0**；产出 `ListenScope-Setup-Windows-x64.exe`（`113,491,155` bytes）、`ListenScope-Core-Windows-x64-Portable.zip`（`154,236,032` bytes）与 `SHA256SUMS.txt`（`210` bytes）。
- **未在云端验证的项目（须 Windows 11 + RTX 5060 Ti 实机安装 `v0.2.5` 产物验收）**：
  - Win11 任务栏图标（`WM_SETICON`）、系统托盘图标、关闭窗口进托盘与托盘右键完全退出。
  - 无边框窗口（`>=940×620`）8 方向边缘拖拽调整大小与 DPI 居中。
  - Microsoft YaHei UI 下「和弦名与级数」字距、顶部无重叠、2-Stem/进程跑马灯观感与可关闭横幅交互。
  - 国内实网下点击设置「一键自动配置 AI + MIDI」测试切换设置页不断线、电池进度与速率、慢源自动切换、安装完一键重启生效与 `%LOCALAPPDATA%\ListenScope\logs\listenscope.log` 落盘。
  - 目标机 WASAPI 音频捕获、RTX 5060 Ti `cu128` GPU 分轨与音乐能量/高潮驱动遥测动画流畅度。
- **Windows 目标机可复制复测命令**：
  ```powershell
  # 若直接下载 v0.2.5 Setup / Portable 实机安装后验证：
  # 1. 启动 ListenScope，核对任务栏/托盘图标、8 边缩放、设置页一键配置与一键重启、外观质感/微动画强度设置
  # 2. 若需在源码目录复跑全量本地测试与镜像测速自检：
  python -m pytest -q --tb=short
  python scripts\mirror_wheel_fetch.py --self-test-pypi
  python main.py
  # 日志目录：%LOCALAPPDATA%\ListenScope\logs\listenscope.log（或在「设置 -> 系统诊断 / 主题与外观」点击「打开日志目录」）
  ```
- **下一步**：请你在 Windows 11 + RTX 5060 Ti 实机安装 `ListenScope-Setup-Windows-x64.exe`（或解压 `ListenScope-Core-Windows-x64-Portable.zip`）实测上述真机交互、网络切换源、任务栏/托盘图标与 WASAPI/GPU 分轨体验并反馈。

## 历史交接：`v0.2.4` 发布（PR #28 `d7f186f` + Windows 跨平台测试与版本收口 `4b9df05` · Tag `v0.2.4`）

- **目标与结果**：根据 `v0.2.2` 首轮实机反馈完成三项体验与初始化修复并合并 [PR #28](https://github.com/Ceph-learner/ListenScope/pull/28)（`d7f186f`）；`v0.2.3`（Tag 保留未发 Release）Windows 构建发现 [`test_run_external_python_capture_output_and_frozen_filtering`](../tests/test_startup_help_bootstrap_fixes.py) 未在 Windows 下 Mock `ctypes.WinDLL` + `subprocess.Popen`（触发 `WinError 193`，其余 205 项均通过），于 `4b9df05` 修复该测试 Mock 并顺延版本至 `0.2.4`，双端 CI 与 [GitHub Release `v0.2.4`](https://github.com/Ceph-learner/ListenScope/releases/tag/v0.2.4) 均一次通过。
  1. **严格仅在 `[?]` 问号徽标处悬浮弹出说明**：新增应用级事件过滤器 `_TooltipOnlyOnHelpBadgeFilter`（[`install_tooltip_guard`](../ui/help_badge.py)）统一拦截所有非 `HelpBadge` 控件的 `QEvent.Type.ToolTip`（调用 `QToolTip.hideText()` 并吞掉事件），清理 `ui/` 普通控件 `.setToolTip(...)`（仅 `help_badge.py` 与 `chroma_widget.py` 的 `chord_progression_lbl` 内部契约属性保留 `.setToolTip(`，且后者运行时弹窗已被过滤器阻断）。
  2. **根治启动与打开「设置」时的卡顿及图标小窗闪烁**：修复 [`HelpBadge._sync_help_mode`](../ui/help_badge.py) 在 `parentWidget() is None` 前即显示导致的 20+ 次 `22×22` 含应用图标顶层小窗闪现；收敛 [`FocusRingAnimator`](../ui/help_badge.py) 并移除 [`SettingsDialog`](../ui/settings_dialog.py) 构造期重复图标渲染、重复全树翻译（`_translate=False`）及 pre-show `setFocus()`；[`ListenScopeController`](../main.py) 启动改用 `_discover_ai_python_executable(allow_broad_scan=False)` + 后台守护线程 `ListenScope-StartupPyTorchScan` 异步发现并在 `_on_ui_tick()` 回填；[`query_smtc_via_powershell`](../core/media_session.py) 与 [`subprocess_no_window_kwargs`](../core/paths.py) 补充 `os.name == "nt"` 与无黑窗参数。
  3. **修复 Windows 一键配置「Python 3.15.2 拒检 + ANSI 乱码 + CP936 乱码」与只读目录/冻结版探测**：[`scripts/setup_windows.ps1`](../scripts/setup_windows.ps1) 新增 `$ErrorView = "NormalView"`、`$PSStyle.OutputRendering = "PlainText"`、UTF-8 编码、多源 `Resolve-LauncherPython` 与 `-AutoInstallPython`（自动通过 `winget` 安装 `Python.Python.3.12` / `Python.Python.3.11`）；[`SettingsDialog`](../ui/settings_dialog.py) 解码 UTF-8/CP936 并洗掉 ANSI/`| ~~~` 诊断噪音、增加「Python 3.12 官方下载」直链与默认开启的 `winget` 自动补装开关（同步补齐 [`core/i18n_catalog.py`](../core/i18n_catalog.py) 四语零泄漏）及只读目录 `~/.listenscope` 回退发现；修复冻结版 Windows [`run_external_python`](../core/paths.py) 并排除冻结版 `sys.executable`。
- **关键改动路径**：
  - 版本、CI 与测试：[`pyproject.toml`](../pyproject.toml)、[`scripts/installer.iss`](../scripts/installer.iss)、[`ui/acid_style.py`](../ui/acid_style.py)、[`.github/workflows/release-windows.yml`](../.github/workflows/release-windows.yml)、[`tests/test_startup_help_bootstrap_fixes.py`](../tests/test_startup_help_bootstrap_fixes.py)。
  - 核心、脚本与 UI：[`core/paths.py`](../core/paths.py)、[`core/system_probe.py`](../core/system_probe.py)、[`core/media_session.py`](../core/media_session.py)、[`core/i18n_catalog.py`](../core/i18n_catalog.py)、[`main.py`](../main.py)、[`scripts/setup_windows.ps1`](../scripts/setup_windows.ps1)、[`ui/help_badge.py`](../ui/help_badge.py)、[`ui/settings_dialog.py`](../ui/settings_dialog.py)、[`ui/main_window.py`](../ui/main_window.py)、[`ui/mixer_widget.py`](../ui/mixer_widget.py)、[`ui/resource_widget.py`](../ui/resource_widget.py)、[`ui/appearance.py`](../ui/appearance.py)、[`ui/chord_practice.py`](../ui/chord_practice.py)、[`ui/chroma_widget.py`](../ui/chroma_widget.py)。
- **已观测验证记录（代码证据基线 `4b9df055cdc07b7079dd81b9f50a6a80d6fc6eb7` · `main`）**：
  - **云端 Linux 本地（Debian 12 · Python 3.11.2 · PySide6 6.9.3 · `QT_QPA_PLATFORM=offscreen`）**：`QT_QPA_PLATFORM=offscreen /home/antigravity/.venv_test/bin/python -m pytest -q --tb=short` 共 **`200 passed, 6 skipped in 80.38s`**（6 项为 Windows 专属 PowerShell/WinRT 跳过）；无硬件 `main.py --simulate --headless-smoke`、`scripts/check_env.py --no-write` 与 `scripts/probe_media_session.py --self-test-mock --json` 于 `fce0d80` 通过。
  - **GitHub Ubuntu 24.04 CI（`tests.yml` Run `44543687832` · `main` @ `4b9df05`）**：**`206 passed in 100.27s`**。
  - **GitHub `windows-latest` Release 构建（`release-windows.yml` Run `44543693468` · Tag `v0.2.4` @ `4b9df05`）**：Windows x64 offscreen `pytest` **`206 passed in 78.62s`**；PyInstaller `ListenScope.exe` 与 8 项 UI SVG/ICO 资产校验通过；重定位 `ListenScope.exe --simulate --headless-smoke` **`ExitCode=0`**；已发布 [GitHub Release `v0.2.4`](https://github.com/Ceph-learner/ListenScope/releases/tag/v0.2.4)：
    - `ListenScope-Setup-Windows-x64.exe`（`113,336,079` bytes, `sha256:8822e5f426240a62269d33b048a236e52e7d7bd2a620460b2959bf377bc6c757`）
    - `ListenScope-Core-Windows-x64-Portable.zip`（`154,072,747` bytes, `sha256:90f42a88db87b7da7e45a0cbca8176eccaed1dcdf1269b04920e56c80bad3259`）
    - `SHA256SUMS.txt`（`210` bytes）
- **历史失败记录（不改写历史）**：`v0.2.3`（Tag 指向 PR #28 合并提交 `d7f186f`，未生成 Release）`release-windows` Run `44542449438` 因 `test_run_external_python_capture_output_and_frozen_filtering` 未在 Windows 下 Mock `Popen` 返回 `205 passed, 1 failed`，已在 `4b9df05` 解决并发布 `v0.2.4`。
- **远端状态**：`main` 与 `origin/main` 同步（随后将推送本交接文档更新），Tag `v0.2.4` 已指向 `4b9df05` 并关联已发布的 GitHub Release；PR #28 已合入关闭。
- **未完成 / Windows 11 目标机复测清单（RTX 5060 Ti 8GB VRAM · 16GB RAM）**：
  1. 下载并试跑 `v0.2.4` 安装包或便携 ZIP，确认打开应用及点「CONFIG // 设置」时无小图标闪烁与明显卡顿；
  2. 将鼠标悬停普通按钮、下拉框、A/B 波形图与 `[?]` 徽标，确认仅 `[?]` 弹出说明浮卡；
  3. 验证「一键自动配置 AI + MIDI」（含 `-AutoInstallPython` 自动补装 Python `3.12`/`3.11` 与无乱码日志，或本地 wheel/手配 Python `3.12` + `cu128` + `requirements-ai.txt`），并实测真实音乐 WASAPI 捕获、声卡试听、RTX 5060 Ti AI 分轨、Basic Pitch MIDI、SMTC 切歌重置及结果写入 [WINDOWS_TEST_REPORT.md](WINDOWS_TEST_REPORT.md)。

---

## 历史基线：`v0.2.2` 回家实测打磨、四语本地化、悬浮帮助模式、双 GPU 卸载与 Windows Release 发布（PR #27 `b89cf2e` · 证据基线 `8ef17c3bb10b1989204b753e9db1cbf234a24637` · Tag `v0.2.2`）

- **状态**：已合入 `main`（`c0461a0` 交接）并发布 [GitHub Release `v0.2.2`](https://github.com/Ceph-learner/ListenScope/releases/tag/v0.2.2)；真实 Windows 11 音频/GPU/核显 DirectML/DAW/高 DPI 验收待随 PR #28 合并后一并按上述清单一并补测并记入 [WINDOWS_TEST_REPORT.md](WINDOWS_TEST_REPORT.md)。

---

## 历史交接：`v0.2.1` Acid Telemetry v2 与 Windows 窄宽修复（PR #25 `f22ae12` · PR #26 `67b1b8b`）

- **状态**：已合入 `main` 并发布 `v0.2.1`（Run `44341616003`），后续已在上述 `v0.2.2` 中完成真机反馈迭代。

---

## 历史记录（PR #24 基线：第 5 档双模主题首次集成与隔离扁平控件）

- **状态**：已合入 `main`，并在上述 `v0.2.1` 迭代中完整升级为 `Acid Telemetry v2`（`ui/acid_style.py` + `acid_*.svg`）及完成商标名词清理。

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
