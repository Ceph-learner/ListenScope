# 功能需求与状态

状态以 [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md) 和代码为准。

- **已实测**：在目标机（Windows 11、RTX 5060 Ti 8 GB 显存、16 GB 内存）上通过，并注明轮次或提交。
- **部分通过**：目标机测试过，但仍有未通过项或证据不足。
- **仅自动化**：只有云端 Linux（offscreen）或 Windows pytest 覆盖，没有在目标机上手动验证。
- **未实现**：只是计划。

| 需求 | 状态 | 证据或缺口 |
| --- | --- | --- |
| 按进程捕获 QQ 音乐并回退到系统环回 | 已实测（第一至四轮） | 第四轮 30 分钟连续捕获：RSS 289–362 MiB，队列 0/64，溢出和欠载均为 0。 |
| 实时波形、FFT、Chroma、和弦、调性、BPM、音高与音准条 | 已实测（第一轮桌面） | [analysis/](../analysis)、[ui/](../ui)。 |
| 120 秒缓冲、A/B 循环、书签、0.5×–1.25× 不变调变速、练习 WAV 导出 | 已实测 A/B 循环和 0.5× 不变调（第一轮） | 书签和导出细节仅自动化。 |
| Capo 移调、Tap 定速、节拍器、预备拍 | 仅自动化 | `5df807d`、`81c361a`；相关测试见 [tests/](../tests)。 |
| 手动「换歌重置」 | 已实测（第四轮） | 一次点击清空 12 步历史。 |
| SMTC 自动切歌重置 | 部分通过（第五轮，`f03dbf1`） | 出现自动重置横幅，但缺少逐次事件日志，无法排除重复重置。[media_session.py](../core/media_session.py)。 |
| GPU 二轨分离（MDX-ONNX）和四轨分离（HTDemucs），6 秒默认 | 已实测（第二至五轮） | 30 秒音频：二轨约 9.5–10.7 秒，四轨约 4.3–4.9 秒；Worker 退出后显存回落。 |
| 内存保护（5120 / 3072 / 2048 MiB）和单 Worker | 已实测（第二轮未误触发），代码锁定 | [config.py](../core/config.py)。 |
| 打包版经独立 Py 3.11 调用 Basic Pitch 转 MIDI | 已实测（第三至五轮） | bass 导出 120 个音符；重启后设置保留。 |
| 直接打开已有单轨 WAV 转 MIDI | 部分通过（第五轮） | 可以导出可解析的 MIDI。历史作业目录内的同名 `.mid` 覆盖问题已修复并通过自动化测试，待目标机复测。 |
| 一键安装 `setup_windows.ps1`，含 cu128 约束、`-CudaWheelDir` 和短路径 MIDI 环境 | 已实测（第五轮本地 wheel 路线） | 在线下载停滞的根因未定位。 |
| PyInstaller 打包 Core | 已实测（第二至五轮） | [build_windows.ps1](../scripts/build_windows.ps1)、[listenscope_core.spec](../packaging/listenscope_core.spec)。 |
| 脱敏诊断 ZIP 导出 | 仅自动化 | [diagnostics.py](../core/diagnostics.py)。 |
| 近实时二轨分离（实验，默认关闭） | 未通过目标机验收 | 第五轮启动即触发内存保护，没有听到输出。监听要求按进程环回，退回系统环回时保留基础分析并拒绝监听。见 [CURRENT_STATE](CURRENT_STATE.md)。 |
| Chroma 纵轴标签与相对调性的和弦级数显示 | 已实现，待目标机复测 | 热图纵轴缩小音名标签。当前和弦按检测到的大调或自然小调显示级数，如 C 大调下 `Am` 显示 `vi`，Capo 移调后级数保持。 |
| 练习和弦弹窗 Row 0 对齐、合成试听与 `.mid` 导出 | 仅自动化 | [ui/chord_practice.py](../ui/chord_practice.py)、[analysis/chord_practice.py](../analysis/chord_practice.py)；覆盖 24 调、Capo 换算、互斥试听，待目标机声卡试听与 DAW 导入。 |
| 贝斯 FFT-YIN 最低音（含 `B0`/`E1` 防 8 度跃变）、MIDI 编号与转调提示 | 仅自动化 | [`analyze_bass_stem`](../analysis/stem_analyzer.py)、[mixer_widget.py](../ui/mixer_widget.py)、[test_turnkey_cubase_bass_theme.py](../tests/test_turnkey_cubase_bass_theme.py)；真实曲库贝斯分轨待目标机验证。 |
| 全路径 MIDI 规范化兼容 Steinberg Cubase (SMF Type-0 / `480 TPB`) | 仅自动化 | [midi_common.py](../analysis/midi_common.py) 覆盖和弦、鼓点及单轨转录；需在 Cubase 内拖入复验轨名、调号、CC 复位与无音符粘连。 |
| 黑夜 / 白天 / 跟随系统主题、本机字体扫描（`11–20 px` 实时预览）与恢复默认 | 仅自动化 | [core/appearance.py](../core/appearance.py)、[ui/appearance.py](../ui/appearance.py) 与图表高对比配色；Windows 11 系统主题实时切换及真机字体/DPI 待实测。 |
| 可切换「酸性遥测 (`Acid Telemetry v2`)」双模工业预设、顶栏快切、`[STATIC_LOCK]`、Paper 扩展坞与扁平隔离控件 | 仅自动化 | [`core/appearance.py`](../core/appearance.py)、[`ui/acid_style.py`](../ui/acid_style.py) 与 `ui/assets/acid_*.svg`（同步随 [listenscope_core.spec](../packaging/listenscope_core.spec) 打包）；含 `ACID & VOID` 暗夜 / `CLINICAL_LIGHT` 临床浅色 / `跟随系统`、`AppearanceDialog` 实时预览与 `经典`/`Lenso` 回退校验；Windows 打包 exe SVG 加载与 DPI 待实测。 |
| 轻量动效（`TuningCentsBar`）、`[?]` 悬浮/点击说明与切页/缓存防卡顿优化 | 仅自动化 | [help_badge.py](../ui/help_badge.py)、[chroma_widget.py](../ui/chroma_widget.py)；全程零 `QGraphicsEffect`，目标机连续刷新与 DPI 待复测。 |
| 同级便携存储、免手工探测运行时、`setup_windows.ps1 -SkipCore` 与 Inno Setup 安装包 | 仅自动化 | [core/paths.py](../core/paths.py)、[installer.iss](../scripts/installer.iss)、[build_windows.ps1](../scripts/build_windows.ps1)；Windows `ISCC.exe` 编译已在 [release-windows.yml](../.github/workflows/release-windows.yml) 集成，干净非 C 盘本机安装体验待实测。 |
| 自动化 CI 与 Core Release 构建 | 已提供 Linux offscreen 测试与 Windows Core 打包发布工作流 | [tests.yml](../.github/workflows/tests.yml) 运行 Linux offscreen pytest；[release-windows.yml](../.github/workflows/release-windows.yml) 运行 Windows pytest、PyInstaller 打包、便携重定位冒烟、ZIP 与 Inno Setup 安装包制作（真机声卡/GPU/Cubase 仍需手动验收）。 |
