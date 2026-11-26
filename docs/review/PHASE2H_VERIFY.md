# Phase 2H Verification (Issue #65: H1–H4)

- Branch: `fix/p2h-retest4` (based on `main` `3461084`)
- Issue: `#65`

## Summary of Fixes

### H1 (Release Blocker): System Loopback Default Playback Device Follow
- **Root Cause**:
  1. `WasapiSystemLoopbackBackend._default_device_changed()` queried `pa.get_default_wasapi_loopback()` on the cached `self._pa` instance, which caches PortAudio's initial device list from `Pa_Initialize()` and never reflects Windows default playback device changes.
  2. `WasapiSystemLoopbackBackend.start()` did not record `self._device_name` into `self._stats.set_process_name(...)`, so the UI lacked the actual captured device name.
- **Changes**:
  - `audio/system_loopback.py`:
    - Added `_query_windows_default_render_endpoint()` using `ctypes` COM (`IMMDeviceEnumerator::GetDefaultAudioEndpoint` + `IMMDevice::GetId`) and `default_device_probe` injection hook for deterministic testing.
    - Polls default endpoint every 20 chunks (~0.4s, well within the 1.5s budget), reinitializes PyAudio/PortAudio stream on change without touching `ring_buffer` or `ab_player.loop_range`.
    - Logs `loopback default device changed old=<old> new=<new>` and updates `self._stats.set_process_name(self._device_name)` and `self._stats.set_device_switch_message(f"已切换到 {self._device_name}")`.
  - `core/models.py` & `audio/capture_base.py`:
    - Added `device_switch_message: Optional[str] = None` to `CaptureStats` and `set_device_switch_message()` to `CaptureStatsTracker`.
  - `ui/main_window.py` (`update_capture_stats`):
    - Displays actual `stats.process_name` for `CaptureMode.SYSTEM_LOOPBACK` in `source_combo` (text + `ToolTipRole`) and status bar, and shows the `device_switch_message` info banner (4-language via i18n).
- **Test**: `tests/test_review_phase2h.py::test_h1_system_loopback_follows_default_device_change_preserves_buffer_and_logs` (Linux/offscreen mock; passed).

### H2: Narrow Chroma Tab Layout at `QT_SCALE_FACTOR=1.25` with Banner + A/B Dock Visible
- **Root Cause**: `Chroma` responsive compact mode was gated by a hardcoded height threshold and left multi-line card headers/secondary controls visible, clipping `chroma_bar_plot` and `÷2`/`×2` buttons when both the top warning banner and bottom A/B dock were open at `1093×566` (`1.25x`, logical `874×453`).
- **Changes**:
  - `ui/chroma_widget.py`: Added `full_mode_min_height()` computed dynamically from card `sizeHint()`s; updated `set_compact_mode()` to collapse cards to single-line (moving titles/notes to tooltips) and hide secondary labels/metronome rows/`progression_mode_combo`/`transpose_combo`/`auto_reset_chk`/`track_status_lbl`, keeping `chroma_bar_plot` completely visible and `chroma_hist_plot` (`>=96px`) in `QScrollArea`, with `tempo_half_btn` / `tempo_double_btn` unclipped.
  - `ui/main_window.py` (`_apply_responsive_layout`): Uses `avail_chroma_h < self.chroma_widget.full_mode_min_height() or w < 1050`.
- **Test**: `tests/test_review_phase2h.py::test_h2_chroma_narrow_125_with_banner_and_ab_dock_shows_chroma_bars_and_tempo_buttons` (Linux/offscreen `QT_SCALE_FACTOR=1.25` subprocess; passed).

### H3: Expanded Backend AST i18n Coverage & Runtime Combo/Reason Translation
- **Root Cause**:
  1. 85 Chinese string literals in `ai/`, `analysis/`, `separation/`, `streaming/`, `audio/` lacked 4-language (`en`/`ko`/`ja`) entries.
  2. `MixerWidget.handle_ai_result()` did not translate `res.error` (e.g. `"用户点击 紧急停止 AI"`) or `oom_msg_lbl`.
  3. `MainWindow._refresh_model_combos()` added `m.display_name` untranslated without refreshing `_ls_orig_item_*`.
- **Changes**:
  - `core/i18n_catalog_p2g.py` & `core/i18n_catalog.py`: Added `P2H_PHRASE_MAP` (covering all 85 backend strings + emergency stop / OOM messages) and `P2H_DYNAMIC_REGEX_RULES` (for `"已切换到 <device>"`, `"[兜底] 系统 WASAPI Loopback · <device>"`, and `"[<state>] <reason>"`).
  - `ui/mixer_widget.py`: Translated `res.error` and `oom_msg_lbl` via `translate_text` / `set_i18n_text` in `handle_ai_result()`.
  - `ui/main_window.py`: Updated `_refresh_model_combos()` to translate `m.display_name` and maintain `_ls_orig_item_{idx}`.
- **Tests**:
  - `tests/test_review_phase2h.py::test_h3_ast_expanded_packages_chinese_strings_covered_by_i18n` (passed)
  - `tests/test_review_phase2h.py::test_h3_runtime_combos_tables_and_emergency_stop_no_chinese_leak` (passed)

