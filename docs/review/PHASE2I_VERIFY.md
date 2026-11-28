# Phase 2I Verification (Issue #94: I1 & I2)

- Branch: `fix/p2i-rc1` (based on `main` `47faba8`)
- Issue: `#94`

## 1. Packaging Spec, Installer & PortAudio DLL Parity Audit

| Aspect | Portable Archive (`ListenScope-Core-Windows-x64-Portable.zip`) | Installer Build (`ListenScope-Setup-Windows-x64.exe`) | Parity / Upgrade Guard |
| :--- | :--- | :--- | :--- |
| Build Source | `PyInstaller packaging/listenscope_core.spec --noconfirm --clean` -> `dist\ListenScopeCore\*` | Same `dist\ListenScopeCore\*` via `#define MySourceDir "..\dist\ListenScopeCore"` | Identical PyInstaller output (`ListenScope.exe` + `_internal\`) |
| `PyAudioWPatch` Binary | `_internal\_portaudiowpatch.cp312-win_amd64.pyd` (pinned `PyAudioWPatch>=0.2.12.6`) | Same PYD bundled from `dist\ListenScopeCore\_internal\` | Added `"pyaudiowpatch"` to `collect_dynamic_libs` loop in `packaging/listenscope_core.spec` alongside `hiddenimports` |
| `sounddevice` PortAudio DLL | `_internal\_sounddevice_data\portaudio-binaries\libportaudio64bit.dll` | Same DLL bundled from `dist\ListenScopeCore\_internal\` | Verified in CI via SHA256 and byte-size equality between `dist\ListenScopeCore` and silently installed build |
| Working Directory | Directory containing `ListenScope.exe` | `[Icons]` sets `WorkingDir: "{app}"`; frozen path resolution uses `sys.executable` / `sys._MEIPASS` | Identical runtime root & relative `_internal` lookup |
| In-Place Upgrade Cleanup | Portable updater replaces `_internal\` atomically while preserving 8 user paths | Added `[InstallDelete]` (`Type: filesandordirs; Name: "{app}\_internal"`) in `scripts/installer.iss` | Prevents stale `_internal` PYDs/DLLs from prior installs while preserving `exports\`, `settings.json`, `workspace_outputs\`, `runtime\ai`, `m\`, `tools\`, `logs\`, `.venv-*` (`AppId` unchanged) |
| CI Installed-Exe Smoke | Relocated `ListenScope.exe --simulate --headless-smoke` | Silent install to `$env:RUNNER_TEMP\listenscope-installed-smoke`, DLL/PYD SHA256 parity check, `"$installDir\ListenScope.exe" --loopback-smoke` | Logs `portaudio_version_text`, PYD/DLL paths & sizes; asserts non-empty `portaudio_version_text` and (`opened == true` or `attempts >= 2`); cleans up in `try/finally` |

## 2. Root Causes & Fixes

### I1 (Release Blocker): Installed System Loopback Startup `[Errno -9996] Invalid device`
- **Root Cause**:
  1. `WasapiSystemLoopbackBackend._open_default_loopback()` created only a single `PyAudio()` session and attempted `pa.get_default_wasapi_loopback()` once. When Windows WASAPI endpoint enumeration was not yet settled or returned a stale device index (`-9996 Invalid device`) during startup, `start()` aborted immediately without terminating PortAudio and re-enumerating via a fresh `PyAudio()` instance.
  2. When `pa.get_default_wasapi_loopback()` failed or returned an unopenable index, there was no fallback to query `pa.get_host_api_info_by_type(paWASAPI)["defaultOutputDevice"]` and match the corresponding loopback device from `pa.get_loopback_device_info_generator()`.
  3. On in-place installer upgrades, `scripts/installer.iss` lacked `[InstallDelete]` for `{app}\_internal`, risking stale binaries from earlier installations, and CI did not verify the silently installed `.exe` or its bundled PortAudio files.
- **Fixes**:
  - `audio/system_loopback.py`:
    - Added `get_portaudio_runtime_info()` returning `pyaudiowpatch_version`, `portaudio_version_text`, `portaudio_pyd_path`, and `portaudio_pyd_size` (safe on non-Windows hosts where `pyaudiowpatch` is absent).
    - Added `startup_open_retries: int = 2` (3 total startup attempts) and `startup_retry_delay_sec: float = 0.15` plus read-only properties `last_open_attempts` and `last_open_errors`.
    - Updated `_open_default_loopback()` to construct a fresh `pa = self._create_pa()` per attempt, always call `pa.terminate()` before any interruptible retry sleep (`delay * attempt`), fall back from `get_default_wasapi_loopback()` to exact/substring default-output loopback matching via `get_host_api_info_by_type(paWASAPI)` + `get_loopback_device_info_generator()` (never picking an unrelated non-default device), and fall back `paFloat32` -> `paInt16` with detailed PortAudio/device diagnostics.
  - `packaging/listenscope_core.spec`, `scripts/installer.iss`, `main.py`, `.github/workflows/release-windows.yml`:
    - Added `"pyaudiowpatch"` to `collect_dynamic_libs`, `[InstallDelete]` for `{app}\_internal` in `installer.iss`, `--loopback-smoke <json_path>` CLI diagnostics in `main.py`, and silent-installer DLL parity + loopback smoke verification in `release-windows.yml`.

### I2 (Release Blocker): Consecutive Default-Device Switches Exhausting Reconnect Budget & Stopping Capture
- **Root Cause**:
  1. `_capture_loop()` shared a single `reconnects` counter bounded by `max_device_reconnects` (3) between genuine unexpected device disconnects and watcher-triggered `DEFAULT_DEVICE_CHANGED` switches. When a newly activated/re-enabled audio driver needed more than 3 attempts to initialize or two switches occurred in quick succession before a clean read reset `reconnects`, capture hit `播放设备中断且重连超过 3 次: DEFAULT_DEVICE_CHANGED` and permanently stopped.
  2. `_device_watcher_loop()` skipped polling whenever `_device_switch_requested.is_set()`, so rapid consecutive switches (`A -> B -> C` while `B` was retrying) were ignored until `B` finished or failed, and `_capture_loop()` could not pivot mid-backoff.
  3. On permanent unexpected-disconnect exit, `_capture_loop()` exited without signaling `_stop_event` for `_watcher_thread`, leaving the watcher alive if `backend.start()` was later invoked again on the same instance.
- **Fixes**:
  - `audio/system_loopback.py`:
    - Separated counters and budgets:
      - `_unexpected_disconnect_attempts` (bounded by `_max_device_reconnects`, default `3`; resets on healthy read or when a proactive watcher switch takes over).
      - `_proactive_switch_attempts` (unbounded by `_max_device_reconnects` so user device changes continue until open succeeds, a newer switch supersedes it, or `stop()` is requested).
      - Added read-only telemetry properties `proactive_switch_success_count`, `proactive_switch_retry_total`, `unexpected_disconnect_retry_total`, `unexpected_disconnect_attempts`, and `proactive_switch_attempts`.
    - Added exponential switch backoff (`switch_backoff_initial_sec: float = 0.05`, `switch_backoff_max_sec: float = 2.0`, scaling `initial * 2 ** min(attempt - 1, 6)` up to `max`), waking immediately via `threading.Condition` (`_wakeup_cond`) on `stop()` or when `_switch_generation` advances.
    - Updated `_device_watcher_loop()` to keep polling continuously regardless of `_device_switch_requested`, incrementing `_switch_generation` and notifying `_wakeup_cond` on every endpoint change so `_capture_loop()` pivots immediately to the newest default device (and closes any stale stream opened for an older generation on the capture thread).
    - During transient switch retries, capture stays active (`is_running == True`, queue remains open), displays a non-fatal status banner without flooding logs past attempt 5, and clears `_stop_event` / joins prior threads cleanly across manual restarts.
  - `core/i18n_catalog_p2g.py`:
    - Added 4-language (`zh`/`en`/`ja`/`ko`) dynamic regex rules (`P2I_DYNAMIC_REGEX_RULES`) for transient device-switch retry status and unexpected-disconnect error messages.

## 3. Thread-Ownership & COM Audit

| Component / API | Owning Thread | Initialization / Cleanup Contract | Verification |
| :--- | :--- | :--- | :--- |
| PortAudio (`PyAudio()`, `get_default_wasapi_loopback`, `get_loopback_device_info_generator`, `open`, `get_read_available`, `read`, `stop_stream`, `close`, `terminate`) | `ListenScope-SystemLoopback` (capture thread) | Fresh `PyAudio()` created and terminated strictly on capture thread; no MTA `CoInitializeEx(0)` on capture thread (PortAudio WASAPI uses STA); stale streams opened before a newer `_switch_generation` are closed on capture thread | `test_i2_thread_ownership_portaudio_capture_and_com_watcher`, `test_h1a_capture_thread_only_stream_ownership_and_zero_read_available_switch` |
| Windows COM (`CoInitializeEx(None, 0x0)`, `IMMDeviceEnumerator::GetDefaultAudioEndpoint`, `CoUninitialize`) | `ListenScope-DefaultDeviceWatcher` (watcher thread) | Initialized once at watcher entry (handling `RPC_E_CHANGED_MODE`), uninitialized once in `finally:`; `_capture_loop` signals `_stop_event` on exit so watcher never leaks | `test_i2_thread_ownership_portaudio_capture_and_com_watcher`, `test_h1b_com_init_uninit_once_per_watcher_and_rpc_e_changed_mode`, `test_i2_manual_recovery_after_permanent_unexpected_disconnect` |
| Qt GUI (`update_capture_stats`, `set_capture_active_ui`, banners, `capture_btn`) | Qt main UI thread | Polled on UI timer; no background thread mutates Qt widgets directly | `test_i2_manual_recovery_after_permanent_unexpected_disconnect`, `test_h1c_device_switch_message_clears_and_aba_round_trip` |

## 4. Verification Results (Linux / Offscreen)

> **Scope Note**: All local pytest runs below executed on Linux (`QT_QPA_PLATFORM=offscreen`) using mock/unit doubles for PortAudio and Windows COM endpoints; real Windows 11 WASAPI audio hardware and Inno Setup installer execution remain unverified until the Windows CI workflow and target-machine retest run.

- `tests/test_review_phase2i.py`: verified I1 startup `-9996` re-enumeration, exact default-loopback matching, `get_portaudio_runtime_info()` + `--loopback-smoke` JSON CLI, spec/installer/workflow contract, I2 counter separation, 2 consecutive switches (2 failures + 3rd success), 5 rapid switches + mid-retry pivot, unexpected-disconnect-to-switch pivot, manual recovery (`backend.start()` + `ListenScopeController.start_capture()`), thread-ownership isolation, and 4-language i18n coverage (`11 passed, 1 skipped` on Linux; Windows-only real loopback smoke test skipped).
- Regression suite batch 1 (`tests/test_review_phase2i.py`, `tests/test_review_phase2h.py`, `tests/test_release_prep_v110.py`, `tests/test_updater.py`, `tests/test_updater_apply.py`, `tests/test_review_phase1.py`): **90 passed, 3 skipped** (all 3 skipped are `sys.platform != "win32"` Windows-only tests).
- Regression suite batch 2 (`tests/test_review_phase2d.py`, `tests/test_audit5_and_phase16.py`, `tests/test_audit_regressions.py`, `tests/test_phase1_capture.py`, `tests/test_phase12_audit_and_features.py`, `tests/test_turnkey_cubase_bass_theme.py`, `tests/test_chord_practice.py`): **70 passed**.

## 5. Windows 11 Target-Machine Retest Checklist

1. **Installer Upgrade & Clean Install Parity (I1)**:
   - Install `ListenScope-Setup-Windows-x64.exe` into `D:\ListenScope` (including over a prior `v1.1.0-rc.1` directory containing user `settings.json` and `exports\`).
   - Confirm `D:\ListenScope\_internal\_portaudiowpatch.cp312-win_amd64.pyd` and `D:\ListenScope\_internal\_sounddevice_data\portaudio-binaries\libportaudio64bit.dll` match the Portable ZIP byte-for-byte (`Get-FileHash -Algorithm SHA256`), and user `settings.json` / `exports\` remain intact.
   - Launch `D:\ListenScope\ListenScope.exe`, select **System WASAPI Loopback**, click **Start Capture**, and confirm capture starts cleanly without `[Errno -9996] Invalid device`.
   - Optionally run `D:\ListenScope\ListenScope.exe --loopback-smoke %TEMP%\smoke.json` and verify `"opened": true` and non-empty `portaudio_version_text`.
2. **Consecutive & Rapid Default Device Switching (I2)**:
   - While capturing in **System WASAPI Loopback** mode, switch Windows default playback device `XIBERIA -> Realtek` and wait for `"已切换到 Realtek..."` and `loopback default device changed old=... new=...` in `logs\listenscope.log`.
   - Switch back `Realtek -> XIBERIA` and perform 5 rapid default-device switches (`A -> B -> C -> D -> E`). Verify capture never stops permanently with `播放设备中断且重连超过 3 次: DEFAULT_DEVICE_CHANGED`, status bar tracks the final active device, and `ring_buffer` / A/B loop markers remain intact.
3. **Genuine Disconnect & Manual Recovery (I2)**:
   - Disable or unplug the active playback device without switching to another valid device. Confirm capture stops cleanly after `max_device_reconnects` (3) attempts with the error banner and the capture button unchecked.
   - Re-enable/reconnect the playback device and click **Start Capture**. Confirm capture resumes cleanly and PCM audio flows immediately.
