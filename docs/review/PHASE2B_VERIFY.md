# Phase 2B 验证与修改方案交接表（Issue #32 · 二、算法）

- **验证者**：Neon（Linux/offscreen 验证，Ubuntu 24.04 + Python 3.12 + PySide6/scipy/numpy/mido/pytest）
- **基线提交**：`e4c49e8`（Phase 2A 合并至 `main` 后），工作分支：`fix/review-p2b-algo`
- **基准冻结声明（强制）**：
  - **`tests/bench/`（含 `algo_benchmark.py` 与 `baseline_e4c49e8.json`）从此冻结，修改者严禁改动 `tests/bench/` 下的任何文件。**
  - **退化判定标准**：每次算法修改后运行 `python -m tests.bench.algo_benchmark --json` 并与 `tests/bench/baseline_e4c49e8.json` 对比；**任一类别准确率下降超过 2 个百分点，或中位音分误差增加超过 1 c，即判定为退化（不通过）**。
- **说明**：本轮仅做 `A-BENCH` 冻结基准建设、修改前基线采集、18 条算法缺陷复现与方案制定，未修改任何业务代码。所有复现测试集中在 `tests/test_review_phase2b.py`，18 条缺陷均标记 `@pytest.mark.xfail(strict=True, reason="<ID>")`；修改者每修完一条须移除对应 `xfail` 标记并确认转绿。严禁违反 `docs/DECISIONS.md` 约束。

## A-BENCH 冻结基线指标（`@e4c49e8`，见 `tests/bench/baseline_e4c49e8.json`）

| 指标组（黑盒公开入口） | 指标名 | 冻结基线 (`e4c49e8`) | 2B 目标参考 |
| --- | --- | --- | --- |
| 调性 (`key`，72 例含 C2 bass) | `mirex_score` / `exact_acc` | **63.33% / 50.00%** | ≥ 85% / ≥ 80% |
| 调性 (`key`) | `major_I_IV_V_I_acc` / `minor_i_iv_V_i_acc` | **100.00% / 0.00%** | ≥ 90% / ≥ 90% |
| 实时和弦 (`rt_chord`，`FixedRingBuffer`+`AnalysisWorker`) | `rt_progression_acc` (`C-G-Am-F`) / `rt_inversion_acc` (`C/E-F/A-G/B`) | **90.00% / 4.44%** | ≥ 90% / ≥ 80% |
| 实时和弦 (`rt_chord`) | `triad_with_sevenths_on_acc` (24 例) | **87.50%** | ≥ 95% |
| 实时速度 (`rt_tempo`，`AnalysisWorker`，11 例×20s) | `66.67ms` `Acc1 / Acc2` | **63.64% / 90.91%** | ≥ 90% / 100% |
| 实时速度 (`rt_tempo`) | `62.5ms` `Acc1 / Acc2` | **0.00% / 0.00%** | ≥ 90% / 100% |
| 实时速度 (`rt_tempo`) | `78.1ms` `Acc1 / Acc2` | **0.00% / 0.00%** | ≥ 90% / 100% |
| 离线速度 (`offline_tempo`，`analyze_drums_stem`，20s) | `48k` `Acc1 / Acc2`；`44k` `Acc1 / Acc2` | **63.64% / 81.82%**（双采样率一致） | ≥ 85% / ≥ 95% |
| 实时音高 (`rt_pitch`，`AnalysisWorker`) | `pure_sine_acc` / `median_cents` (E1–C6) | **100.00% / 0.70c** | ≥ 98% / ≤ 1.7c |
| 实时音高 (`rt_pitch`) | `harmonic_acc` / `median_cents` (E1–C6) | **100.00% / 0.70c** | ≥ 98% / ≤ 1.7c |
| 实时音高 (`rt_pitch`) | `weak_f0_acc` (E1–E3 弱基频 25 例) | **0.00%** | ≥ 95% |
| 离线贝斯 (`offline_bass`，`analyze_bass_stem`) | `pure_sine_acc` / `808_acc` (48k & 44k) | **100.00% / 100.00%** | ≥ 98% / ≥ 98% |
| 离线贝斯 (`offline_bass`) | `repeated_a1_count` (期望 4，48k / 44k) | **3 / 3** | **4 / 4** |

## 逐条验证与精确修改步骤

