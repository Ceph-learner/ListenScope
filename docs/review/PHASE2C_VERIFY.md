# Phase 2C 验证与修改方案交接表（Issue #32 · 三、UI + A-M6-UI）

- **验证者**：Neon（Linux/offscreen 验证，Ubuntu 24.04 + Python 3.12 + PySide6/pyqtgraph/numpy/pytest）
- **基线提交**：`86938ef`（Phase 2B 合并至 `main` 后），工作分支：`fix/review-p2c-ui`
- **说明**：本轮仅做复现验证、offscreen 合成数据修改前截图留证与方案制定，未修改任何业务代码。所有 18 条复现测试集中在 `tests/test_review_phase2c.py`，均标记 `@pytest.mark.xfail(strict=True, reason="<ID>")`；修改者每修完一条须移除对应 `xfail` 标记并确认转绿，完成 UI 修改后须按同方式在 `docs/review/screens/` 补拍 `p2c_after_*.png`（每张 ≤ 200 KB）对照。严禁违反 `docs/DECISIONS.md` 约束（保留手动「换歌重置」、`settings schema_version == 2` 等）。

## Offscreen 截图留证规范（`docs/review/screens/`，每张 PNG ≤ 200 KB）

### 修改前（已留证）
- `docs/review/screens/p2c_before_small_1093x566.png`（149 KB，请求 1093×566 被 `minimumSize(940, 620)` 强撑至 1093×620，且四张图各约 15 px 高）
- `docs/review/screens/p2c_before_spectrum_fft.png`（45 KB，FFT 低频稀疏线性抽样 + 无弹道峰值保持）
- `docs/review/screens/p2c_before_chroma_tempo.png`（90 KB，缺少速度 `×2/÷2` 按钮 + 无 Chroma 弹道）
- `docs/review/screens/p2c_before_mixer_progress.png`（61 KB，混音标题被 `AI SEPARATION` 分组框遮挡、进度区压成一行、`[INFERRING]` 原始枚举 + 212 px 固定进度条）

### 修改后（已补齐 6 张，每张 ≤ 200 KB）
- `docs/review/screens/p2c_after_small_1093x566.png`（128.3 KB，对应 `p2c_before_small_1093x566.png`）
- `docs/review/screens/p2c_after_1366x768.png`（165.4 KB，标准笔记本分辨率）
- `docs/review/screens/p2c_after_spectrum_fft.png`（56.4 KB，对应 `p2c_before_spectrum_fft.png`）
- `docs/review/screens/p2c_after_chroma_tempo.png`（110.6 KB，对应 `p2c_before_chroma_tempo.png`）
- `docs/review/screens/p2c_after_mixer_progress.png`（87.0 KB，对应 `p2c_before_mixer_progress.png`）
- `docs/review/screens/p2c_after_en_dark_1366x768.png`（125.4 KB，英文 + 暗色主题）

## 逐条验证与精确修改步骤

