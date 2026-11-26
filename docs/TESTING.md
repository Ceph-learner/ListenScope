# 测试与基准指南（Testing Guide）

## 一、测试分层

1. **Core 自动化回归测试（`tests/test_*.py`）**
   - 在无 GPU、无真实声卡的 Core 环境中运行：
     ```bash
     QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short
     ```
   - 覆盖配置迁移（schema 2）、i18n 四语完整性、分析算法正确性、UI 布局与无障碍/遥测回归、子进程 Worker 协议与内存护栏模拟等。
   - **禁止放宽既有测试断言**。

2. **算法基准测试（`tests/bench/`）**
   - `tests/bench/algo_benchmark.py`（A-BENCH）：合成标准信号评估频谱、音准、和弦、调性、BPM 精度与延迟。
   - `tests/bench/realistic_mix.py`：贴近真实编曲混音的多轨合成基准。
   - 运行方式：
     ```bash
     python tests/bench/algo_benchmark.py --json
     PYTHONPATH=. python tests/bench/realistic_mix.py --json
     ```
   - **冻结规则**：`tests/bench/` 为只读冻结基准，任何开发任务不得修改基准用例以迎合算法改动；修改 `analysis/` 时必须对比改动前后两套基准输出，确保无退步。

3. **无硬件冒烟与真机 Windows 验收**
   - 无声卡冒烟：`python main.py --simulate --headless-smoke`。
   - 真实 Windows 11 + 声卡 + GPU 分轨 + Cubase 导入验收需在目标机手动执行，结果记录在 [WINDOWS_TEST_REPORT.md](WINDOWS_TEST_REPORT.md)（Linux/offscreen 结果不得写成 Windows 实机已验证）。

## 二、如何编写回归测试

- UI 测试须兼容 `QT_QPA_PLATFORM=offscreen`，避免依赖真实音频设备或系统弹窗阻塞。
- 涉及 `settings` 的测试须使用临时目录（`tmp_path`），不读写仓库根目录配置。
- 涉及 AI/MIDI 子进程的测试可使用 `tests/conftest.py` 中的轻量模拟环境或 mock，不依赖下载外部模型权重。

## 三、调试环境变量与诊断命令

- `LISTENSCOPE_DEBUG_RESTART_AFTER_S=<秒>`：仅在显式设置时生效（默认未启用）。主窗口显示后在指定秒数后调用一次 `restart_application()` 并记录 warning 日志，用于真机验证无需先完成一键配置即可触发「立即重启」；启动新实例前会自动从子进程环境中移除该变量，避免无限重启。
- 默认播放设备热切换诊断（Windows）：
  ```bash
  python -m audio.system_loopback --probe-default [--seconds 15]
  ```
  每秒通过 `IMMDeviceEnumerator::GetDefaultAudioEndpoint` 打印一次当前时间、`HRESULT`、默认渲染端点 ID 与设备名，用于在目标机独立验证默认设备切换检测是否工作（不依赖捕获流）。

