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
2. **托盘图标与退出耗时**：确认托盘溢出区显示 3 竖条单色图标并随系统明暗切换；点击 `Quit ListenScope` 后 2 s 内主进程与子进程全部退出，日志可见各阶段 `shutdown stage=... elapsed_ms=...`。
3. **真实音频持续播放 BPM**：确认 15 s 内稳定出 BPM（不再等到 100+ s）。
