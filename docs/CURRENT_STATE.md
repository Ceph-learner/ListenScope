# ListenScope 当前状态

证据基线和检出分支记录在 [HANDOFF.md](HANDOFF.md)。功能清单见 [REQUIREMENTS](REQUIREMENTS.md)，长期约束见 [DECISIONS](DECISIONS.md)。

## 项目与已实现范围

ListenScope 是 Windows 本地音乐分析与练习工作台。入口 [main.py](../main.py) 和 [GUI](../ui/main_window.py) 连接以下模块：

- [进程音频捕获](../audio/process_loopback.py)
- [固定 PCM 环](../audio/ring_buffer.py)
- 实时 Chroma 页的「练习和弦」根据最近和弦排列本地大小调模板，支持手动选调、Capo 指型显示、旋律通道 `.mid` 导出（[`export_chord_progression_midi`](../analysis/chord_practice.py)）与本地 CPU 合成试听（[`render_chord_progression_preview`](../analysis/chord_practice.py)，复用 [`DrumPreviewPlayer`](../audio/drum_preview.py) 并与 A/B、混音、节拍器、鼓试听及系统环回/近实时互斥）。已通过自定义 `_PracticeTableDelegate` 消除 `#practiceTable` 第 0 行焦点框缩进并与表头对齐；同时为主音高增加轻量 90ms `QVariantAnimation` 准音刻度条（`TuningCentsBar`，全程零 `QGraphicsEffect`）并在复杂控件旁补充 `[?]` 悬浮/点击说明徽标（`HelpBadge`）。

- **全链路贝斯基频与转调提示**：[`analyze_bass_stem`](../analysis/stem_analyzer.py) 采用 `[28 Hz, 350 Hz]` FFT-YIN (CMNDF) + 2 倍谐波防跃变验证，精确测量低至 `B0`/`E1` 的音名、实音/移调 MIDI 编号、中心频率及时间戳，并对半程根音重心迁移给出疑似转调提示（联动混音摘要与 Chroma `key_relation_lbl` 警告色调）。

- **Cubase 兼容标准 MIDI 规范化**：和弦进行、鼓点与单轨 Basic Pitch 转录统一接入 [`analysis/midi_common.py`](../analysis/midi_common.py)，输出 SMF Type-0 (`480 TPB`)、Tick 0 英文轨名/拍号/BPM/等音映射 `key_signature`/Controller Reset (`CC 121=0`, `CC 64=0`, `pitchwheel=0`) 及 GM 音色号，并裁切重叠且确保 `note_off` 先于 `note_on`。

- A/B 历史波形支持横向缩放。停止 A/B 后可点击「贴近零点」，在每个已选边界的 ±5 ms 内查找更安静的实际播放边缘。

