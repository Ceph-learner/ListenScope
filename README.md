# ListenScope

完全免费、离线、本地运行的 Windows 音乐分析与扒谱辅助工具（当前已完成 **Phase 0 环境与资源监控基础** 与 **Phase 1 Windows WASAPI 音频捕获 PoC**）。

## 硬性目标硬件约束（不可误写）

- **目标系统**: Windows 10 / 11 (20H1+, Build >= 19041)
- **GPU**: NVIDIA GeForce RTX 5060 Ti (Blackwell, `sm_120`)
- **GPU 显存**: **8GB VRAM**（非 16GB VRAM）
- **系统内存**: **16GB RAM**

所有默认资源策略均以 **8GB VRAM + 16GB RAM** 为硬边界：
- 实时基础分析默认仅使用 CPU，不加载 PyTorch。
- 音频队列与监测历史均为固定有界上限，禁止无限增长。
- 后续阶段 AI 分轨将在独立子进程中严格串行运行（每次最多 1 个模型、1 个任务）。

## 当前仓库范围（仅 Phase 0 + Phase 1）

按项目开发顺序，当前仅实现并验证：
1. **Phase 0 (`core/system_probe.py`, `scripts/check_env.py`, `core/resource_manager.py`)**:
   - 系统 RAM/可用 RAM、GPU/VRAM/驱动（NVML + `nvidia-smi` fallback）、PyTorch CUDA/`sm_120` 冒烟检测、ONNX Runtime `CUDAExecutionProvider` 检测。
   - 自动生成 `SYSTEM_REPORT.md`。
   - `ResourceManager` + `ResourceLimits`：集中管理 RAM/VRAM 警戒线与 AI 启动准入控制。
2. **Phase 1 (`audio/`, `capture_test.py`)**:
   - 枚举音频会话进程（Windows 通过 `pycaw` + `psutil`，支持 QQ 音乐、浏览器、播放器、Cubase 等任意应用，不硬编码 exe 名）。
   - Windows WASAPI Process Loopback 主路径（`proctap`）与 System WASAPI Loopback 兜底路径（`PyAudioWPatch`，强制提示“其他应用声音可能被混入”）。
   - 内部统一转换为 `48000 Hz / 2ch / float32` PCM。
   - `capture_test.py` 实时显示 PID、进程名、采样率、声道、RMS、Peak、每秒 frames、buffer underrun/overrun、RAM/VRAM 状态。

> [!WARNING]
> 本仓库目前在 **Linux 开发沙箱** 中完成代码与单元测试编写，**Windows WASAPI Process Loopback 与 RTX 5060 Ti 真机测试尚未在 Windows 真机验证**。请在目标 Windows 电脑上按下方步骤实测。

## Windows 真机安装与验证步骤（Phase 0 + Phase 1）

```powershell
# 1. 创建独立 Core 虚拟环境（Python 3.11 或 3.12）
python -m venv .venv-core
.\.venv-core\Scripts\activate
pip install -r requirements-windows.txt

# 2. 运行 Phase 0 硬件与环境检测并更新 SYSTEM_REPORT.md
python scripts\check_env.py --write-report

# 3. 列出当前正在发声的进程（播放 QQ 音乐后运行）
python capture_test.py --list-procs

# 4. 捕获 QQ 音乐（或任意应用，如 chrome.exe / Cubase13.exe）
python capture_test.py --name QQMusic.exe --fallback-system

# 5. 或使用交互式进程选择
python capture_test.py
```

## 运行自动化测试

```bash
pip install pytest
pytest -v
```
