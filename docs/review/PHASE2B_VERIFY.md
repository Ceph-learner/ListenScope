# Phase 2B 验证与修改方案交接表（Issue #32 · 二、算法）

- **验证者**：Neon（Linux/offscreen 验证，Ubuntu 24.04 + Python 3.12 + PySide6/scipy/numpy/mido/pytest）
- **基线提交**：`e4c49e8`（Phase 2A 合并至 `main` 后），工作分支：`fix/review-p2b-algo`
- **说明**：本轮仅做 `A-BENCH` 基准建设、修改前基线采集、18 条算法缺陷复现与方案制定，未修改任何业务代码。所有复现测试集中在 `tests/test_review_phase2b.py`，18 条缺陷均标记 `@pytest.mark.xfail(strict=True, reason="<ID>")`；修改者每修完一条须移除对应 `xfail` 标记、确认转绿并跑 `python -m tests.bench.algo_benchmark` 对比基线。严禁违反 `docs/DECISIONS.md` 约束（不给 Core 引入重型依赖、保持现有 9 例调性回归不低于 8/9 等）。

## A-BENCH 修改前基线指标（`@e4c49e8`，`python -m tests.bench.algo_benchmark`）

| 指标组 | 指标名 | 修改前基线 (`e4c49e8`) | 2B 目标参考 |
| --- | --- | --- | --- |
| 调性 (`key`，72 例含 C2 bass) | `mirex_score` | **63.33%** | ≥ 85% |
| 调性 (`key`) | `exact_acc` | **50.00%** | ≥ 80% |
| 调性 (`key`) | `major_I_IV_V_I_acc` (12 例) | **100.00%** | ≥ 90% |
| 调性 (`key`) | `minor_i_iv_V_i_acc` (12 例) | **0.00%** | ≥ 90% |
| 和弦 (`chord`) | `triad_acc` (24 例) | **100.00%** | ≥ 95% |
| 和弦 (`chord`) | `triad_with_sevenths_on_acc` (24 例) | **87.50%** | ≥ 95% |
| 和弦 (`chord`) | `inversion_acc` (12 例转位) | **0.00%** | ≥ 80% |
| 速度 (`tempo`，60–174 BPM 10 例) | `rt_acc1` / `rt_acc2` | **70.0% / 90.0%** | ≥ 90% / 100% |
| 速度 (`tempo`) | `offline_acc1` / `offline_acc2` | **30.0% / 70.0%** | ≥ 80% / 90% |
| 音高 (`pitch`) | `pitch_std_acc` / `median_cents` | **100.0% / 0.65c** | ≥ 95% / ≤ 5c |
| 音高 (`pitch`) | `pitch_weak_f0_acc` (E1–E3 弱基频 25 例) | **0.00%** | ≥ 95% |

## 逐条验证与精确修改步骤

