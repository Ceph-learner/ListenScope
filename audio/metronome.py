"""Pure-CPU Tap Tempo tracker & sample-accurate Practice Metronome (zero GPU / bounded RAM)."""

from __future__ import annotations

from collections import deque
import logging
import math
import threading
import time
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


class TapTempoTracker:
    """Bounded monotonic-clock Tap Tempo estimator (CPU-only, max 8 recent taps)."""

    def __init__(self, *, max_taps: int = 8, reset_gap_sec: float = 2.5) -> None:
        self._taps: deque[float] = deque(maxlen=max(3, int(max_taps)))
        self._reset_gap_sec = max(0.8, float(reset_gap_sec))
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._taps.clear()

    @property
    def tap_count(self) -> int:
        with self._lock:
            return len(self._taps)

    def tap(self, timestamp_sec: Optional[float] = None) -> Optional[float]:
        """Record one beat tap and return stabilized median BPM once >= 2 taps exist."""
        now = time.monotonic() if timestamp_sec is None else float(timestamp_sec)
        if not math.isfinite(now):
            return None
        with self._lock:
            if self._taps and (now - self._taps[-1] > self._reset_gap_sec or now <= self._taps[-1]):
                self._taps.clear()
            self._taps.append(now)
            if len(self._taps) < 2:
                return None
            pts = np.asarray(self._taps, dtype=np.float64)
        ibis = np.diff(pts)
        ibis = ibis[ibis > 0.05]
        if ibis.size == 0:
            return None
        median_ibi = float(np.median(ibis))
        bpm = 60.0 / median_ibi
        if not math.isfinite(bpm):
            return None
        return round(max(30.0, min(240.0, bpm)), 1)


