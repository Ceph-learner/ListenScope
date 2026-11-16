# 最新交接

- **结果**：本地音频导入使用固定输出采样网格，块边保留滤波所需的源样本，消除每块独立补零和独立向上取整。SoundFile 与 WAV 回退复用连续重采样路径，按顺序解码。WAV 回退成功时重写历史缓冲，避免保留主解码器已经写过的前段。[实现](../audio/ring_buffer.py)
- **证据**：基于 PR #13 合并提交 `6bd60e9a3cf7ae066332f80d2ee92a14e231014b`。分支 `fix/continuous-import-resampling`，代码证据 `9e827101883dc69541cf1cf061f07f694d1d9729`。两位 Worker 的建议和用量见 [协同报告](AI_COLLABORATION.md)。
- **专项验证**：Windows Core 中 `python -m pytest -q --tb=short tests/test_phase2_ring_buffer.py tests/test_audit4_regressions.py -k 'continuous or short_read'` 通过 13 项。另对 8–192 kHz 的 27 组输入逐样本比对，最大差值为 0。

## Windows 目标机复测

1. 按 [PACKAGING](PACKAGING.md) 将 Core 应用运行在目标机上，分别测光学效果关闭、小件和全部面板。每档用相同的音频源连续播放至少 60 秒，并切换频谱、和弦、混音和设置页面。记录 RAM、捕获溢出和实际听感。
2. 选择预设后修改字号和颜色，验证取消和重启恢复。用 100% 和常用缩放检查工具栏、紧急停止和 A/B 控件。
3. 近实时音频的目标机验收继续按 [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md) 进行。速度基准与运行统计按可播放步长计算 RTF（合并提交 `01dd09f`）。
4. 分别测试播放中 A/B 旧片段的原速回放、原速和慢速导出、离线分轨接缝。合成回放已验证其中一条重复帧路径，离线模型和声卡听感仍待记录。
5. 导入一段 44.1 kHz 音频，检查 A/B 跨整数秒边界的实际听感。当前仅完成合成文件与离屏测试。
