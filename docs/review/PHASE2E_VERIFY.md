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
| **E1** | `CONFIRMED` | `test_e1_topbar_single_row_le_56px_and_idle_estop_neutral` | 1366×768 下顶栏仍为双行且含 `_skin_badge` / `_shortcut_pill`；AI 空闲时 E-STOP 仍为红底。<br>改为单行 `<= 56 px`：左侧品牌/可拉伸音源/唯一实心主按钮(开始停止捕获)/电平小表/冻结图标；右侧合并资源胶囊/空闲隐藏 AI 胶囊/明暗/快捷键/设置图标/中性描边 E-STOP(AI 运行时红底脉冲)/窗口按钮；主题名移入设置页。 |
| **E2** | `CONFIRMED` | `test_e2_no_double_slash_in_interactive_buttons_or_tabs_and_5_tabs_fit_1093` | 实测 5 个标签页全含 `//`（如 `// 01 SPECTRUM // 实时频谱`），7 个可见按钮含 `//`（如 `CAPTURE_START // 开始捕获`）。<br>按钮/标签页/下拉仅显示当前语言文字，工程代号仅保留在卡片 eyebrow 或 tooltip；1093 宽下 5 个标签页无滚动完整显示。 |
| **E3** | `CONFIRMED` | `test_e3_footer_is_real_24px_status_bar_not_decorative_barcode` | `ui/acid_style.py` 仍渲染装饰性 `85/15_ANTI_FATIGUE: OK :: ZERO_GLOW: TRUE` 与条形码。<br>改为 24 px 真实状态栏：版本号（W9）、捕获源/48 kHz、分析周期 p50 (ms)、缓冲时长、CPU%、右侧「减少动效」开关；荧光底仅 Acid 预设使用，条形码默认关闭。 |
| **E4** | `CONFIRMED` | `test_e4_visible_help_badges_le_10_per_page_and_f1_help_supported` | 实测和弦页整窗可见 `HelpBadge` 为 **11 个**（> 10）且缺 F1 焦点控件帮助。<br>每个卡片/区块仅保留 1 个 `?`，控件级说明转为 tooltip（内容不丢），补充 `F1` 快捷键打开当前焦点控件帮助。 |
| **E5** | `CONFIRMED` | `test_e5_mixer_empty_state_shows_le_3_disabled_buttons` | 实测分轨前混音页可见禁用按钮 **12 个**（> 3）。<br>分轨前折叠依赖分轨结果的控件，只显示空状态引导卡（「① 选中片段 → ② AI 2-Stem 分轨」+ 主按钮），空表格居中提示与操作入口。 |
| **E6** | `CONFIRMED` | `test_e6_chord_card_deduplicates_primary_label_and_uses_stability_meter` | 实测和弦卡仍重复显示主和弦名并展示原始 `稳定度: ... \| 相关 ... \| 差 ...` 字符串。<br>主和弦名只显示一次，副行显示「级数 · 构成音 · 第二候选」，稳定度改为 5 格小表 + 文字等级（原始数值放 tooltip），调性卡同理。 |
| **E7** | `CONFIRMED` | `test_e7_charts_uniform_fft_ticks_left_alignment_and_perceptual_colormap` | 实测 FFT 纵轴仍为 `-100/-80/-60/-40/-20/0` 且三图左边距未对齐。<br>统一 10–11 px 等宽轴字与 >=3:1 对比度；明暗两套感知均匀时频图色图（首尾 CIELAB L* 差 >= 60%，配 dB 色标，来源登记 `THIRD_PARTY_NOTICES`）；FFT 纵轴固定 `0 / -30 / -60 / -90 dB`；三图左边距对齐 ±2 px。 |
| **E8** | `CONFIRMED` | `test_e8_unified_lucide_icons_registered_and_no_unicode_window_buttons` | 实测 `ui/assets/icons/ICONS.md` 不存在，窗口按钮仍用 Unicode 字符 `□ ❐ × −`。<br>统一使用 Lucide SVG 图标置于 `ui/assets/icons/` 并在 `ICONS.md` 逐一登记；运行时按主题替换 `currentColor`；窗口按钮改为 SVG 图标（46×32，关闭悬停 `#C42B1C`）。 |
| **E9** | **`PENDING`** | *（暂不写断言，待仓库主人选定图标概念稿 A/B/C 后再实现）* | 保持 `PENDING`。选定后精修 SVG/16px 简化版、生成多尺寸 `.ico` + 托盘单色版 + 1280×640 社交预览图、完成竞品相似度比对写 `docs/design/ICON.md` 并归档旧图标至 `docs/design/legacy/`。 |
| **E10** | `CONFIRMED` | `test_e10_design_doc_and_design_sheet_cli_exist` | 实测 `docs/DESIGN.md` 不存在，`scripts/make_screenshots.py` 尚不支持 `--design-sheet`。<br>新建 `docs/DESIGN.md` 记录间距 `4/8/12/16/24/32`、圆角 `0/2/4`、字号 `11/12/13/16/20/28`、字体栈（不打包字体）、明暗颜色 token 与组件状态，并扩展 `scripts/make_screenshots.py --design-sheet`。 |
| **E11** | `CONFIRMED` | `test_e11_default_ab_panel_single_row_le_120px_at_1366x768` | **W13 后复测**：虽然 `_ab_more_panel` 默认收起，但 1366×768 下 `_bottom_dock` 实测高度仍为 **172 px > 120 px**。<br>将「选最近 10/30/60 s」合并为分段按钮，「A±1s / B±1s」合并为两组微调按钮，书签与 AI 分轨移入「更多」，确保默认状态单行且 `<= 120 px`。 |
