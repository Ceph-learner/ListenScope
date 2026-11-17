# 最新交接

- 设置已采用 B「分类入口」方案，外观、资源保护、AI 与 MIDI、系统诊断分别走独立入口。使用原生 Qt 控件和随包分发的 Lucide 图标。切页保留编辑值，MIDI 快捷入口直达路径输入。宽窗两列，窄窗一列。

- A/B 启动前区分全零选区、过期和已重置的音频历史，保留微弱有效信号。回放过程中发现历史重置便停止。Windows 图标已接入 Qt、任务栏分组及 PyInstaller，实际打包图标和目标机固定图标待验收。
- 换歌重置与 DSP 更新互斥，重置后的和弦分析从新采集帧开始。主动导入已解码文件仍可立即分析，旧缓冲继续可用于 A/B。
- 现有设置表单可以在较低窗口滚动，MIDI 快捷入口会把解释器字段滚动到视口。三种设置重排方案在浏览器原型中供评审，选定后再重排原生设置结构。

- 原生 Qt 已集成 A 工作台、B 双栏扒谱（默认）和 C 练习优先。设置入口为「外观主题 → 界面布局」。切换复用混音和波形实例，保留 A/B 状态。横轴可用滚轮、放大缩小按钮和总览控制。

## 分轨分析与练习界面预览（2026-11-17）

- 基于实机反馈提交 `8de56f4622074d25aa2c174087fafcbeb85b57c1`。公司机使用原生 Qt 离屏窗口与合成素材。实际目标机音频设备、DPI、分轨和独立 MIDI 环境需另行验收。
- 弱信号分析使用已有分析配置的 −60 dBFS 静音门限，保留原频谱置信度检查。合成弱贝斯、弱和弦、全零和低电平噪声均有回归。混音页分别提示缺轨、低于静音门限、无稳定音符；MIDI 页可直接定位解释器设置。
- 新增分轨结果清除、局部 A/B 波形缩放与总览、设备打开失败提示、最近和弦名与级数切换、Chroma 刻度抽样、16 步鼓点查看。清除保留源 WAV 与历史缓冲，过滤被清除任务的晚到结果。
- Windows Core 离屏全量 169 项通过。原生 Qt 预览取 1280 × 920。额外检查确认 MIDI 设置进入正确页签，键盘焦点定位到解释器输入框。请求 1200 × 800 时，离屏窗口的实际高度被布局撑到 888。
- 待处理：A/B 纯静音及换设备场景的实机复现，缩放后的零交叉吸附，鼓点试听和 MIDI 导出，独立吉他分轨的资源与音色实测，本地练习和弦推荐。保留下文的现场复现和期望作为原始依据。

## 分轨深度分析与练习功能待办（2026-11-16）

记录于 2026-11-16。证据基线：`main` 上的 `aa1054af5a5c890d26c0dd4626bbebbd1f86137b`（贝斯独听与界面修订）。Windows 11，RTX 5060 Ti 8 GB，16 GB RAM。本轮只做只读复现及文档交接；未改源码、未重打包，未重跑全量 pytest。

### 已复现与接手起点

在同一台 Windows 机对现场 10 秒四轨的原始 WAV 调用 analyze_stems_offline。返回和声源 other + bass、调性 Unknown、和弦只有一段 N（静音）、Bass 音符 0；鼓检测返回 Kick 32 / Snare 38 / Hi-Hat 9 个候选。此前确认原贝斯轨约 −45.0 dBFS RMS 且能听到。这个最小复现不用再捕获或跑 GPU，适合下一轮先定位分析门槛；鼓候选数量未做人工标注对照。

---
name: project-continuity
description: Recover development context from repository instructions, Git, and handoff notes before beginning or resuming software work.
---

1. Read root and applicable nested AGENTS.md. Check git status --short --branch, git rev-parse HEAD, and recent commits. Identify the caller's branch, local edits and their relation to the requested work.
2. Read the project overview, current state and latest handoff using the links in AGENTS.md. Follow architecture, requirements, decisions and development links when relevant.
3. Treat handoff claims as leads. Verify the recorded baseline, changed paths, tests and constraints against the current tree, history and available CI evidence. Inspect commits since the recorded baseline. Label checkout, remote and historical release state separately.
4. Identify implemented scope, unresolved work and known risks. Preserve existing edits and respect the current request when choosing the next action. Continue with the requested work.

