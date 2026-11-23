# Windows 11 实机复测总清单（各阶段共用）

- **目标硬件**：Windows 11 + NVIDIA GeForce RTX 5060 Ti (**8 GB VRAM**) + **16 GB RAM**
- **使用方式**：各阶段（Phase 1 / 2A / 2B / 2C / 3）凡判定为 `NEEDS_TARGET` 的条目均追加到此表；目标机实测后填写「实测结果」列并同步记录到 `docs/WINDOWS_TEST_REPORT.md`。

| ID | 前置条件 | 操作步骤 | 期望结果 | 实测结果 |
| --- | --- | --- | --- | --- |
| E1 | 已安装 `.venv-ai` 且存在 `UVR-MDX-NET-Inst_HQ_3.onnx` 权重 | 1. 运行 `.\.venv-ai\Scripts\python.exe -c "import inspect; from audio_separator.separator import Separator; print(inspect.signature(Separator.__init__))"` 核对参数名。<br>2. 运行 10s 440 Hz 48 kHz 正弦波真实 2-stem 分轨（`MdxOnnxTwoStemBackend().load_model(..., use_gpu=True)` → `separate_chunk(pcm, 48000)`），测各输出轨的 `shape`、采样率与 FFT 主频。 | 输出帧数等于 `480000`（10.00s），非静音轨主频在 `440.0 ± 2.0 Hz`，无末尾 0.49s 静音截断与块间增益跳变；若参数名不兼容则有 warning 日志且不崩溃。 | |
| U-B04 | Windows 11 已启用微软拼音等中文输入法；启动 `ListenScope.exe` 或 `.\.venv-core\Scripts\python.exe main.py` | 1. 切换至中文输入法，按 `Space` 测试播放/暂停，再依次测试 `L` / `[` / `]` / `-` / `=` / `0` / `T` / `M` / `Ctrl+B`。<br>2. 点击书签名称输入框或数值 SpinBox，输入含空格、字母 `l`/`t`/`m` 及 `-`/`=` 的文本。 | 播放/循环/调速等快捷键响应正常不被输入法截获；在输入框/数字框内打字时单键快捷键不误触，文本正常录入。 | |
| U-B21 | Windows 11 打开任务管理器 → 详细信息 → 勾选「GDI 对象」与「句柄」列；启动 `ListenScope.exe` | 1. 记录初始 GDI 对象数与句柄数。<br>2. 反复将主窗口最小化到托盘并还原（触发 `showEvent`）至少 10 次。<br>3. 退出程序。 | 每次还原后 GDI/图标句柄数保持稳定不随显示次数递增；退出后无残留进程或错误日志。 | |
| E2 | Windows 11 已打包 `dist/ListenScope/ListenScope.exe`（PyInstaller onedir）且存在 `.venv-ai` | 1. 启动打包版 `ListenScope.exe`，跑一次 2-stem AI 离线分轨与一次实时分轨（或基准测试）。<br>2. 在日志中核对 `.venv-ai` 子进程打印的 `sys.executable` 与 debug 日志记录的 `numpy.__file__`、`soundfile.__file__`、`onnxruntime.__file__` 路径，确认全部位于 `.venv-ai` 下且不含 `_internal` / `_MEIPASS`。 | `.venv-ai` 子进程成功启动并完成 2-stem 分离，无 `DLL load failed` / `ModuleNotFoundError`，且 `numpy`、`soundfile`、`onnxruntime` 的 `__file__` 路径均在 `.venv-ai\Lib\site-packages` 下而非打包目录 `_internal`。 | |
| A-H1 | Windows 11 正常运行 `ListenScope.exe` 或 `.\.venv-core\Scripts\python.exe main.py`（开启系统回环捕获） | 1. 依次播放标准 60 / 90 / 120 / 140 BPM 节拍器或鼓组音频各 15 秒，记录实时 BPM 面板读数。<br>2. 在有轻度 CPU 负载（如同时打开浏览器/拖动窗口，诱发 Windows 15.6 ms 定时抖动）下重复 90 / 120 BPM 测试，并记录诊断日志中的调度周期分布。 | 实时 BPM 读数与真实速度误差均在 ±1% 以内，不随 Windows 定时粒度或轻度掉帧产生比例漂移。 | |
| U-B03 | Windows 11 显示缩放分别设为 125%（1366×768 / 1280×800 等效）与 150%（1536×864 等效） | 1. 启动 `ListenScope.exe`，检查实时/和弦/混音三页所有按钮与文字是否完整显示不被裁切。<br>2. 将鼠标悬停最大化按钮或按 `Win+Z` 测试 Win11 Snap Layouts（半屏/四分屏）。 | 125%/150% 缩放下底部常驻层与「⋯ 更多」折叠层无裁切溢出，Win11 Snap Layouts 正常弹出并可贴靠。 | |
| U-FX3 | Windows 11 设置 → 辅助功能 → 视觉效果 → 关闭「动画效果」 | 1. 关闭系统动画效果后启动 `ListenScope.exe`。<br>2. 观察焦点环、跑马灯、Tab 下划线与遥测微动画状态；悬停 HelpBadge 约 0.5 s 检查延迟，触发 ok/info 与 warn/error 横幅。 | 系统关闭动画时默认不播放装饰动效且焦点环仍清晰可见；HelpBadge 悬停约 450 ms 后弹出；ok/info 横幅 6 s 自动收起，warn/error 常驻。 | |
| U-B22 | Windows 10（或禁用 DWM 圆角环境）启动 `ListenScope.exe` | 1. 在普通/最大化切换状态下观察主窗口四角边缘与标题栏。 | 无锯齿状多边形遮罩毛边，四角渲染干净（抗锯齿圆角或干净直角）。 | |



