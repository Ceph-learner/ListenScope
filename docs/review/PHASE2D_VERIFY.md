# Phase 2D Verification Report (Issue #40 — Windows Real-Machine Regression Fixes)

- **Branch**: `fix/review-p2d-windows` (cut from `main` @ `6fe01c5`)
- **Verifier**: Neon (Linux/offscreen + GitHub Actions `windows-latest` offscreen)
- **Windows CI Baseline**: Run [#45177310043](https://github.com/Ceph-learner/ListenScope/actions/runs/45177310043) on `2fbe726` (`3 failed, 313 passed`)
- **Latest CI Verification**: Run [#45188859134](https://github.com/Ceph-learner/ListenScope/actions/runs/45188859134) on `5a740a6`
  - `pytest` (`ubuntu-24.04`, `QT_QPA_PLATFORM=offscreen`): **PASSED** (4m38s)
  - `pytest-windows` (`windows-latest`, `QT_QPA_PLATFORM=offscreen`): **PASSED** (7m22s)
- **Verification Tests**: [`tests/test_review_phase2d.py`](../../tests/test_review_phase2d.py)（全部 `xfail` 已移除，11 项回归测试在 Linux + Windows offscreen CI 均已通过；W1/W2/W3/W5 真机部分待 Windows 11 实机复测）

---

## W1–W9 Verification Matrix

| ID | 判定 | 复现测试名 (`tests/test_review_phase2d.py`) | 修改状态与验收说明 |
|---|---|---|---|
| **W1** | `FIXED (CI) / NEEDS_TARGET (真机)` | `test_w1_system_loopback_follows_default_device_change_without_stream_error` | **已通过 Linux + Windows offscreen CI**；`audio/system_loopback.py` 增加默认设备轮询与静默切换重连（不弹红色流错误），`core/settings_store.py` 增加 `follow_default_device`（schema_version=2）。真机耳机/音箱热切换仍为 `NEEDS_TARGET`（见 `WINDOWS_RETEST.md`）。 |
| **W2** | `FIXED (CI) / NEEDS_TARGET (真机)` | `test_w2_force_quit_from_hidden_tray_quits_app_hides_tray_and_has_exit_watchdog`<br>`test_w2_guard_all_source_threads_are_daemon`<br>`test_w2_process_loopback_stop_then_start_receives_audio_frames` | **已通过 Linux + Windows offscreen CI**；已修 `force_quit()` 隐藏托盘退出、`shutdown()` 取消 bootstrap 与统一清理 `_ACTIVE_SUBPROCS`、音频回调 `_closing` 保护（含 `WasapiProcessLoopbackBackend.start()` 重置 `_closing`）与 5 s `os._exit(0)` 看门狗。真机打包版托盘退出 + 2 s 清零 + 删目录 + 无 `0xC0000005` 仍为 `NEEDS_TARGET`。 |
| **W3** | `FIXED (CI) / NEEDS_TARGET (真机)` | `test_w3_bass_midi_postprocess_removes_simultaneous_octave_ghost_notes` | **已通过 Linux + Windows offscreen CI**；`analysis/midi_transcription.py` 新增 `suppress_bass_octave_ghosts`（<=40 ms 的 +12/+24 半音鬼音）并对 bass 轨限定 Basic Pitch `30–400 Hz`（兼容测试替身签名），A-BENCH 无退化。真机 Basic Pitch MIDI-SMOKE 仍为 `NEEDS_TARGET`。 |
| **W4** | `FIXED (Linux + Windows CI)` | `test_w4_system_animations_disabled_zeroes_tab_underline_duration` | **已通过 Linux + Windows offscreen CI**；`ui/help_badge.py`、`ui/acid_style.py` 与 `ui/main_window.py` 同步 `system_animations_enabled()`，禁用动画时 `AcidTabBar` 下划线 `duration=0` 且微动画直跳终点。 |
| **W5** | `FIXED (CI) / NEEDS_TARGET (真机)` | `test_w5_spectrogram_axis_ticks_adapt_to_available_height`<br>（`test_ub03` 已在 `windows-latest` CI 转绿） | **已通过 Linux + Windows offscreen CI**；`ui/spectrum_widget.py` 新增 `_refresh_axis_ticks()`（间距 >= 1.6 倍字高、矮时隐藏次要轴标题），`ui/main_window.py` 收窄/折叠 `1093×566` 窄矮窗口次要控件解决 `_history_box` 溢出。真机 125%/150% DPI 展开/收起 A/B 截图仍为 `NEEDS_TARGET`。 |
| **W6** | `FIXED (Linux + Windows CI)` | `test_w6_startup_broad_scan_test_isolates_home_and_root` + 5 处隔离/断言修复 | **已通过 Linux + Windows offscreen CI**；已修 GUI 内存 mock、`test_ub21` 图标缓存与 `dwmapi`、`test_e6` NVML 隔离、`test_ub32` `MarqueeComboBox` 省略断言、`test_ub03` 溢出与启动宽扫描隔离。 |
| **W7** | `FIXED (Linux + Windows CI)` | `test_w7_readme_documents_win11_snap_layouts_known_limitation` | **已通过 Linux + Windows offscreen CI**；`docs/review/PHASE2C_VERIFY.md` 已标 `DEFER → #33 P3-WIN`，`README.md` 已写明 Win11 Snap Layouts 已知限制。 |
| **W8** | `FIXED (Linux + Windows CI)` | `test_w8_windows_retest_checklist_includes_w1_w2_w3_w5_and_safe_audio_spec` | **已通过 Linux + Windows offscreen CI**；`docs/review/WINDOWS_RETEST.md` 已更新 E3/E4 安全音频规格（`-20 dBFS` / 50 ms 淡入淡出 / <=5 s 钢琴拨弦）并补充 W1/W2/W3/W5 实机复测步骤。 |
| **W9** | `FIXED (Linux + Windows CI)` | `test_w9_dev_build_displays_real_version_with_git_short_sha` | **已通过 Linux + Windows offscreen CI**；新增 `core/version.py`（不改 `pyproject.toml` `version`），替换 `ui/acid_style.py` 底栏硬编码并在 `.github/workflows/release-windows.yml` 注入版本元数据。 |

---

## W2 全量线程与子进程审计表

### 1. 全部 `threading.Thread(` 创建点（共 33 处）

| 位置 | 线程名 / 句柄 | `daemon` | `join` / 停止机制 | 风险评级与退出残留分析 |
|---|---|---|---|---|
| `main.py:438` | `ListenScope-ResourceSampler` | `True` | **无线程引用、无 `join`** | **高风险**：后台每轮调用 `nvidia-smi` (`subprocess.run(timeout=5)`)，关闭时若卡在子进程或回调中无取消机制。 |
| `main.py:452` | `ListenScope-StartupPyTorchScan` | `True` | **无线程引用、无 `join`** | **高风险**：调用 `run_external_python`，退出时子进程不会被主动 `terminate()`。 |
| `main.py:490` | `ListenScope-ExtAIProbe` | `True` | **无线程引用、无 `join`** | **高风险**：调用 `run_external_python`，退出时子进程不会被主动 `terminate()`。 |
| `main.py:603` | `self._drain_thread` | `True` | `shutdown()` 置停止事件 + `join` | 低风险：确认 `join` 带有限超时且不再向已销毁 Qt 对象发信号。 |
| `main.py:686` | `self._track_monitor_thread` | `True` | `shutdown()` 置停止事件 + `join` | 低风险：确认 `core/media_session.py:632` `subprocess.run` 超时短且退出时不阻塞。 |
| `main.py:1032` | `ListenScope-ExportAB` | `True` | 无 `join` | 中低风险：仅写文件，无外部子进程。 |
| `main.py:1188` | `ListenScope-ExportDiag` | `True` | 无 `join` | 中低风险：仅导出诊断 zip。 |
| `main.py:1289` | `ListenScope-AICancel` | `True` | 无 `join` | 低风险：调用 `ai_job_manager.cancel_job`。 |
| `main.py:1308` | `ListenScope-EmergencyStop` | `True` | 无 `join` | 低风险：紧急停止动作。 |
| `main.py:1392` | `ListenScope-ExportMix` | `True` | 无 `join` | 中低风险：混音导出。 |
| `main.py:1459` | `ListenScope-ImportAudio` | `True` | 无 `join` | 中低风险：导入解码。 |
| `main.py:1554` | `ListenScope-StemDeepAnalyze` | `True` | 无 `join` | 中低风险：纯 Python/numpy 计算。 |
| `main.py:1808` | `ListenScope-MidiTranscribe` | `True` | **无线程引用、无 `join`** | **高风险**：内部 `main.py:1720` 调用 `run_external_python`（Basic Pitch，长耗时），退出时无法 `terminate()` 该子进程。 |
| `main.py:1824` | `ListenScope-LiveBench` | `True` | 无 `join` | **中高风险**：内部 `streaming/benchmark.py:194` 调用 `popen_external_python`，退出时未统一取消。 |
| `main.py:1862` | `ListenScope-LiveStart` | `True` | 无 `join` | 中风险：启动 `live_separator`。 |
| `main.py:1869` | `ListenScope-LiveStop` | `True` | 无 `join` | 低风险：停止 `live_separator`。 |
| `core/bootstrap_manager.py:320` | `ListenScope-TurnkeySetup` | `True` | 有 `cancel()`，但 **`main.py:shutdown()` 从未调用** | **高风险**：`main.py:shutdown()` 只断开信号，从未调用 `get_bootstrap_manager().cancel()`，导致 `self._proc`（uv/pip 安装子进程）残留。 |
| `streaming/benchmark.py:220-221` | `ListenScope-BenchOut` / `BenchErr` | `True` | 随 `proc` 结束 `join` | 中风险：若主进程退出时 `proc` 未被 `terminate()`，将残留外部 python。 |
| `streaming/live_separator.py:562,565,568,776` | `_subproc_writer/reader/stderr_thread`, `_feed_thread` | `True` | `stop()` 关闭管道并 `terminate()/kill()` | 中低风险：确认 `shutdown()` 总是同步调用 `live_separator.stop()`。 |
| `ui/settings_dialog.py:1222,1464,1482` | `ListenScope-ScanPyTorch`, `VerifyAIEnv`, `VerifyMidiEnv` | `True` | 无 `join` | 中风险：调用 `run_external_python`，若对话框打开探测期间强制退出，子进程未登记取消。 |
| `analysis/worker.py:113` | `self._thread` | `True` | `stop()` 置 `_stop_event` + `join` | 低风险。 |
| `audio/process_loopback.py:188` | `self._watchdog_thread` | `True` | `stop()` + `join` | 中风险：需给原生音频回调加原子 `_closing` 保护防 `0xC0000005`。 |
| `audio/system_loopback.py:165,350` | `self._thread` | `True` | `stop()` + `join` | 中风险：同上，需原子 `_closing` 标志。 |
| `ai/job_manager.py:263,434,439` | `monitor_thread`, `_subproc_reader/stderr_thread` | `True` | `cancel_job()` 终止 `_subproc`/`_spawn_proc` | 低风险：确认 `shutdown()` 强制等待 `cancel_job()` 终止子进程。 |

### 2. 全部子进程 / 多进程创建点汇总

- **已接入 `shutdown()` 终止**：`ai/job_manager.py:351` (`popen_external_python` / `multiprocessing.Process`)、`streaming/live_separator.py:425` (`popen_external_python` / `multiprocessing.Process`)。
- **退出时未接入终止（W2 重点修）**：
  1. `core/bootstrap_manager.py:186,333` (`self._proc` — `shutdown()` 未调 `cancel()`)；
  2. `core/paths.py:91` `run_external_python`（被 `main.py:1720`、`core/system_probe.py:537,622,969` 调用，建议维护全局活动子进程登记表 `_ACTIVE_SUBPROCS`，退出时统一 `terminate()` -> 等待 -> `kill()`）；
  3. `streaming/benchmark.py:194` (`popen_external_python`，接入同一活动子进程登记表)；
  4. `core/system_probe.py:30` (`nvidia-smi` `subprocess.run`)、`core/media_session.py:632` (`subprocess.run`)。
- **非阻塞拉起**：`main.py:1951` (`subprocess.Popen` 打开外部文件/目录，无需终止)。
- **直接导致"托盘退出卡死"的主因**：`ui/main_window.py:1171` `force_quit()` 在窗口隐藏到托盘（`close_to_tray=True` + `setQuitOnLastWindowClosed(False)`）时仅调用 `self.close()`，Qt 对已隐藏窗口不会触发 `lastWindowClosed`，且未隐藏 `_tray_icon` 或调用 `app.quit()`。

---

## W6：Windows pytest 6 项失败逐条判定

> 依据：GitHub Actions `windows-latest` offscreen CI Run [#45177310043](https://github.com/Ceph-learner/ListenScope/actions/runs/45177310043)（3 failed, 313 passed）与代码核对。

| # | 用例 / 现象 | Windows CI 是否复现 | 判定（测试问题 vs 真 bug） | 精确根因与修改方向 |
|---|---|---|---|---|
| 1 | GUI 冒烟测试中紧急停止级别期望 `Normal`，实际 `Critical` | 否（CI 可用内存充足） | **测试隔离问题** | 测试未 mock `psutil` / `ResourceManager`，读取了实机真实可用内存（~3.9 GB 落入降级/临界区间）。修改：在测试中 mock 内存采样为充足值，并顺带确认 5120/3072/2048 MiB 阈值映射无误。 |
| 2 | `tests/test_review_phase1.py::test_ub21_win32_icon_handles_not_reloaded_every_show_event`（`LoadImageW` 期望 2 实际 0） | **是**（Run `#45177310043` 复现） | **测试 mock 隔离问题** | `test_ub21` 在 Windows 下构造 `ListenScopeMainWindow` 时 `sys.platform` 已为 `"win32"`，且 `fake_windll = SimpleNamespace(user32=_FakeUser32())` 缺少 `dwmapi`（或图标句柄已在构造阶段缓存），导致 `LoadImageW` 计数为 0；实机 GDI 句柄计数已通过。修改：清零 `_win_icon_handles` 缓存并补全 `fake_windll`（含 `dwmapi`）。 |
| 3 | E6：2 s 内 `nvidia-smi` 调用 0 次，期望 1 次 | 否（CI 无 NVIDIA GPU / NVML） | **测试隔离问题** | 实机装有 RTX 5060 Ti 和 NVML，采样器优先走 NVML 路径，不会调 `nvidia-smi`。修改：测试中强制 mock NVML 不可用，使其确定性地走 `nvidia-smi` 回退路径。 |
| 4 | `tests/test_review_phase2c.py::test_ub32_fixed_width_controls_elide_with_ellipsis_and_full_tooltip`（宽度 240 时 `'2-Stem 低显存默认 (MDX-Net ONNX)'` 未带省略号） | **是**（Run `#45177310043` 复现） | **测试断言与控件实现不匹配**（需核对绘制） | Windows 字体下 `fm.horizontalAdvance(text) > avail` 为真，但测试检查的是 `MarqueeComboBox.currentText()`（始终返回原始全文本），而省略/跑马灯发生在 `paintEvent`。修改：核对 `MarqueeComboBox` 在禁动画/静态模式下确实使用 `ElideRight` 绘制，并将测试改为按 `fontMetrics` / 控件实际省略文本方法断言 + 增加一个必定溢出的长文本用例。 |
| 5 | `tests/test_review_phase2c.py::test_ub03_dark_dock_contrast_header_no_clip_1093_no_overflow_and_tab05_accessible`（`_history_box` 按钮底边 153 > 容器底边 134） | **是**（Run `#45177310043` 复现） | **真 bug（归入 W5）** | Windows 字体行高下 `1093×566` 历史区按钮纵向溢出容器底边。随 **W5** 修复 `_history_box` 矮窗口紧凑布局。 |
| 6 | `tests/test_startup_help_bootstrap_fixes.py::test_startup_skips_broad_pytorch_scan`（关闭广泛扫描仍找到解释器） | 否（CI 无本机 `.venv-ai`） | **测试隔离问题** | 测试未 monkeypatch `main_mod.ROOT` 和 `Path.home()`，在已安装 `.venv-ai` 的实机上即使 `allow_broad_scan=False` 也会扫描标准路径找到 `.venv-ai`。修改：在测试中将 `main_mod.ROOT` 与 `Path.home()` 隔离到 `tmp_path`（同时在 `tests/test_review_phase2d.py` 保留回归断言）。 |

---

## W9：开发构建显示真实版本号规格

- **不修改 `pyproject.toml` 中的 `version`**（保持 `1.1.0`）。
- **未打 tag 的开发构建 / 源码运行**：底栏（替代 `ui/acid_style.py:2265` 硬编码的 `LISTENSCOPE_V1.0.1`）和关于页统一显示 `1.1.0-dev+<shortSHA>`（格式 `<base_version>-dev+<7位以上十六进制短SHA>`）。
- **已打 tag 的正式构建**：显示 `<base_version>`（如 `1.1.0`）。
- **来源优先级**：
  1. 构建时注入的环境变量或打包生成的版本元数据（例如 `LISTENSCOPE_BUILD_VERSION` / `LISTENSCOPE_GIT_SHA` / 打包内置 `_build_info.py`）；
  2. 源码运行时从 `git describe --tags --exact-match` / `git rev-parse --short HEAD` 读取；
  3. 无 git 信息时安全回退到 `<base_version>-dev`。
