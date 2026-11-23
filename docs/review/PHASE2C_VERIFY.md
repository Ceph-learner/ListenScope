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

### 修改后（修改者 Hydrogen 必须按同口径补齐以下 6 张，每张 ≤ 200 KB）
- `docs/review/screens/p2c_after_small_1093x566.png`（对应 `p2c_before_small_1093x566.png`）
- `docs/review/screens/p2c_after_1366x768.png`（标准笔记本分辨率）
- `docs/review/screens/p2c_after_spectrum_fft.png`（对应 `p2c_before_spectrum_fft.png`）
- `docs/review/screens/p2c_after_chroma_tempo.png`（对应 `p2c_before_chroma_tempo.png`）
- `docs/review/screens/p2c_after_mixer_progress.png`（对应 `p2c_before_mixer_progress.png`）
- `docs/review/screens/p2c_after_en_dark_1366x768.png`（英文 + 暗色主题，检查 i18n 完整度与对比度）

## 逐条验证与精确修改步骤

| ID | 判定 | 复现测试名 | 给修改者的精确修改步骤 / 跳过原因 |
| --- | --- | --- | --- |
| U-B02 | `CONFIRMED` | `test_ub02_fft_display_uses_log_frequency_resampling_with_dense_bass_bins` | 修改 `analysis/worker.py`（L162-164）与 `ui/spectrum_widget.py`（L398-404）：在 worker 端按 1/24 倍频程预计算 `self._disp_f = np.geomspace(27.5, 16000.0, 221).astype(np.float32)`，低频对数插值、高频区间取最大值（确保 27.5–110 Hz ≥ 24 点），并直接以 float32 序列传递；UI 侧预计算 `self._fft_x = np.log10(disp_f)`、线性模式绘制 + 自定义 Hz 刻度轴，`setData(..., skipFiniteCheck=True)`。 |
| U-B03 | `CONFIRMED` | `test_ub03_main_window_fits_small_screens_1093x566_and_1024x528` | 修改 `ui/main_window.py`（L510、L803-1029）与 `ui/spectrum_widget.py`：1) 横向：`setMinimumSize` 降至 `<= 760×540`（宽 ≤ 500 epx 进入紧凑模式），底部控制区拆为常驻核心层与「⋯ 更多」折叠层，横排控件改 `FlowLayout`，监听 `screenChanged`/`logicalDotsPerInchChanged`；2) **纵向（核心修复）**：顶栏在窗口高度 `< 760` 时合并为一行；四张数值卡片在矮窗口下切换为紧凑单行；底部 A/B 面板放进 `QSplitter`（默认占比 `<= 35%`）并支持折叠（暴露 `set_bottom_panel_collapsed(bool)`，折叠后图表区高度显著增加，折叠状态写入 `PersistedSettings` 可选字段、**保持 `schema_version == 2` 不变**）；四张图（波形/声谱/FFT/对数频谱）在矮窗口下改为 2×2 网格或分页标签，确保 `1093×566` / `1366×768` 下每个可见 `PlotWidget` 高度 `>= 120 px`（`1024×528` 下 `>= 100 px`）且所有按钮在窗口内。真机 DPI 与 Snap Layouts 仍保留在 `docs/review/WINDOWS_RETEST.md`。 |
| U-B07 | `CONFIRMED` | `test_ub07_ui_tick_deduplicates_snapshots_throttles_hidden_and_uses_precise_timer` | 修改 `main.py`（L420、L2117-2165）：1) 将 `self._timer` 改为 `QtCore.Qt.TimerType.PreciseTimer`；2) 按 `snap_ts != self._last_snap_ts` 去重渲染，窗口隐藏/最小化时跳过绘制并将 interval 降频至 `250 ms`（可见时 `45 ms`），仅刷新当前可见 tab；3) **基于 Phase 2A `E6` 已实现的无锁缓存 `ResourceManager.sample()`**，将资源采样移至独立低频后台线程（~1–2 s 更新一次 `self._latest_rsnap`），`_on_ui_tick` 仅读取缓存结果、严禁在 GUI 线程同步调用 `resource_manager.sample()`。 |
| U-FX1 | `CONFIRMED` | `test_ufx1_frame_clock_exists_and_decouples_display_interpolation` | 在 `ui/`（如新建 `ui/frame_clock.py` 或放入 `ui/acid_style.py`）新增统一 `FrameClock(QtCore.QObject)`（`tick = Signal(float)`、`PreciseTimer`、`set_active(on, hz=60)`，节能 30 Hz，窗口隐藏/最小化时停表）；将 `TuningCentsBar`（U-B05）及表头/指针插值接入 `FrameClock`，使数据 15 Hz 与显示 60/30 Hz 彻底解耦。 |
| U-FX2 | `CONFIRMED` | `test_ufx2_ballistics_and_spectrogram_ring_buffer_exist` | 1) 新增 `Ballistics` 类（上升立即跟随、回落 `20/1.7 dB/s`、峰值保持 `1.5 s` 后 `12 dB/s` 回落），接入 `ui/spectrum_widget.py` 的 FFT 曲线（加实时最大值副曲线与可选 0/3/4.5 dB/oct slope）、RMS/准峰值双条（>-0.3 dBFS 削波锁存灯点击清除）及 `ui/chroma_widget.py` 的 Chroma 柱状图（回落 τ≈200 ms + 峰值短横线）；数字 dB 读数降频至 4–6 Hz；2) 所有 pyqtgraph 曲线加 `skipFiniteCheck=True`，历史波形加 `setClipToView(True)` / `setDownsampling(auto=True, method="peak")`，`SpectrumAnalyzer` 声谱图历史改为预分配环形 ndarray 消除每 3 tick `np.stack`。 |
| U-B08 | `CONFIRMED` | `test_ub08_set_i18n_text_prevents_dynamic_label_reversion_on_language_switch` | 1) 在 `core/i18n.py` 新增统一入口 `set_i18n_text(widget, zh_text)`：同步更新 `widget.setProperty("_ls_orig_text", zh_text)` 并按当前语言 `translate_text` 设置文本；2) 将 `job_status_lbl`、`subloop_badge_lbl`、`live_chord_hud_lbl`、`track_status_lbl`、`tap_status_lbl`、`_feedback_lbl`、`bootstrap_meta_lbl` 等动态 label 改为调用 `set_i18n_text`，确保切换语言（`zh→en→zh`）不再还原为初始静态文案。 |
| U-B13 | `CONFIRMED` | `test_ub13_tooltip_filter_allows_native_tooltips_unless_lsSuppressTip_set` | 修改 `ui/help_badge.py` `_TooltipOnlyOnHelpBadgeFilter`（L640-651）：不再一刀切拦截所有非 `HelpBadge` 的原生 `QEvent.ToolTip`，改为仅当 `bool(obj.property("lsSuppressTip"))` 为真时返回 `True`；为 `□ ❐ × − +` 等纯图标按钮补充清晰的本地化 tooltip。 |
| U-B14 | `CONFIRMED` | `test_ub14_help_badge_is_keyboard_focusable_and_at_least_24px` | 修改 `ui/help_badge.py` `HelpBadge`（L328-331）：尺寸改为 `max(24, self.fontMetrics().height() + 6)`（满足 WCAG 2.5.8 ≥ 24 px），焦点策略改为 `QtCore.Qt.FocusPolicy.TabFocus`；获得焦点时**不**自动弹窗，按 `Enter` / `Space` / `F1` 才弹出/切换气泡；同步更新现有 `test_help_badge_no_focus_popup*` 断言（验证焦点可到达且不自动弹窗）。 |
| U-B15 | `CONFIRMED` | `test_ub15_focus_ring_uses_2px_accent_secondary_even_when_animation_disabled` | 修改 `ui/acid_style.py`（L2386、L2444-2471）：将 `:focus` 样式改为 `2px solid` 的 `accent_secondary`（与 hover 明显区分），补齐 `QCheckBox`/`QRadioButton`/`QSlider`/`QTabBar` 的可见焦点态；当「交互聚焦动画」关闭时 `FocusRingAnimator` 仍显示静态 2 px 焦点环，不可彻底隐藏焦点。 |
| U-B17 | `CONFIRMED` | `test_ub17_static_lock_split_from_freeze_screen` | 修改 `ui/main_window.py`（L1502、L2459）：将原 `_static_lock` 拆分为两个独立状态——`_freeze_screen`（「⏸ 冻结画面」，快捷键 `F`，冻结频谱/和弦/调性/音准数据刷新）与 `_static_lock`（「静态装饰」，只停装饰动效、**绝不**在 `update_analysis_snapshot` 中提前 `return`）。 |
| U-B18 | `CONFIRMED` | `test_ub18_ai_progress_localized_stages_and_stretchable_bar` | 修改 `ui/mixer_widget.py`（L237、L1272）与 `ui/main_window.py`：1) 将 `AIJobState` 枚举映射为本地化阶段文案（准备 / 加载模型 / 推理第 k/n 块 / 写出），显示已用时间与块耗时移动平均 ETA；2) 进度条改用 `setMinimumWidth(160)` 允许拉伸；3) `LOADING_MODEL` 阶段允许取消并提示“正在释放显存…”；4) 任务完成且主窗隐藏时触发托盘提醒与 `QApplication.alert(self)`。 |
| U-B19 | `CONFIRMED` | `test_ub19_marquee_combobox_does_not_scroll_infinitely_at_rest` | 修改 `ui/acid_style.py` `MarqueeComboBox`（L1039-1120）：默认静止并用省略号截断（tooltip 显示全文）；仅在 hover 或获得焦点且未开启减少动画时启动滚动，最多滚动 1–2 轮即停止（符合 WCAG 2.2.2）。 |
| U-FX3 | `NEEDS_TARGET` | `test_ufx3_system_animations_helper_help_badge_delay_and_explicit_banner_tone` | 1) 新增 `system_animations_enabled() -> bool`（Win32 读 `SPI_GETCLIENTAREAANIMATION = 0x1042`），系统关闭动画时默认关闭焦点动画/遥测微动画/跑马灯/Tab 滑动；2) `HelpBadge` 悬停延迟从 `110 ms` 改为 `450 ms`（已有 popover 时相邻切换 `0 ms`）；3) `show_banner_message(text, tone=...)` 全面显式传 `tone`（`ok`/`info` 6 s 自动收起，`warn`/`error` 常驻），不再依赖中文关键词推断；4) 实时页未捕获时展示空状态引导卡。Windows 系统动画开关联动须按 `docs/review/WINDOWS_RETEST.md` 实测。 |
| U-B22 | `NEEDS_TARGET` | `test_ub22_win10_rounded_mask_avoids_jagged_qregion_polygon` | 修改 `ui/main_window.py` `_update_rounded_mask`（L1202-1220）：移除锯齿状 `QRegion(path.toFillPolygon().toPolygon())` 窗口遮罩；Win11 沿用 DWM 原生圆角，Win10 及非 Win11 改用直角或抗锯齿 `paintEvent` 渲染。Win10 视觉边缘须在目标系统复测（见 `docs/review/WINDOWS_RETEST.md`）。 |
| U-B26 | `CONFIRMED` | `test_ub26_mixer_widget_uses_bisect_for_chord_and_midi_lookup` | 修改 `ui/mixer_widget.py`（L992-1031）：载入和弦段与 MIDI 音符时预生成排序起点数组（`chord_starts`、`note_starts`），播放定位查找改用 `bisect.bisect_right` 替代每 tick O(N) 线性遍历。 |
| U-B27 | `CONFIRMED` | `test_ub27_appearance_dialog_debounces_font_spinbox_changes` | 修改 `ui/appearance.py`（L890、L1123-1189）：为字号 SpinBox 及滑块变动增加 `120 ms` `QTimer.singleShot` 防抖，且实时预览仅刷新对话框内示例区，点击「应用/确定」时再对主窗口整套重设 QSS。 |
| U-B30 | `CONFIRMED` | `test_ub30_telemetry_pulse_strip_accepts_real_level_or_is_static_by_default` | 修改 `ui/acid_style.py` `TelemetryPulseStrip`（L661-731）：增加 `set_level(rms_db)` / `set_bands(levels)` 接口由真实音频电平/频带驱动（无信号或默认强度下保持静止，不再用假正弦动画冒充电平表），并在主窗更新快照时传入真实电平。 |
| A-M6-UI | `CONFIRMED` | `test_am6_ui_tempo_half_double_buttons_present_in_chroma_widget` | 并入自 Phase 2B `A-M6`：在 `ui/chroma_widget.py` BPM 显示旁新增 `÷2` 与 `×2` 快捷切换按钮（支持显示 `TempoEstimate.alt_bpm` 次候选并一键倍速/半速切换，同步影响「采用 BPM」写入节拍器的数值）。 |
| U-B31 | `CONFIRMED` | `test_ub31_mixer_header_does_not_overlap_groupbox_and_progress_visible` | 修改 `ui/mixer_widget.py`（L223-245）：修复混音页顶部 `TelemetryHeader`（「分轨混音 · 深度扒谱 · MIDI 转录」）与 `AI SEPARATION` `QGroupBox` 垂直布局挤压重叠问题（给 header 明确最小高度与间距，或放入可滚动区域），并确保 AI 进度区 `job_status_lbl` 在矮高度下不被压扁（高度 `>= fontMetrics().height()` 且正常显示本地化阶段文字）。 |
| U-B32 | `CONFIRMED` | `test_ub32_fixed_width_controls_elide_with_ellipsis_and_full_tooltip` | 修改 `ui/main_window.py`（`ai_2stem_combo`、`ai_gpu_chk` 等固定宽度控件）与 `ui/acid_style.py`（依赖 `U-B13` 恢复原生 tooltip）：当文本超过控件可用宽度时使用 `Qt.TextElideMode.ElideRight` 显示省略号「…」，不再硬裁切（如「2-Stem 低显存默认 (MD」「优先 GPU (未检测到可用 NVI」），并同步将完整文本写入 `toolTip()`。 |
| P2C-PERF | `CONFIRMED` | `test_p2c_perf_analyze_latest_once_cpu_within_5ms_median` | 2B `A-H1` 性能补测显示 `analyze_latest_once` 稳态中位数由 `3.11 ms` 增至 `6.80 ms`（`+3.69 ms`）、p95 由 `4.94 ms` 增至 `8.87 ms`（`+3.93 ms`），超过 3 ms 阈值。修改 `analysis/worker.py`、`analysis/tempo.py`、`analysis/fft.py`：1) 确保 `TempoEstimator` 真正降频到每 `0.5 s`（约 47 hop）做一次 FFT ACF 估计；2) 在 `worker.py` 复用/合并 rFFT 与频谱计算，避免每周期 6 个 hop 与主频谱/YIN 重复做多余大窗口 rFFT，使稳态中位数回到 `<= 5.0 ms` 且保持 `A-BENCH` 零退化。 |

