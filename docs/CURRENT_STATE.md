# ListenScope 当前状态

证据基线和检出分支记录在 [HANDOFF.md](HANDOFF.md)。功能清单见 [REQUIREMENTS](REQUIREMENTS.md)，长期约束见 [DECISIONS](DECISIONS.md)。

## 项目与已实现范围

ListenScope 是 Windows 本地音乐分析与练习工作台。入口 [main.py](../main.py) 和 [GUI](../ui/main_window.py) 连接以下模块：

- [进程音频捕获](../audio/process_loopback.py)
- [固定 PCM 环](../audio/ring_buffer.py)
- CPU 分析：频谱、Chroma、和弦与 BPM
- A/B 回放与导出

GPU 分轨和 CPU MIDI 各用独立环境。实验性近实时分轨位于 [streaming](../streaming)，默认关闭。软件版本 `0.2.0`（[pyproject.toml](../pyproject.toml)）。

## 当前验证基线

- **目标机**：[Windows 验收](WINDOWS_TEST_REPORT.md) 第五轮对应 `f03dbf1`。
  - Windows pytest 115 项通过。
  - 打包、短段离线 MDX、直接打开 WAV 转 MIDI 已验证。
  - QQ Music 暂停、恢复、切歌时捕获基本正常。自动清理是否重复触发，尚无充分的事件记录。
  - 之后的提交只改文档、AI 指令和 CI，没有改软件代码，目标机未重测。
- **云端 Linux**：2026-11-15 在 `6d9ade0` 上运行 `QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short`，115 passed。环境为 Debian 12、Python 3.11.2。仅安装 [requirements-core.txt](../requirements-core.txt) 和 pytest 的全新 venv 结果相同。
- 该报告与 [README](../README.md) 的历史说明写于不同时间，有出入时以对应 SHA 和证据为准。
- **GitHub**（2026-11-15 查询）：没有 Issue、PR、Release，也没有版本标签。`*-backup` 标签和 `backup/*` 分支是早期阶段的快照。CI 见 [DEVELOPMENT](DEVELOPMENT.md)。

## 已知问题与下一步

1. **近实时**：在目标机上启动即触发内存保护，没有听到首段，真实延迟和长期是否累积未知。
   - 代码已确认：[`pull_mixed_block`](../streaming/live_separator.py#L810-L835) 每次都返回最新的 `take` 帧，不推进读游标，也不减少 `_out_available`，所以会反复读出尾帧。
   - 推断（待目标机确认）：主循环在资源状态为 WARNING 时就会自动停止（[live_separator.py](../streaming/live_separator.py#L843-L850)），WARNING 包括可用内存低于 5120 MiB（[resource_manager.py](../core/resource_manager.py)）。这可能是 16 GB 机器上触发保护的原因。
   - 建议：先为跨回调的顺序消费和游标推进补回归测试，再验证输出与资源保护。
2. **单轨 MIDI 覆盖同名文件**：直接打开的 WAV 位于 `work_dir`（历史分轨作业目录）内时，[`_resolve_intermediate_midi_path`](../main.py) 返回 `src.with_suffix(".mid")`，会覆盖同名 MIDI（代码已确认）。需要补该路径的隔离测试。
3. 为 SMTC 自动重置补事件计数。Chroma 纵轴拥挤、和弦级数显示待后续处理。
4. 在线下载 torch wheel 停滞，根因未定位；本地 wheel 路线可用。

## 测试

见 [DEVELOPMENT](DEVELOPMENT.md)。在 Core 环境下运行 `python -m pytest -q --tb=short`，窗口测试设置 `QT_QPA_PLATFORM=offscreen`。安装、打包和三个环境的约束见 [PACKAGING](PACKAGING.md)。真实 QQ Music、GPU 和近实时功能要在目标机上分别验证。
