# 技术决策与失败经验

本文件记录不能随意更改的长期决策。每条标明证据来源。修改其中任何一条前，先在 [Windows 验收记录](WINDOWS_TEST_REPORT.md) 中找到新的实测依据，并同步更新本文件与 [当前状态](CURRENT_STATE.md)。

标记：**[实测]** 目标机已验证；**[代码]** 由源码或测试锁定；**[历史]** 来自提交说明或旧报告，未重新复测。

## 硬件与产品边界

| 决策 | 理由与证据 |
| --- | --- |
| 目标机固定为 Windows 11、RTX 5060 Ti（sm_120）**8 GB 显存**、**16 GB 内存**。文档和代码不得写成 16 GB 显存。 | [实测] [WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md) 各轮；[README](../README.md) 硬件规范。 |
| 通过 WASAPI 按进程环回捕获 QQ 音乐输出（Build ≥ 20348），失败时回退系统环回。不下载、解密或绕过 DRM。 | [实测] 第一至四轮，含 30 分钟连续捕获；[代码] [process_loopback.py](../audio/process_loopback.py)、[system_probe.py](../core/system_probe.py)。 |
| 全部本地离线运行，实时分析只用 CPU，不依赖 GPU。 | [代码] [analysis/](../analysis)；[README](../README.md)。 |

## 进程与环境隔离

| 决策 | 理由与证据 |
| --- | --- |
| 三个独立环境：`.venv-core`（Py 3.12，GUI/捕获/DSP）、`.venv-ai`（Py 3.12，torch 2.11.0+cu128 等）、`.venv-midi`（Py 3.11，Basic Pitch CPU）。Core 不得引入 torch/CUDA/TensorFlow。 | [实测] 第二至五轮三环境均通过 `pip check`；[PACKAGING](PACKAGING.md) 第 1 节；[listenscope_core.spec](../packaging/listenscope_core.spec) 排除列表。 |
| AI 分轨在子进程 Worker 中运行，同一时间只运行一个分轨 Worker。紧急停止时结束整个进程树并清理暂存。 | [代码] [job_manager.py](../ai/job_manager.py)、[worker.py](../ai/worker.py)；[实测] Worker 退出后显存回落（第二、四轮）。 |
| Basic Pitch 只能经独立 Py 3.11 解释器调用；打包版通过 [`run_external_python`](../core/paths.py) 隔离包内 `_internal` 的 DLL 和 PYTHONPATH。 | [实测] 第三至五轮打包版导出 120 音符 MIDI；[代码] 测试 [test_windows_defaults_and_midi_routing.py](../tests/test_windows_defaults_and_midi_routing.py)。 |
| AI 依赖安装必须使用 [constraints-ai-cu128.txt](../constraints-ai-cu128.txt)，以保住已安装的 torch/torchaudio 2.11.0+cu128 和 torchvision 0.26.0+cu128。onnxruntime-gpu 限定 `<1.27`。 | [实测] 第三轮发现 pip 解析 torchvision 时会替换 cu128 torch；[代码] [setup_windows.ps1](../scripts/setup_windows.ps1)。 |
| PySide6 限定 `<6.10`。 | [历史] [requirements-core.txt](../requirements-core.txt) 注释：6.12 存在 Signal.emit 引用计数回归。 |

## 资源保护与默认参数

| 决策 | 理由与证据 |
| --- | --- |
| 内存阈值：可用内存低于 5120 MiB 时告警，低于 3072 MiB 时拒绝新分轨，低于 2048 MiB 时紧急停止。 | [代码] [config.py](../core/config.py) `ResourceLimits`、[resource_manager.py](../core/resource_manager.py)；[实测] 第二轮最低可用约 2.4 GB 时未误触发急停。 |
| 离线分块 `long_audio_chunk_seconds=6.0`，HTDemucs 模型分段 `demucs_default_segment_sec=6`。MDX 的 `segment_size=256` 含义不同，应分开配置。用户已保存的自定义值优先。 | [实测] 第二至四轮 6 秒配置跑通二轨和四轨；[代码] [config.py](../core/config.py)、[models.py](../ai/models.py)。 |
| `PersistedSettings.schema_version` 保持 2，并兼容旧设置。 | [代码] [settings_store.py](../core/settings_store.py) 与对应测试。 |
| 环形缓冲固定 120 秒（48 kHz、立体声、float32），队列有界，禁止整首解码进内存。 | [代码] [ring_buffer.py](../audio/ring_buffer.py)、[config.py](../core/config.py)。 |

## 交互与输出约定

| 决策 | 理由与证据 |
| --- | --- |
| 保留手动「换歌重置」。SMTC 自动切歌重置只作为可关闭的附加功能（`auto_reset_on_track_change`）。 | [实测] 第四轮手动重置；第五轮自动重置出现横幅，但未排除重复触发。 |
| JSON 命令行输出保持 ASCII 安全，以兼容 GBK 控制台。 | [实测] 第一轮 GBK 问题已修复；[代码] [check_env.py](../scripts/check_env.py)、[probe_media_session.py](../scripts/probe_media_session.py)。 |
| MIDI 转录拒绝完整混音文件名，只用于分轨后的单轨。轻量回退时界面应显示实际使用的算法。 | [代码] [main.py](../main.py) `_on_open_single_stem_midi`、[midi_transcription.py](../analysis/midi_transcription.py)。 |
| 近实时分轨（[streaming/](../streaming)）是实验功能，默认关闭。 | [实测] 第五轮触发内存保护，持续播放尚未通过。 |

## 失败方案与教训

| 方案 | 结果与处理 |
| --- | --- |
| 首轮用临时 `sitecustomize.py` 修改 ORT 参数。 | 已废弃，不作为运行依赖。第二轮使用正常 ORT 配置跑通（[WINDOWS_TEST_REPORT](WINDOWS_TEST_REPORT.md) 第二轮）。 |
| 把 basic-pitch 放进 Py 3.12 的 `requirements-ai.txt`。 | 依赖无法解析，已迁到独立的 `.venv-midi`（Py 3.11）（提交 `51f4554`）。 |
| 不加约束地安装 AI 依赖。 | torchvision 解析会替换 cu128 torch。已改用 cu128 约束文件（`873db54`）。 |
| 打包 exe 直接启动外部 Py 3.11。 | 加载包内 `python312.dll` 和 `_socket` 发生冲突。由 `run_external_python` 隔离解决（`873db54`）。 |
| 在长路径目录安装 TensorFlow（`LongPathsEnabled=0`）。 | 安装失败。改用 `E:\LS-midi` 一类短路径（第三轮）。 |
| 在线下载 2.75 GB 的 torch wheel。 | 曾出现 0 字节停滞，**根因未定位**。可通过 `-CudaWheelDir` 改用本地官方 wheel（`f03dbf1`，第五轮已通过）。 |
