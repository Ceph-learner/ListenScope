# Phase 2G（retest3 遗留问题 G1–G6）修复与验证记录

- **分支**：`fix/p2g-retest3`（基于最新 `main` `ce71926`，保留 PR #63 顶栏两级渐进折叠 `_compute_wide_req` 与 `ResourceMonitorBar.set_compact_mode`）
- **关联 Issue**：#62

---

## 修改与验证总表（G1–G6）

| 项 | 原因分析与修改内容 | 测试名 | Linux/offscreen 验证结果 |
|---|---|---|---|
| **G1 (阻塞)：运行态英文残留中文 + AST 静态覆盖** | 1. 补充 [`core/i18n.py`](../../core/i18n.py) 与新增 [`core/i18n_catalog_p2g.py`](../../core/i18n_catalog_p2g.py)（合入 [`core/i18n_catalog.py`](../../core/i18n_catalog.py)）：补齐系统 WASAPI Loopback 警告、音高卡「低音 / 多声部 · 显示低音」、SMTC 无会话/过渡/合成源提示，以及 `ui/`、`main.py`、`core/` 中所有 UI/横幅/状态字符串的四语翻译。<br>2. [`main.py`](../../main.py) `_on_ui_tick`、导入/单轨送入分析路径中对 `history_coverage_lbl` 的更新改用 `set_i18n_text()`，修复捕获前每秒轮询覆盖成中文「已缓冲: 0.0 / 120.0 s」的问题。 | `tests/test_review_phase2g.py::test_g1_runtime_states_no_chinese_leak_en_ja_ko`<br>`tests/test_review_phase2g.py::test_g1_ast_static_chinese_strings_covered_by_i18n`<br>`tests/test_review_phase2f.py::test_f6_no_chinese_leak_in_en_ja_ko` | **PASSED** |
| **G2：和弦页窄窗口热图被挤出 & 标题截断** | 1. [`ui/acid_style.py`](../../ui/acid_style.py) `TelemetryHeader.set_compact_mode()`：窄窗口隐藏右侧 badge pill（移入 tooltip）并收紧高度，释放标题水平空间使 `TONALITY // 02` / `调性推测` 不再截断为 `TONAL…` / `调性…`。<br>2. [`ui/chroma_widget.py`](../../ui/chroma_widget.py) `set_compact_mode()` & [`ui/main_window.py`](../../ui/main_window.py) `_apply_responsive_layout()`：在 `h < 600 or w < 1050` 时将次要说明与节拍器扩展行收入 tooltip/折叠，保持手动「换歌重置」与 Chroma 柱状图 + 热图（`>= 96 px`）无需滚动即可完整显示。 | `tests/test_review_phase2g.py::test_g2_chroma_narrow_window_heatmap_visible_and_headers_not_elided`<br>`tests/test_review_phase2g.py::test_g2_g3_scaled_125_1093x566` | **PASSED**（覆盖 `874×453` 逻辑与 `QT_SCALE_FACTOR=1.25`） |
| **G3 (阻塞)：A/B 展开「更多」溢出窗口** | [`ui/main_window.py`](../../ui/main_window.py)：`self.tabs` 设垂直 `Ignored` 策略与 `minimumHeight(110)`，新增 `_apply_ab_more_splitter_fit()` 在 `_on_ab_more_toggled` 与 `_apply_responsive_layout` 时按窗口可用高度重新分配 `_main_splitter` 比例，确保展开「⋯ 更多」后全部按钮（含 `AI 4-Stem`）均在窗口内可点击。 | `tests/test_review_phase2g.py::test_g3_ab_more_expanded_all_buttons_inside_window`<br>`tests/test_review_phase2g.py::test_g2_g3_scaled_125_1093x566` | **PASSED**（覆盖 `874×453`、`1093×566` 与 `1.25×`） |
| **G4：点击分轨无反馈排查与加固** | **原因查明**：(a) 受 G3 影响窄窗下 4-Stem 按钮部分溢出窗口底部；(b) `main.py` `_on_start_ai_separation` 拒绝分支（如 `live_separator_active`、`insufficient_buffer`、`submit_rejected`）此前未记录结构化拒批日志且部分分支删除了刚建的 `task_dir` (`shutil.rmtree`)，导致日志无记录、目录无新增。<br>**修改**：[`main.py`](../../main.py) 所有拒批分支统一记录 `ai launch rejected reason=...` 日志并调用 `show_banner_message(..., tone="warn")`。 | `tests/test_review_phase2g.py::test_g4_ai_launch_always_gives_feedback_or_starts_and_logs_rejection` | **PASSED** |
| **G5：英文窄窗口细节** | 1. [`ui/acid_style.py`](../../ui/acid_style.py) `MarqueeComboBox.paintEvent()`：当 `placeholderText()` 超宽时改用 `ElideRight` 省略绘制，避免硬截断成 `Select audio sour`。<br>2. [`ui/mixer_widget.py`](../../ui/mixer_widget.py)：`_track_scroll` 禁用横向滚动条、`_empty_tracks_hint_lbl` 设水平 `Ignored` + `wordWrap=True`、空状态按钮行改用 `FlowLayout`。<br>3. [`ui/main_window.py`](../../ui/main_window.py)：`populate_audio_sources` 为每项写入 `ToolTipRole` 并通过 `_sync_source_combo_tooltip()` 同步完整设备名到 `source_combo.toolTip()`。 | `tests/test_review_phase2g.py::test_g5_english_narrow_details_source_combo_mixer_empty_and_loopback_tooltip` | **PASSED** |
| **G6：「立即重启」实机可测性调试钩子** | [`main.py`](../../main.py)：支持 `LISTENSCOPE_DEBUG_RESTART_AFTER_S=<秒>` 在启动后定时调用一次 `ctrl.restart_application()`（写入 warning 日志），且 `restart_application()` 启动子进程前从 `child_env` 移除该变量防止无限重启；已补充说明到 [`docs/TESTING.md`](../TESTING.md)。 | `tests/test_review_phase2g.py::test_g6_debug_restart_hook_env_and_strips_from_child` | **PASSED** |

---

## Windows 目标机待复测项（不属 Linux/offscreen 已验证范围）
1. 播放过程中切换语言，确认时频图历史是否保留。
2. 使用 `LISTENSCOPE_DEBUG_RESTART_AFTER_S=3` 分别从「终端启动」和「双击启动」各测一次重启，确认新窗口保持运行且不无限重启。
3. 第 10 项：鼠标悬停查看 Chroma/FFT/Waveform 提示；托盘图标放大截图。
4. W1：切换默认输出设备后用普通应用（系统设置「测试」或 QQ 音乐）出声，验证 ListenScope 跟随到新设备且状态栏显示新设备名。
5. 4-Stem 分轨中途执行 E-STOP（G3 已修复按钮可达性）。
