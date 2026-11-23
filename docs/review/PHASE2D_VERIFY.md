# Phase 2D Verification Report (Issue #40 — Windows Real-Machine Regression Fixes)

- **Branch**: `fix/review-p2d-windows` (cut from `main` @ `6fe01c5`)
- **Verifier**: Neon (Linux/offscreen + GitHub Actions `windows-latest` offscreen)
- **Windows CI Baseline**: Run [#45177310043](https://github.com/Ceph-learner/ListenScope/actions/runs/45177310043) on `2fbe726`
  - `pytest` (`ubuntu-24.04`, `QT_QPA_PLATFORM=offscreen`): **PASSED**
  - `pytest-windows` (`windows-latest`, `QT_QPA_PLATFORM=offscreen`): **3 failed, 313 passed** (`test_ub21`, `test_ub32`, `test_ub03`)
- **Verification Tests**: [`tests/test_review_phase2d.py`](../../tests/test_review_phase2d.py) (`10 xfailed` strict under Linux/offscreen; zero business code modified in verification commit)

---

## W1–W9 Verification Matrix

| ID | 判定 | 复现测试名 (`tests/test_review_phase2d.py`) | 给修改者的精确修改步骤 / 跳过原因 |
|---|---|---|---|
| **W1** | `NEEDS_TARGET` | `test_w1_system_loopback_follows_default_device_change_without_stream_error` | **云端已复现根因（mock 默认设备 ID 切换）**，真机耳机/音箱热切换需 Windows 实测。<br>1. 在 `audio/system_loopback.py` 轮询默认输出设备（`sounddevice.default.device[1]` 或 WASAPI 默认 loopback 端点）并监听 `AUDCLNT_E_DEVICE_INVALIDATED` / `PortAudioError`；<br>2. 默认设备变更或流失效时，先关闭旧流、清零旧回调缓冲，再用新默认设备重连；<br>3. 不向 UI 抛出红色"流错误"，改为记录 `INFO` 日志并通过状态栏提示已切换输出设备；`stop()` 时干净退出重连循环。 |
| **W2** | `NEEDS_TARGET` | `test_w2_force_quit_from_hidden_tray_quits_app_hides_tray_and_has_exit_watchdog`<br>`test_w2_guard_all_source_threads_are_daemon` | **云端已复现 `force_quit()` 隐藏托盘卡死与退出看门狗缺失**，真机打包版托盘退出 + 删目录 + 无 `0xC0000005` 需 Windows 实测。<br>1. `ui/main_window.py:1171` `force_quit()`：当 `close_to_tray=True` 且窗口已隐藏在托盘时，先 `hide()` `_tray_icon` 并显式触发退出流程 + `QApplication.instance().quit()`（不能只调 `self.close()`）；<br>2. `main.py` `shutdown()`：必须调用 `get_bootstrap_manager().cancel()` 终止 `ListenScope-TurnkeySetup` 子进程，取消/登记 `ListenScope-ResourceSampler`、`ListenScope-StartupPyTorchScan`、`ListenScope-ExtAIProbe`、`ListenScope-MidiTranscribe` 的子进程句柄并在退出时 `terminate()/kill()`；<br>3. 音频回调（`audio/system_loopback.py`, `audio/process_loopback.py`, `audio/playback.py`, `audio/metronome.py`）检查原子 `_closing` 标志后立即返回；<br>4. `main.py` 退出收尾阶段启动 5 s 守护看门狗线程，超时仍未退出时调用 `os._exit(0)`（见下方 W2 全量审计表）。 |
| **W3** | `NEEDS_TARGET` | `test_w3_bass_midi_postprocess_removes_simultaneous_octave_ghost_notes` | **云端已写单音贝斯八度鬼音后处理复现测试**，真机 Basic Pitch MIDI-SMOKE 需 Windows 实测。<br>1. 在 `separation/midi_transcriber.py` 新增贝斯单音后处理函数（如 `filter_bass_octave_ghost_notes`）：当 `stem_type == "bass"` 时，若两音符起音相差 `<= 40 ms` 且音高相差 `12` 或 `24` 半音，且较高音力度低于较低音或时值被较低音覆盖，则滤除较高音；<br>2. 调用 Basic Pitch 推理时，若 `stem_type == "bass"`，传入 `minimum_frequency=30.0`、`maximum_frequency=400.0`（或接近的贝斯音域）；<br>3. 人声/旋律轨不受影响，回退转录路径结果不变。 |
| **W4** | `CONFIRMED` | `test_w4_system_animations_disabled_zeroes_tab_underline_duration` | 1. 在 `ui/acid_style.py`（`AcidTabBar` 等）与 `ui/main_window.py` 的启动及每次 `apply_appearance` 中同步 `system_animations_enabled()` 结果（用户手动开关优先）；<br>2. 禁用动画时：`AcidTabBar._anim.setDuration(0)`（或直接跳终点）、`MarqueeComboBox` 不启动跑马灯定时器、遥测微动画与分隔条 hover 动画直接跳终点；<br>3. 可选：在 Windows 收到 `WM_SETTINGCHANGE` 时刷新动画状态。 |
| **W5** | `CONFIRMED` | `test_w5_spectrogram_axis_ticks_adapt_to_available_height`<br>（另在 Windows CI Run `#45177310043` 复现 `test_ub03` `_history_box` 按钮底边 153 > 134） | **部分 `NEEDS_TARGET`**（125%/150% DPI 展开/收起 A/B 截图需真机验证）。<br>1. 在 `ui/spectrum_widget.py` 为时频图和 FFT 纵轴实现按可用像素高度自适应选刻度（相邻刻度间距 `>= 1.6 * font_height`，高度不足时减少刻度并隐藏次要坐标轴标题）；<br>2. 修复 `ui/main_window.py` `_history_box` 在 Windows 字体 `1093×566` 下的按钮溢出（底边 153 > 容器底边 134），矮窗口下收起次要按钮或紧凑换行，确保 `test_ub03` 在 `windows-latest` CI 通过。 |
| **W6** | `CONFIRMED` | `test_w6_startup_broad_scan_test_isolates_home_and_root` + 修复 `tests/` 中 5 处测试隔离/断言问题（见下表） | 按下方 W6 6 项逐条判定修复，确保 `ubuntu-24.04` 与 `windows-latest` 两个 CI 全绿，不得删除断言或滥用 skip。 |
| **W7** | `CONFIRMED` | `test_w7_readme_documents_win11_snap_layouts_known_limitation` | 1. 将 `docs/review/PHASE2C_VERIFY.md` 中 `U-B03` 的 Snap Layouts 相关条目显式标记为 `DEFER → #33 P3-WIN`；<br>2. 在 `README.md` 的「已知限制」中写明暂不支持 Win11 Snap 布局（需 `WM_NCHITTEST` 返回 `HTMAXBUTTON`，归入 Phase 3）。 |
| **W8** | `CONFIRMED` | `test_w8_windows_retest_checklist_includes_w1_w2_w3_w5_and_safe_audio_spec` | 更新 `docs/review/WINDOWS_RETEST.md`：<br>1. 将 E3/E4 测试音频规范更新为 `-20 dBFS`、带 `50 ms` 淡入淡出、钢琴/拨弦类合成音色、每段 `<= 5 s`；<br>2. 补充 W1（输出设备热切换）、W2（托盘退出 + 2 s 进程清零 + 删目录）、W3（bass MIDI-SMOKE）、W5（125%/150% DPI A/B 展开/收起截图）的实机复测步骤。 |
| **W9** | `CONFIRMED` | `test_w9_dev_build_displays_real_version_with_git_short_sha` | **不修改 `pyproject.toml` 中的 `version`**。<br>1. 在 `core/`（如 `core/version.py`）提供版本格式化函数（如 `get_app_version_display()`）：读取构建时注入的环境变量/版本元数据（例如 `LISTENSCOPE_BUILD_VERSION` / `LISTENSCOPE_GIT_SHA`），源码运行时若未打 tag 则通过 `git rev-parse --short HEAD` 生成 `<base>-dev+<shortSHA>`（当前为 `1.1.0-dev+<shortSHA>`），打 tag 构建时显示正式版本；<br>2. 替换 `ui/acid_style.py:2265` 等处硬编码的 `LISTENSCOPE_V1.0.1`，在底栏和关于页统一显示真实版本号；<br>3. 在打包脚本/工作流中支持注入 git 短 SHA（如 `scripts/build_windows.py` / `.github/workflows/release-windows.yml`）。 |

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
