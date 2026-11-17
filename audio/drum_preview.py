"""Short, local drum audition with its own nonblocking output stream."""

from __future__ import annotations

import logging
from math import isfinite

import numpy as np

from core.models import DrumsAnalysisResult


def render_drum_preview(drums: DrumsAnalysisResult, sample_rate: int) -> np.ndarray:
    """Audition up to eight seconds starting at the first detected hit."""
    times_by_voice = [
        sorted({time for time in times if isfinite(time) and 0 <= time < drums.duration_sec})
        for times in (drums.kick_times_sec, drums.snare_times_sec, drums.hihat_times_sec)
    ]
    first = min((times[0] for times in times_by_voice if times), default=None)
    if first is None:
        return np.empty(0, dtype=np.float32)

    limit = 8 * sample_rate
    preview = np.zeros(limit, dtype=np.float32)
    rng = np.random.default_rng(0)
    voices = []
    for duration, decay in ((0.20, 0.060), (0.14, 0.032), (0.07, 0.015)):
        time = np.arange(round(duration * sample_rate)) / sample_rate
        voices.append((time, np.exp(-time / decay)))
    kick_time, kick_decay = voices[0]
    kick = 0.47 * np.sin(2 * np.pi * (48 * kick_time + 2.1 * (1 - np.exp(-kick_time / 0.025)))) * kick_decay
    snare_time, snare_decay = voices[1]
    snare = (0.30 * rng.uniform(-1, 1, snare_time.size) + 0.12 * np.sin(2 * np.pi * 185 * snare_time)) * snare_decay
    hat_time, hat_decay = voices[2]
    hat = 0.16 * np.diff(rng.uniform(-1, 1, hat_time.size + 1)) * hat_decay

    used = 0
    for voice, times in zip((kick, snare, hat), times_by_voice):
        fade = min(max(1, round(0.003 * sample_rate)), voice.size // 2)
        voice[:fade] *= np.linspace(0, 1, fade)
        voice[-fade:] *= np.linspace(1, 0, fade)
        for start in sorted({round((hit - first) * sample_rate) for hit in times if hit - first < 8}):
            stop = min(limit, start + voice.size)
            if stop > start:
                preview[start:stop] += voice[:stop - start]
                used = max(used, stop)

    preview = preview[:used]
    tail = min(preview.size, max(1, round(0.005 * sample_rate)))
    if tail:
        preview[-tail:] *= np.linspace(1, 0, tail)
    peak = np.max(np.abs(preview), initial=0)
    if peak > 0.65:
        preview *= 0.65 / peak
    return preview


class DrumPreviewPlayer:
    """The UI thread owns the stream. The callback only copies prepared PCM."""

    def __init__(self, sample_rate: int, channels: int) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._stream = None

    def play(self, pcm: np.ndarray) -> None:
        import sounddevice as sd

        self.stop()
        position = 0

        def callback(outdata, frames, _time_info, _status):
            nonlocal position
            count = min(frames, pcm.size - position)
            outdata[:count] = pcm[position:position + count, None]
            outdata[count:].fill(0)
            position += count
            if position == pcm.size:
                raise sd.CallbackStop

        stream = sd.OutputStream(
            samplerate=self.sample_rate, channels=self.channels,
            dtype="float32", callback=callback,
        )
        self._stream = stream
        try:
            stream.start()
        except Exception:
            self.stop()
            raise

    def close_if_finished(self) -> bool:
        if self._stream is None:
            return False
        try:
            if self._stream.active:
                return False
        except Exception:
            logging.getLogger(__name__).debug("Could not query drum preview stream", exc_info=True)
        return self.stop()

    def stop(self) -> bool:
        stream, self._stream = self._stream, None
        if stream is None:
            return False
        try:
            stream.abort()
        except Exception:
            logging.getLogger(__name__).debug("Drum preview abort failed", exc_info=True)
        try:
            stream.close()
        except Exception:
            logging.getLogger(__name__).debug("Drum preview close failed", exc_info=True)
        return True