- 深度分轨的「鼓点」页支持导出独立鼓 MIDI，以及最多 8 秒合成试听。沿用检测的击打时间，可在 DAW 中选择鼓音源；映射见 [MIDI Association 打击乐说明](https://midi.org/general-midi-lite)。

- CPU 分析：频谱、Chroma、和弦与 BPM；高频标签、x 轴缓冲与性能表格通过缓存与签名去重降低内存波动与重绘开销。
- **外观、主题、字体与同级便携存储**：支持 **黑夜 / 白天 / 跟随系统**（Qt 6.8 `colorScheme()` 实时响应系统明暗变化与图表高对比配色）、扫描本机已安装字体 + `11–20 px` 字号**实时预览**与「**恢复默认**」/取消安全回退；已集成可切换的第 5 档 **「酸性遥测 (`Acid Telemetry v2`, 预设 ID `acid_telemetry`)」** 无圆角工业双模预设（[`ui/acid_style.py`](../ui/acid_style.py)、`ui/assets/acid_*.svg` 与 [`packaging/listenscope_core.spec`](../packaging/listenscope_core.spec) 打包绑定），含 `ACID & VOID` 暗夜（`#0B0D0F` / `#CEFF18` / `#2211FF`）与 `CLINICAL_LIGHT` 临床浅色（`#EEF2F6` / `#00A878`）顶栏快切持久化、底部 **Clinical Paper 对比扩展坞（`#historyPaperDock`）**、45° 警示斜纹 [`HazardStripeBar`](../ui/acid_style.py)、动态 5 点置信矩阵 [`DotMatrixWidget`](../ui/acid_style.py)、准星/棋盘格/序号水印 [`AcidGraphicOverlay`](../ui/acid_style.py)、交互式 `[STATIC_LOCK]` 条码底栏 [`AcidBarcodeFooter`](../ui/acid_style.py)、`ChamferBadge` 切角铭牌与 `TelemetryHeader` 双语遥测头，隔离消除原生 Fusion 3D 凸起（不影响 `经典`/`Lenso`/`Codex`/`Claude Code`，切离完整隐藏 Acid 装饰与恢复样式，旧预设 ID 在 [`core/appearance.py`](../core/appearance.py) 静默迁移）。配置与导出（[`core/paths.py`](../core/paths.py)）优先保存在程序同级目录（不写 `C:\`），仅在只读目录回退用户目录；启动自动探测随包 `runtime/ai`、短路径 `m`、`.venv-*` 并在设置页提供一键自动配置与 Inno Setup 6 安装包（[`scripts/installer.iss`](../scripts/installer.iss)）。

GPU 分轨和 CPU MIDI 各用独立环境（Core 仍保持零 Torch/CUDA/TF，面向目标基线 Windows 11 · RTX 5060 Ti 8GB VRAM · 16GB RAM）。实验性近实时分轨位于 [streaming](../streaming)，默认关闭。软件版本 `0.2.1`（[pyproject.toml](../pyproject.toml)、[installer.iss](../scripts/installer.iss)）。

## 当前验证基线

- **`v0.2.1` 开发分支（`feat/acid-telemetry-v2-release`，基于 PR #24 合入后 `main`）云端 Linux 离屏验证**：在 Debian 12 / Python 3.11.2 / PySide6 6.8.3 / pyqtgraph 0.14.0 下运行 `QT_QPA_PLATFORM=offscreen pytest -q --tb=short`，全量 **`189 passed, 6 skipped`**（6 项为 Windows PowerShell / setup 专属测试），含定向回归 [`test_acid_telemetry_v2_preset_integration_topbar_sync_persistence_and_packaging`](../tests/test_turnkey_cubase_bass_theme.py) 与全仓库商标词正则扫描校验；已逐张目检真实 PySide6 离屏截图（`ACID & VOID` Tab 1–4、1280×800 窄窗与 `[STATIC_LOCK: ON]`、顶栏实测点击切入 `CLINICAL_LIGHT` 临床浅色、设置外观/MIDI 滚动区、外观/和弦练习弹窗与经典暗黑回退对照），并修正顶栏徽章 CSS 特异性掩蔽及 `SettingsDialog` 滚动区白底缺陷；GitHub Actions 新增 [release-windows.yml](../.github/workflows/release-windows.yml) 用于 Windows x64 Core 打包、便携重定位冒烟与 Inno Setup Release 生成，真机 Windows 11 音频/GPU/DAW/高 DPI 验收待目标机按 [HANDOFF](HANDOFF.md) 补测。
- **PR #24 合入基线（历史档案）**：PR #24 完成第 5 档双模工业主题首次集成与隔离扁平控件重塑（`189 passed, 6 skipped`）。
- **PR #23 合并前云端基线（`2a9c335`，历史参照）**：`QT_QPA_PLATFORM=offscreen pytest -q --tb=short` 共 `188 passed, 6 skipped`。

- **四轨监听复测**：Windows 现场 10 秒 GPU 四轨完成。贝斯独听默认 +12 dB，可关闭，原始 WAV 和导出保持原音量。混音页禁用缺轨独听，复选框选中态更清楚。Windows pytest 165 项通过。见 [Windows 验收报告](WINDOWS_TEST_REPORT.md)。

- **目标机第六轮**：`b58c758` 源码快照通过 164 项 Windows pytest。打包、44.1 kHz 导入与 A/B 导出、三档外观捕获、自然切歌和相对和弦级数已复测。普通窗口 Chroma 热图纵轴仍重叠，AI 分轨受 RAM 门槛限制未复测。详见 [Windows 验收报告](WINDOWS_TEST_REPORT.md)。

- **目标机**：[Windows 验收](WINDOWS_TEST_REPORT.md) 第五轮对应 `f03dbf1`。
  - Windows pytest 115 项通过。
  - 打包、短段离线 MDX、直接打开 WAV 转 MIDI 已验证。
  - QQ Music 暂停、恢复、切歌时捕获基本正常。后续版本已在诊断日志加入自动重置计数，待目标机复核。
  - 目标机尚未复测后续的分轨接缝、近实时播放、和弦级数与历史目录 MIDI 输出修复。
- **云端 Linux（历史基线）**：2026-11-15 在 `6d9ade0` 上运行 `QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short`，115 passed。环境为 Debian 12、Python 3.11.2。仅安装 [requirements-core.txt](../requirements-core.txt) 和 pytest 的全新 venv 结果相同。
- 该报告与 [README](../README.md) 的历史说明写于不同时间，有出入时以对应 SHA 和证据为准。
- **GitHub**：2026-11-16，CUDA wheel 预检经 [PR #10](https://github.com/Ceph-learner/ListenScope/pull/10) 合入 `main`（`29be3d4`）。前两次 CI 在 checkout 失败，第三次 [CI](https://github.com/Ceph-learner/ListenScope/actions/runs/43799776097/attempts/3) 通过 139 项。`*-backup` 标签和 `backup/*` 分支是早期阶段的快照。

## 已知问题与下一步

1. **近实时**：在目标机上启动即触发内存保护，没有听到首段，真实延迟和长期是否累积未知。
   - `bb3e588` 已修复 [`pull_mixed_block`](../streaming/live_separator.py#L810-L836)。输出按未读顺序消费，欠载时在末尾补静音，溢出时保留缓冲容量内最新的帧。UI 的输出缓冲时长按剩余未读帧计算。
   - `ea85d23` 增加回包序号检查，跳号时清空旧交叠尾部。真实播放启动及欠载恢复时先预缓冲到最多两个步长，受原有容量限制。等待会增加首段和恢复延迟，模型长期跑不过实时仍会出现静音。
   - `f1bd25f` 按捕获实际模式拒绝系统环回下的近实时监听，包括进程捕获退回系统环回。停止或切换捕获时自动关闭监听，基础捕获及分析仍可用。
   - 实验页与诊断摘要分别提供输入跳段、输出重缓冲和声卡报告欠载的次数，以及输出缓冲溢出丢弃的帧数。已播放的帧与捕获源失效时的主动清空不计入输出溢出。超长批次按两条轨的共同帧位置取尾段，避免错位。
   - `c7d37b4` 在声卡回调中直接写输出缓冲，回绕时分段读取。非默认增益复用至多 32 KiB 的工作区。本机合成回调验证了帧序、补静音和临时分配改善，真实设备听感待复测。
   - 速度基准和运行 RTF 都按新增可播放音频时长计算，重叠部分不会重复计入。短基准沿用生产块长。旧报告的 RTF 数值采用旧口径，需在目标机重跑才能直接对照。
   - 推断（待目标机确认）：主循环在资源状态为 WARNING 时就会自动停止（[live_separator.py](../streaming/live_separator.py#L843-L850)），WARNING 包括可用内存低于 5120 MiB（[resource_manager.py](../core/resource_manager.py)）。这可能是 16 GB 机器上触发保护的原因。
   - 下一步按 [HANDOFF](HANDOFF.md) 复测实际输出和资源保护。
2. **单轨 MIDI 输出隔离**：`607d4aa` 修复了从历史分轨作业目录打开 WAV 时覆盖同名 MIDI 的问题。直接打开和混音器内转录均经 [`_on_transcribe_stem_midi`](../main.py#L1298) 写入 `work_dir/midi/`，每次生成独立中间文件。专项测试验证重复转换与手动另存，目标机独立 MIDI 环境待复测。
3. **和弦级数与 SMTC**：Chroma 页显示当前和弦相对检测调性的罗马数字级数，Capo 同时移调后级数不变。热图纵轴使用较小的音名标签。SMTC 每次实际自动重置写一条含累计次数的日志，可在诊断包中排查同一切歌是否重复触发。
4. 在线下载 Torch wheel 停滞的根因未定位。本地 wheel 路线可用，`804a2a7` 增加 `-CheckCudaWheels` 文件名预检及安装前验证。见 [PACKAGING](PACKAGING.md)。
5. **离线分轨接缝**：`35add3c` 将相邻推理窗口在同一源帧位置的预测淡入淡出，输出帧数和既有分块参数保持。合成信号验证帧序和短尾块，真实模型听感待目标机复测。
6. **A/B 历史缓冲**：原速回放按缓冲实际返回的帧位置推进。导出保留已完成 WAV，遇到尚未读取的源帧被覆盖或历史重置时，报错并清理临时文件。音高搜索边缘采用两侧真实谱值插值，BPM 识别计入从静音开始的有效瞬态。
7. **本地音频导入**：分块重采样共用从文件起点计算的输出相位，并保留滤波器所需的边界样本。主解码器和 WAV 回退均顺序读取；解码中途回退成功时重新写入历史缓冲。

## 测试

见 [DEVELOPMENT](DEVELOPMENT.md)。在 Core 环境下运行 `python -m pytest -q --tb=short`，窗口测试设置 `QT_QPA_PLATFORM=offscreen`。安装、打包和三个环境的约束见 [PACKAGING](PACKAGING.md)。真实 QQ Music、GPU 和近实时功能要在目标机上分别验证。