| ID | 判定 | 复现测试名 | 给修改者的精确修改步骤 / 跳过原因 |
| --- | --- | --- | --- |
| U-B02 | `CONFIRMED` | `test_ub02_fft_display_uses_log_frequency_resampling_with_dense_bass_bins` | 修改 `analysis/worker.py` 与 `ui/spectrum_widget.py`：worker 端按 1/24 倍频程预计算 `self._disp_f`（221 点），低频线性插值、高频区间取最大值，沿用 `fft_freqs_hz`/`fft_db` 字段传递；UI 侧预计算 `self._fft_x = np.log10(disp_f)`、线性模式绘制 + 自定义 Hz 刻度轴，`setData(..., skipFiniteCheck=True)`。已改 @123f42d |
| U-B03 | `CONFIRMED` | `test_ub03_main_window_fits_small_screens_1093x566_and_1024x528` | 修改 `ui/main_window.py`、`ui/spectrum_widget.py`、`ui/acid_style.py`、`core/settings_store.py`：`setMinimumSize(760, 520)`，底部控制区拆为核心 `FlowLayout` 与「⋯ 更多」折叠层，放入 `QSplitter` 并提供 `set_bottom_panel_collapsed(bool)`（持久化可选字段，保持 `schema_version == 2`）；`SpectrumAnalysisWidget` 在矮窗口下自动切为 2 页 1×2 分页标签，确保 `1093×566`/`1366×768` 图高 `>= 120 px`、`1024×528` 图高 `>= 100 px`。真机 DPI/Snap 保留在 `docs/review/WINDOWS_RETEST.md`。已改 @afcb742 **复审未通过**：1) 截图 `p2c_after_en_dark_1366x768.png` 中底部 `RING BUFFER // 120S HISTORY` 面板在暗色主题下仍呈浅灰底（`#F0F0F0`），且暗色图表坐标轴文字（`Envelope Samples`、`Frequency (Hz)`）对比度偏低；2) `p2c_after_spectrum_fft.png` / `p2c_after_small_1093x566.png` / `p2c_after_en_dark_1366x768.png` 中 `SpectrumAnalysisWidget._header` 副标题（「实时频谱与波形分析」/`Realtime Spectrum & Waveform Analysis`）底部被下方 4 张数值卡片轻微裁切约 2–3 px。**修改要求**：修复 `_bottom_dock`/`_history_box`/`_ab_more_panel` 暗色 QSS 继承及暗色图表轴文字对比度；增加 `SpectrumAnalysisWidget._header` 最小高度或下边距消除副标题裁切；带合成数据重拍 `p2c_after_en_dark_1366x768.png`（同时展示暗色曲线）及受影响截图。已改 @e6b0bd8 |
| U-B07 | `CONFIRMED` | `test_ub07_ui_tick_deduplicates_snapshots_throttles_hidden_and_uses_precise_timer` | 修改 `main.py`：`PreciseTimer`、按 `snap.timestamp` 去重、隐藏/最小化降频至 `250 ms` 并跳过绘制、仅刷新可见 tab，资源采样移至后台线程 `ListenScope-ResourceSampler`。已改 @17468be |
| U-FX1 | `CONFIRMED` | `test_ufx1_frame_clock_exists_and_decouples_display_interpolation` | 新增 `ui/frame_clock.py` `FrameClock`（主窗唯一实例，隐藏/最小化停表，`prepare_for_shutdown` 停止），驱动 `TuningCentsBar` 与频谱/色度弹道 60/30 Hz 插值。已改 @afb9086 |
| U-FX2 | `CONFIRMED` | `test_ufx2_ballistics_and_spectrogram_ring_buffer_exist` | 在 `ui/frame_clock.py` 新增就地 `Ballistics` 类，在 `FrameClock` 步进更新 `ui/spectrum_widget.py`（FFT 峰值保持、0/3/4.5 dB/oct slope、>-0.3 dBFS 削波锁存灯、5 Hz 数字降频）与 `ui/chroma_widget.py`（τ≈200ms 回落 + 峰值短横线）；全曲线加 `skipFiniteCheck=True`、波形加 `setClipToView`/`setDownsampling`；`SpectrumAnalyzer` 声谱历史改预分配环形 ndarray。已改 @2e062fd |
| U-B08 | `CONFIRMED` | `test_ub08_set_i18n_text_prevents_dynamic_label_reversion_on_language_switch` | 在 `core/i18n.py` 新增 `set_i18n_text(widget, zh_text)`，并更新 `main.py`/`chroma_widget.py`/`chord_practice.py`/`settings_dialog.py`/`mixer_widget.py` 动态标签调用。已改 @1e5ad5b **复审未通过**：截图 `p2c_after_en_dark_1366x768.png` 英文界面残留 5 处 Phase 2C 新增中文：`⏸ 冻结画面`（顶栏）、`▾ 收起 A/B`（Tab 右角）、`波形与 FFT 频谱` 与 `频带能量与声谱图`（紧凑频谱子标签）、`⋯ 更多`（底部 A/B 区）。**修改要求**：1) 在 `core/i18n.py` 补齐上述 5 处及其切换态（`▶ 恢复画面`、`▸ 展开 A/B`、`▴ 收起更多` 等）四语/英文译文，并确保 `translate_widget_tree` 同步翻译 `_compact_tabs` 与 corner widget；2) 在 `tests/test_review_phase2c.py` 补充英文模式下主窗可见按钮与子标签无残留中文字符的断言；3) 重拍 `p2c_after_en_dark_1366x768.png`。已改 @e6b0bd8 |
| U-B13 | `CONFIRMED` | `test_ub13_tooltip_filter_allows_native_tooltips_unless_lsSuppressTip_set` | 修改 `ui/help_badge.py` `_TooltipOnlyOnHelpBadgeFilter`，仅在 `obj.property("lsSuppressTip")` 为真时拦截原生 tooltip。已改 @65b8bb5 |
| U-B14 | `CONFIRMED` | `test_ub14_help_badge_is_keyboard_focusable_and_at_least_24px` | 修改 `ui/help_badge.py` `HelpBadge`：尺寸 `max(24, fontMetrics().height()+6)`、`TabFocus`、仅 `Enter`/`Space`/`F1` 弹窗，同步更新 `test_ui_ux_polish_v1.py` 断言。已改 @a753d6f |
| U-B15 | `CONFIRMED` | `test_ub15_focus_ring_uses_2px_accent_secondary_even_when_animation_disabled` | 修改 `ui/acid_style.py` 与 `ui/help_badge.py`：`:focus` 改为 `2px solid accent_secondary` 并覆盖 CheckBox/Radio/Slider/TabBar；关闭交互动画时 `FocusRingAnimator` 仍显示静态 2 px 焦点环。已改 @2cdd865 |
| U-B17 | `CONFIRMED` | `test_ub17_static_lock_split_from_freeze_screen` | 修改 `ui/main_window.py`：拆分 `_freeze_screen`（「⏸ 冻结画面」，快捷键 `F` 受 `_TextInputGuard` 保护）与 `_static_lock`（仅停装饰动效，`update_analysis_snapshot` 不再因 `_static_lock` 提前 return）。已改 @3e8a00f |
| U-B18 | `CONFIRMED` | `test_ub18_ai_progress_localized_stages_and_stretchable_bar` | 修改 `ui/mixer_widget.py` 与 `ui/main_window.py`：本地化 `AIJobState` 阶段文案 + 已用时间/块耗时移动平均 ETA、进度条 `setMinimumWidth(160)` 可拉伸（别名 `progress_bar`）、`LOADING_MODEL` 取消提示释放显存、后台完成托盘与 `QApplication.alert` 提醒。已改 @840388d |
| U-B19 | `CONFIRMED` | `test_ub19_marquee_combobox_does_not_scroll_infinitely_at_rest` | 修改 `ui/acid_style.py` `MarqueeComboBox`：静止时省略号截断 + tooltip，仅悬停（150ms 意图防抖）或键盘 Tab 聚焦时滚动最多 2 轮即停止。已改 @03dfa80 |
| U-FX3 | `NEEDS_TARGET` | `test_ufx3_system_animations_helper_help_badge_delay_and_explicit_banner_tone` | 在 `ui/help_badge.py` 新增 `system_animations_enabled()`（Win32 `SPI_GETCLIENTAREAANIMATION=0x1042`）、悬停延迟改 `450 ms`（相邻切换 `0 ms`）；`show_banner_message` 支持显式 `tone` 及 `ok`/`info` 6 s 自动收起。Windows 实机动画开关联动保留在 `docs/review/WINDOWS_RETEST.md`。已改 @4dd9d52 |
| U-B22 | `NEEDS_TARGET` | `test_ub22_win10_rounded_mask_avoids_jagged_qregion_polygon` | 修改 `ui/main_window.py` `_update_rounded_mask`：移除锯齿 `QRegion(path.toFillPolygon().toPolygon())` 遮罩，改为 `clearMask()`。Win10 视觉边缘保留在 `docs/review/WINDOWS_RETEST.md`。已改 @bc33e55 |
| U-B26 | `CONFIRMED` | `test_ub26_mixer_widget_uses_bisect_for_chord_and_midi_lookup` | 修改 `ui/mixer_widget.py`：预生成 `_chord_starts` / `_note_starts`，`sync_playback_position` 改用 `bisect.bisect_right`。已改 @36a8fbb |
| U-B27 | `CONFIRMED` | `test_ub27_appearance_dialog_debounces_font_spinbox_changes` | 修改 `ui/appearance.py`：字号 SpinBox 与滑块变动增加 `120 ms` `QTimer` 防抖并仅刷新示例区，确定/应用时再整套重设主窗 QSS。已改 @f8d03bd |
| U-B30 | `CONFIRMED` | `test_ub30_telemetry_pulse_strip_accepts_real_level_or_is_static_by_default` | 修改 `ui/acid_style.py` `TelemetryPulseStrip`：新增 `set_level(rms_db)` / `set_bands(levels)`，无信号或默认强度下保持静止。已改 @21b3f54 |
| A-M6-UI | `CONFIRMED` | `test_am6_ui_tempo_half_double_buttons_present_in_chroma_widget` | 修改 `ui/chroma_widget.py`：新增 `÷2` / `×2` 按钮（仅缩放显示值与「同步检测BPM」写入节拍器值，不修改分析器内部状态，并导出 `ChromaChordWidget` 别名）。已改 @12f69ba |
| U-B31 | `CONFIRMED` | `test_ub31_mixer_header_does_not_overlap_groupbox_and_progress_visible` | 修改 `ui/mixer_widget.py`：固定 `_header` 与 `job_box` 最小高度及纵向策略，确保矮高度下不重叠且 `job_status_lbl` 显示本地化阶段文字。已改 @3e11519 |
| U-B32 | `CONFIRMED` | `test_ub32_fixed_width_controls_elide_with_ellipsis_and_full_tooltip` | 修改 `ui/main_window.py`：固定宽度控件（`ai_gpu_chk`、`ai_2stem_combo`）超宽时 `ElideRight` 显示省略号并写入完整 `toolTip()`。已改 @682c36f |
| P2C-PERF | `CONFIRMED` | `test_p2c_perf_analyze_latest_once_cpu_within_5ms_median` | 修改 `analysis/worker.py` 与 `analysis/fft.py`：按 `self._onset_cursor` 缩窄环形缓冲读取与降混窗口，新增向量化 `log_spectrum_batch` 替代逐 hop Python 循环与 `np.mean(np.square(...))`，`analyze_latest_once` 稳态中位数降至 **3.60 ms**（`<= 5.0 ms`）且 `A-BENCH` 零退化。已改 @14fc5ab |
| U-B34 | `CONFIRMED` | `test_ub34_realtime_waveform_envelope_4s_uniform_band_for_440hz_and_1khz` | **根因**：`ui/spectrum_widget.py` 将实时波形横轴标为 `-4..0 s`，但 `analysis/worker.py` 仅将 `0.15 s`（7200 点）传给 `compute_waveform_envelope(..., 512)`，每桶仅 14 点（0.29 ms < 440 Hz/1 kHz 周期），导致 440 Hz/1 kHz 正弦波 `min(waveform_max)` 跌至 `-0.464/-0.305` 并出现视觉混叠波浪。**修改要求**：1) 在 `analysis/worker.py` 改为对真实 4 s 窗口（如 `ring_buffer` 最近 4 s 或分块 `np.minimum.reduceat`/`np.maximum.reduceat`）计算 512 桶 min/max 包络（不足 4 s 时左侧补 0 对齐右端 `0 s`，并确保 `P2C-PERF` 中位数仍 `<= 5.0 ms`）；2) 在 `ui/spectrum_widget.py` 用 `pg.FillBetweenItem` 填充 `_wave_min_curve` 与 `_wave_max_curve` 之间的包络带；3) 移除 `test_ub34` 的 `xfail` 标记并重拍 `docs/review/screens/p2c_after_en_dark_1366x768.png`（≤ 200 KB）确认显示均匀 ±A 带状。 |

