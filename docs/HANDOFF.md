# ListenScope 最近开发交接（HANDOFF）

- **日期**：2026-11-23
- **当前分支与基线**：`main` @ `8285509`（PR #41 普通 merge commit，已合并 Phase 1 #31、Phase 2A/2B/2C #32 及 **Phase 2D #40 W1–W15**）
- **验证环境**：Linux Ubuntu 24.04 + `QT_QPA_PLATFORM=offscreen` 与 GitHub Actions `windows-latest` offscreen CI（Run [#45216747073](https://github.com/Ceph-learner/ListenScope/actions/runs/45216747073) 双绿；**非 Windows 11 RTX 5060 Ti 真机实测**）

## 本轮已完成内容

1. **Issue #31（Phase 1，30 条）**：已合并至 `main`（`d3d2edc`，PR #34）。
2. **Issue #32（Phase 2A/2B/2C + `U-B34`）**：已合并至 `main`（`e4c49e8` / `86938ef` / `1601344` / `6fe01c5`）。
3. **Issue #40（Phase 2D，Windows 实测回归修复 W1–W15）**：已合并至 `main`（`8285509`，PR #41，来源分支 `fix/review-p2d-windows` @ `8e1f220`）：
   - **Round 1（W1–W9）**：默认输出设备热切换重连、托盘退出看门狗与 `_ACTIVE_SUBPROCS` 清理（含 `WasapiProcessLoopbackBackend.start()` 重置 `_closing`）、bass MIDI 八度鬼音后处理与 30–400 Hz 约束、系统动画开关同步、频谱自适应纵轴刻度与 `1093×566` `_history_box` 修复、Windows CI 6 项 pytest 失败修复、`windows-latest` offscreen CI 作业、Snap Layouts 延期说明、安全音频测试规格与 `core/version.py` 开发版本号。
   - **Round 2（W10–W15 + W2 关闭按钮行为）**：`handle_ai_result` 枚举修复 + AST 守护 + `_on_ui_tick` 分队列异常隔离（W10）；新增冻结 `tests/bench/realistic_mix.py` 与 `baseline_6fe01c5_realistic.json`，`analysis/tempo.py` 调优后 `realistic_mix` BPM Acc1 `40.0% → 86.67%`、Acc2 `66.67% → 100.0%`、非节奏负样本 `100.0%` 返回 `None`，原有 `A-BENCH` 无退化（W11）；多声部 175 Hz 低通 + ×8 降采样低音回退与静音防误判（W12）；2×2 `ViewBox` 数据区高度 `>= 80 px`、默认精简 A/B、波形自动增益/固定 `±1` 切换按钮与 Chroma 秒轴（W13）；`close_behavior` 全链路持久化 + 设置页入口 + Inno Setup `CloseApplications/AppMutex`（W2）；AI 空闲低内存（2048–3072 MB）显示琥珀色「内存偏低」并留存 `docs/WINDOWS_TEST_REPORT.md`（W14）；水印/顶栏拉伸/SMTC 精简/轨名省略/页脚字距打磨（W15）。
   - **Issue #37 R4-1 备注**：已补充发布时统一 `pyproject.toml`、`scripts/installer.iss` 和 `core/version.py` 的 `_FALLBACK_BASE_VERSION` 为 `1.1.0`。
4. **测试与 CI 基线**：
   - GitHub Actions Run [#45216747073](https://github.com/Ceph-learner/ListenScope/actions/runs/45216747073)（`8e1f220`）：`pytest`（`ubuntu-latest`，4m9s）与 `pytest-windows`（`windows-latest`，7m41s）双绿；
   - `tests/test_review_phase2d.py`：`20 passed`；`tests/bench/` 冻结基准零退化。

## 下一步计划

1. 在目标机（Windows 11 + RTX 5060 Ti 8 GB + 16 GB RAM）按 [`docs/review/WINDOWS_RETEST.md`](review/WINDOWS_RETEST.md) 完成待实测项：**`W1`、`W2`、`W3`、`W5`、`W11`（本机音乐）、`W12`、`W13`（125%/150% 截图）、`W14`**。
2. 真机全部通过后关闭 Issue #40、#31、#32，再按 Issue #37 进入发布准备（含 R4-1 统一 `1.1.0` 版本号）。
