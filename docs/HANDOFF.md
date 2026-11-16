# 最新交接

- **结果**：[`setup_windows.ps1`](../scripts/setup_windows.ps1) 新增 `-CheckCudaWheels`。默认按 Py3.12 x64、cu128 和配置版本检查本地三件套的文件名标签，成功时列出匹配文件。该命令不启动 Python 或 pip。普通模式也会先检查给定目录和本地 wheel，再创建或更新环境，缺少部分文件时保留在线回退。
- **基线与分支**：PR #9 的合并提交 `ac093fd34373b4bef7a762178e58fb395767f0b6`。预检代码与测试提交 `804a2a7681dcac618d565e27ce025aa32f123bb3`，分支 `fix/cuda-wheel-preflight`。
- **约束**：预检只检查文件名及参数匹配，文件完整性、传递依赖、驱动和 GPU 仍需正式安装验证。原有三环境隔离、cu128 约束和在线索引沿用。参见 [安装步骤](PACKAGING.md)。
- **协作**：Command Code GOAT 负责完整文本脚本方案。OpenCode Go V4 Pro 独立设计兼容和异常路径验证。各一次成功，无重试。详见 [协同报告](AI_COLLABORATION.md)。
- **验证**：Windows，Python 3.11.17，Core 环境位于 ASCII 路径，`QT_QPA_PLATFORM=offscreen`。PowerShell 合成复现旧脚本在坏目录前调用安装。修复后 `python -m pytest -q --tb=short tests/test_windows_defaults_and_midi_routing.py -k cuda_wheel` 通过 6 项，全量 `python -m pytest -q --tb=short` 通过 139 项。
- **待验证**：目标机实际 cu128 三件套、GPU 推理、原生声卡持续监听。在线下载停滞的根因仍待查。

## Windows 目标机复测

1. 检出包含 `804a2a7` 的提交，运行 `pwsh -NoProfile -File scripts\setup_windows.ps1 -CheckCudaWheels -CudaWheelDir E:\cuda_wheels`。确认三条匹配。用另一份缺项目录运行，应列出缺少的 wheel 并返回非零。
2. 按 [PACKAGING](PACKAGING.md) 在目标机用真实 wheel 执行正常安装，检查 `pip check`、安装版本和 GPU 基准。在线停滞时记录实际命令进度与原始错误。
3. 启动应用，在 QQ 音乐以按进程环回监听 60 秒，尝试默认和非默认增益、暂停恢复及切换捕获。导出诊断包，记录 RTF、缓冲、输入跳段、输出溢出帧、重缓冲和设备欠载。离线分轨试听 6 秒及 12 秒接缝。把实际提交和结果写入 [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md)。