---

## 基线、新增测试与完成状态

- **基线测试（`86938ef`，Linux/offscreen 验证）**：全量 `283 passed, 6 skipped`
- **本批修改后专项测试（`tests/test_review_phase2c.py`，Linux/offscreen 验证）**：**23 passed**（0 failed，0 xfailed）
- **判定统计（共 21 条）**：`CONFIRMED` 19 条 + `NEEDS_TARGET` 2 条已全部实现并移除 `xfail`（Windows 真机 DPI/Snap/系统动画/Win10 边缘保留在 `docs/review/WINDOWS_RETEST.md`）。

---

## 最终复审结论（复审者 Neon）

- **复审状态**：**全部 21 条通过（批准合并至 `main`）**。
- **首轮退回与返修核验**：首轮截图审查发现 `U-B08`（英文暗色截图残留 5 处中文）与 `U-B03`（暗色底部面板浅灰底、坐标轴对比度偏低及频谱副标题微裁切）；返修提交 `e6b0bd8` 已全部修复，并新增 `en/ja/ko` 全可见控件零残留遍历测试与暗色对比度/1093 布局单测，6 张 `p2c_after_*.png`（55–166 KB）逐张视觉复检全部通过。
- **冻结基准与独立复测（Linux/offscreen 验证，非 Windows 11 实机/GPU/exe）**：
  - `git diff 86938ef..HEAD -- tests/bench/`：**0 字节**；
  - `A-BENCH` 对照 `docs/review/bench_after_p2b.json`：**`REGRESSIONS: NONE`**；
  - 专项 `tests/test_review_phase2c.py`：**`23 passed`**（未削弱任何断言）；
  - 全量 `QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short`：**`306 passed, 6 skipped`**（0 failed）。
- **专项代码核查**：`FrameClock` 全工程单实例且隐藏/最小化/关闭均停表；后台资源采样线程不触碰 Qt 控件；快捷键 `F` 受 `_TextInputGuard` 保护；`AnalysisSnapshot` 旧字段完全兼容；未违反 `docs/DECISIONS.md`。