公司电脑没有原 WAV 时，可以先用任意合法测试素材完成四轨，保留原混音和各轨 WAV；然后在 Windows Core 环境对这些 WAV 调用 [`analysis/stem_analyzer.py`](../analysis/stem_analyzer.py) 的 `analyze_stems_offline`。同一组输入对照原增益、诊断性增益及真正的全零信号。记录 RMS、每帧门限判定、有效帧、调性、和弦段与 Bass 音符；优先区分真实静音与有声但无法识别的片段。现场 WAV 不入库。修复后按 [开发文档](DEVELOPMENT.md) 跑专项回归与 Windows 全量测试，再用 GUI 复测。

### 按顺序处理

| 顺序 | 反馈 | 第一轮验证及完成条件 |
| --- | --- | --- |
| 1 | 深度分析的和弦候选显示静音，调性未知，Bass 无结果；MIDI 页空 | 用现场同一组 WAV 直接调用分析器，记录分析源、原混音及各轨的窗口电平、静音判定、有效帧和音符数。现有四轨和声分析使用 65% other + 35% bass；检查弱信号是否被判为静音、调性是否因有效帧不足。对比原音量与诊断性增益的同一输入，再补弱音及真静音回归。输出区分“缺轨”“确实静音”“信号弱或置信度不足”“尚未转录”，并显示分析源。 |
| 2 | MIDI 提示缺 Python，深度分析和 MIDI 的关系不清楚 | MIDI 转录需单独点轨道的「转 MIDI」。本机已存在独立 Python 3.11 环境，在正在使用的 exe 中选该解释器并验证。复测 Bass 的 MIDI 钢琴卷帘、有效音符与重启恢复。应用提示应能直接带用户到设置。鼓点 MIDI 与有音高单轨转录应分开实现。 |
| 3 | 底部 A/B 有时按播放无声 | 分别复现暂停后选进纯静音、书签被 120 秒环形缓冲覆盖、正在捕获时回放旧区间、输出设备切换。记录实际 A/B 时间、绝对帧范围、选区电平、播放游标、设备及错误。预期有音有声，无法播放则明确提示原因。 |
| 4 | 分轨后缺少清除结果 | 加「清除分轨结果」的设计。清除本次轨道、分析、MIDI 预览和播放状态，阻止旧后台任务结果回填；保留原 WAV、已导出文件和 120 秒捕获缓冲。 |
| 5 | A/B 横轴需要精确缩放 | 当前历史波形关闭了鼠标缩放。用 pyqtgraph 的 ViewBox 做横轴缩放和平移、回到 120 秒总览，缩放时按可见范围重采样峰谷包络，保留 A/B 拖选。支持时间标签、A/B 标记和小步进。极近时再考虑波形采样点、峰谷或零交叉吸附。附查普通窗口 Chroma 热图音名重叠。 |
| 6 | 最近和弦进行可用级数显示 | 设置选择「和弦名 / 罗马数字 / 两者」。沿用已有级数计算，明确按当前有效调性显示，遇到未知调性保留和弦名；检验切歌、调性候选和 Capo 移调。 |
| 7 | 鼓的展示再直观些，吉他轨和节奏推荐 | 把已有 Kick / Snare / Hi-Hat 事件画成 16 步三行网格，支持按需试听和导出独立鼓 MIDI。将吉他分轨、从吉他轨估计节奏、按 BPM/拍号推荐扫弦或分解节奏拆为独立任务。现有四轨的「其他」可能含吉他，不能当成独立吉他。仅把六轨 htdemucs_6s 做候选，先测目标机内存/显存、串音与音色。 |
| 8 | 推荐常见和弦进行，或给出与片段搭配的几个候选 | 先做随软件分发的本地罗马数字模板库，从调性、已识别和弦前缀、拍号与节奏筛选，再转成当前调的和弦、试听和导出 MIDI。区分「原曲检测」「可能的延续」「练习推荐」，不确定时显示依据。可借鉴公开统计接口的排序思路；仅将来源与可再分发授权明确的数据纳入内置库。 |

### 已核对的说明

- Demucs seg 是四轨模型单次推理使用的时间窗口，默认 6 秒，不是 A/B 长度或最后导出时长。更短通常有助于降低显存负担，暂保留已实测默认值。
- 两条 proctap INFO 是两次捕获初始化时确认音频已是 48 kHz / float32，因此跳过格式转换。它们没有报错，也不足以判定选区播放或深度分析是否正常。
- MIDI 使用独立的 Python 3.11 环境，按 [安装说明](PACKAGING.md) 准备后，在「设置 / 系统状态 → 资源安全阈值与 AI 配置 → 独立 CPU MIDI Python 路径」选择 `.venv-midi\Scripts\python.exe`，再点「验证 MIDI 环境」。