### H4: Status Bar Device Name Elision & Tooltip
- **Root Cause**: `ui/main_window.py` hard-sliced `src_txt[:28]` and `AcidStatusFooter` did not elide long device names or expose the full name as a tooltip.
- **Changes**:
  - `ui/acid_style.py` (`AcidStatusFooter._refresh_text`): Uses `fontMetrics().elidedText(..., QtCore.Qt.TextElideMode.ElideRight, 190)` and sets `status_lbl.setToolTip(full_src)` + `self.setToolTip(full_src)`.
  - `ui/main_window.py` (`update_capture_stats`): Removed `[:28]` hard slice and passes full actual device name.
- **Test**: `tests/test_review_phase2h.py::test_h4_status_bar_device_name_elided_with_tooltip_and_actual_device` (passed).

## Verification Results (Linux / Offscreen)
- `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_review_phase2h.py -q --tb=short`: **5 passed**.
- Full Linux/offscreen suite (excluding `tests/bench/`):
  - Batch 1 (`test_appearance.py` .. `test_phase7_9_mixer_live_midi.py`): 170 passed; `test_audit5_and_phase16.py` + `test_review_phase2h.py` re-run after fix: **14 passed**.
  - Batch 2a-1 (`test_resource_leaks.py` .. `test_review_phase2c.py`): **100 passed**.
  - Batch 2a-2 (`test_review_phase2d.py` .. `test_review_phase2f.py`): **63 passed, 2 skipped**.
  - Batch 2b (`test_review_phase2g.py` .. `test_windows_defaults_and_midi_routing.py`): **53 passed, 6 skipped**.

## Windows 11 Target-Machine Retest Steps
1. Start ListenScope in **System WASAPI Loopback** mode while playing audio on default device A (`XIBERIA` / speakers); record some audio and set an A/B loop range.
2. Switch Windows 11 default playback device to device B (e.g., `Realtek Digital Output` or headphones).
   - Verify capture switches to device B within ~1.5s without clearing the 120s ring buffer or A/B selection.
   - Verify top info banner shows `"已切换到 <device B>"` (or localized equivalent), log contains `loopback default device changed old=... new=...`, and both `source_combo` and status bar display device B's actual name (with ellipsis + full tooltip if long).
3. Set Windows display scaling to `125%` (`QT_SCALE_FACTOR=1.25`), resize window to `1093×566` (or `874×453` logical), open **Chroma** tab with top warning banner visible and bottom A/B dock expanded:
   - Verify cards collapse to single-line, `chroma_bar_plot` is fully visible, `chroma_hist_plot` is reachable via scroll, and `÷2`/`×2` buttons are not clipped.

## Round 2 (PR #67 Quick 复审修复：H1-a / H1-b / H1-c)

- **H1-a（阻塞项：独立 watcher 线程 + 主动中断阻塞 read）**：
  - `audio/system_loopback.py`：新增 `_device_watcher_loop()`（`ListenScope-DefaultDeviceWatcher` 线程，默认每 `0.5s` 独立轮询 `IMMDeviceEnumerator::GetDefaultAudioEndpoint`），不再依赖 `stream.read()` 返回。
  - 检测到默认设备变化后，watcher 置位 `_device_switch_requested` 并调用 `_interrupt_stream()`（`stop_stream()` / `close()`）主动中断可能永久阻塞在静音旧设备上的 `stream.read()`，由 capture 线程重建流并更新 `_active_dev_index` / `_active_dev_name`。
  - 新增测试：`tests/test_review_phase2h.py::test_h1a_blocked_read_switches_within_1_5s_and_preserves_buffer`（模拟切换后旧流 `read()` 永久阻塞 `Event.wait()`，验证 1.5s 内完成切换且保留 `ring_buffer` 与 `ab.loop_range`）。
- **H1-b（COM 生命周期与 ole32 签名）**：
  - `audio/system_loopback.py`：`_make_ole32_and_guid()` 为 `CoInitializeEx`、`CoUninitialize`、`CoCreateInstance`、`CoTaskMemFree` 显式配置 `argtypes`/`restype`；`_com_initialize_thread()` 兼容 `RPC_E_CHANGED_MODE`（`-2147417850`，不调用 `CoUninitialize` 并继续执行）；watcher 线程仅在入口初始化 COM 一次、退出 `finally` 调用 `CoUninitialize()` 一次。
  - 新增测试：`tests/test_review_phase2h.py::test_h1b_com_init_uninit_once_per_watcher_and_rpc_e_changed_mode`。
- **H1-c（切换提示 TTL 自动清除与 A→B→A 往返切换）**：
  - `audio/capture_base.py`：`CaptureStatsTracker.set_device_switch_message(..., ttl_sec=5.0)` 与 `snapshot()` 支持 5s 自动过期清除，避免长期遮挡 `SYSTEM_LOOPBACK_WARNING` 并确保 A→B→A 切回原设备时仍能重新弹出切换横幅。
  - 新增测试：`tests/test_review_phase2h.py::test_h1c_device_switch_message_clears_and_aba_round_trip`。
