# Windows 11 实机复测总清单（各阶段共用）

- **目标硬件**：Windows 11 + NVIDIA GeForce RTX 5060 Ti (**8 GB VRAM**) + **16 GB RAM**
- **使用方式**：各阶段（Phase 1 / 2A / 2B / 2C / 3）凡判定为 `NEEDS_TARGET` 的条目均追加到此表；目标机实测后填写「实测结果」列并同步记录到 `docs/WINDOWS_TEST_REPORT.md`。

| ID | 前置条件 | 操作步骤 | 期望结果 | 实测结果 |
| --- | --- | --- | --- | --- |
| E1 | 已安装 `.venv-ai` 且存在 `UVR-MDX-NET-Inst_HQ_3.onnx` 权重 | 1. 运行 `.\.venv-ai\Scripts\python.exe -c "import inspect; from audio_separator.separator import Separator; print(inspect.signature(Separator.__init__))"` 核对参数名。<br>2. 运行 10s 440 Hz 48 kHz 正弦波真实 2-stem 分轨（`MdxOnnxTwoStemBackend().load_model(..., use_gpu=True)` → `separate_chunk(pcm, 48000)`），测各输出轨的 `shape`、采样率与 FFT 主频。 | 输出帧数等于 `480000`（10.00s），非静音轨主频在 `440.0 ± 2.0 Hz`，无末尾 0.49s 静音截断与块间增益跳变；若参数名不兼容则有 warning 日志且不崩溃。 | |
| U-B04 | Windows 11 已启用微软拼音等中文输入法；启动 `ListenScope.exe` 或 `.\.venv-core\Scripts\python.exe main.py` | 1. 切换至中文输入法，按 `Space` 测试播放/暂停，再依次测试 `L` / `[` / `]` / `-` / `=` / `0` / `T` / `M` / `Ctrl+B`。<br>2. 点击书签名称输入框或数值 SpinBox，输入含空格、字母 `l`/`t`/`m` 及 `-`/`=` 的文本。 | 播放/循环/调速等快捷键响应正常不被输入法截获；在输入框/数字框内打字时单键快捷键不误触，文本正常录入。 | |
| U-B21 | Windows 11 打开任务管理器 → 详细信息 → 勾选「GDI 对象」与「句柄」列；启动 `ListenScope.exe` | 1. 记录初始 GDI 对象数与句柄数。<br>2. 反复将主窗口最小化到托盘并还原（触发 `showEvent`）至少 10 次。<br>3. 退出程序。 | 每次还原后 GDI/图标句柄数保持稳定不随显示次数递增；退出后无残留进程或错误日志。 | |
