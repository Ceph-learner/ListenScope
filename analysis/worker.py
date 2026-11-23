"""Background CPU DSP worker thread decoupled from GUI main thread."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import numpy as np

from audio.pcm_utils import compute_rms_and_peak
from audio.ring_buffer import FixedRingBuffer
from core.config import AnalysisConfig, AudioConfig
from core.models import AnalysisSnapshot

from .chords import ChordDetector
from .chroma import ChromaExtractor
from .fft import SpectrumAnalyzer
from .key_detection import KeyDetector
from .pitch import PitchEstimator
from .tempo import TempoEstimator

logger = logging.getLogger(__name__)


class AnalysisWorker:
    """Runs CPU-only FFT, chroma, chord, key, BPM, and pitch analysis off the GUI thread."""

    def __init__(
        self,
        ring_buffer: FixedRingBuffer,
        *,
        audio_config: Optional[AudioConfig] = None,
        analysis_config: Optional[AnalysisConfig] = None,
    ) -> None:
        self.ring_buffer = ring_buffer
        self.audio_config = audio_config or ring_buffer.audio_config
        self.config = analysis_config or AnalysisConfig()

        sr = self.audio_config.sample_rate
        self.spectrum = SpectrumAnalyzer(sample_rate=sr, config=self.config)
        self.chroma = ChromaExtractor(
            sample_rate=sr,
            config=self.config,
            fmin_hz=self.config.harmony_chroma_fmin_hz,
        )
        self.chords = ChordDetector()
        self.key_detector = KeyDetector()
        self.tempo = TempoEstimator(config=self.config, sample_rate=sr)
        self.pitch = PitchEstimator(sample_rate=sr, fft_size=self.config.fft_size)

        self._lock = threading.Lock()
        self._analysis_lock = threading.Lock()
        self._latest_snapshot: Optional[AnalysisSnapshot] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_analyzed_frame: int = -1
        self._onset_cursor: Optional[int] = None
        self._onset_generation: Optional[int] = None
        self._frame_count: int = 0
        self._harmony_generation: int = 0
        self._reset_boundary: tuple[int, int] | None = None
        self._dropped_cycles: int = 0

        # 1/24-octave log-frequency FFT display grid (27.5 Hz .. 16 kHz, 221 bins)
        self._disp_f = np.geomspace(
            max(20.0, float(self.config.min_freq_hz)),
            max(1000.0, float(self.config.max_freq_hz)),
            221,
        ).astype(np.float32)
        self._disp_f_list = self._disp_f.tolist()
        fft_freqs = self.spectrum.fft_freqs
        half_step = 2.0 ** (1.0 / 48.0)
        self._disp_max_ranges: list[tuple[int, int, int]] = []
        self._disp_interp_idx: list[int] = []
        for i, fc in enumerate(self._disp_f):
            lo_idx = int(np.searchsorted(fft_freqs, float(fc) / half_step, side="left"))
            hi_idx = int(np.searchsorted(fft_freqs, float(fc) * half_step, side="right"))
            if hi_idx - lo_idx >= 2:
                self._disp_max_ranges.append((i, lo_idx, hi_idx))
            else:
                self._disp_interp_idx.append(i)
        self._disp_interp_idx_arr = np.asarray(self._disp_interp_idx, dtype=np.intp)
        self._disp_interp_f_arr = self._disp_f[self._disp_interp_idx_arr] if self._disp_interp_idx else np.empty(0, dtype=np.float32)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()

    @property
    def dropped_cycles(self) -> int:
        return self._dropped_cycles

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="ListenScope-CPUAnalysisWorker",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def reset_harmony(self, *, include_buffered_audio: bool = False) -> None:
        """Reset chord, chroma history, key window, and BPM accumulators cleanly (e.g. on song change)."""
        with self._analysis_lock:
            self._harmony_generation += 1
            _, end, generation = self.ring_buffer.frame_state()
            self._reset_boundary = None if include_buffered_audio else (generation, end)
            self.chords.reset()
            self.chroma.clear()
            self.tempo.reset()
            self._frame_count = 0
            self._last_analyzed_frame = -1
            self._onset_cursor = None
            self._onset_generation = None
            with self._lock:
                self._latest_snapshot = None

    def latest_snapshot(self) -> Optional[AnalysisSnapshot]:
        with self._lock:
            return self._latest_snapshot

    def analyze_latest_once(self) -> AnalysisSnapshot:
        """Synchronously compute one analysis snapshot from recent ring buffer audio."""
        with self._analysis_lock:
            return self._analyze_latest_locked()

    def _analyze_latest_locked(self) -> AnalysisSnapshot:
        sr = self.audio_config.sample_rate
        fft_size = self.config.fft_size
        window_sec = max(0.1, fft_size / float(sr))
        _, latest_abs, ring_generation = self.ring_buffer.frame_state()
        if self._onset_generation != ring_generation:
            self.tempo.reset()
            self._onset_cursor = None
            self._onset_generation = ring_generation

        recent_frames = max(fft_size, int(0.36 * sr))
        max_read_frames = max(recent_frames, int(round(max(window_sec, 2.0 + window_sec) * sr)))
        if self._onset_cursor is None:
            read_frames = max_read_frames
        else:
            needed_for_onset = max(0, latest_abs - (self._onset_cursor - fft_size) + self.tempo.hop_frames)
            read_frames = min(max_read_frames, max(recent_frames, needed_for_onset))
        pcm, start_abs, end_abs = self.ring_buffer.read_recent(read_frames / float(sr))
        if self._reset_boundary is not None and self._reset_boundary[0] == ring_generation:
            cut = max(0, self._reset_boundary[1] - start_abs)
            pcm = pcm[cut:]
            start_abs = max(start_abs, self._reset_boundary[1])

        if pcm.shape[0] == 0:
            mono = np.zeros(fft_size, dtype=np.float32)
            mono_recent = mono
            mono_all = mono[:0]
            rms_db = -120.0
            peak_db = -120.0
            audio_silent = True
            is_silent = True
        else:
            if pcm.shape[1] == 2:
                mono_all = (0.5 * (pcm[:, 0] + pcm[:, 1])).astype(np.float32, copy=False)
            else:
                mono_all = np.mean(pcm, axis=1, dtype=np.float32)
            pcm_recent = pcm[-recent_frames:]
            mono_recent = mono_all[-recent_frames:]
            pitch_frames = max(fft_size, int(0.15 * sr))
            mono = mono_all[-pitch_frames:]
            _, rms_db, _, peak_db = compute_rms_and_peak(pcm[-pitch_frames:])
            prev_abs = self._last_analyzed_frame
            audio_silent = rms_db < self.config.silence_threshold_dbfs
            is_silent = (end_abs == prev_abs) or audio_silent

        wf_min, wf_max = self.spectrum.compute_waveform_envelope(mono)
        fft_mag, fft_db, log_db = self.spectrum.analyze_frame(mono)
        pitch_est = self.pitch.estimate_from_pcm(mono, is_silent=is_silent)

        self._last_analyzed_frame = end_abs
        record_hist = not (pcm.shape[0] == 0 and self._reset_boundary is not None)
        chroma_12, bass_12 = self.chroma.extract_with_bass_from_pcm(
            mono_recent, record_history=record_hist, is_silent=is_silent
        )
        chord_est = self.chords.update(chroma_12, is_silent=is_silent, bass_chroma=bass_12)

        self._frame_count += 1
        # Update key every ~8 cycles (~0.5s) to keep CPU overhead negligible
        with self._lock:
            prev_snap = self._latest_snapshot
        if self._frame_count % 8 == 1 or prev_snap is None:
            chroma_win, weight_win, bass_win = self.chroma.recent_chroma_bundle(
                seconds=float(self.config.key_window_seconds)
            )
            key_est = self.key_detector.estimate(
                chroma_win, frame_weights=weight_win, bass_window=bass_win
            )
        else:
            key_est = prev_snap.key

        # Advance sample-clock HOP=512 onset envelope decoupled from GUI/timer scheduling rate
        hop = self.tempo.hop_frames
        if mono_all.shape[0] >= fft_size:
            min_cursor = start_abs + fft_size
            max_catchup_start = max(min_cursor, end_abs - 2 * sr)
            if self._onset_cursor is None or self._onset_cursor < min_cursor:
                cursor = min_cursor
            elif self._onset_cursor < max_catchup_start:
                cursor = max_catchup_start
            else:
                cursor = self._onset_cursor

            silence_sq = float(10.0 ** (self.config.silence_threshold_dbfs / 10.0))
            active_slices: list[np.ndarray] = []
            hop_flags: list[bool] = []
            while cursor <= end_abs:
                end_off = cursor - start_abs
                win_slice = mono_all[end_off - fft_size : end_off]
                mean_sq = float(np.dot(win_slice, win_slice)) / float(fft_size)
                if not np.isfinite(mean_sq) or mean_sq < silence_sq:
                    hop_flags.append(True)
                else:
                    hop_flags.append(False)
                    active_slices.append(win_slice)
                cursor += hop
            self._onset_cursor = cursor
            if active_slices:
                batch_db = self.spectrum.log_spectrum_batch(np.stack(active_slices, axis=0))
                b_idx = 0
                for silent_hop in hop_flags:
                    if silent_hop:
                        self.tempo.push_frame(np.empty(0, dtype=np.float32), is_silent=True)
                    else:
                        self.tempo.push_frame(batch_db[b_idx], is_silent=False)
                        b_idx += 1
            else:
                for _ in hop_flags:
                    self.tempo.push_frame(np.empty(0, dtype=np.float32), is_silent=True)

        tempo_est = self.tempo.maybe_estimate()

        # Log-frequency 1/24-octave display resampling (dense bass bins + high-freq max-pooling)
        fft_freqs = self.spectrum.fft_freqs
        disp_db = np.empty(self._disp_f.shape[0], dtype=np.float32)
        if self._disp_interp_idx_arr.size > 0:
            disp_db[self._disp_interp_idx_arr] = np.interp(
                self._disp_interp_f_arr, fft_freqs, fft_db
            ).astype(np.float32)
        for out_i, lo_i, hi_i in self._disp_max_ranges:
            disp_db[out_i] = float(np.max(fft_db[lo_i:hi_i]))

        snap = AnalysisSnapshot(
            timestamp=time.time(),
            waveform_min=wf_min.tolist(),
            waveform_max=wf_max.tolist(),
            fft_freqs_hz=self._disp_f_list,
            fft_db=disp_db.tolist(),
            log_freqs_hz=self.spectrum.log_freqs.tolist(),
            log_spectrum_db=log_db.tolist(),
            chroma_12=chroma_12.tolist(),
            chord=chord_est,
            key=key_est,
            tempo=tempo_est,
            pitch=pitch_est,
            rms_dbfs=rms_db,
            peak_dbfs=peak_db,
            window_seconds=self.ring_buffer.available_seconds,
        )
        with self._lock:
            self._latest_snapshot = snap
        return snap

    def _run_loop(self) -> None:
        period = 1.0 / max(1.0, self.config.analysis_rate_hz)
        while not self._stop_event.is_set():
            t0 = time.monotonic()
            try:
                self.analyze_latest_once()
            except Exception:
                logger.exception("Error in CPU AnalysisWorker")
            elapsed = time.monotonic() - t0
            if elapsed > period:
                self._dropped_cycles += 1
            remaining = max(0.005, period - elapsed)
            self._stop_event.wait(timeout=remaining)