| ID | 判定 | 复现测试名 | 给修改者的精确修改步骤 / 跳过原因 |
| --- | --- | --- | --- |
| A-BENCH | `CONFIRMED` | `test_abench_benchmark_suite_runs_and_returns_all_metrics` | 已由验证者建好 `tests/bench/algo_benchmark.py`（含 24 调×3 进行/音阶、和弦三和弦/七和弦/转位、60–174 BPM click/rock/DnB、E1–C6 与弱基频音高扫描）并采集上述基线。修改者每次改动算法后均须运行 `python -m tests.bench.algo_benchmark` 并在交接表记录前后对比。 |
| A-H1 | `NEEDS_TARGET` | `test_ah1_realtime_bpm_decoupled_from_scheduler_rate` | 1) 在 `analysis/fft.py` 新增 `log_spectrum_only(mono)`（只算 rFFT + log 滤波，不写 UI 历史）；2) 在 `analysis/tempo.py` 将 `TempoEstimator` 改为采样时钟基准 `self._rate_hz = sample_rate / 512`（93.75 Hz），新增 `push_frame(log_db, is_silent=...)` 逐 hop 累积 onset，并用 FFT ACF（`irfft(|rfft(centered, 2*n)|^2)[:n]`）每 0.5 s 估计一次（同时兼容原 `update(log_db, is_silent=...)` 调用）；3) 在 `analysis/worker.py` 维护 `self._onset_cursor` 按环形缓冲绝对帧号以 `HOP=512` 推进 `tempo.push_frame(...)`（拉大读取窗口覆盖两次调度间全部音频）。注：Windows 15.6 ms 定时粒度下的真实 `period` 分布须按 `docs/review/WINDOWS_RETEST.md` 实测。 |
| A-H2 | `CONFIRMED` | `test_ah2_realtime_bpm_140_bpm_rock_within_1_percent` | 随 `A-H1` 切到 `HOP=512`（93.75 Hz）后，140 BPM 周期从 6.43 帧提升到 40.18 帧、174 BPM 提升到 32.33 帧；同时验证 60/90/120/140 BPM click 与 rock 误差均 `< 1%` 且保持 `tests/test_phase3_analysis.py` 通过。 |
| A-M6 | `CONFIRMED` | `test_am6_high_tempo_174_bpm_not_locked_to_half_time` | 修改 `analysis/tempo.py`（L94）与 `analysis/stem_analyzer.py` `_estimate_offline_bpm_from_flux`（L501）：将单峰先验改为双峰 `prior = np.maximum(np.exp(-0.5*(np.log2(bpms/100.0)/0.45)**2), 0.8*np.exp(-0.5*(np.log2(bpms/170.0)/0.15)**2))`，避免 174 BPM 被锁死到 87 BPM；如 `TempoEstimate` 支持可选次候选字段可在不破坏旧字段前提下暴露。 |
| A-H3 | `CONFIRMED` | `test_ah3_realtime_pitch_weak_fundamental_e1_to_e3_accuracy` | 1) 将 `analysis/stem_analyzer.py` 中的 `_yin_bass_frame_f0` 抽到独立模块 `analysis/yin.py`（`stem_analyzer.py` 重新导入复用，避免循环依赖）；2) 在 `analysis/pitch.py` `PitchEstimator` 新增 `estimate_from_pcm(mono, *, is_silent)`：取最新 `min(mono.size, 7200)` 点（48k 下 0.15 s）调用 YIN（`min_hz=38.0, max_hz=1600.0`），返回 `PitchEstimate`；3) 在 `analysis/worker.py`（L136）改为调用 `self.pitch.estimate_from_pcm(mono, is_silent=is_silent)`。验收：E1–E3 弱基频准确率 ≥ 95%，1/k 谐波中位误差 ≤ 5 音分。 |
| A-M2 | `CONFIRMED` | `test_am2_red_noise_returns_unknown_not_fake_e1_with_saturated_confidence` | 在 `analysis/pitch.py` 中：1) `estimate_from_pcm` 直接使用 YIN 的 `1 - CMNDF(τ)` 作为置信度，并增加谱平坦度门控（复用 `ChromaExtractor._compute_tonality`，当 `tonality < 0.2` 返回 `Unknown`）；2) `estimate_from_magnitude` 也同步增加相同谱平坦度门控，防止红噪声被误报为 E1 且置信度饱和 1.0。 |
| A-L9 | `CONFIRMED` | `test_al9_short_256_sample_buffer_returns_unknown_not_bogus_pitch` | 修改 `analysis/pitch.py`：`estimate_from_pcm` 要求 `mono.size >= max(self.fft_size // 2, 2 * int(self.sample_rate / 40.0))`（约 2400 点），不足直接返回 `Unknown`；`estimate_from_magnitude` 新增可选参数 `valid_len: Optional[int] = None`，当 `valid_len is not None and valid_len < self.fft_size // 2` 时直接返回 `Unknown`。 |
| A-H4 | `CONFIRMED` | `test_ah4_repeated_same_pitch_bass_notes_not_merged` | 1) 修改 `analysis/stem_analyzer.py` `analyze_bass_stem`（L353、L362-398）与 `_coalesce_note_frames`（L167-228）：将 `hop_size` 从 2048 缩至 512–1024，帧观测带上 `rms`；在 `_coalesce_note_frames` 中检测起音跃升（`rms > 1.6 * max(prev_rms, 1e-6)` 或局部峰值），即使 `midi_num == cur_midi` 遇新起音也先 `_flush()` 再开启新音符；2) 同步修改 `analysis/midi_transcription.py` `_fallback_pitch_notes`（L132-160），遇能量跃升时切分同音高重复音。 |
| A-L6 | `CONFIRMED` | `test_al6_bass_note_onset_timestamp_not_systematically_late` | 结合 `A-H4` 将 `analyze_bass_stem` 的 `hop_size` 降至 512（10.67 ms）并用窗口内能量/RMS 上升沿（或 onset 局部峰）回溯校正音符起音时间 `start_sec`，消除 8192 点中心偏移导致的 +23–64 ms 滞后，使 `0.510s` 起音误差 ≤ ±15 ms。 |
| A-H5 | `CONFIRMED` | `test_ah5_minor_cadence_with_c2_bass_not_misclassified_as_parallel_major` | **以 `A-BENCH` 与仓库原有 9 例调性测试（`tests/test_key_detection_accuracy.py`）共同验收**：1) 将调性/和弦默认 chroma 下限提升至 `130.81 Hz`（C3，bass 仍通过 `_bass_fb` 独立提供主音先验 `_compute_tonic_bonus`）；2) 在 `analysis/key_detection.py` 新增 `"keyfinder"` 轮廓或将默认轮廓调整为在 `A-BENCH` 上 `minor_i_iv_V_i_acc >= 90%`、`major_I_IV_V_I_acc >= 90%` 且原有 9 例不低于 `8/9`（若与 9 例存在权衡须在交接表写明数据对比）。 |
| A-L7 | `CONFIRMED` | `test_al7_key_modulation_returns_second_half_key_not_third_key` | 修改 `analysis/key_detection.py` `KeyDetector.estimate`（L249-265）：当检测到 `modulation = True`（前后两半最佳调不同且各自相关性 `>= 0.55`）时，将 `primary` 切换为后半段的调 `self._names[h2_idx]`（`secondary` 可设为 `self._names[h1_idx]`），避免全局平均给出既非前半也非后半的第三调。 |
| A-L3 | `CONFIRMED` | `test_al3_bass_modulation_does_not_false_positive_on_diatonic_verse_chorus` | 修改 `analysis/stem_analyzer.py` `_detect_bass_modulation`（L320-346）：改用 `KeyDetector`（或 12 维音高分布的调性匹配）分别评估前后两半，仅当两半最佳调不同且各自调性相关性/置信度均高（如 `>= 0.65`）时才判为转调，避免同一 C 大调内的 `vi-IV` → `I-V` 误报。 |
| A-M4 | `CONFIRMED` | `test_am4_first_inversion_chords_not_misclassified_as_relative_minor` | 1) 结合 `A-H5` 将和弦主 chroma 下限设为 `130.81 Hz`（避免 C2 bass 淹没上方三和弦，使 `C/E` 不再被误判为 `Em`）；2) 在 `analysis/chords.py` `ChordDetector.update` 新增可选参数 `bass_chroma: Optional[np.ndarray] = None`，当 `bass_pc = int(np.argmax(bass_chroma))` 属于最佳和弦内音且 `bass_pc != root_pc` 时输出 slash 和弦（如 `C/E`、`F/A`）；并在 `analysis/worker.py` / `stem_analyzer.py` 传入 `bass_chroma`。 |
| A-L10 | `CONFIRMED` | `test_al10_sevenths_enabled_preserves_triad_accuracy_and_supports_dim` | 修改 `analysis/chords.py` `_build_chord_templates` 与 `ChordDetector.update`（L216-280）：1) 对七和弦模板（`maj7`/`m7`/`7`/`sus4`）施加 `-0.03` 得分偏置，避免纯三和弦在开启七和弦模式时被误吸为七和弦（确保 `triad_with_sevenths_on_acc >= 95%`）；2) 补充 `dim`（`[1.0, 0, 0, 0.85, 0, 0, 0.90, ...]`）与 `aug`（`[1.0, 0, 0, 0, 0.85, 0, 0, 0, 0.90, ...]`）模板，使 `Bdim` 正确输出 `Bdim`。 |
| A-M5 | `CONFIRMED` | `test_am5_drum_band_crosstalk_1500hz_click_does_not_trigger_kick` | 修改 `analysis/stem_analyzer.py` `analyze_drums_stem`（L546-575）：在计算 `k_flux`/`s_flux`/`h_flux` 时同步记录每帧三频段能量 `E_k`/`E_s`/`E_h`，在 `_pick_band_onsets` 之后加跨频段相对能量门（例如 `kicks` 要求 `E_k / (E_k + E_s + 1e-9) > 0.35`，`hihats` 要求 `E_h / (E_s + E_h + 1e-9) > 0.25`），消除 1.5 kHz 单频 click 串扰触发底鼓/踩镲。 |
| A-L2 | `CONFIRMED` | `test_al2_midi_normalize_preserves_multi_tempo_onset_timing` | 修改 `analysis/midi_common.py` `normalize_midi_file_for_cubase`（L245-295）：先按原文件完整 tempo map（所有 `set_tempo` 事件，不加 `bpm == default_bpm` 限制）将每个 `note_on`/`note_off` 的 tick 精确换算为真实秒数，再统一按目标单 tempo（或保留原 tempo map）量化回 tick，确保 120→60 BPM 变速 MIDI 的起音秒数误差 `< 50 ms`。 |
| A-L4 | `CONFIRMED` | `test_al4_bass_median_filter_does_not_average_two_neighbors_to_1_5f` | 修改 `analysis/stem_analyzer.py` `analyze_bass_stem`（L389-395）：仅在 `len(nbrs) == 3` 时取 `float(np.median(nbrs))`，否则保留原值 `freq`，消除两邻居取中位数得出 `1.5f`（高纯五度）的错误。 |
| A-L5 | `CONFIRMED` | `test_al5_iter_aligned_mono_48k_frames_uses_streaming_resampler_without_chunk_glitches` | 修改 `analysis/stem_analyzer.py` `_iter_aligned_mono_48k_frames`（L117-136）：为每个 `sr != CANONICAL_SR` 的 reader 维护独立 `StreamingResampler(sr, CANONICAL_SR, 1)`（复用 Phase 2A E3 成品，结束时 `flush()`），彻底消除 0.5 s 分块重采样边界 5.4% 毛刺。 |
| A-PERF | `CONFIRMED` | `test_aperf_spectrum_analyze_frame_supports_record_false` | 1) 在 `analysis/fft.py` `SpectrumAnalyzer.analyze_frame(self, mono, *, record: bool = True)` 增加 `record` 开关，`record=False` 时不写 `self._log_history`（离线 `analyze_harmony_and_chords` 传 `record=False`）；2) 在 `analysis/chroma.py` 将 `_history`/`_weight_history`/`_bass_history` 改为预分配环形 ndarray（省去每次 `np.stack` 540 个小数组）；3) `ChromaExtractor.extract_from_pcm` 按需优化降采样复用（确保不引入精度退化，用 `A-BENCH` 回归验证）。 |