def _synthesize_click(
    *,
    sample_rate: int,
    channels: int,
    freq_hz: float,
    duration_ms: float,
    decay_tau_ms: float,
    amplitude: float,
) -> np.ndarray:
    n = max(16, int(round(sample_rate * (duration_ms / 1000.0))))
    t = np.arange(n, dtype=np.float32) / float(sample_rate)
    tau = max(1e-4, decay_tau_ms / 1000.0)
    attack_len = max(1, min(n // 4, int(round(0.0015 * sample_rate))))
    env = np.exp(-t / tau).astype(np.float32)
    env[:attack_len] *= np.linspace(0.0, 1.0, attack_len, dtype=np.float32)
    # Slight transient pitch drop gives clean woodblock/click articulation in dense mixes
    phase = 2.0 * np.pi * (freq_hz * t + 0.12 * freq_hz * tau * (1.0 - np.exp(-t / tau)))
    mono = (amplitude * env * np.sin(phase)).astype(np.float32)
    return np.repeat(mono[:, None], max(1, channels), axis=1)


class PracticeMetronome:
    """Thread-safe sample-accurate CPU practice metronome supporting standalone output & playback overlay."""

    def __init__(self, *, sample_rate: int = 48000, channels: int = 2) -> None:
        self.sample_rate = max(8000, int(sample_rate))
        self.channels = max(1, int(channels))
        self._lock = threading.RLock()

        self._bpm: float = 120.0
        self._beats_per_bar: int = 4
        self._volume: float = 0.70
        self._overlay_enabled: bool = False
        self._count_in_enabled: bool = False
        self._count_in_remaining: int = 0
        self._count_in_beats_started: int = 0
        self._standalone_playing: bool = False
        self._stream: Any = None

        # Pre-synthesized immutable clicks (~46 KB total)
        self._accent_click = _synthesize_click(
            sample_rate=self.sample_rate,
            channels=self.channels,
            freq_hz=1560.0,
            duration_ms=36.0,
            decay_tau_ms=6.5,
            amplitude=0.82,
        )
        self._beat_click = _synthesize_click(
            sample_rate=self.sample_rate,
            channels=self.channels,
            freq_hz=1040.0,
            duration_ms=28.0,
            decay_tau_ms=5.2,
            amplitude=0.56,
        )

        # Beat grid & active tail cursors
        self._sample_in_beat: float = 0.0
        self._beat_idx: int = 0
        self._first_beat_pending: bool = True
        self._active_click: Optional[np.ndarray] = None
        self._active_pos: int = 0

    @property
    def bpm(self) -> float:
        with self._lock:
            return self._bpm

    @property
    def beats_per_bar(self) -> int:
        with self._lock:
            return self._beats_per_bar

    @property
    def volume(self) -> float:
        with self._lock:
            return self._volume

    @property
    def overlay_enabled(self) -> bool:
        with self._lock:
            return self._overlay_enabled

    @property
    def count_in_enabled(self) -> bool:
        with self._lock:
            return self._count_in_enabled

    @property
    def is_counting_in(self) -> bool:
        with self._lock:
            return self._count_in_remaining > 0

    @property
    def count_in_remaining_frames(self) -> int:
        with self._lock:
            return self._count_in_remaining

    @property
    def standalone_playing(self) -> bool:
        with self._lock:
            return self._standalone_playing

    def set_bpm(self, bpm: float) -> float:
        f = float(bpm)
        with self._lock:
            if not math.isfinite(f):
                return self._bpm
            self._bpm = round(max(30.0, min(240.0, f)), 1)
            return self._bpm

    def set_beats_per_bar(self, beats: int) -> int:
        val = max(1, min(12, int(beats)))
        with self._lock:
            self._beats_per_bar = val
            self._beat_idx %= val
            return self._beats_per_bar

    def set_volume(self, volume: float) -> float:
        f = float(volume)
        with self._lock:
            if not math.isfinite(f):
                return self._volume
            self._volume = max(0.0, min(1.5, f))
            return self._volume

    def set_overlay_enabled(self, enabled: bool) -> None:
        with self._lock:
            prev = self._overlay_enabled
            self._overlay_enabled = bool(enabled)
            if enabled and not prev and self._count_in_remaining <= 0:
                self._reset_phase_locked()

    def set_count_in_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._count_in_enabled = bool(enabled)
            if not self._count_in_enabled:
                self._count_in_remaining = 0
                self._count_in_beats_started = 0

    def count_in_bar_frames(self, *, rate_scale: float = 1.0) -> int:
        raw_scale = float(rate_scale)
        if not math.isfinite(raw_scale):
            raw_scale = 1.0
        with self._lock:
            scale = max(0.25, min(2.0, raw_scale))
            eff_bpm = max(15.0, min(480.0, self._bpm * scale))
            period_samples = (60.0 / eff_bpm) * float(self.sample_rate)
            return max(1, int(round(max(1, self._beats_per_bar) * period_samples)))

    def begin_count_in(self, *, rate_scale: float = 1.0) -> int:
        with self._lock:
            if not self._count_in_enabled:
                self._count_in_remaining = 0
                self._count_in_beats_started = 0
                return 0
            self._reset_phase_locked()
            raw_scale = float(rate_scale)
            if not math.isfinite(raw_scale):
                raw_scale = 1.0
            scale = max(0.25, min(2.0, raw_scale))
            eff_bpm = max(15.0, min(480.0, self._bpm * scale))
            period_samples = (60.0 / eff_bpm) * float(self.sample_rate)
            bar_frames = max(1, int(round(max(1, self._beats_per_bar) * period_samples)))
            self._count_in_remaining = bar_frames
            self._count_in_beats_started = 0
            return bar_frames

    def cancel_count_in(self) -> None:
        with self._lock:
            self._count_in_remaining = 0
            self._count_in_beats_started = 0

    def reset_phase(self) -> None:
        with self._lock:
            self._reset_phase_locked()

    def _reset_phase_locked(self) -> None:
        self._sample_in_beat = 0.0
        self._beat_idx = 0
        self._first_beat_pending = True
        self._active_click = None
        self._active_pos = 0

    def _render_clicks_locked(
        self,
        num_frames: int,
        *,
        rate_scale: float = 1.0,
        max_total_beats: Optional[int] = None,
    ) -> np.ndarray:
        n = max(0, int(num_frames))
        out = np.zeros((n, self.channels), dtype=np.float32)
        if n == 0:
            return out

        raw_scale = float(rate_scale)
        if not math.isfinite(raw_scale):
            raw_scale = 1.0

        gain = self._volume
        scale = max(0.25, min(2.0, raw_scale))
        eff_bpm = max(15.0, min(480.0, self._bpm * scale))
        period_samples = (60.0 / eff_bpm) * float(self.sample_rate)
        beats_bar = max(1, self._beats_per_bar)

        pos = 0
        while pos < n:
            if self._first_beat_pending:
                if max_total_beats is None or self._count_in_beats_started < max_total_beats:
                    self._active_click = self._accent_click if (self._beat_idx % beats_bar == 0) else self._beat_click
                    self._active_pos = 0
                    self._beat_idx = (self._beat_idx + 1) % beats_bar
                    self._count_in_beats_started += 1
                self._sample_in_beat = 0.0
                self._first_beat_pending = False

            rem_to_next_beat = max(1.0, period_samples - self._sample_in_beat)
            step = min(n - pos, int(np.ceil(rem_to_next_beat)))
            if step <= 0:
                step = 1

            if self._active_click is not None and gain > 1e-6:
                avail_tail = int(self._active_click.shape[0]) - self._active_pos
                copy_n = min(step, max(0, avail_tail))
                if copy_n > 0:
                    out[pos : pos + copy_n] += (
                        self._active_click[self._active_pos : self._active_pos + copy_n] * gain
                    )
                    self._active_pos += copy_n
                if self._active_pos >= self._active_click.shape[0]:
                    self._active_click = None
                    self._active_pos = 0

            pos += step
            self._sample_in_beat += float(step)
            if self._sample_in_beat >= period_samples - 1e-5:
                self._sample_in_beat %= period_samples
                if max_total_beats is None or self._count_in_beats_started < max_total_beats:
                    self._active_click = self._accent_click if (self._beat_idx % beats_bar == 0) else self._beat_click
                    self._active_pos = 0
                    self._beat_idx = (self._beat_idx + 1) % beats_bar
                    self._count_in_beats_started += 1

        np.clip(out, -1.0, 1.0, out=out)
        return out

    def render_click_block(self, num_frames: int, *, rate_scale: float = 1.0) -> np.ndarray:
        """Render exact `(num_frames, channels)` float32 click audio aligned to `bpm * rate_scale`."""
        with self._lock:
            return self._render_clicks_locked(num_frames, rate_scale=rate_scale, max_total_beats=None)

    def consume_count_in_block(self, num_frames: int, *, rate_scale: float = 1.0) -> tuple[np.ndarray, int]:
        """Consume up to `num_frames` of active 1-bar count-in pre-roll, returning `(pcm, consumed_frames)`."""
        req = max(0, int(num_frames))
        if req == 0:
            return np.empty((0, self.channels), dtype=np.float32), 0
        with self._lock:
            if self._count_in_remaining <= 0:
                return np.empty((0, self.channels), dtype=np.float32), 0
            take = min(req, self._count_in_remaining)
            block = self._render_clicks_locked(
                take,
                rate_scale=rate_scale,
                max_total_beats=max(1, self._beats_per_bar),
            )
            self._count_in_remaining -= take
            if self._count_in_remaining <= 0:
                self._count_in_remaining = 0
                self._count_in_beats_started = 0
                self._reset_phase_locked()
            return block, take

    def overlay_into(self, pcm_block: np.ndarray, *, rate_scale: float = 1.0) -> np.ndarray:
        """Mix synchronized beat click in-place into an existing PCM block when overlay is enabled."""
        with self._lock:
            active = self._overlay_enabled and self._volume > 1e-6
        if not active or pcm_block.size == 0:
            return pcm_block
        click = self.render_click_block(pcm_block.shape[0], rate_scale=rate_scale)
        if pcm_block.ndim == 1:
            pcm_block += click[:, 0]
        else:
            ch = pcm_block.shape[1]
            if click.shape[1] >= ch:
                pcm_block += click[:, :ch]
            else:
                pcm_block += np.repeat(click[:, :1], ch, axis=1)
        np.clip(pcm_block, -1.0, 1.0, out=pcm_block)
        return pcm_block

    def start_standalone(self, *, open_audio_device: bool = True) -> None:
        with self._lock:
            self._reset_phase_locked()
            self._standalone_playing = True
        if open_audio_device:
            self._ensure_output_stream()

    def stop_standalone(self) -> None:
        with self._lock:
            self._standalone_playing = False
        self._close_output_stream()

    def _ensure_output_stream(self) -> None:
        with self._lock:
            if self._stream is not None or not self._standalone_playing:
                return
        try:
            import sounddevice as sd  # type: ignore[import-not-found]
        except ImportError:
            return

        def _callback(outdata, frames, _time_info, _status) -> None:
            with self._lock:
                playing = self._standalone_playing
            if not playing:
                outdata.fill(0.0)
                return
            outdata[:] = self.render_click_block(frames, rate_scale=1.0)

        stream = None
        try:
            stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                callback=_callback,
            )
            stream.start()
            discard = False
            with self._lock:
                if not self._standalone_playing or self._stream is not None:
                    discard = True
                else:
                    self._stream = stream
            if discard:
                stream.stop()
                stream.close()
        except Exception as exc:
            logger.warning("Metronome output stream unavailable (pull-only mode): %s", exc)
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            with self._lock:
                self._stream = None

    def _close_output_stream(self) -> None:
        with self._lock:
            stream = self._stream
            self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
