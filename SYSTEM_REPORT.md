# ListenScope 系统与硬件检测报告 (Phase 0)

- **检测时间**: `2026-11-13 08:55:47 UTC`

## 1. 目标用户真机硬性规格（不可更改）

所有内存、显存预算与 AI 分轨保护策略均严格以下列目标硬件为准：

- **目标系统**: Windows 10/11 (Build >= 19041, 20H1+ 以支持 WASAPI Process Loopback)
- **目标 GPU**: `NVIDIA GeForce RTX 5060 Ti` (Blackwell (sm_120))
- **GPU 显存**: **8GB VRAM**（严禁误写作 16GB VRAM）
- **系统内存**: **16GB RAM**
- **CUDA / PyTorch 最低兼容要求**: CUDA >= `12.8`，PyTorch >= `2.7.0` (需包含 `sm_120` 支持)

## 2. 当前执行环境实测结果

> [!WARNING]
> **当前环境为 `Linux 6.12.105+ (x86_64)`，不是 Windows 真机。**
> **状态：未在 Windows 真机验证。** 下方数据仅反映当前开发/测试沙箱的真实探测结果，绝不伪装为 RTX 5060 Ti Windows 实测结果。

| 项目 | 当前环境实测值 | 目标真机要求 |
| :--- | :--- | :--- |
| 操作系统 | `Linux 6.12.105+` (`x86_64`) | Windows 10/11 20H1+ (`build >= 19041`) |
| Windows Build | `N/A (非 Windows)` | `>= 19041` |
| WASAPI Process Loopback | `不可用 / 未在 Windows 真机验证` | 需要 Windows 20H1+ |
| Python 版本 | `3.11.2` | `>= 3.11` (建议 3.11/3.12) |
| Git 版本 | `git version 2.39.5` | 已安装 |
| CPU | `Intel(R) Xeon(R) Platinum 8481C` (2 逻辑核) | Windows PC CPU (实时分析默认 CPU 运行) |
| 系统总 RAM | `7947.7 MB` (7.76 GB) | **16GB RAM** |
| 当前可用 RAM (`psutil.available`) | `7209.5 MB` (7.04 GB) | AI 前建议 >= 5GB，低于 3GB 拒绝启动 |
| NVML (`pynvml`) | `不可用` | 可用 (用于监控 8GB VRAM) |
| `nvidia-smi` | `未找到` | 可用 |
| NVIDIA 驱动 | `未检测到` | 支持 CUDA >= 12.8 |
| GPU / VRAM | `未检测到 NVIDIA GPU` | `NVIDIA GeForce RTX 5060 Ti` (**8GB VRAM**) |

## 3. PyTorch / CUDA / ONNX Runtime 环境核对

- **PyTorch 已安装**: `否`
- **torch.cuda.is_available()**: `不可用`
- **PyTorch CUDA Build**: `N/A`
- **GPU Compute Capability**: `N/A`
- **sm_120 (Blackwell) 支持**: `未验证`
- **CUDA Kernel 冒烟测试**: `未执行`
- **ONNX Runtime 已安装**: `否`
- **ONNX Runtime Providers**: `[]`
- **CUDAExecutionProvider 是否存在**: `否`
- **GPU AI 推理准入状态 (`gpu_ai_ready`)**: `BLOCKED`
- **GPU AI 阻断原因（拒绝静默伪装 GPU 正常）**: No NVIDIA GPU detected via NVML/nvidia-smi; GPU AI inference disabled.

## 4. 默认资源安全预算 (`ResourceLimits` & `AudioConfig`)

| 参数 | 默认安全值 | 说明 |
| :--- | :--- | :--- |
| 内部统一 PCM 格式 | `48000 Hz / 2ch / float32` | 120s 原始环形缓冲约 `43.95 MiB` (`46.08 MB`) |
| 音频捕获队列上限 | `64` chunks | 有界队列，满时丢弃最旧帧并计数 `overrun` |
| 主程序 RAM 目标 / 警戒 | `< 1024 MB` / `1536 MB` | 核心分析全 CPU 轻量运行 |
| AI 启动前可用 RAM 提示 / 拒绝 / 急停 | `< 5120 MB` 提示 / `< 3072 MB` 拒绝 / `< 2048 MB` 急停 | 以 `psutil.virtual_memory().available` 为准 |
| GPU 空闲显存阈值 (2-stem / 4-stem) | `>= 4096 MB` / `>= 5632 MB` | 保留 >= `768 MB` 给桌面、QQ 音乐、浏览器 |
| 最大并发 AI 任务 / 加载模型数 | `1` / `1` | 严格串行单模型，独立子进程运行（后期阶段启用） |

## 5. 告警与未验证项

- 当前运行环境为 Linux (x86_64)，并非目标 Windows PC；Windows WASAPI Process Loopback 与 RTX 5060 Ti CUDA 推理均未在 Windows 真机验证。

### Windows 真机部署建议（Stage 5+ AI 环境启用前核对）

1. Core 与 AI Worker 环境隔离：Core 仅安装 `requirements-windows.txt`，不引入 PyTorch。
2. 在 Windows PC 上运行 `python scripts/check_env.py --write-report` 更新本报告为真机实测值。
3. 后续建立 AI Worker 独立虚拟环境时，安装支持 Blackwell `sm_120` 的 PyTorch (`>= 2.7.0`, CUDA `>= 12.8`, 例如 `--index-url https://download.pytorch.org/whl/cu128` 或 `cu130`+) 与匹配的 `onnxruntime-gpu` (`CUDAExecutionProvider` + cuDNN 9.x)。