---

## 基线、新增测试与建议修复顺序

- **基线测试（`e4c49e8`，Linux/offscreen 验证）**：全量 `264 passed, 6 skipped`
- **本批新增测试（`tests/test_review_phase2b.py`，Linux/offscreen 验证）**：`1 passed`（`A-BENCH`）+ `18 xfailed`（0 failed，0 xpassed）
- **判定统计（共 19 条）**：`CONFIRMED` 18 条（含 `A-BENCH`），`FALSE_POSITIVE` 0 条，`NEEDS_TARGET` 1 条（`A-H1`，已追加至 `docs/review/WINDOWS_RETEST.md`）
- **建议修复顺序（供修改者 Hydrogen 参考）**：
  1. **基础设施与低风险单点**：`A-L5`（复用 E3 `StreamingResampler`）→ `A-L4` → `A-L2` → `A-PERF`
  2. **BPM 采样时钟解耦**：`A-H1` → `A-H2` → `A-M6`
  3. **实时音高 YIN 与门控**：`A-H3` → `A-M2` → `A-L9`
  4. **离线贝斯/MIDI 起音与鼓组抗串扰**：`A-H4` → `A-L6` → `A-M5`
  5. **调性与和弦联合优化（每次改动跑 `A-BENCH` + `test_key_detection_accuracy.py`）**：`A-H5` → `A-L7` → `A-L3` → `A-M4` → `A-L10`
