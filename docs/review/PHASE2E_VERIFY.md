# Phase 2E Verification Report (Issue #42 — UI Visual & Interaction Polish)

- **Branch**: `feature/ui-polish-p2e` (cut from `main` @ `f4fcaf1`)
- **Verifier**: Neon (Linux/offscreen + GitHub Actions `windows-latest` offscreen screenshot artifact)
- **Before Screenshots (Linux)**:
  - `docs/review/screens/p2e_before_light_spectrum_1366x768.png` (152.3 KB)
  - `docs/review/screens/p2e_before_dark_en_spectrum_1366x768.png` (129.3 KB)
  - `docs/review/screens/p2e_before_light_chord_1366x768.png` (195.7 KB)
  - `docs/review/screens/p2e_before_light_mixer_empty_1366x768.png` (196.7 KB)
  - `docs/review/screens/p2e_before_small_1093x566.png` (126.4 KB)
- **Windows CI Screenshot Artifact**: `.github/workflows/tests.yml` `pytest-windows` job runs `scripts/make_screenshots.py` and uploads `p2e-windows-screenshots` (Run [#45300101648](https://github.com/Ceph-learner/ListenScope/actions/runs/45300101648)).
- **Verification Tests**: [`tests/test_review_phase2e.py`](../../tests/test_review_phase2e.py) (`10 xfailed` strict; zero business code modified).
- **W13/W15 Pre-check**: W13 & W15 partially improved `source_combo` stretching, chord card watermark alpha, and default `_ab_more_panel` collapse, but **none of E1–E11 are fully `DONE`** on `main@f4fcaf1` (notably E11 `_bottom_dock` is still `172 px > 120 px` at `1366×768`).

---

## E1–E11 Verification Matrix

| ID | 判定 | 复现测试名 (`tests/test_review_phase2e.py`) | 现状实测与给修改者的精确修改步骤 |
|---|---|---|---|
| **E1** | `已改 @a5920ad` | `test_e1_topbar_single_row_le_56px_and_idle_estop_neutral` | 1366×768 下顶栏仍为双行且含 `_skin_badge` / `_shortcut_pill`；AI 空闲时 E-STOP 仍为红底。<br>改为单行 `<= 56 px`：左侧品牌/可拉伸音源/唯一实心主按钮(开始停止捕获)/电平小表/冻结图标；右侧合并资源胶囊/空闲隐藏 AI 胶囊/明暗/快捷键/设置图标/中性描边 E-STOP(AI 运行时红底脉冲)/窗口按钮；主题名移入设置页。 |
| **E2** | `已改 @0c83d80` | `test_e2_no_double_slash_in_interactive_buttons_or_tabs_and_5_tabs_fit_1093` | 实测 5 个标签页全含 `//`（如 `// 01 SPECTRUM // 实时频谱`），7 个可见按钮含 `//`（如 `CAPTURE_START // 开始捕获`）。<br>按钮/标签页/下拉仅显示当前语言文字，工程代号仅保留在卡片 eyebrow 或 tooltip；1093 宽下 5 个标签页无滚动完整显示。 |
| **E3** | `已改 @551adb7` | `test_e3_footer_is_real_24px_status_bar_not_decorative_barcode` | `ui/acid_style.py` 仍渲染装饰性 `85/15_ANTI_FATIGUE: OK :: ZERO_GLOW: TRUE` 与条形码。<br>改为 24 px 真实状态栏：版本号（W9）、捕获源/48 kHz、分析周期 p50 (ms)、缓冲时长、CPU%、右侧「减少动效」开关；荧光底仅 Acid 预设使用，条形码默认关闭。 |
| **E4** | `已改 @c2c30e1` | `test_e4_visible_help_badges_le_10_per_page_and_f1_help_supported` | 实测和弦页整窗可见 `HelpBadge` 为 **11 个**（> 10）且缺 F1 焦点控件帮助。<br>每个卡片/区块仅保留 1 个 `?`，控件级说明转为 tooltip（内容不丢），补充 `F1` 快捷键打开当前焦点控件帮助。 |
| **E5** | `已改 @5c0584d` | `test_e5_mixer_empty_state_shows_le_3_disabled_buttons` | 实测分轨前混音页可见禁用按钮 **12 个**（> 3）。<br>分轨前折叠依赖分轨结果的控件，只显示空状态引导卡（「① 选中片段 → ② AI 2-Stem 分轨」+ 主按钮），空表格居中提示与操作入口。 |
| **E6** | `已改 @ffa7b46` | `test_e6_chord_card_deduplicates_primary_label_and_uses_stability_meter` | 实测和弦卡仍重复显示主和弦名并展示原始 `稳定度: ... \| 相关 ... \| 差 ...` 字符串。<br>主和弦名只显示一次，副行显示「级数 · 构成音 · 第二候选」，稳定度改为 5 格小表 + 文字等级（原始数值放 tooltip），调性卡同理。 |
| **E7** | `已改 @8e7b557` | `test_e7_charts_uniform_fft_ticks_left_alignment_and_perceptual_colormap` | 实测 FFT 纵轴仍为 `-100/-80/-60/-40/-20/0` 且三图左边距未对齐。<br>统一 10–11 px 等宽轴字与 >=3:1 对比度；明暗两套感知均匀时频图色图（首尾 CIELAB L* 差 >= 60%，配 dB 色标，来源登记 `THIRD_PARTY_NOTICES`）；FFT 纵轴固定 `0 / -30 / -60 / -90 dB`；三图左边距对齐 ±2 px。 |
| **E8** | `已改 @2b1dbe1` | `test_e8_unified_lucide_icons_registered_and_no_unicode_window_buttons` | 实测 `ui/assets/icons/ICONS.md` 不存在，窗口按钮仍用 Unicode 字符 `□ ❐ × −`。<br>统一使用 Lucide SVG 图标置于 `ui/assets/icons/` 并在 `ICONS.md` 逐一登记；运行时按主题替换 `currentColor`；窗口按钮改为 SVG 图标（46×32，关闭悬停 `#C42B1C`）。 |
| **E9** | `已改 @5677c2c` | `test_e9_app_icon_ico_tray_and_icon_doc` | 已按 #42 E9 定稿生成 10 尺寸 `.ico`（16–32 px 取自 3 柱 `small_dark`）、`listenscope_master_light.svg`、按 `SystemUsesLightTheme` 切换托盘图标、1280×640 `social_preview.png`、`docs/design/ICON.md` 10 竞品对比，旧图标归档至 `docs/design/legacy/listenscope_v1.svg`。 |
| **E10** | `已改 @0f8e981` | `test_e10_design_doc_and_design_sheet_cli_exist` | 实测 `docs/DESIGN.md` 不存在，`scripts/make_screenshots.py` 尚不支持 `--design-sheet`。<br>新建 `docs/DESIGN.md` 记录间距 `4/8/12/16/24/32`、圆角 `0/2/4`、字号 `11/12/13/16/20/28`、字体栈（不打包字体）、明暗颜色 token 与组件状态，并扩展 `scripts/make_screenshots.py --design-sheet`。 |
| **E11** | `已改 @6df380f` | `test_e11_default_ab_panel_single_row_le_120px_at_1366x768` | **W13 后复测**：虽然 `_ab_more_panel` 默认收起，但 1366×768 下 `_bottom_dock` 实测高度仍为 **172 px > 120 px**。<br>将「选最近 10/30/60 s」合并为分段按钮，「A±1s / B±1s」合并为两组微调按钮，书签与 AI 分轨移入「更多」，确保默认状态单行且 `<= 120 px`。 |

---

## 2E-R｜截图复审修正（Issue #52）

> 上次 `release/v1.1-prep` 合并后 `main` CI（Run `45311282823`）结果：346 passed，1 failed（`test_audit5_and_phase16.py::test_system_loopback_reconnect_updates_name_and_clears_transient_notice` 时序抖动）。

| ID | 现状确认 | 修改 | 已改 @SHA |
|---|---|---|---|
| **ER1** | `freeze_screen_btn` 与 `core/i18n.py` 文本含 `⏸`/`▶` | 去掉文案中 `⏸`/`▶` 字符，仅保留 SVG 图标；新增 `test_er_1` 断言 | 已改 `@a235d3b` |
| **ER2** | `core/i18n.py` 英文标签含 `&` 被 Qt 当作助记符显示下划线 | 英文标签改用 `·` 分隔（不含 `_`/`//`/`&`）；同步更新 `test_turnkey_cubase_bass_theme.py` 并新增 `test_er_2` | 已改 `@a235d3b`、`@404b023` |
| **ER3** | `ResourceMonitorBar` 文本过长且 `emergency_stop_btn` 未锁定 `sizeHint` 宽度导致截断 | 胶囊改为宽屏 `G` 单位/窄屏隐藏 RAM/VRAM 仅保留状态徽标，`E-STOP` 锁定 `Fixed` 策略与 `sizeHint` 最小宽度（`<920px` 纯图标+tooltip/accessibleName）；新增 `test_er_3` | 已改 `@a235d3b`、`@404b023` |
| **ER4** | 实测 `main.py --simulate` 缓冲同步正常，截图 `0.0s` 为脚本未调 `update_capture_stats`；但 `p50` 因 `AnalysisSnapshot` 缺 `latency_ms` 恒为 `--` 且 `CPU` 误调全局 `psutil.cpu_percent` | 代码修复：`AnalysisSnapshot` 补 `latency_ms`（中位数 p50）、`CPU` 改为 `psutil.Process().cpu_percent` 按核数归一化 1Hz 更新、模拟源显示 `Simulated`；脚本补 `update_capture_stats`；新增 `test_er_4`（`analysis/worker.py` 改动已跑 A-BENCH 与 `realistic_mix` 确认 0 退化） | 已改 `@a235d3b` |
| **ER5** | `spec_plot` 未固定 X 轴范围且空状态无提示 | X 轴固定 `-30..0 s`、关闭 SI 前缀、中央加「开始捕获后显示」占位，截图脚本填入时频历史；新增 `test_er_5` | 已改 `@a235d3b` |
| **ER6** | `make_screenshots.py` 传入 `(12, 45)` 转置且未禁用 SI 前缀；tick stride 过大 | 关闭 `enableAutoSIPrefix`、X 轴 `-30..0 s`、`update_analysis` 规范化 `(frames, 12)` 方向、`stride <= 2`；新增 `test_er_6` | 已改 `@a235d3b` |
| **ER7** | `spectrum_widget.py` 紧凑卡片硬编码 `maxHeight=36` 裁切数值 | 移除 `36px` 限制并按紧凑模式缩放数值字号（14/13px）；新增 `test_er_7` | 已改 `@a235d3b` |
| **ER8** | 混音页空状态主按钮为 WAV 转 MIDI、含 `4X` 水印、右表无提示 | 主按钮改为「选最近 30 s 并 2-Stem 分轨」（联动 30s+2-Stem），WAV 转 MIDI 降为链接，移除 `4X` 水印，右表居中提示；新增 `test_er_8` | 已改 `@a235d3b` |
| **ER9** | `ACID_DARK.plot_region_rgba` 为深海军蓝 `(34, 17, 255, 34)` | 改为暗色主题 lime 半透明 `(206, 255, 24, 38)` / `#CEFF18`；新增 `test_er_9_10_11` | 已改 `@a235d3b` |
| **ER10** | `chroma_widget.py` 当 `relation_note` 为空时拼接多余 ` · ` | `relation_note` 为空时不拼接分隔符；新增 `test_er_9_10_11` | 已改 `@a235d3b` |
| **ER11** | `source_combo` 空列表时显示空白框 | 设置四语 i18n 占位文字「选择音源…」；新增 `test_er_9_10_11` | 已改 `@a235d3b` |
| **ER12** | Windows CI `offscreen` 缺 `msyh.ttc` 导致简体中文显示为方块 | `make_screenshots.py` 在 `win32` 显式 `addApplicationFont("msyh.ttc")` 并断言 `QFontDatabase.families()` 含微软雅黑/Segoe UI，CI 重拍确认中文无方块 | 已改 `@86bf444` |
| **ER13** | 多处文档与提示写「Windows 10 Build ≥ 20348」 | 统一改为「进程环回需要 Windows 11（Build ≥ 20348）；Windows 10 可用系统环回」（`README*.md` 按指示跳过，转由 PR #53 处理）；新增 `test_er_12_13_14` | 已改 `@404b023`、`@86bf444` |
| **ER14** | `rg "import soxr\|from soxr\|certifi"` 确认仓库源码 0 处直接导入 | 从 `THIRD_PARTY_NOTICES.md` 移除未直接引用的 `soxr` 与 `certifi`，标注 `NEEDS_TARGET` 待 Windows `dist/` 实测核对 | 已改 `@a235d3b` |
| **ER15** | 需用修复后界面重拍截图 | 已重拍 Linux `p2er_after_*.png`、Windows CI `p2er_after_*_win.png` 及 README `docs/images/listenscope_*.png`（5 张） | 已改 `@a235d3b` |

---

## 仓库维护（2026-11-23）

### 1. About、Topics 与合并自动删分支
- 已更新 `Ceph-learner/ListenScope` 描述为：「🎧 免费、离线的 Windows 练耳扒谱工作台：实时频谱与和弦调性识别，120 秒回溯 A/B 慢放循环，本地 AI 分轨与 MIDI 导出。」
- Topics 已设为：`music`, `ear-training`, `music-transcription`, `chord-detection`, `key-detection`, `audio-analysis`, `stem-separation`, `demucs`, `midi`, `wasapi`, `pyside6`, `windows`。
- 已开启 `Settings → Automatically delete head branches`（`--delete-branch-on-merge`）。

### 2. 分支备份与清理清单（共删除 39 个，保留 `main` 与 `docs/readme-zh-refresh`）
- **备份至私有库 `Ceph-learner/ListenScope-archive` 并 1:1 核对 SHA 后删除（12 个）**：
  `archive/internal-docs` (`13df0bf0f0`)、`backup/phase0-10-audit` (`b7938cbc64`)、`backup/phase0-13-audit3` (`c3f07bc5dc`)、`backup/phase0-phase1` (`1dbc91ce5b`)、`design/layout-review-20261117` (`4c62c63f49`)、`design/realtime-analysis-review` (`0d2d0afde1`)、`feature/ab-zero-crossing` (`7aa6ae7389`)、`feature/chord-practice-midi-audition` (`ff62a14dbd`)、`feature/drum-audition` (`d511bb47e1`)、`feature/drum-midi-export` (`3563623eea`)、`feature/local-chord-practice` (`3b902a62f8`)、`fix/help-hover-startup-flash-and-bootstrap` (`c06c7f2fd7`)。
- **已完全合入 `main` 直接删除（27 个）**：
  `docs/ai-memory-audit`、`feat/key-detection-upgrade`、`feature/appearance-presets`、`feature/live-playback-diagnostics`、`feature/settings-categories`、`feature/ui-polish-p2e`、`fix/ab-playback-diagnostics`、`fix/continuous-import-resampling`、`fix/cuda-wheel-preflight`、`fix/live-loopback-feedback`、`fix/live-output-overwrite-diagnostics`、`fix/live-output-ring`、`fix/live-practice-reliability`、`fix/live-rtf-hop-timing`、`fix/offline-stem-seams`、`fix/review-p2a-engine`、`fix/review-p2b-algo`、`fix/review-p2c-ui`、`fix/review-p2d-windows`、`fix/review-phase1`、`fix/review-ub34-waveform`、`fix/single-stem-midi-output`、`fix/stem-analysis-workflow`、`fix/synthetic-audio-audit`、`fix/ui-ux-polish-v1`、`perf/live-output-callback`、`release/v1.1-prep`。

### 3. CI 偶发失败根因与修复
- **失败用例**：`main@1ce38c9`（Run `45311282823`）、`#43`（Run `45310837871`）与 `#45`（Run `45311401035`）均在同一用例失败：`tests/test_audit5_and_phase16.py::test_system_loopback_reconnect_updates_name_and_clears_transient_notice`（`AssertionError: assert False is True`）。
- **根因**：该测试的 `_FakeStream.read()` 无延迟，在重连到 `Desk Speakers` 后，后台 `_capture_loop` 线程在数十微秒内即完成 3 次健康读取并调用 `set_error(None)` 清除了重连提示；主测试线程在 `read_chunk(timeout=0.05)` 唤醒后才轮询 `backend.get_stats()`，已错过瞬时提示窗口，导致 `saw_reconnect_msg` 为 `False`。
- **修复**：在测试中包装 `backend._stats.set_error` 记录有序状态迁移列表，确定性断言先出现含 `Desk Speakers` 的瞬时重连提示、随后在健康帧后被清除为 `None`，消除线程调度竞态且不弱化断言。

### 4. Dependabot 处置与规则收紧
- **已合并**：`#44`（`actions/upload-artifact` 4→7）、`#46`（`actions/checkout` 4→7）；`#45`（`actions/setup-python` 5→7）重跑通过后合并。
- **已关闭**：`#47`（`numpy` 2.x 未完成评估，已记入 `#33`）、`#48` / `#49` / `#51`（`winrt` 4.x 双平台 CI 失败）、`#50`（`setuptools` 双平台 CI 失败）。
- **配置更新**：`.github/dependabot.yml` 改为 `monthly`，`github-actions` 与 `pip` 各自用 `groups` 合并为单 PR，`open-pull-requests-limit: 2`，忽略 `numpy` 与 `winrt-*` 的主版本升级。
- **待公开仓库后执行**：开启 `main` 分支保护，要求 `pytest` 与 `pytest-windows` 均通过才可合并。

