# Phase 1 验证与修改方案交接表（Issue #31）

- **验证者**：Neon（Linux/offscreen 验证，Ubuntu 24.04 + Python 3.12 + PySide6/scipy/numpy/pytest）
- **基线提交**：`f43601e`（v1.0.1），工作分支：`fix/review-phase1`
- **说明**：本轮仅做复现验证与方案制定，未修改任何业务代码。所有复现测试集中在 `tests/test_review_phase1.py`，均标记 `@pytest.mark.xfail(strict=True, reason="<ID>")`；修改者每修完一条须移除对应 `xfail` 标记并确认转绿。严禁违反 `docs/DECISIONS.md` 约束（三环境隔离、6s 分块、单 Worker、5120/3072/2048 MiB 阈值、settings schema 2、保留手动换歌重置等）。

## 逐条验证与精确修改步骤

| ID | 判定 | 复现测试名 | 给修改者的精确修改步骤 / 跳过原因 |
| --- | --- | --- | --- |
| E1 | `NEEDS_TARGET` | `test_e1_mdx_separator_44k_output_preserves_pitch_and_duration` | 1) 在 `separation/mdx_backend.py` (`load_model` L185-197) 和 `separation/demucs_backend.py` (`load_model` L140-151) 构造 `Separator(**kwargs)` 时，按签名探测传入 `sample_rate=48000`、`normalization_threshold=1.0`、`amplification_threshold=0.0`；2) 在 `mdx_backend.py` (`separate_chunk` L270) 与 `demucs_backend.py` (`_separate_chunk_audio_separator` L305) 改为先完整读出 `arr, out_sr = _read_wav_f32(path)`（不先截断），若 `out_sr != sample_rate` 则调用 `_resample_chunk(arr, out_sr, sample_rate)`（可抽到公共辅助函数复用）再 `_fit_frames(arr, target_frames)`。注意：不改动 6s 分块/单 Worker/cu128 约束；真实模型输出音高与时长须按文末 Windows 步骤实测。 已改 @df454b8 |
| E5 | `CONFIRMED` | `test_e5_system_loopback_retries_up_to_max_device_reconnects` | 修改 `audio/system_loopback.py` `_capture_loop`（L217-255）：读流异常 `_close_stream()` 后进入内层重连循环 `while reconnects < self._max_device_reconnects and not self._stop_event.is_set():`，每次递增 `reconnects`、等待 `0.35 * reconnects` 秒后调用 `_open_default_loopback()`，成功则更新 `self._pa`/`self._stream` 与 `src_rate`/`src_channels`/`self._device_name` 并 `break` 回主循环；仅当次数用尽或 `_stop_event` 置位时才退出主循环，避免一次重开失败就因 `self._stream is None` 直接 `break`。同时注意保持 `test_audit5_and_phase16.py` 中 `test_system_loopback_reconnect_updates_name_and_clears_transient_notice` 通过。 已改 @bc340c9 |
| E9 | `CONFIRMED` | `test_e9_diagnostics_sanitizes_json_escaped_windows_home_paths` | 修改 `core/diagnostics.py` `_sanitize_text`（L20-35）：在 `variants` 中追加 `json.dumps(home_str)[1:-1]` 以及 `home_str.replace("\\", "\\\\")`、`home_str.replace("/", "\\\\")` 变体（按长度降序替换），确保 JSON 转义后的 Windows 路径 `C:\\Users\\Alice` 同样被替换为 `~`；并在 `tests/test_phase14_practice_tools_and_diag.py` 同步补充对 `json.dumps(home_str)[1:-1]` 的断言。 已改 @bc340c9 |
| E10 | `CONFIRMED` | `test_e10_pyproject_toml_dependencies_under_project_table` | 修改 `pyproject.toml`（L13-36）：将 `dependencies = [...]` 整段移到 `[project]` 表内、`[project.urls]` 之前，并将 `"sounddevice>=0.4.6"` 放入 `[project].dependencies`（与 `requirements-core.txt` 对齐）；保留 `PySide6>=6.8.0,<6.10` 约束。用 `python -c "import tomllib, pathlib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text('utf-8')); assert 'dependencies' in d['project'] and 'dependencies' not in d['project']['urls']"` 自检。 已改 @bc340c9 |
| E13 | `CONFIRMED` | `test_e13_output_stream_oserror_resets_playing_state` | 修改 `audio/playback.py` `StemMixerEngine._ensure_output_stream`（L1191-1195）与 `audio/metronome.py` `PracticeMetronome._ensure_output_stream`（L365-369）：将 `except ImportError:` 改为 `except (ImportError, OSError):`，并在异常分支加锁复位 `self._is_playing = False` / `self._standalone_playing = False` 后返回；打开/启动 `OutputStream` 异常分支保留 pull-only 模式以兼容无声卡 CI。 已改 @bc340c9 |
| E19 | `CONFIRMED` | `test_e19_mirror_downloader_rejects_truncated_response` | 修改 `scripts/mirror_wheel_fetch.py` `_download_with_monitor`（L213-256）：在读取循环 `break` 之后、`part.replace(dest)` 之前增加校验：`if total_size > 0 and total_rx != total_size: part.unlink(missing_ok=True); raise _SlowMirrorError(f"{mirror_label} 下载不完整 ({total_rx}/{total_size} bytes)")`，避免无 sha256 时将截断的 wheel 当成成功。 已改 @bc340c9 |
| E20 | `CONFIRMED` | `test_e20_release_workflow_avoids_inline_expression_injection` | 修改 `.github/workflows/release-windows.yml` "Resolve application version" 步骤（L51-67）：增加 `env: RELEASE_TAG_INPUT: ${{ inputs.release_tag }}` 和 `EVENT_NAME: ${{ github.event_name }}`，PowerShell 内改为读取 `$env:RELEASE_TAG_INPUT.Trim()` 与 `$env:EVENT_NAME`，彻底移除 `run:` 内的 `"${{ inputs.release_tag }}"` 直接插值。 已改 @bc340c9 |
| A-M1 | `CONFIRMED` | `test_am1_realtime_pitch_parabolic_interpolation_bass_accuracy` | 修改 `analysis/pitch.py` `PitchEstimator.estimate_from_magnitude`（L61-68）：不再对谐波和 `score` 做抛物线插值，改为先定位基频局部峰 `k = peak_bin - 1 + int(np.argmax(fft_mag[peak_bin - 1 : peak_bin + 2]))`（做好边界 `1 <= k < fft_mag.shape[0] - 1` 保护），再对 `np.log(np.maximum(fft_mag[k - 1 : k + 2], 1e-12))` 做三点抛物线插值 `delta = max(-0.5, min(0.5, 0.5 * (a - c) / den))`，最后 `freq = float((k + delta) * self._bin_hz)`。注意保持 `tests/test_phase3_analysis.py::test_pitch_refines_both_search_edges_without_half_bin_bias` 通过。 已改 @ca1d57e |
| A-M3 | `CONFIRMED` | `test_am3_offline_bass_yin_pure_sine_no_octave_down_error` | 修改 `analysis/stem_analyzer.py` `_yin_bass_frame_f0`（L297）：将次谐波校验阈值改为 `if float(np.max(mag[lo_b:hi_b])) > max(1.8 * spec_med, 0.1 * float(np.max(mag))):`，防止纯正弦/808 贝斯因谱中位数接近 0 而被 -64 dB 旁瓣触发低八度误判。 已改 @ca1d57e |
| A-M7 | `CONFIRMED` | `test_am7_steady_sine_does_not_report_high_confidence_fake_bpm` | 修改 `analysis/tempo.py` `TempoEstimator.update`（L66-70）与 `analysis/stem_analyzer.py` `_estimate_offline_bpm_from_flux`（L482-490）：在计算 ACF 前检查 onset 包络尖峰度 `peakiness = float(np.percentile(arr, 95)) / (float(np.median(arr)) + 1e-9)`，若 `peakiness < 4.0` 直接返回 `TempoEstimate(bpm=None, stability="Unknown", confidence_score=0.0)`。注意保留 `tests/test_phase3_analysis.py` 现有 120 BPM 脉冲与静音间隔测试全部通过。 已改 @ca1d57e |
| A-M8 | `CONFIRMED` | `test_am8_wsola_time_stretch_preserves_low_e1_pitch` | 修改 `audio/time_stretch.py` `StreamingTimeStretcher.__init__`（L22-33）：将默认参数更新为适配低音 E1 (41.2 Hz) 的窗长与搜索半径（建议 `win_size=4096` 或按采样率自适应 `search_radius = max(64, int(round(sample_rate / 75.0)))` 约 640、`cmp_len = max(128, min(self.win_size - self.syn_hop, int(round(sample_rate / 47.0))))` 约 1021，并确保 `fifo_cap >= self.win_size * 4`）。验证 `tests/test_phase4_playback.py` 全部通过且 E1 @ 1.25x/0.75x 误差 < 5 音分。 已改 @ca1d57e |
| A-M9 | `CONFIRMED` | `test_am9_major_seventh_uppercase_M7_parsed_as_maj7_not_m7` | 在 `analysis/chords.py` 新增公共辅助 `_normalize_chord_quality(suffix: str) -> str`：当 `suffix` 以 `("M", "Δ")` 开头且不以 `("Ma", "Mi")` 开头时替换为 `"maj" + suffix[1:]`，再 `.lower()`。在 `analysis/chords.py` (`chord_scale_degree` L68、`transpose_chord_symbol` L120、`spell_chord_tones` L173) 与 `analysis/chord_practice.py` (`chord_midi_notes` L132) 统一调用，确保 `CM7` 解析为 `maj7`（`(60, 64, 67, 71)`、`Imaj7`）而非 `m7`。 已改 @ca1d57e |
| A-M10 | `CONFIRMED` | `test_am10_spell_chord_tones_uses_diatonic_letter_spelling` | 修改 `analysis/chords.py` `spell_chord_tones`（L159-180）：按音名字母跨度（`_IV_LETTER = {0:0, 2:1, 3:2, 4:2, 5:3, 6:4, 7:4, 8:5, 9:5, 10:6, 11:6}`）根据输入根音字母（保留原始 `b`/`#`）推算各和弦音的正确等音拼写（如 `Fm` → `F · Ab · C`、`Bb` → `Bb · D · F`）。注意兼容现有测试对常见升号/白键和弦的断言。 已改 @ca1d57e |
| A-L1 | `CONFIRMED` | `test_al1_transpose_note_name_handles_b_sharp_and_c_flat_octaves` | 修改 `analysis/chords.py` `transpose_note_name`（L84-95）：解析基础字母半音值 `letter_pc`（C=0,D=2,E=4,F=5,G=7,A=9,B=11）与升降号偏移 `acc`（`#`=+1, `b`=-1），用未取模的 `raw_pc = letter_pc + acc` 计算 `midi = (int(oct_str) + 1) * 12 + raw_pc + semi`，再格式化输出 `f"{PITCH_CLASSES[midi % 12]}{(midi // 12) - 1}"`，修复 `B#3+12→C5`、`Cb4+12→B4`。 已改 @ca1d57e |
| U-B01 | `CONFIRMED` | `test_ub01_spectrogram_displays_full_96_log_bins_and_hz_axis` | 修改 `ui/spectrum_widget.py`（L190-203 及 `update_snapshot`）：将 `spec_plot.setYRange(0, n_bins, padding=0)`（`n_bins = AnalysisConfig().log_freq_bins = 96`），按 `np.geomspace(27.5, 16000.0, n_bins)` 设置左轴频率刻度（31.5/63/125/250/500/1k/2k/4k/8k/16k Hz）与轴标签 `"频率 (Hz)"`，底轴标签改为 `"时间 (s)"` 并通过 `self._spec_img.setRect(QtCore.QRectF(-frames / 15.0, 0, frames / 15.0, n_bins))` 映射真实秒数与全 96 频带。 已改 @51f36dc |
| U-B04 | `NEEDS_TARGET` | `test_ub04_practice_shortcuts_do_not_rely_solely_on_ctrl_space` | 修改 `ui/main_window.py`（L562-565、L726）：1) 新增基础练习快捷键（`Space` 播放/暂停、`L` 循环、`[`/`]` 设 A/B、`Alt+Left/Right` 微调 A、`Shift+Alt+Left/Right` 微调 B、`-`/`=`/`0` 调速、`T` Tap BPM、`M` 节拍器、`Ctrl+B` 书签），保留或降级 `Ctrl+Space`；2) 安装 `_TextInputGuard` 事件过滤器拦截 `ShortcutOverride`，当焦点在 `QLineEdit`/`QAbstractSpinBox`/`QPlainTextEdit` 时不吞单键输入；3) 顶栏原 `CTRL+SPACE // 播放控制` 改为快捷键提示入口。注意：中文输入法截获实测须在 Windows 11 按文末步骤复测。 已改 @51f36dc |
| U-B05 | `CONFIRMED` | `test_ub05_tuning_cents_bar_matches_5c_20c_thresholds_and_amber_slight_color` | 修改 `ui/chroma_widget.py` `TuningCentsBar`（L61-198）：1) 阈值统一为 `±5c` 绿、`±20c` 琥珀色（如 `#D97706` / `#F59E0B`，替代原蓝色 `#0284C7`）、`>20c` 红，中心绿带宽度改为 `track.width() * 0.10`（对应 `±5c`）；2) 增加指数平滑 + 颜色滞回（进 5c / 出 7c；进 20c / 出 21.5c）+ 失锁保持 0.35s 淡出，替代每次 `set_pitch` 强行 `stop()+start()` 的 90ms 动画；3) 轨道最小高度按 `max(18, int(self.fontMetrics().height() * 1.2))` 自适应，并在条内绘制当前偏移数值如 `+3.2c`。 已改 @51f36dc |
| U-B06 | `CONFIRMED` | `test_ub06_banner_label_roundtrip_zh_en_zh_preserves_original_text` | 修改 `ui/main_window.py` `set_capture_active_ui`（L2272-2274）和 `show_banner_message`（L2296-2297）：不要预先调用 `translate_text(...)` 再传给 `_set_label_cached`，直接传中文原文 `_set_label_cached(self.capture_status_lbl, "未捕获")` 和 `_set_label_cached(self.notice_banner, text)`，由 `_set_label_cached` 统一写入 `_ls_orig_text` 并按当前语言翻译，保证 `zh→en→zh` 无损往返。 已改 @476f745 |
| U-B09 | `CONFIRMED` | `test_ub09_translate_widget_tree_translates_qaction_tooltip_and_accessible_name` | 修改 `core/i18n.py` `translate_widget_tree`（L666-772）：1) 遍历 `root.findChildren(QtGui.QAction)` 翻译非空 `act.text()`（缓存 `_ls_orig_text`）；2) 对所有 `widgets` 补充翻译非空 `w.accessibleName()`（`_ls_orig_an`）与 `w.toolTip()`（`_ls_orig_tip`，跳过 `HelpBadge` 因其由 `apply_language` 单独管理）；3) 在 `ui/main_window.py` 托盘气泡（L1988-1993）改用 `translate_text(..., get_current_language())`，并在 `apply_language` 时顺带翻译 `self._tray_icon.contextMenu()`。 已改 @476f745 |
| U-B10 | `CONFIRMED` | `test_ub10_non_acid_capture_button_uses_i18n` | 修改 `ui/main_window.py` `set_capture_active_ui`（L2266-2267）：将非酸性主题分支改为 `self.capture_btn.setText(translate_text("停止捕获" if active else "开始捕获", lang))`，不再写死中文。 已改 @476f745 |
| U-B11 | `CONFIRMED` | `test_ub11_gpu_checkbox_does_not_hardcode_rtx_5060_ti` | 修改 `ui/main_window.py`（L999、L1023、`update_hardware_report`）与 `main.py`（L1848）：根据 `hardware_report.gpus[0]` 动态生成文案（如 `f"优先 GPU ({gpu.name} · {gpu.total_vram_mb / 1024.0:.0f} GB)"`，无 GPU 时显示 `"优先 GPU (未检测到可用 NVIDIA GPU)"`），移除硬编码 `"RTX 5060 Ti"`；帮助文案与成功横幅同步改为通用 GPU/显存描述，并补齐四语 i18n 规则。注意保留 `README*.md` 中的实测硬件说明与 `docs/DECISIONS.md` 不动。 已改 @476f745 |
| U-B12 | `CONFIRMED` | `test_ub12_settings_and_appearance_dialogs_do_not_leak_children` | 修改 `ui/main_window.py` `open_settings_dialog`（L2400-2446）与 `open_appearance_dialog`（L1853-1867）：在 `exec()` 及读取返回值之后、函数退出前于 `finally` 中调用 `dlg.setParent(None)` 与 `dlg.deleteLater()`，彻底释放已关闭的模态对话框避免子控件列表膨胀。 已改 @51f36dc |
| U-B16 | `CONFIRMED` | `test_ub16_light_theme_primary_button_and_in_tune_meet_wcag_aa` | 修改 `ui/acid_style.py` 浅色主题 `ACID_PALETTES["light"]`：将浅色主按钮底色 `accent` 加深为 `#007A57`（白字 `#FFFFFF` 对比度 `5.36:1 >= 4.5:1`，同时改善 `plot_wave`/`plot_log` 与准音绿在浅底 `#F8FAFC` 上的对比度）；同步更新 `ui/chroma_widget.py` `COLOR_IN_TUNE`。 已改 @476f745 |
| U-B20 | `CONFIRMED` | `test_ub20_maximize_button_syncs_on_system_window_state_change` | 修改 `ui/main_window.py` `ListenScopeMainWindow`：覆写 `changeEvent(self, event)`，当 `event.type() == QtCore.QEvent.Type.WindowStateChange` 时同步 `m = self.isMaximized()`、`self.win_max_btn.set_maximized(m)`、`self.win_max_btn.setText("❐" if m else "□")` 与 `self._update_rounded_mask()`，确保 Win+↑ / 拖拽贴边最大化时图标完全同步。 已改 @51f36dc |
| U-B21 | `NEEDS_TARGET` | `test_ub21_win32_icon_handles_not_reloaded_every_show_event` | 修改 `ui/main_window.py` `_apply_windows_taskbar_and_rounding`（L1125-1140）与 `closeEvent`：仅在 `not getattr(self, "_win32_hicons", None)` 时调用 `user32.LoadImageW` 加载图标并缓存，已加载则直接复用 `SendMessageW`；在 `closeEvent` 真正退出窗口时对缓存句柄调用 `user32.DestroyIcon(h)` 并清空 `self._win32_hicons = None`。真机 GDI 句柄不增长须按文末 Windows 步骤复测。 已改 @51f36dc |
| U-B23 | `CONFIRMED` | `test_ub23_settings_store_persists_window_geometry_within_schema_2` | 修改 `core/settings_store.py`：在 `PersistedSettings`（保持 `schema_version: int = 2` 不变！）追加可选字段 `window_geometry: str = ""`，在序列化/反序列化（`save_settings` / `load_settings`）中容错读写该字符串（兼容无此字段的旧配置）；在 `ui/main_window.py` 启动加载后若 `window_geometry` 非空则 `restore_saved_geometry`（校验位于可用屏幕内，否则回退 `center_on_screen()`），退出保存时写入 `bytes(self.saveGeometry().toBase64()).decode("ascii")`。 已改 @51f36dc |
| U-B24 | `CONFIRMED` | `test_ub24_log_panel_preserves_scroll_position_when_user_scrolled_up` | 修改 `ui/resource_widget.py` `ResourceStatusPanel` `update_logs`（L294-304）：保持 `setMaximumBlockCount(500)`；更新前先判断 `at_bottom = bar.value() >= max(0, bar.maximum() - 2)`，保留旧滚动位置 `prev_val = bar.value()`，仅在 `at_bottom` 时滚动到底部，否则保持 `bar.setValue(min(prev_val, bar.maximum()))` 不打断用户翻阅旧日志。 已改 @51f36dc |
| U-B25 | `CONFIRMED` | `test_ub25_spectrogram_and_chroma_history_duration_labels_match_actual_30s` | 统一时长文案与真实配置一致：1) `ui/spectrum_widget.py`（L215）：将 `"120S HISTORY"` 改为动态 `f"{spec_hist_sec}S HISTORY"`（默认 `"30S HISTORY"`）；2) `ui/chroma_widget.py` 热图标题与 `main.py`（L1947 `seconds=30.0`）对齐（将热图标题中的 `(120s)` 改为 `(30s)` 并同步 `core/i18n.py` 对应词条），避免三处时长互相打架。 已改 @476f745 |
| U-B28 | `CONFIRMED` | `test_ub28_i18n_has_no_mixed_scripts_and_no_conflicting_duplicate_keys` | 1) 修改 `core/i18n.py:L188`：将日文 `"メ트로ノーム"`（混入韩文 `트로`）修正为 `"メトロノーム"`；2) 清理 `core/i18n.py` 与 `core/i18n_catalog.py` 中 3 个冲突重复键（`紧急停止 AI`、`CHROMA HEATMAP // 有界时序热图 (120s)`、`12-BIN CHROMA // 实时色度分布`），保留唯一一致译文；3) 保留并扩展脚本混用与重复键一致性单测。 已改 @476f745 |
| U-B29 | `CONFIRMED` | `test_ub29_dark_theme_status_warn_is_amber_not_cyan` | 修改 `ui/acid_style.py` `ACID_PALETTES["dark"]`（L125-127）：将 `status_warn_bg` 改为 `"#2B2108"`、`status_warn_fg` 改为 `"#FFB020"`、`status_warn_bd` 改为 `"#FFB020"`，使其与青色 `info` / `accent_secondary (#77DCE4)` 清晰区分。 已改 @476f745 |