### 初步参考

- [Demucs 官方仓库](https://github.com/facebookresearch/demucs) 与 [六轨发布说明](https://github.com/facebookresearch/demucs/blob/main/docs/release.md)
- [Spotify Basic Pitch](https://basicpitch.spotify.com/about)
- [pyqtgraph ViewBox](https://pyqtgraph.readthedocs.io/en/latest/api_reference/graphicsItems/viewbox.html)
- [Hooktheory 的和弦转移 API](https://www.hooktheory.com/api/trends/docs)

## 贝斯独听和界面复测（2026-11-16）

- 基线为 `218e2c9e03702a944476551a1bf158e7d2e04a7b`。`audio/playback.py` 只在贝斯独自出声时给监听 +12 dB，并平滑限制接近满幅的峰值。`ui/mixer_widget.py` 提供开关，缺轨时禁用相应独听。`ui/main_window.py` 强化复选框选中态，提示 GPU 是否就绪。
- 在 Windows Core 设置 `QT_QPA_PLATFORM=offscreen`、`PYTHONUTF8=1`，运行 `python -m pytest -q --tb=short`，165 项通过。新 PyInstaller 包短时启动正常。现场 10 秒 HTDemucs GPU 四轨和贝斯原音量及 +12 dB 对照详见 [Windows 验收报告](WINDOWS_TEST_REPORT.md)。
- 后续复测普通窗口 Chroma 纵轴、较长片段的离线分轨接缝和有足够 RAM 时的持续近实时播放。

## 上一次交接

## 最新本机验收（2026-11-16）

- 目标源码 `b58c758d38d13e6bb58504b3f6e874994cf6e3c4`。Git 直连超时，本机使用 `f03dbf1` 和逐项核对 Git blob SHA 的 51 个变更文件重建测试目录。
- Windows Core 以 `PYTHONUTF8=1`、`QT_QPA_PLATFORM=offscreen` 运行 `python -m pytest -q --tb=short`，164 项通过。打包启动、44.1 kHz 导入与原速导出逐样本比对、半速导出、原速试听与三档外观各 60 秒捕获已验证。详见 [Windows 验收报告](WINDOWS_TEST_REPORT.md#第六轮-windows-首轮复测--b58c758--2026-11-16)。
- 已观察到和弦相对级数及一次自然切歌的一次重置日志。普通窗口 Chroma 热图纵轴仍重叠。下一轮先复查小窗口和 DPI，然后在可用 RAM 足够时复测真实离线与近实时分轨。继续检查录制时回放旧片段、累计溢出和 MIDI 路径隔离。

## 上一轮开发交接

- **结果**：本地音频导入使用固定输出采样网格，块边保留滤波所需的源样本，消除每块独立补零和独立向上取整。SoundFile 与 WAV 回退复用连续重采样路径，按顺序解码。WAV 回退成功时重写历史缓冲，避免保留主解码器已经写过的前段。[实现](../audio/ring_buffer.py)
- **证据**：基于 PR #13 合并提交 `6bd60e9a3cf7ae066332f80d2ee92a14e231014b`。分支 `fix/continuous-import-resampling`，代码证据 `9e827101883dc69541cf1cf061f07f694d1d9729`。两位 Worker 的建议和用量见 [协同报告](AI_COLLABORATION.md)。
- **专项验证**：Windows Core 中 `python -m pytest -q --tb=short tests/test_phase2_ring_buffer.py tests/test_audit4_regressions.py -k 'continuous or short_read'` 通过 13 项。另对 8–192 kHz 的 27 组输入逐样本比对，最大差值为 0。

## Windows 目标机复测

1. 按 [PACKAGING](PACKAGING.md) 将 Core 应用运行在目标机上，分别测光学效果关闭、小件和全部面板。每档用相同的音频源连续播放至少 60 秒，并切换频谱、和弦、混音和设置页面。记录 RAM、捕获溢出和实际听感。
2. 选择预设后修改字号和颜色，验证取消和重启恢复。用 100% 和常用缩放检查工具栏、紧急停止和 A/B 控件。
3. 近实时音频的目标机验收继续按 [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md) 进行。速度基准与运行统计按可播放步长计算 RTF（合并提交 `01dd09f`）。
4. 分别测试播放中 A/B 旧片段的原速回放、原速和慢速导出、离线分轨接缝。合成回放已验证其中一条重复帧路径，离线模型和声卡听感仍待记录。
5. 导入一段 44.1 kHz 音频，检查 A/B 跨整数秒边界的实际听感。当前仅完成合成文件与离屏测试。
