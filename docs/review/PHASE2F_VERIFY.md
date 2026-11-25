# Phase 2F Verification Report (Issue #60 — retest2 回归修复)

- **Branch**: `fix/p2f-retest2` (cut from `main` @ `59c26de`)
- **Author**: Hydrogen
- **Verification Environment**: Linux / Qt `offscreen`（含 `QT_SCALE_FACTOR=1.25` + `874×453` 逻辑尺寸 / `1093×566` 物理尺寸）；Windows 实机音频、GPU 与打包 exe 需在目标机复测。
- **Test Suite**: [`tests/test_review_phase2f.py`](../../tests/test_review_phase2f.py)（12 项均先以 `xfail(strict=True)` 复现后再修复转正）
- **Screenshots (`scripts/make_screenshots.py --p2f`)**:
  - `docs/review/screens/p2f_after_narrow_125_spectrum_1093x566.png`
  - `docs/review/screens/p2f_after_narrow_125_mixer_1093x566.png`
  - `docs/review/screens/p2f_after_light_en_chord_1366x768.png`

---

## F1–F12 逐项修复与验证清单

| ID | 修改内容与文件 | 复现/回归测试名 (`tests/test_review_phase2f.py`) | Linux/offscreen 验证结果 |
|---|---|---|---|
| **F1** | [`ui/main_window.py`](../../ui/main_window.py) `_apply_responsive_layout`、`core/i18n.py`：<br>- 窄窗口（`<1020px`）顶栏将刷新/捕获/冻结/设置切换为纯图标+tooltip，主题切换合并为单个图标按钮 `_theme_icon_btn`；<br>- `emergency_stop_btn` 窄窗口保留四语短标签 `btn_estop_short`（急停 / E-Stop / 緊急停止 / 긴급 정지）；<br>- 移除 `recent_60_btn` 的隐藏逻辑，保持 `10s / 30s / 60s` 均可见。 | `test_f1_narrow_topbar_no_clipping_and_60s_visible` | **PASSED**（`874×453` 逻辑尺寸与 `QT_SCALE_FACTOR=1.25` 子进程双覆盖） |
| **F2** | [`ui/resource_widget.py`](../../ui/resource_widget.py) `ResourceMonitorBar.update_snapshot`、[`core/i18n.py`](../../core/i18n.py)：<br>- 移除 `not self._compact_mode` 分支差异，宽/窄模式共用 `low_ram_idle` 状态映射（`tone="warn"`），紧凑模式仅缩短文字为「低内存 / Low RAM / RAM少 / 메모리 부족」；<br>- 布局加 `SetFixedSize` 约束防止标签裁切。 | `test_f2_resource_capsule_status_consistent_wide_and_compact` | **PASSED** |
| **F3** | [`ui/acid_style.py`](../../ui/acid_style.py) `ACID_PALETTES["light"]`：<br>- 将浅色 `status_warn_*` 从蓝色（`#E0F2FE`/`#0369A1`/`#0284C7`）改为高对比度琥珀色（`#FEF3C7` / `#92400E` / `#D97706`，对比度 ~7.3:1 ≥ 4.5:1）。 | `test_f3_light_theme_warn_color_is_amber_not_blue` | **PASSED** |
| **F4** | [`ui/main_window.py`](../../ui/main_window.py) `update_capture_stats`、[`core/i18n.py`](../../core/i18n.py)：<br>- 宽屏保证 `setMinimumWidth(sizeHint().width())` 不截断并附全文 tooltip；<br>- 窄屏（`<1100px`）显示短状态（如 `[Warn] Silent`）+ 完整 RMS tooltip。 | `test_f4_capture_status_capsule_not_clipped_in_en_1600` | **PASSED** |
| **F5** | [`ui/mixer_widget.py`](../../ui/mixer_widget.py)、[`core/i18n.py`](../../core/i18n.py)：<br>- 空状态引导语与主按钮统一为「选最近 30 s 并 2-Stem 分轨」（四语一致）；<br>- 英文按钮 `Select Last 30s && 2-Stem`、`Import && 2-Stem/4-Stem Split` 转义 `&` 为 `&&`；<br>- 降低子标签页最小高度并增加紧凑 `resizeEvent`，确保 `874×453` 下主按钮不滚动即可见。 | `test_f5_mixer_empty_state_consistency_ampersand_and_narrow_visible` | **PASSED** |
| **F6** | [`core/i18n.py`](../../core/i18n.py)、[`core/i18n_catalog.py`](../../core/i18n_catalog.py)、[`ui/spectrum_widget.py`](../../ui/spectrum_widget.py)、[`ui/main_window.py`](../../ui/main_window.py)：<br>- 补齐设置保存提示、调性卡「有效音频帧不足」、E-STOP 横幅、时频图占位 `TextItem`、急停/紧缺 RAM 原因、SMTC 提示、BPM `÷2/×2` 与 `| Alt:`、`CHORD_PRACTICE`、`RESET // TRACK` 四语翻译；`show_banner_message` 统一走 `translate_text`。 | `test_f6_no_chinese_leak_in_en_ja_ko` | **PASSED**（全 5 页 `en`/`ko` 可见 `QLabel`/`QPushButton` 文本与 tooltip 0 汉字残留） |
| **F7** | [`ui/spectrum_widget.py`](../../ui/spectrum_widget.py) `SpectrumWidget`：<br>- 新增 `_has_spec_data` 标记，仅在无历史数据时显示占位；`apply_theme` 与 `spectrogram=None` 的帧跳过不再重新显示「开始捕获后显示」。 | `test_f7_spectrogram_preserved_after_apply_appearance` | **PASSED** |
| **F8** | [`ui/chroma_widget.py`](../../ui/chroma_widget.py)：<br>- `chroma_hist_plot` 最小高度提升至 `96px`，默认分割比例 `[180, 270]`，`refresh_chroma_note_ticks` 支持 `1/2/3` 自适应刻度步长（`1366×768` 与 `874×453` 均不重叠）。 | `test_f8_chroma_heatmap_readable_height_and_ticks` | **PASSED** |
| **F9** | [`main.py`](../../main.py) `ListenScopeController.shutdown` & `_exit_watchdog`：<br>- 为各关闭阶段（`previews`/`capture`/`playback`/`analysis_worker`/`live_separator`/`ai_job_manager`/`subprocesses`/`resource_manager`）增加有界超时封装与逐阶段耗时日志；`_exit_watchdog` 超时降至 `2.0s`；子进程 `terminate → kill` 超时收紧至 `0.25s`。 | `test_f9_quit_completes_within_2s_with_blocking_thread_and_subprocess` | **PASSED**（阻塞捕获下 `shutdown()` ≤ 2.0s） |
| **F10** | [`analysis/tempo.py`](../../analysis/tempo.py) `TempoEstimator.estimate`：<br>- 将 `peakiness < 2.5` 提前拒判放宽至 `peakiness < 1.2`（配合 `std(env) < 1e-3` 拦截纯和弦静态垫音），避免持续混音因和声/贝斯连续能量导致自相关峰被误置为 `0.00`。 | `test_f10_bpm_detected_within_15s_on_synthetic_mix` | **PASSED**；`tests/bench/realistic_mix`：`acc1=86.67%`、`acc2=100.0%`、`neg_controls_none_pct=100.0%`（0 退化） |
| **F11** | [`core/resource_manager.py`](../../core/resource_manager.py)、[`main.py`](../../main.py)、[`ui/main_window.py`](../../ui/main_window.py)、[`core/i18n_catalog.py`](../../core/i18n_catalog.py)：<br>- 拒绝与急停文案均补充可操作建议（关闭浏览器等占用内存/显存的程序后重试，四语）；<br>- 横幅明确区分「用户手动紧急停止 AI」与「内存护栏自动紧急停止 AI」。 | `test_f11_memory_guardrail_messages_actionable_and_distinguish_manual_vs_auto` | **PASSED**（内存阈值 `5120/3072/2048 MiB` 未改动） |
| **F12** | [`ui/main_window.py`](../../ui/main_window.py) `_load_tray_icon` & `apply_appearance`：<br>- 确认 `ui/assets/listenscope_tray_*.svg` 与 `docs/design/icon/listenscope_tray_*.svg` 100% 一致（3 根竖条）；`apply_appearance` 切换系统明暗时同步刷新 `_tray_icon`。 | `test_f12_tray_icon_uses_3_bar_svg_and_follows_system_theme` | **PASSED** |