---

## NEEDS_TARGET 条目 Windows 11 实机复测步骤

修改者完成上述改动后，以下 3 条**必须在目标机（Windows 11 + RTX 5060 Ti 8 GB + 16 GB RAM）**实测并将结果记录到 `docs/WINDOWS_TEST_REPORT.md`：

1. **E1（AI 分轨采样率与归一化）**：
   ```powershell
   # 1. 检查 .venv-ai 中 audio-separator 的 Separator 签名与默认 sample_rate
   .\.venv-ai\Scripts\python.exe -c "import inspect; from audio_separator.separator import Separator; print(inspect.signature(Separator.__init__))"
   # 2. 生成 10s 440Hz 48kHz 测试音并跑真实 2-stem 分轨，核对输出采样率、时长与主频
   .\.venv-ai\Scripts\python.exe -c "
   import numpy as np, soundfile as sf
   from pathlib import Path
   from separation.mdx_backend import MdxOnnxTwoStemBackend
   sr = 48000; t = np.arange(sr*10, dtype=np.float32)/sr
   pcm = np.stack([0.35*np.sin(2*np.pi*440.0*t)]*2, axis=1)
   b = MdxOnnxTwoStemBackend(); b.load_model('UVR-MDX-NET-Inst_HQ_3.onnx', use_gpu=True)
   out = b.separate_chunk(pcm, sr)
   for k, v in out.items():
       mag = np.abs(np.fft.rfft(v[:,0]*np.hanning(len(v))))
       hz = float(np.fft.rfftfreq(len(v), 1/sr)[int(np.argmax(mag))])
       print(k, v.shape, 'peak_hz=', round(hz, 2))
   "
   ```
   验收标准：输出帧数等于 `480000`（10.00s），非静音轨主频在 `440.0 ± 2.0 Hz`，无末尾 0.49s 静音截断与块间增益跳变。