| ID | 判定 | 复现测试名 | 给修改者的精确修改步骤 / 跳过原因 |
| --- | --- | --- | --- |
| A-BENCH | `CONFIRMED` | `test_abench_benchmark_suite_runs_and_returns_all_metrics` | 已建好并冻结 `tests/bench/algo_benchmark.py`（全黑盒公开入口：`FixedRingBuffer`+`AnalysisWorker`、`analyze_drums_stem`、`analyze_bass_stem`、`--json`）及 `tests/bench/baseline_e4c49e8.json`。修改者不得修改 `tests/bench/`，每次改动算法后跑基准对照退化阈值。 |
| A-H1 | `CONFIRMED` | `test_ah1_realtime_bpm_decoupled_from_scheduler_rate` | 1) 在 `analysis/fft.py` 新增 `log_spectrum_only(mono)`（只算 rFFT + log 滤波，不写 UI 历史）；2) 在 `analysis/tempo.py` 将 `TempoEstimator` 改为采样时钟基准 `self._rate_hz = sample_rate / 512`（93.75 Hz），新增 `push_frame(log_db, is_silent=...)` 逐 hop 累积 onset，并用 FFT ACF 每 0.5 s 估计一次（兼容原 `update` 调用）；3) 在 `analysis/worker.py` 维护 `self._onset_cursor` 按环形缓冲绝对帧号以 `HOP=512` 推进 `tempo.push_frame(...)`（拉大读取窗口覆盖两次调度间全部音频）。**验收（以冻结 A-BENCH `rt_tempo` 为准）**：`66.67ms`、`62.5ms`、`78.1ms` 三组调度周期的 `Acc1` 均由当前 `63.64% / 0% / 0%` 提升至 `≥ 90%`（且三组结果一致、不受周期漂移）；Windows 真机定时周期分布保留在 `docs/review/WINDOWS_RETEST.md`。 |
| A-H2 | `CONFIRMED` | `test_ah2_realtime_bpm_140_bpm_rock_within_1_percent` | 随 `A-H1` 切到 `HOP=512`（93.75 Hz）后，140 BPM 周期从 6.43 帧提升到 40.18 帧、174 BPM 提升到 32.33 帧；验收：60/90/120/140 BPM click 与 rock 误差均 `< 1%`，且 `A-BENCH` `rt_tempo` 达标、`tests/test_phase3_analysis.py` 通过。 |
| A-M6 | `CONFIRMED` | `test_am6_high_tempo_174_bpm_not_locked_to_half_time` | 修改 `analysis/tempo.py`（L94）与 `analysis/stem_analyzer.py` `_estimate_offline_bpm_from_flux`（L501）：将单峰先验改为双峰 `prior = np.maximum(np.exp(-0.5*(np.log2(bpms/100.0)/0.45)**2), 0.8*np.exp(-0.5*(np.log2(bpms/170.0)/0.15)**2))`，避免 174 BPM 被锁死到 87 BPM，提升 `A-BENCH` `rt_tempo` 与 `offline_tempo` 的 `Acc1`。 |
| A-H3 | `CONFIRMED` | `test_ah3_realtime_pitch_weak_fundamental_e1_to_e3_accuracy` | 1) 将 `analysis/stem_analyzer.py` 中的 `_yin_bass_frame_f0` 抽到独立模块 `analysis/yin.py`（`stem_analyzer.py` 重新导入复用，避免循环依赖）；2) 在 `analysis/pitch.py` `PitchEstimator` 新增 `estimate_from_pcm(mono, *, is_silent)`：取最新 `min(mono.size, 7200)` 点（48k 下 0.15 s）调用 YIN（`min_hz=38.0, max_hz=1600.0`），返回 `PitchEstimate`；3) 在 `analysis/worker.py`（L136）改为调用 `self.pitch.estimate_from_pcm(mono, is_silent=is_silent)`。**验收（以冻结 A-BENCH `rt_pitch` 为准）**：`weak_f0_acc` 由 `0.00%` 提升至 `≥ 95%`，同时 `pure_sine_acc` / `harmonic_acc` 不低于 `98%` 且中位音分误差不超过 `1.7c`（不退化超 1c）。 |
| A-M2 | `CONFIRMED` | `test_am2_red_noise_returns_unknown_not_fake_e1_with_saturated_confidence` | 在 `analysis/pitch.py` 中：1) `estimate_from_pcm` 使用 YIN 的 `1 - CMNDF(τ)` 作为置信度，并增加谱平坦度门控（复用 `ChromaExtractor._compute_tonality`，`tonality < 0.2` 返回 `Unknown`）；2) `estimate_from_magnitude` 同步增加谱平坦度门控，防止红噪声被误报为 E1 且置信度饱和 1.0。 |
| A-L9 | `CONFIRMED` | `test_al9_short_256_sample_buffer_returns_unknown_not_bogus_pitch` | 修改 `analysis/pitch.py`：`estimate_from_pcm` 要求 `mono.size >= max(self.fft_size // 2, 2 * int(self.sample_rate / 40.0))`（约 2400 点），不足直接返回 `Unknown`；`estimate_from_magnitude` 新增可选参数 `valid_len: Optional[int] = None`，当 `valid_len is not None and valid_len < self.fft_size // 2` 时直接返回 `Unknown`。 |
| A-H4 | `CONFIRMED` | `test_ah4_repeated_same_pitch_bass_notes_not_merged` | 1) 修改 `analysis/stem_analyzer.py` `analyze_bass_stem`（L353、L362-398）与 `_coalesce_note_frames`（L167-228）：将 `hop_size` 从 2048 缩至 512–1024，帧观测带上 `rms`；在 `_coalesce_note_frames` 中检测起音跃升（`rms > 1.6 * max(prev_rms, 1e-6)` 或局部峰值），即使 `midi_num == cur_midi` 遇新起音也先 `_flush()` 再开启新音符；2) 同步修改 `analysis/midi_transcription.py` `_fallback_pitch_notes`（L132-160）。验收：`A-BENCH` `offline_bass.repeated_a1_count_48k` 与 `44k` 均由 `3` 变为 `4`，且 `pure_sine_acc` / `808_acc` 无退化。 |
| A-L6 | `CONFIRMED` | `test_al6_bass_note_onset_timestamp_not_systematically_late` | 结合 `A-H4` 将 `analyze_bass_stem` 的 `hop_size` 降至 512（10.67 ms）并用窗口内能量/RMS 上升沿回溯校正音符起音时间 `start_sec`，消除 8192 点中心偏移导致的 +23–64 ms 滞后，使 `0.510s` 起音误差 ≤ ±15 ms。 |
| A-H5 | `CONFIRMED` | `test_ah5_minor_cadence_with_c2_bass_not_misclassified_as_parallel_major` | **以冻结 `A-BENCH` `key` 与仓库原有 9 例调性测试（`tests/test_key_detection_accuracy.py`）共同验收**：1) 将调性/和弦默认 chroma 下限提升至 `130.81 Hz`（C3，bass 仍通过 `_bass_fb` 独立提供主音先验 `_compute_tonic_bonus`）；2) 在 `analysis/key_detection.py` 新增 `"keyfinder"` 轮廓或调整默认轮廓，使 `minor_i_iv_V_i_acc >= 90%`、`major_I_IV_V_I_acc >= 90%` 且原有 9 例不低于 `8/9`（若存在权衡须在交接表写明数据对比）。 |
| A-L7 | `CONFIRMED` | `test_al7_key_modulation_returns_second_half_key_not_third_key` | 修改 `analysis/key_detection.py` `KeyDetector.estimate`（L249-265）：当检测到 `modulation = True`（前后两半最佳调不同且各自相关性 `>= 0.55`）时，将 `primary` 切换为后半段的调 `self._names[h2_idx]`（`secondary` 设为 `self._names[h1_idx]`），避免全局平均给出第三调。 |
| A-L3 | `CONFIRMED` | `test_al3_bass_modulation_does_not_false_positive_on_diatonic_verse_chorus` | 修改 `analysis/stem_analyzer.py` `_detect_bass_modulation`（L320-346）：改用 `KeyDetector` 分别评估前后两半音高分布，仅当两半最佳调不同且各自调性相关性/置信度均高（如 `>= 0.65`）时才判为转调，避免同一 C 大调内的 `vi-IV` → `I-V` 误报。 |
| A-M4 | `CONFIRMED` | `test_am4_first_inversion_chords_not_misclassified_as_relative_minor` | 1) 结合 `A-H5` 将和弦主 chroma 下限设为 `130.81 Hz`（避免 C2 bass 淹没上方三和弦，使 `C/E` 不再误判为 `Em`）；2) 在 `analysis/chords.py` `ChordDetector.update` 新增可选参数 `bass_chroma: Optional[np.ndarray] = None`，当 `bass_pc = int(np.argmax(bass_chroma))` 属于最佳和弦内音且 `bass_pc != root_pc` 时输出 slash 和弦（如 `C/E`、`F/A`）；并在 `analysis/worker.py` / `stem_analyzer.py` 传入 `bass_chroma`。验收：`A-BENCH` `rt_chord.rt_inversion_acc` 由 `4.44%` 提升至 `≥ 80%`。 |
| A-L10 | `CONFIRMED` | `test_al10_sevenths_enabled_preserves_triad_accuracy_and_supports_dim` | 修改 `analysis/chords.py` `_build_chord_templates` 与 `ChordDetector.update`（L216-280）：1) 对七和弦模板施加 `-0.03` 得分偏置，确保 `triad_with_sevenths_on_acc >= 95%`；2) 补充 `dim` 与 `aug` 模板，使 `Bdim` 正确输出 `Bdim`。 |
| A-M5 | `CONFIRMED` | `test_am5_drum_band_crosstalk_1500hz_click_does_not_trigger_kick` | 修改 `analysis/stem_analyzer.py` `analyze_drums_stem`（L546-575）：在计算 `k_flux`/`s_flux`/`h_flux` 时同步记录每帧三频段能量 `E_k`/`E_s`/`E_h`，在 `_pick_band_onsets` 后加跨频段相对能量门（`kicks`: `E_k/(E_k+E_s+1e-9) > 0.35`，`hihats`: `E_h/(E_s+E_h+1e-9) > 0.25`），消除 1.5 kHz 单频 click 串扰触发底鼓/踩镲，且不导致 `offline_tempo` 退化。 |
| A-L2 | `CONFIRMED` | `test_al2_midi_normalize_preserves_multi_tempo_onset_timing` | 修改 `analysis/midi_common.py` `normalize_midi_file_for_cubase`（L245-295）：按原文件完整 tempo map 将所有 `note_on`/`note_off` tick 精确换算为秒，再统一按目标 tempo 量化回 tick（或保留完整 tempo map），确保 120→60 BPM 变速 MIDI 起音秒数误差 `< 50 ms`。 |
| A-L4 | `CONFIRMED` | `test_al4_bass_median_filter_does_not_average_two_neighbors_to_1_5f` | 修改 `analysis/stem_analyzer.py` `analyze_bass_stem`（L389-395）：仅在 `len(nbrs) == 3` 时取 `float(np.median(nbrs))`，否则保留原值 `freq`。 |
| A-L5 | `CONFIRMED` | `test_al5_iter_aligned_mono_48k_frames_uses_streaming_resampler_without_chunk_glitches` | 修改 `analysis/stem_analyzer.py` `_iter_aligned_mono_48k_frames`（L117-136）：为每个 `sr != CANONICAL_SR` 的 reader 维护独立 `StreamingResampler(sr, CANONICAL_SR, 1)`（复用 Phase 2A E3，结束时 `flush()`），消除 0.5 s 分块边界 5.4% 毛刺。 |
| A-PERF | `CONFIRMED` | `test_aperf_spectrum_analyze_frame_supports_record_false` | 1) `analysis/fft.py` `SpectrumAnalyzer.analyze_frame(self, mono, *, record: bool = True)` 增加 `record` 开关（离线 `analyze_harmony_and_chords` 传 `record=False`）；2) `analysis/chroma.py` 将 `_history`/`_weight_history`/`_bass_history` 改为预分配环形 ndarray；3) `ChromaExtractor.extract_from_pcm` 按需优化降采样复用并用 `A-BENCH` 确认零退化。 |

---

## 基线、新增测试与建议修复顺序

- **基线测试（`e4c49e8`，Linux/offscreen 验证）**：全量 `264 passed, 6 skipped`
- **本批新增测试（`tests/test_review_phase2b.py`，Linux/offscreen 验证）**：`1 passed`（`A-BENCH`）+ `18 xfailed`（0 failed，0 xpassed）
- **判定统计（共 19 条）**：`CONFIRMED` 19 条（含 `A-BENCH` 与已黑盒复现的 `A-H1`；Windows 真机定时周期分布仍保留在 `docs/review/WINDOWS_RETEST.md`），`FALSE_POSITIVE` 0 条，`NEEDS_TARGET` 0 条
- **建议修复顺序（供修改者 Hydrogen 参考）**：
  1. `A-L5` → `A-L4` → `A-L2` → `A-PERF`
  2. `A-H1` → `A-H2` → `A-M6`
  3. `A-H3` → `A-M2` → `A-L9`
  4. `A-H4` → `A-L6` → `A-M5`
  5. `A-H5` → `A-L7` → `A-L3` → `A-M4` → `A-L10`
