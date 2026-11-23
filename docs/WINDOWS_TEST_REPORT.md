# ListenScope Windows 11 实机验收记录

- **目标硬件**：Windows 11 + NVIDIA GeForce RTX 5060 Ti (**8 GB VRAM**, `sm_120`) + **16 GB RAM**
- **护栏阈值（[DECISIONS.md](DECISIONS.md)）**：`min_ram_before_ai_mb = 5120` MiB、`pause_ram_before_ai_mb = 3072` MiB、`critical_ram_mb = 2048` MiB（不可随意修改）

---

## AI 分轨实测基准（Issue #40 / W14）

| 测试项 | 输入时长 | 模型 / 模式 | Worker 峰值内存 | 峰值显存 | RTF | 结论 |
|---|---|---|---|---|---|---|
| 2-Stem 离线分轨实测 | 20 s | MDX-Net ONNX (GPU) | **1830 MB** | **3893 MB** | **0.435** | 通过，显存与内存均在 8 GB VRAM / 16 GB RAM 安全余量内 |

## 实机回归复测状态

- 具体复测步骤与结果记录表见 [docs/review/WINDOWS_RETEST.md](review/WINDOWS_RETEST.md) 与 [docs/review/PHASE2D_VERIFY.md](review/PHASE2D_VERIFY.md)。
