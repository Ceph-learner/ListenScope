"""Pure-CPU pitch-preserving WSOLA time-stretcher with bounded O(1) memory."""

from __future__ import annotations

from typing import Callable

import numpy as np


class StreamingTimeStretcher:
    """Real-time pull-based WSOLA time-scaler preserving fundamental pitch over 0.5x..1.5x.

    Uses preallocated float32 overlap-add accumulators and Hann-squared weight normalization
    so gain stays strictly unity across arbitrary speed ratios, loop boundaries, and seeks.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 48000,
        channels: int = 2,
        win_size: int = 2048,
        syn_hop: int = 512,
        search_radius: int = 384,
        cmp_len: int = 512,
    ) -> None:
        self.sample_rate = max(8000, int(sample_rate))
        self.channels = max(1, int(channels))
        self.win_size = max(512, int(win_size))
        self.syn_hop = max(128, min(self.win_size // 2, int(syn_hop)))
        self.search_radius = max(64, int(search_radius))
        self.cmp_len = max(128, min(self.win_size - self.syn_hop, int(cmp_len)))

        # Symmetric nonzero-endpoint Hann window for exact COLA weight normalization
        phase = 2.0 * np.pi * (np.arange(self.win_size, dtype=np.float32) + 0.5) / float(self.win_size)
        self._window = (0.5 - 0.5 * np.cos(phase)).astype(np.float32)
        self._window_2d = self._window[:, None]

        accum_len = self.win_size + self.syn_hop
        self._ola_accum = np.zeros((accum_len, self.channels), dtype=np.float32)
        self._weight_accum = np.zeros(accum_len, dtype=np.float32)

        fifo_cap = max(self.win_size * 4, 8192)
        self._fifo = np.zeros((fifo_cap, self.channels), dtype=np.float32)
        self._fifo_count = 0

        self._primed = False
        self._src_cursor_float = 0.0
        self._last_cursor = 0
        self._eof_flushed = False

    def reset(self, rel_cursor: float = 0.0) -> None:
        self._ola_accum.fill(0.0)
        self._weight_accum.fill(0.0)
        self._fifo.fill(0.0)
        self._fifo_count = 0
        self._primed = False
        self._src_cursor_float = max(0.0, float(rel_cursor))
        self._last_cursor = max(0, int(round(self._src_cursor_float)))
        self._eof_flushed = False

    def _push_fifo(self, frames: np.ndarray) -> None:
        n = int(frames.shape[0])
        if n <= 0:
            return
        cap = int(self._fifo.shape[0])
        if self._fifo_count + n > cap:
            # Drop oldest overflow if a pathological caller requests huge blocks repeatedly
            overflow = (self._fifo_count + n) - cap
            if overflow >= self._fifo_count:
                self._fifo_count = 0
            else:
                remain = self._fifo_count - overflow
                self._fifo[:remain] = self._fifo[overflow : overflow + remain]
                self._fifo_count = remain
        take = min(n, cap)
        self._fifo[self._fifo_count : self._fifo_count + take] = frames[:take]
        self._fifo_count += take

    def _pop_fifo(self, dst: np.ndarray, offset: int, count: int) -> int:
        take = min(count, self._fifo_count)
        if take <= 0:
            return 0
        dst[offset : offset + take] = self._fifo[:take]
        remain = self._fifo_count - take
        if remain > 0:
            self._fifo[:remain] = self._fifo[take : take + remain]
        self._fifo_count = remain
        return take

    def _fetch_region(
        self,
        start_rel: int,
        count: int,
        *,
        span_frames: int,
        loop_enabled: bool,
        read_rel_fn: Callable[[int, int], np.ndarray],
    ) -> np.ndarray:
        out = np.zeros((count, self.channels), dtype=np.float32)
        if count <= 0 or span_frames <= 0:
            return out

        if loop_enabled:
            pos = int(start_rel) % span_frames
            written = 0
            while written < count:
                take = min(count - written, span_frames - pos)
                seg = np.asarray(read_rel_fn(pos, take), dtype=np.float32)
                if seg.ndim == 1:
                    seg = np.repeat(seg[:, None], self.channels, axis=1)
                elif seg.shape[1] == 1 and self.channels == 2:
                    seg = np.repeat(seg, 2, axis=1)
                elif seg.shape[1] > self.channels:
                    seg = seg[:, : self.channels]
                actual = min(take, int(seg.shape[0]))
                if actual <= 0:
                    break
                out[written : written + actual] = seg[:actual]
                written += actual
                pos = (pos + actual) % span_frames
            return out

        src_start = max(0, int(start_rel))
        dst_off = src_start - int(start_rel)
        if src_start >= span_frames or dst_off >= count:
            return out
        take = min(count - dst_off, span_frames - src_start)
        seg = np.asarray(read_rel_fn(src_start, take), dtype=np.float32)
        if seg.ndim == 1:
            seg = np.repeat(seg[:, None], self.channels, axis=1)
        elif seg.shape[1] == 1 and self.channels == 2:
            seg = np.repeat(seg, 2, axis=1)
        elif seg.shape[1] > self.channels:
            seg = seg[:, : self.channels]
        actual = min(take, int(seg.shape[0]))
        if actual > 0:
            out[dst_off : dst_off + actual] = seg[:actual]
        return out

    def _find_best_delta(
        self,
        base_pos: int,
        *,
        span_frames: int,
        loop_enabled: bool,
        read_rel_fn: Callable[[int, int], np.ndarray],
    ) -> int:
        cmp_n = self.cmp_len
        w_head = self._weight_accum[:cmp_n]
        valid_mask = w_head > 1e-4
        if not np.any(valid_mask):
            return 0

        ref_stereo = np.zeros((cmp_n, self.channels), dtype=np.float32)
        ref_stereo[valid_mask] = self._ola_accum[:cmp_n][valid_mask] / w_head[valid_mask, None]
        ref_mono = np.mean(ref_stereo, axis=1) if self.channels > 1 else ref_stereo[:, 0]
        e_ref = float(np.dot(ref_mono, ref_mono))
        if e_ref < 1e-8:
            return 0

        r_neg = self.search_radius if loop_enabled else min(self.search_radius, max(0, base_pos))
        r_pos = (
            self.search_radius
            if loop_enabled
            else min(self.search_radius, max(0, span_frames - cmp_n - base_pos))
        )
        total_offsets = r_neg + r_pos + 1
        if total_offsets <= 1:
            return 0

        cand_stereo = self._fetch_region(
            base_pos - r_neg,
            cmp_n + r_neg + r_pos,
            span_frames=span_frames,
            loop_enabled=loop_enabled,
            read_rel_fn=read_rel_fn,
        )
        cand_mono = np.mean(cand_stereo, axis=1) if self.channels > 1 else cand_stereo[:, 0]
        corr = np.correlate(cand_mono, ref_mono, mode="valid")
        if corr.shape[0] != total_offsets:
            return 0

        sq = cand_mono * cand_mono
        cs = np.concatenate([np.zeros(1, dtype=np.float32), np.cumsum(sq, dtype=np.float32)])
        e_cand = cs[cmp_n : cmp_n + total_offsets] - cs[:total_offsets]
        denom = np.sqrt(np.maximum(e_ref * e_cand, 1e-12))
        scores = corr / denom
        scores[r_neg] += 1e-3  # Slight tie-break favoring zero shift
        best_idx = int(np.argmax(scores))
        return best_idx - r_neg

    def _synthesize_step(
        self,
        *,
        speed: float,
        span_frames: int,
        loop_enabled: bool,
        read_rel_fn: Callable[[int, int], np.ndarray],
    ) -> bool:
        """Place one WSOLA grain, push `syn_hop` normalized frames to FIFO, return True if EOF reached."""
        if span_frames <= 0:
            self._eof_flushed = True
            return True

        if not loop_enabled and self._src_cursor_float >= span_frames:
            if not self._eof_flushed:
                # Flush any residual overlapping tail cleanly
                valid = self._weight_accum[: self.win_size] > 1e-4
                if np.any(valid):
                    last_valid = int(np.max(np.where(valid)[0])) + 1
                    tail = self._ola_accum[:last_valid] / np.maximum(self._weight_accum[:last_valid, None], 1e-4)
                    self._push_fifo(tail)
                self._ola_accum.fill(0.0)
                self._weight_accum.fill(0.0)
                self._eof_flushed = True
            self._last_cursor = span_frames
            return True

        if loop_enabled and self._src_cursor_float >= span_frames:
            self._src_cursor_float = self._src_cursor_float % float(span_frames)

        base_pos = int(round(self._src_cursor_float))
        if not self._primed:
            delta = 0
            self._primed = True
        else:
            delta = self._find_best_delta(
                base_pos,
                span_frames=span_frames,
                loop_enabled=loop_enabled,
                read_rel_fn=read_rel_fn,
            )

        actual_pos = base_pos + delta
        if loop_enabled:
            actual_pos %= span_frames
        else:
            actual_pos = max(0, min(span_frames - 1, actual_pos))

        grain = self._fetch_region(
            actual_pos,
            self.win_size,
            span_frames=span_frames,
            loop_enabled=loop_enabled,
            read_rel_fn=read_rel_fn,
        )
        self._ola_accum[: self.win_size] += grain * self._window_2d
        self._weight_accum[: self.win_size] += self._window

        hop = self.syn_hop
        w_out = self._weight_accum[:hop]
        hop_out = np.zeros((hop, self.channels), dtype=np.float32)
        valid_out = w_out > 1e-4
        hop_out[valid_out] = self._ola_accum[:hop][valid_out] / w_out[valid_out, None]
        self._push_fifo(hop_out)

        remain_accum = self._ola_accum.shape[0] - hop
        self._ola_accum[:remain_accum] = self._ola_accum[hop:]
        self._ola_accum[remain_accum:] = 0.0
        self._weight_accum[:remain_accum] = self._weight_accum[hop:]
        self._weight_accum[remain_accum:] = 0.0

        self._last_cursor = actual_pos
        self._src_cursor_float += float(hop) * speed
        return False

    def render_block(
        self,
        num_frames: int,
        *,
        speed: float,
        span_frames: int,
        rel_cursor: int,
        loop_enabled: bool,
        read_rel_fn: Callable[[int, int], np.ndarray],
    ) -> tuple[np.ndarray, int, bool]:
        """Produce `num_frames` pitch-preserved stretched frames and return `(audio, new_rel_cursor, hit_eof)`."""
        out = np.zeros((num_frames, self.channels), dtype=np.float32)
        if num_frames <= 0 or span_frames <= 0:
            return out, 0, True

        spd = max(0.5, min(1.5, float(speed)))
        if not self._primed:
            self._src_cursor_float = max(0.0, float(min(int(rel_cursor), span_frames)))

        written = 0
        while written < num_frames:
            taken = self._pop_fifo(out, written, num_frames - written)
            written += taken
            if written >= num_frames:
                break
            if self._eof_flushed:
                break
            eof_now = self._synthesize_step(
                speed=spd,
                span_frames=span_frames,
                loop_enabled=loop_enabled,
                read_rel_fn=read_rel_fn,
            )
            if eof_now and self._fifo_count == 0:
                break

        np.clip(out, -1.0, 1.0, out=out)
        done_eof = (not loop_enabled) and self._eof_flushed and (self._fifo_count == 0)
        new_cursor = self._last_cursor
        if done_eof:
            new_cursor = span_frames
        elif loop_enabled and span_frames > 0:
            new_cursor = new_cursor % span_frames
        elif not loop_enabled:
            new_cursor = min(span_frames, max(0, new_cursor))
        return out, int(new_cursor), bool(done_eof)
