# [审查 Phase 2H] retest4 遗留：系统环回不跟随默认设备（W1，阻塞发布）、和弦页窄窗、ai/ 目录及数据字段的中文残留、状态栏截断

来源：Windows 11 实机 retest4（`a31fdfb`，PR #64，125% 缩放，RTX 5060 Ti 8 GB / 16 GB）。
#64 已在实机通过的项：G1 运行时英文界面、G3「更多」面板、G4 4-Stem 中途急停（显存 1699→1374 MiB）、G6 两种启动方式各重启一次（都只重启一次）、播放中切换语言后时频图历史保留、托盘图标为三竖条、托盘退出 585 ms。
剩下的问题如下。H1 是功能缺陷，**发布 v1.1.0 前必须修好**；H2–H4 是界面问题。

## 规则（同前）
- 每条先写复现测试（`xfail(strict=True)`），修复后转正；不放宽旧断言；不改 `tests/bench/`。
- 遵守 AGENTS.md / DECISIONS.md；所有文案走 i18n（zh/en/ja/ko）。
- 分支 `fix/p2h-retest4`，走 PR，必须通过 pytest 和 pytest-windows；交接写到 `docs/review/PHASE2H_VERIFY.md`。

## H1 系统环回不跟随默认播放设备（W1，阻塞发布）
**实机复现**：音源选「系统环回」并开始捕获 → 在 Windows 声音设置里把默认输出从 XIBERIA 改成 `Realtek Digital Output` → 点系统的「测试」出声。ListenScope 一直显示 Silent，状态栏仍是旧设备，没有切换。retest3 也是同样结果。
**原因推测**：#40 做的「设备掉线后重连」只在旧设备报错时触发；切换默认设备时旧设备还在、不报错，所以不会重连。
**要求**：
1. 在系统环回模式下监听默认渲染设备的变化（`IMMNotificationClient.OnDefaultDeviceChanged`，flow=eRender，role=eConsole/eMultimedia；如果 COM 回调不好接，可以每 1 s 轮询一次默认设备 ID 作为兜底），变化后在 1.5 s 内重新打开新设备的环回流。
2. 切换过程中环形缓冲不清空（与手动换歌重置无关），A/B 选区保留；横幅提示「已切换到 <新设备名>」（四语），并写日志 `loopback default device changed old=... new=...`。
3. 状态栏和音源框显示当前实际捕获的设备名，不要只显示「[Fallback] System WASAPI Loopback」。
4. 进程捕获模式不受影响。
5. 测试：mock 掉默认设备查询，模拟设备 ID 变化，断言会重新打开到新设备、缓冲样本数不减少、横幅和日志都出现。

## H2 和弦页窄窗口（G2 实机未通过）
**实机**：125% 下 1093×566（逻辑 874×453），顶部有环回警告横幅，A/B 底栏是默认高度。第三张卡标题被截成「Tempo · Pitch · CPU Met」，右侧的 ÷2/×2 按钮被裁掉，Chroma 柱状图和热图完全不在可视区内；SMTC 提示被截成「you can still use」。
**CI 为什么通过**：`test_g2_*` 测的是没有横幅、可能也没有 A/B 底栏的状态，而真实布局里横幅约 35 px、底栏约 110 px，剩下给 Chroma 的高度几乎为 0。
**要求**：
1. 测试必须在「横幅可见 + A/B 底栏默认展开 + 1.25 倍缩放」的真实条件下进行（另测 874×453 逻辑尺寸）。
2. 紧凑高度（可用高度 < 某个阈值，根据 sizeHint 计算，不要写死数字）下：三张卡改为单行（只显示数值，标题和说明移到 tooltip）；「最近进行」和「Transpose / SMTC」两行合并为一行或折叠成按钮；**Chroma 柱状图必须完整可见**。热图在空间不够时可以放在柱状图下方，通过页内滚动查看，但不能被底栏完全遮住。
3. 第三张卡的 ÷2/×2 按钮在窄宽度下也必须完整可点。

## H3 英文界面仍残留中文
- 模型下拉框：`2-Stem 低显存默认…`（模型注册表多半在 `ai/` 下）。
- 任务队列的辅助名称：`[EmergencyStopped] 用户点击 紧急停止 AI`（这是传给 `emergency_stop()` 的 reason 字符串，作为数据存起来后原样显示了）。
**原因**：G1 的 AST 测试只扫描了 `ui/`、`main.py`、`core/`；另外，存进数据模型后再显示的字符串没有经过翻译。
**要求**：
1. AST 扫描范围扩大到 `ai/`、`analysis/`、`separation/`、`streaming/`、`audio/`（日志、注释和 docstring 除外）。
2. reason/status 这类会显示给用户的字段，改为存「稳定 key + 参数」，显示时再翻译；或者至少在显示的地方统一调用 `translate_text`。
3. 扩展运行时扫描测试：遍历所有可见的 QComboBox **下拉项**、QListWidget/QTableWidget/QTreeWidget 单元格，en/ja/ko 下都不能出现中文。

## H4 状态栏的设备名被硬截断
底部状态栏显示 `[Fallback] System WASAPI Loo · 48kHz`，被直接截断，没有省略号。改为省略显示（ElideRight 或 ElideMiddle），tooltip 显示完整名称；H1 改完后显示的是实际设备名。

## 下次实机复测补测
悬停查看 Chroma / FFT / 波形的说明气泡并截图；悬停在长环回设备名上，截图完整 tooltip；混音页空状态的说明卡（截图前先清空缓冲）。