---

## Windows 目标机待复测项
1. **125% 缩放窄窗口（1093×566 物理）**：确认顶栏无半截字、E-STOP 保留短标签、混音空状态主按钮无需滚动即可点击。
2. **托盘图标与退出耗时**：确认托盘溢出区显示 3 竖条单色图标并随系统明暗切换；点击 `Quit ListenScope` 后 2 s 内主进程与子进程全部退出，日志可见各阶段 `shutdown stage=... elapsed_ms=...`。另在启动一次 2-Stem 分轨、AI 子进程运行中用 `taskkill /F /PID <主进程>` 强制结束主进程，5 秒内 AI/MIDI 子进程也应全部退出。
3. **真实音频持续播放 BPM**：确认 15 s 内稳定出 BPM（不再等到 100+ s）。
9. **重启与外部程序脱离 Job（Round 4 / Round 5）**：分别在 **Cursor 终端里启动** 和 **双击 `.bat` / 资源管理器里启动** 两种方式下，各在设置里点一次「立即重启 ListenScope 生效」，确认新窗口均能正常起来并保持运行；另在打开导出文件夹后关闭 ListenScope，资源管理器窗口不能被一起关掉。

---

## Round 2（PR #61 复审回归 + 补充复审 A–E）

| 项 | 修改内容与文件 | 测试名 | Linux/offscreen 验证结果 |
|---|---|---|---|
| **Neon #1** | [`ui/main_window.py`](../../ui/main_window.py) `handle_ai_result`：改用 `res.error`（而非不存在的 `res.error_message`）。 | `tests/test_review_phase2d.py::test_w10_handle_ai_result_handles_every_ai_job_state_and_notifies_mixer` | **PASSED** |
| **Neon #2** | [`ui/main_window.py`](../../ui/main_window.py) `show_banner_message`：直接将 `raw_text` 传入 `_set_label_cached`，避免覆盖 `_ls_orig_text` 破坏 `zh → en → zh` 往返。 | `tests/test_review_phase1.py::test_ub06_banner_label_roundtrip_zh_en_zh_preserves_original_text` | **PASSED** |
| **A (F9 子进程与 Job Object)** | 1. [`core/paths.py`](../../core/paths.py)：Windows 下创建 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` Job Object，在 `register_active_subprocess` 中绑定子进程；新增 `kill_all_active_subprocesses()`。<br>2. [`main.py`](../../main.py)：`_exit_watchdog` 触发 `os._exit(0)` 前先调用 `kill_all_active_subprocesses()`；`shutdown()` 改为统一 `1.6s` 截止时间并保证 `subprocesses` 阶段执行（`min_timeout_s=0.25`）。 | `tests/test_review_phase2f.py::test_f9_quit_completes_within_2s_with_blocking_thread_and_subprocess`（含真实忽略 `SIGTERM` 的子进程） | **PASSED**（`543.7 ms` 内结束并杀掉子进程） |
| **B (F1 动态顶栏阈值)** | [`ui/main_window.py`](../../ui/main_window.py)：移除硬编码 `1020px`，按当前语言顶栏按钮 `sizeHint` 总和动态计算 `wide_req`；`source_combo` 最小宽度按约 12 字符（`>=116px`）锁定；同步修复 [`core/i18n.py`](../../core/i18n.py) `Waveform && FFT` / `Bands && Spectrogram` 及 [`ui/spectrum_widget.py`](../../ui/spectrum_widget.py) `_refresh_axis_ticks` 轴标题翻译。 | `tests/test_review_phase2f.py::test_f1_narrow_topbar_no_clipping_and_60s_visible`（874–1366 每 64px 步进 × 四语） | **PASSED** |
| **C (F11 结构化急停来源)** | [`core/models.py`](../../core/models.py) `AIJobResult` 新增 `stop_reason: Optional[Literal["user", "ram_guard", "vram_guard"]] = None`；[`ai/job_manager.py`](../../ai/job_manager.py) 写入对应来源；`handle_ai_result` 据此区分横幅，不再做中文字符串匹配。 | `tests/test_review_phase2f.py::test_f11_memory_guardrail_messages_actionable_and_distinguish_manual_vs_auto` | **PASSED** |
| **D (F6 `ja` 遍历)** | [`tests/test_review_phase2f.py`](../../tests/test_review_phase2f.py) `test_f6_no_chinese_leak_in_en_ja_ko` 补齐 `ja` 全 5 页可见控件与 tooltip 扫描。 | `tests/test_review_phase2f.py::test_f6_no_chinese_leak_in_en_ja_ko` | **PASSED** |
| **E (F10 负样本与量纲)** | [`analysis/tempo.py`](../../analysis/tempo.py) 将 `peakiness` 阈值调整为 `1.8`（拦截 5.2 Hz 颤音长音 `peakiness=1.66`）。<br>**`std(env) < 1e-3` 量纲说明**：`env` 为 96 个对数频带线性幅度谱通量 `mag_like = 10^(dBFS/20)` 的正向差分之和；静态和弦垫音 `pure_chord_pad` 在 `-10 dBFS` 下因杂散拍频仅产生 `std(env) ≈ 2.1e-4`（`< 1e-3`），而正常音乐在 96 频带下 `std(env)` 通常 `>= 5e-3 ~ 1e-1`（相当于总通量波动 `> -60 dBFS`）。 | `tests/test_review_phase2f.py::test_f10_negative_controls_chord_pad_noise_vibrato`（纯和弦垫音、白噪声、颤音长音 3 组负样本） | **PASSED** |

### Round 2 新增截图（`QT_SCALE_FACTOR=1.25`）
- `docs/review/screens/p2f_after_125_en_spectrum_1366x768.png`（1.25× 缩放 1366×768 物理 / 1093×614 逻辑英文实时频谱页）
- `docs/review/screens/p2f_after_narrow_125_spectrum_1093x566.png`
- `docs/review/screens/p2f_after_narrow_125_mixer_1093x566.png`
- `docs/review/screens/p2f_after_light_en_chord_1366x768.png`

### Round 2 退出耗时实测日志（含阻塞捕获 + 真实忽略 `SIGTERM` 子进程）
```text
INFO     listenscope.shutdown:main.py:2283 shutdown stage=previews elapsed_ms=0.7
WARNING  listenscope.shutdown:main.py:2279 shutdown stage=capture timed out after 353.2 ms
INFO     listenscope.shutdown:main.py:2283 shutdown stage=playback elapsed_ms=2.4
INFO     listenscope.shutdown:main.py:2283 shutdown stage=analysis_worker elapsed_ms=0.4
INFO     listenscope.shutdown:main.py:2283 shutdown stage=ai_job_manager elapsed_ms=0.2
INFO     listenscope.shutdown:main.py:2283 shutdown stage=subprocesses elapsed_ms=182.0
INFO     listenscope.shutdown:main.py:2283 shutdown stage=resource_manager elapsed_ms=0.2
INFO     listenscope.shutdown:main.py:2320 shutdown total elapsed_ms=543.7
```

---

## Round 3（`wide_req` 实际布局计算 + Job Object 健壮性）

| 项 | 修改内容与文件 | 测试名 | Linux/offscreen 验证结果 |
|---|---|---|---|
| **1. `wide_req` 实际布局计算** | [`ui/main_window.py`](../../ui/main_window.py)：保存 `self._topbar_cmd_row`，`_apply_responsive_layout` 按顶栏外/内边距 + `spacing × (可见控件数 − 1)` + 所有可见固定控件与宽按钮 `sizeHint` 之和 + `8px` 余量计算 `wide_req`（不再硬编码 `48`/`160`）。 | `tests/test_review_phase2c.py::test_ub03_main_window_fits_small_screens_1093x566_and_1024x528`<br>`tests/test_review_phase2f.py::test_f1_narrow_topbar_no_clipping_and_60s_visible`<br>`tests/test_review_phase2f.py::test_f1_ub03_scaled_125_zh_en` | **PASSED**（含 `1.25x` 下 `zh`/`en` × `1093×566` / `1024×528`；`p2f_after_light_en_chord_1366x768.png` 确认 `VRAM 7.0/8.0G` 不被挤压） |
| **2. Windows Job Object 健壮性** | [`core/paths.py`](../../core/paths.py) & [`main.py`](../../main.py)：<br>- 为 `CreateJobObjectW`、`SetInformationJobObject`、`AssignProcessToJobObject`、`GetCurrentProcess`、`CloseHandle` 显式声明 `argtypes` / `restype`（`wintypes.HANDLE` 等）；<br>- 新增 `ensure_current_process_in_kill_job()` 并在 `main()` 启动时将主进程加入 Job（后代自动继承），保留 per-process 绑定作为兜底；<br>- 所有失败路径记录 `warning` 日志（不静默吞掉）。 | 代码路径走查（Windows Job Object API 需目标机 `taskkill /F /PID` 实测） | **Linux/offscreen 回归全绿；待 Windows 实测** |

---

## Round 4（`JOB_OBJECT_LIMIT_BREAKAWAY_OK` + `launch_detached()` + 全仓启动点排查）

### 修改内容与测试
| 项 | 修改内容与文件 | 测试名 | Linux/offscreen 验证结果 |
|---|---|---|---|
| **1. Job 允许子进程脱离** | [`core/paths.py`](../../core/paths.py) `_ensure_windows_kill_job()`：`LimitFlags` 由 `0x2000` 改为 `0x2000 \| 0x0800`（`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE \| JOB_OBJECT_LIMIT_BREAKAWAY_OK`）。 | `tests/test_review_phase2f.py::test_round4_launch_detached_not_in_active_subprocs_and_job_breakaway` | **PASSED**（源码及常量核对；Windows 实机行为待目标机验证） |
| **2. 封装 `launch_detached(...)`** | [`core/paths.py`](../../core/paths.py) 新增 `launch_detached(cmd, **kwargs)`：Windows 下 `creationflags` 含 `CREATE_BREAKAWAY_FROM_JOB (0x01000000)` + `CREATE_NEW_PROCESS_GROUP (0x00000200)`（未传 `CREATE_NO_WINDOW` 时并入 `DETACHED_PROCESS (0x00000008)`），非 Windows 设置 `start_new_session=True`，且**不调用** `register_active_subprocess()`。 | `tests/test_review_phase2f.py::test_round4_launch_detached_win32_flags_and_not_registered`（mock `win32` 校验 `creationflags` 与 `_ACTIVE_SUBPROCS`）<br>`tests/test_review_phase2f.py::test_round4_launch_detached_not_in_active_subprocs_and_job_breakaway`（真实子进程不进入 `_ACTIVE_SUBPROCS`） | **PASSED** |
| **3. 迁移非 AI/MIDI/探针启动点** | [`main.py`](../../main.py) `restart_application`、[`ui/settings_dialog.py`](../../ui/settings_dialog.py) `_start_bootstrap`、[`core/bootstrap_manager.py`](../../core/bootstrap_manager.py) `BootstrapCoordinator.start` 默认工厂均改用 `launch_detached`。 | 同上 | **PASSED** |

### 全仓启动点排查清单（`Popen` / `os.startfile` / `QProcess.startDetached` / `openUrl` / `subprocess.run`）

| 位置 | 用途 | 类别 | 处理方式 |
|---|---|---|---|
| `main.py:1957` (`restart_application`) | 「立即重启 ListenScope 生效」拉起新实例 | 重启新实例 | **已改用 `launch_detached()`**（脱离 Job，不注册 `_ACTIVE_SUBPROCS`） |
| `ui/settings_dialog.py:1344` (`_start_bootstrap`) | 一键环境配置运行 PowerShell `setup_windows.ps1` | 外部配置脚本 | **已改用 `launch_detached()`**（脱离 Job，支持 `CREATE_NO_WINDOW`，不注册 `_ACTIVE_SUBPROCS`） |
| `core/bootstrap_manager.py:186` (`BootstrapCoordinator.start`) | 一键环境配置默认进程工厂 | 外部配置脚本 | **已改用 `launch_detached` 作为默认工厂** |
| `core/paths.py:330` (`run_external_python`) | 外部 AI/MIDI 环境探针（同步） | AI/MIDI/探针 | **保持不变**（保留在 Job 内并注册 `_ACTIVE_SUBPROCS`） |
| `core/paths.py:378, 424` (`popen_external_python`) | AI 分离 Worker（`ai/job_manager.py`、`streaming/live_separator.py`）及 MIDI 探针 | AI/MIDI/探针 | **保持不变**（保留在 Job 内并注册 `_ACTIVE_SUBPROCS`） |
| `core/version.py:59` / `core/system_probe.py:30` / `core/media_session.py:632` / `core/bootstrap_manager.py:333` | `git`、`nvidia-smi`、SMTC PowerShell、`taskkill` 等短生命周期同步 `subprocess.run` | 探针/取消辅助 | **保持不变**（同步短命令，留在 Job 内） |
| `ui/resource_widget.py:289` / `ui/settings_dialog.py:111,115,714` | `QtGui.QDesktopServices.openUrl`（打开日志/导出目录、网页与系统设置） | 系统 Shell / DCOM | **保持不变**（经 Windows Shell/Explorer 进程间调用打开，非 `Popen` 子进程） |
| 全仓 `os.startfile` / `QProcess.startDetached` | 全仓搜索 | — | **无调用** |

---

## Round 5（`launch_detached` winerror=5 兜底 + 先起新进程再退出 + 已知边界）

| 项 | 修改内容与文件 | 测试名 | Linux/offscreen 验证结果 |
|---|---|---|---|
| **1. `launch_detached` `winerror=5` 回退重试** | [`core/paths.py`](../../core/paths.py) `launch_detached()`：Windows 下带 `CREATE_BREAKAWAY_FROM_JOB` 调用 `Popen` 若抛出 `OSError` 且 `winerror == 5`（典型场景：被套在不允许 breakaway 的外层 IDE/终端 Job 内），记录 `warning` 日志说明原因及子进程将留在父 Job 内，随后去掉 `CREATE_BREAKAWAY_FROM_JOB` 重试一次。 | `tests/test_review_phase2f.py::test_round5_launch_detached_retries_without_breakaway_on_winerror_5` | **PASSED** |
| **2. `restart_application` 先启动新进程再 `shutdown()`** | [`main.py`](../../main.py) `restart_application()`：改为先执行 `launch_detached(cmd, cwd=restart_cwd)`，成功后再执行 `self.shutdown()` 与退出；若新进程启动失败则保留旧窗口、不调用 `shutdown()`，并弹出横幅「重启失败，请手动重新打开」（已在 [`core/i18n.py`](../../core/i18n.py) 补齐 `zh/en/ko/ja` 四语）。 | `tests/test_review_phase2f.py::test_round5_restart_application_keeps_window_and_skips_shutdown_on_failure` | **PASSED** |

### 已知边界（本轮不改）
- 如果在一键配置（`BootstrapCoordinator`）运行过程中退出 ListenScope，配置脚本的 `stdout` 管道会断开，可能导致安装中断；下次打开时重新运行一键配置即可恢复。

---

## Round 6（`relax_kill_on_close_for_restart()` + `allow_job_relax` 仅用于重启）

| 项 | 修改内容与文件 | 测试名 | Linux/offscreen 验证结果 |
|---|---|---|---|
| **1. `relax_kill_on_close_for_restart()`** | [`core/paths.py`](../../core/paths.py)：对当前 `_win_job_handle` 调用 `SetInformationJobObject`，将 `LimitFlags` 改为仅保留 `JOB_OBJECT_LIMIT_BREAKAWAY_OK (0x0800)`（移除 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE (0x2000)`），避免回退到不带 breakaway 启动的新实例在旧进程退出关闭 Job 句柄时被一起杀掉；失败时记录 `warning` 日志并返回 `False`。 | `tests/test_review_phase2f.py::test_round6_relax_kill_on_close_for_restart_sets_breakaway_only_and_logs_on_failure` | **PASSED** |
| **2. `launch_detached(..., allow_job_relax=False)`** | [`core/paths.py`](../../core/paths.py) & [`main.py`](../../main.py)：`launch_detached` 新增 `allow_job_relax: bool = False`，在 `winerror == 5` 回退分支里仅当 `allow_job_relax=True` 时先调用 `relax_kill_on_close_for_restart()` 再重试；全仓仅 `restart_application()` 传入 `allow_job_relax=True`。 | `tests/test_review_phase2f.py::test_round6_launch_detached_relaxes_job_only_when_allow_job_relax_true` | **PASSED** |

### 说明与已知边界
- **不留残留子进程**：即使重启回退时放宽了 `KILL_ON_JOB_CLOSE`，旧进程的 `shutdown()` 仍会显式调用 `terminate_all_active_subprocesses()`（并在看门狗兜底中调用 `kill_all_active_subprocesses()`）终止所有已注册的 AI/MIDI/探针子进程，因此不会留下孤儿进程。
- **一键配置 PowerShell 保持 `allow_job_relax=False`**：在回退分支中不会放宽 Job，退出 ListenScope 时配置脚本会随 Job 结束（与 `stdout` 管道断开的已知边界一致，下次重新运行一键配置即可恢复）。
- **实机第 9 项日志提示**：在 Cursor 终端启动后点「立即重启」，若外层终端 Job 禁止 breakaway，日志应依次出现 `winerror=5` 回退警告与 `Relaxed JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE on current Job Object for restart`（若外层 Job 允许 breakaway 则直接成功且无回退日志，同样算通过）。





