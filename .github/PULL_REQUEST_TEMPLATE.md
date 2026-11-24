## 变更摘要

<!-- 简要说明本次 PR 解决的问题、实现方式及关联 Issue（如 Closes #xx） -->

## 验证与检查清单

- [ ] **测试**：已运行 `QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short` 且全部通过（未放宽既有断言）
- [ ] **基准（如涉及 `analysis/`）**：已运行 `algo_benchmark.py` 与 `realistic_mix.py`，确认无退步且未修改 `tests/bench/`
- [ ] **界面与截图（如涉及 `ui/`）**：已检查亮暗双模与最小窗口布局，无 `QGraphicsEffect` 或控件遮挡
- [ ] **国际化（如新增/修改界面文案）**：已同步更新 `zh` / `en` / `ko` / `ja` 四种语言
- [ ] **架构约束**：已核对 [docs/DECISIONS.md](docs/DECISIONS.md)（Core 零 PyTorch/CUDA/TF、`settings` schema 保持 2、未降低内存/显存阈值）
- [ ] **实测边界**：未在真实 Windows 11 / 声卡 / GPU 环境实测的改动已明确标注为「Linux/offscreen 验证」
