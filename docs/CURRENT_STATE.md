# ListenScope 当前状态

## 项目与已实现范围

Windows 本地音乐分析与练习工作台。入口 [main.py](../main.py) 和 [GUI](../ui/main_window.py) 连接 [进程音频捕获](../audio/process_loopback.py)、[固定 PCM 环](../audio/ring_buffer.py) 和 CPU 分析。实现频谱、Chroma、和弦与 BPM、A/B 回放与导出。GPU 分轨和 CPU MIDI 分别用独立环境。实验性近实时实现位于 [streaming](../streaming)。

## 当前验证基线

[Windows 验收](WINDOWS_TEST_REPORT.md) 的第五轮记录对应 f03dbf1。Windows pytest 115 项通过，打包、短段离线 MDX 和直开 WAV 转 MIDI 已验证。QQ Music 暂停、恢复、切歌捕获基本通过，自动清理是否重复触发尚无充分事件记录。该报告与 [README](../README.md) 的历史说明时间不同，优先按对应 SHA、项目和证据判断。

## 已知问题与下一步

- 持续近实时在目标机上触发内存保护，未听到首段，真实延迟和长期是否累计未知。独立样本发现输出环在尾帧反复读取且游标不推进。优先为跨回调顺序与游标推进补回归，再验证输出与资源保护。
- 从历史分轨作业目录直开 WAV 可能覆盖同名 MIDI。补该路径的隔离测试。
- 补 SMTC 自动重置事件计数。Chroma 纵轴拥挤以及和弦级数待后续处理。

## 测试

在核心 Python 环境下运行 `python -m pytest -q --tb=short`。窗口测试可设置 `QT_QPA_PLATFORM=offscreen`。安装、打包与三个环境约束见 [PACKAGING](PACKAGING.md)。真实 QQ Music、GPU 和近实时测试分别核验。