2. **U-B04（快捷键与中文输入法冲突）**：
   - 在 Windows 11 切换到微软拼音中文输入法，启动 `ListenScope.exe`（或 `.\.venv-core\Scripts\python.exe main.py`）；
   - 按 `Space` 验证播放/暂停不被输入法截获；按 `L` / `[` / `]` / `-` / `=` / `0` / `T` / `M` 验证响应正常；
   - 点击书签名称输入框或数字微调框，输入含空格、字母 `l`/`t`/`m` 和 `-`/`=`，确认文本正常录入而不误触快捷键。
3. **U-B21（Win32 图标句柄不泄漏）**：
   - 启动任务管理器 → 详细信息 → 添加「GDI 对象」与「句柄」列；
   - 反复将 ListenScope 最小化到托盘并还原（`showEvent`）10 次以上，观察 GDI/图标句柄数保持稳定不随每次显示递增；退出程序后无残留进程或报错。

---

## 汇总统计与建议修改顺序

- **基线测试结果**（Linux/offscreen，`f43601e`，不含新增测试）：
  - `QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short` → **`218 passed, 1 failed, 6 skipped in 163.12s`**（其中 `tests/test_audit5_and_phase16.py::test_system_loopback_reconnect_updates_name_and_clears_transient_notice` 为时序偶发失败：25 帧瞬态提示在 CPU 负载下被过快清除）。
- **新增验证测试**：`tests/test_review_phase1.py` 共 **30 条**最小复现测试，当前全部严格触发预期失败：**`30 xfailed in 4.09s`**。
- **判定统计**：`CONFIRMED` **27 条** | `FALSE_POSITIVE` **0 条** | `NEEDS_TARGET` **3 条**（`E1`、`U-B04`、`U-B21`）。
- **建议修改顺序**（按依赖与风险从低到高，分小提交便于逐批回归）：
  1. **打包/安全/配置地基**：`E10` → `E20` → `E9` → `E19` → `E13` → `E5`
  2. **算法精度修复（互不耦合、可独立单测）**：`A-M9` → `A-L1` → `A-M10` → `A-M1` → `A-M3` → `A-M7` → `A-M8`
  3. **AI 分轨采样率修复**：`E1`（完成后交付 Windows `.venv-ai` 实测）
  4. **i18n 与配色/状态修复**：`U-B28` → `U-B06` → `U-B10` → `U-B09` → `U-B16` → `U-B29` → `U-B11` → `U-B25`
  5. **UI 控件、窗口与交互增强**：`U-B12` → `U-B20` → `U-B21` → `U-B23` → `U-B24` → `U-B01` → `U-B05` → `U-B04`
