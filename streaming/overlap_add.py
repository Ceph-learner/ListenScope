"""Fixed-size overlap-add crossfader for smooth chunked 2-stem assembly."""

from __future__ import annotations

import numpy as np


class OverlapAddAccumulator:
    """Crossfades trailing overlap samples between consecutive stem chunks in fixed memory."""

    def __init__(self, *, channels: int = 2, overlap_frames: int = 12000) -> None:
        self.channels = channels
        self.overlap_frames = max(0, int(overlap_frames))
        self._tails: dict[str, np.ndarray] = {}

        if self.overlap_frames > 0:
            t = np.linspace(0.0, np.pi * 0.5, self.overlap_frames, dtype=np.float32)
            # Squared-cosine crossfade sums strictly to 1.0 across overlap region
            self._fade_in = np.square(np.sin(t)).reshape(-1, 1)
            self._fade_out = np.square(np.cos(t)).reshape(-1, 1)
        else:
            self._fade_in = np.empty((0, 1), dtype=np.float32)
            self._fade_out = np.empty((0, 1), dtype=np.float32)

    def reset(self) -> None:
        self._tails.clear()

    def process_chunk(self, stems: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """Accept chunk of length >= overlap_frames and emit glitch-free assembled frames."""
        out: dict[str, np.ndarray] = {}
        ov = self.overlap_frames
        for name, chunk in stems.items():
            arr = np.asarray(chunk, dtype=np.float32)
            if arr.ndim == 1:
                arr = np.column_stack([arr, arr])
            if ov <= 0 or arr.shape[0] <= ov:
                out[name] = arr
                continue

            body_len = arr.shape[0] - ov
            tail_next = np.array(arr[-ov:], dtype=np.float32, copy=True)
            prev_tail = self._tails.get(name)

            if prev_tail is None:
                # First chunk outputs everything up to trailing overlap
                emitted = np.array(arr[:body_len], dtype=np.float32, copy=True)
            else:
                emitted = np.array(arr[:body_len], dtype=np.float32, copy=True)
                cross_len = min(ov, body_len)
                emitted[:cross_len] = (
                    prev_tail[:cross_len] * self._fade_out[:cross_len]
                    + emitted[:cross_len] * self._fade_in[:cross_len]
                )
            self._tails[name] = tail_next
            out[name] = emitted
        return out