---

## 基线、新增测试与建议修复顺序

- **基线测试（`86938ef`，Linux/offscreen 验证）**：全量 `283 passed, 6 skipped`
- **本批新增复现测试（`tests/test_review_phase2c.py`，Linux/offscreen 验证）**：`21 xfailed`（0 failed，0 xpassed）
- **判定统计（共 21 条）**：`CONFIRMED` **19** 条（含 `U-B03`、`U-B31`、`U-B32`、`P2C-PERF`、`A-M6-UI`），`NEEDS_TARGET` **2** 条（`U-FX3`、`U-B22`；`U-B03` 的真机 DPI/Snap 复测仍保留在 `docs/review/WINDOWS_RETEST.md`），`FALSE_POSITIVE` **0** 条，`SKIPPED` **0** 条
- **建议修复顺序（供修改者 Hydrogen 参考）**：
  1. **性能与基础设施快修**：`P2C-PERF` → `U-B26` → `U-B27` → `U-B08` → `U-B13` → `U-B14` → `U-B19` → `U-B15`
  2. **时钟、刷新与渲染架构**：`U-B07`（基于 2A `E6`）→ `U-FX1` → `U-B02` → `U-FX2` → `U-B30` → `U-B17`
  3. **布局、防裁切与功能补全**：`U-B03` → `U-B31` → `U-B32` → `U-B18` → `U-FX3` → `U-B22` → `A-M6-UI`（完成后按清单补拍 6 张 `p2c_after_*.png`）
