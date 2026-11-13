"""History A/B loop playback (from FixedRingBuffer) and synchronized multi-stem mixer."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import threading
from typing import Any, Optional
import wave

import numpy as np

from core.config import AudioConfig

from .pcm_utils import normalize_to_canonical_pcm
from .ring_buffer import FixedRingBuffer

logger = logging.getLogger(__name__)

AB_PAUSE_PLAYER_HINT = "建议暂停原播放器（如 QQ 音乐），避免与 ListenScope A/B 回放重音叠加。"


@dataclass
class StemTrackState:
    name: str
    path: Path
    duration_sec: float
    total_frames: int       # Total frames aligned to StemMixerEngine.sample_rate
    sample_rate: int        # Native source WAV sample rate
    channels: int
    muted: bool = False
    solo: bool = False
    volume: float = 1.0
    native_total_frames: int = 0


class _StemHandle:
    """Streaming reader over `soundfile.SoundFile` (with stdlib `wave` fallback)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.sf_handle: Any = None
        self.wf_handle: Any = None
        try:
            import soundfile as sf  # type: ignore[import-untyped]

            handle = sf.SoundFile(str(path), "r")
            self.sf_handle = handle
            self.sample_rate = int(handle.samplerate)
            self.channels = int(handle.channels)
            self.total_frames = int(handle.frames)
        except Exception:
            wf = wave.open(str(path), "rb")
            self.wf_handle = wf
            self.sample_rate = int(wf.getframerate())
            self.channels = int(wf.getnchannels())
            self.total_frames = int(wf.getnframes())

    def read_frames_f32(self, start_frame: int, num_frames: int) -> np.ndarray:
        if start_frame < 0:
            start_frame = 0
        if start_frame >= self.total_frames or num_frames <= 0:
            return np.empty((0, max(1, self.channels)), dtype=np.float32)

        take = min(num_frames, self.total_frames - start_frame)
        if self.sf_handle is not None:
            self.sf_handle.seek(start_frame)
            data = self.sf_handle.read(take, dtype="float32", always_2d=True)
            return np.asarray(data, dtype=np.float32)

        assert self.wf_handle is not None
        self.wf_handle.setpos(start_frame)
        raw = self.wf_handle.readframes(take)
        sw = int(self.wf_handle.getsampwidth())
        ch = max(1, self.channels)
        if sw == 2:
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sw == 3:
            raw_u8 = np.frombuffer(raw, dtype=np.uint8)
            usable_b = (raw_u8.size // 3) * 3
            triplets = raw_u8[:usable_b].reshape(-1, 3).astype(np.int32)
            signed = triplets[:, 0] | (triplets[:, 1] << 8) | (triplets[:, 2] << 16)
            signed = np.where(signed & 0x800000, signed - 0x1000000, signed)
            arr = signed.astype(np.float32) / 8388608.0
        elif sw == 4:
            arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
        elif sw == 1:
            arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        else:
            arr = np.zeros(0, dtype=np.float32)
        usable = (arr.size // ch) * ch
        if usable == 0:
            return np.empty((0, ch), dtype=np.float32)
        return arr[:usable].reshape(-1, ch)

    def close(self) -> None:
        for h in (self.sf_handle, self.wf_handle):
            if h is not None:
                try:
                    h.close()
                except Exception:
                    pass
        self.sf_handle = None
        self.wf_handle = None


class HistoryABPlayer:
    """Sample-accurate A/B loop player reading directly from ListenScope's 120s FixedRingBuffer."""

    def __init__(
        self,
        ring_buffer: FixedRingBuffer,
        *,
        audio_config: Optional[AudioConfig] = None,
    ) -> None:
        self.ring_buffer = ring_buffer
        self.audio_config = audio_config or ring_buffer.audio_config
        self._lock = threading.RLock()

        self._a_frame: int = 0
        self._b_frame: int = 0
        self._cursor_frame: int = 0
        self._loop_enabled: bool = True
        self._is_playing: bool = False
        self._stream: Any = None

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._is_playing

    @property
    def loop_range(self) -> tuple[int, int]:
        with self._lock:
            return self._a_frame, self._b_frame

    @property
    def position_frame(self) -> int:
        with self._lock:
            return self._cursor_frame

    def select_recent_seconds(self, seconds: float) -> tuple[int, int]:
        """Select the latest N seconds currently retained in the 120s ring buffer."""
        sr = self.ring_buffer.sample_rate
        newest = self.ring_buffer.total_written_frames
        oldest = self.ring_buffer.oldest_abs_frame
        req = max(1, int(round(seconds * sr)))
        a = max(oldest, newest - req)
        b = newest
        with self._lock:
            self._a_frame = a
            self._b_frame = b
            self._cursor_frame = a
        return a, b

    def set_ab_range(self, a_frame: int, b_frame: int) -> tuple[int, int]:
        oldest = self.ring_buffer.oldest_abs_frame
        newest = self.ring_buffer.total_written_frames
        a = max(oldest, min(int(a_frame), newest))
        b = max(a, min(int(b_frame), newest))
        with self._lock:
            self._a_frame = a
            self._b_frame = b
            self._cursor_frame = a
        return a, b

    def set_loop(self, enabled: bool) -> None:
        with self._lock:
            self._loop_enabled = enabled

    def seek(self, abs_frame: int) -> None:
        with self._lock:
            self._cursor_frame = max(self._a_frame, min(int(abs_frame), self._b_frame))

    def start_playback(self, *, open_audio_device: bool = True) -> str:
        """Start A/B playback and return user-facing QQ Music pause reminder."""
        with self._lock:
            if self._b_frame <= self._a_frame:
                raise ValueError("请先在 120s 历史时间轴选择有效的 A/B 片段。")
            if self._cursor_frame < self._a_frame or self._cursor_frame >= self._b_frame:
                self._cursor_frame = self._a_frame
            self._is_playing = True

        if open_audio_device:
            self._ensure_output_stream()
        return AB_PAUSE_PLAYER_HINT

    def pause(self) -> None:
        with self._lock:
            self._is_playing = False
        self._close_output_stream()

    def stop(self) -> None:
        with self._lock:
            self._is_playing = False
            self._cursor_frame = self._a_frame
        self._close_output_stream()

    def render_block(self, num_frames: int) -> np.ndarray:
        """Pull exact PCM block of shape (num_frames, 2) float32 with A/B wrap-around."""
        out = np.zeros((num_frames, self.audio_config.channels), dtype=np.float32)
        with self._lock:
            if not self._is_playing or self._b_frame <= self._a_frame:
                return out

            oldest = self.ring_buffer.oldest_abs_frame
            a = max(oldest, self._a_frame)
            b = self._b_frame
            if b <= a:
                self._is_playing = False
                return out

            written = 0
            while written < num_frames:
                if self._cursor_frame < a or self._cursor_frame >= b:
                    if self._loop_enabled:
                        self._cursor_frame = a
                    else:
                        self._is_playing = False
                        break

                take = min(num_frames - written, b - self._cursor_frame)
                seg = self.ring_buffer.read_range(self._cursor_frame, self._cursor_frame + take)
                if seg.shape[0] == 0:
                    if self._loop_enabled:
                        self._cursor_frame = a
                        break
                    self._is_playing = False
                    break
                actual = int(seg.shape[0])
                out[written : written + actual] = seg
                written += actual
                self._cursor_frame += actual
                if self._cursor_frame >= b and not self._loop_enabled:
                    self._is_playing = False
                    break

        return out

    def _ensure_output_stream(self) -> None:
        if self._stream is not None:
            return
        try:
            import sounddevice as sd  # type: ignore[import-not-found]
        except ImportError:
            logger.debug("sounddevice not installed; HistoryABPlayer running in pull-only mode")
            return

        def _callback(outdata, frames, _time_info, _status) -> None:
            block = self.render_block(frames)
            outdata[:] = block

        try:
            self._stream = sd.OutputStream(
                samplerate=self.audio_config.sample_rate,
                channels=self.audio_config.channels,
                dtype="float32",
                callback=_callback,
            )
            self._stream.start()
        except Exception as exc:
            logger.warning("Failed to open sounddevice output stream (pull-only mode active): %s", exc)
            self._stream = None

    def _close_output_stream(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass


class StemMixerEngine:
    """Time-synchronized multi-stem player and streaming WAV exporter."""

    def __init__(self, sample_rate: int = 48000, channels: int = 2) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._lock = threading.RLock()
        self._tracks: dict[str, StemTrackState] = {}
        self._wave_handles: dict[str, _StemHandle] = {}
        self._position_frame: int = 0
        self._max_frames: int = 0
        self._is_playing: bool = False
        self._loop_enabled: bool = True
        self._stream: Any = None

    @property
    def tracks(self) -> dict[str, StemTrackState]:
        with self._lock:
            return dict(self._tracks)

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._is_playing

    @property
    def position_frame(self) -> int:
        with self._lock:
            return self._position_frame

    @property
    def max_frames(self) -> int:
        with self._lock:
            return self._max_frames

    def clear(self) -> None:
        self.stop()
        with self._lock:
            for h in self._wave_handles.values():
                h.close()
            self._wave_handles.clear()
            self._tracks.clear()
            self._max_frames = 0
            self._position_frame = 0

    def load_stems(self, stem_paths: dict[str, str | Path]) -> dict[str, StemTrackState]:
        """Register stem WAV files using streaming handles (supports 16/24/32-bit/float32 & resampling)."""
        self.clear()
        with self._lock:
            for stem_name, raw_path in stem_paths.items():
                path = Path(raw_path)
                if not path.exists():
                    continue
                handle = _StemHandle(path)
                native_frames = handle.total_frames
                sr = handle.sample_rate
                ch = handle.channels
                engine_frames = (
                    native_frames
                    if sr == self.sample_rate
                    else int(round(native_frames * (self.sample_rate / float(max(1, sr)))))
                )
                self._wave_handles[stem_name] = handle
                self._tracks[stem_name] = StemTrackState(
                    name=stem_name,
                    path=path,
                    duration_sec=native_frames / float(max(1, sr)),
                    total_frames=engine_frames,
                    sample_rate=sr,
                    channels=ch,
                    native_total_frames=native_frames,
                )
                self._max_frames = max(self._max_frames, engine_frames)
            return dict(self._tracks)

    def set_mute(self, stem_name: str, muted: bool) -> None:
        with self._lock:
            if stem_name in self._tracks:
                self._tracks[stem_name].muted = muted

    def set_solo(self, stem_name: str, solo: bool) -> None:
        with self._lock:
            if stem_name in self._tracks:
                self._tracks[stem_name].solo = solo

    def set_volume(self, stem_name: str, volume: float) -> None:
        with self._lock:
            if stem_name in self._tracks:
                self._tracks[stem_name].volume = max(0.0, min(1.5, float(volume)))

    def apply_preset(self, preset: str) -> None:
        """Apply quick listening presets: bass_only, drums_only, vocals_only, other_only, instrumental_mix, all."""
        with self._lock:
            for t in self._tracks.values():
                t.solo = False
                t.muted = False
            if preset == "all":
                return
            if preset == "instrumental_mix":
                if "instrumental" in self._tracks:
                    for name, t in self._tracks.items():
                        t.muted = name != "instrumental"
                elif "vocals" in self._tracks:
                    self._tracks["vocals"].muted = True
                return
            target = preset.replace("_only", "").lower()
            for name, t in self._tracks.items():
                t.muted = name.lower() != target

    def seek(self, frame: int) -> None:
        with self._lock:
            self._position_frame = max(0, min(int(frame), self._max_frames))

    def play(self, *, open_audio_device: bool = True) -> None:
        with self._lock:
            if self._max_frames <= 0:
                return
            self._is_playing = True
        if open_audio_device:
            self._ensure_output_stream()

    def pause(self) -> None:
        with self._lock:
            self._is_playing = False
        self._close_output_stream()

    def stop(self) -> None:
        with self._lock:
            self._is_playing = False
            self._position_frame = 0
        self._close_output_stream()

    def _effective_gain(self, track: StemTrackState, any_solo: bool) -> float:
        if any_solo:
            return track.volume if (track.solo and not track.muted) else 0.0
        return 0.0 if track.muted else track.volume

    def _read_track_chunk(self, name: str, start_frame: int, num_frames: int) -> np.ndarray:
        handle = self._wave_handles.get(name)
        track = self._tracks.get(name)
        if handle is None or track is None or start_frame >= track.total_frames or num_frames <= 0:
            return np.zeros((num_frames, self.channels), dtype=np.float32)

        if track.sample_rate == self.sample_rate:
            raw_arr = handle.read_frames_f32(start_frame, num_frames)
            if raw_arr.shape[0] == 0:
                return np.zeros((num_frames, self.channels), dtype=np.float32)
            ch = raw_arr.shape[1]
            if ch == 1 and self.channels == 2:
                raw_arr = np.repeat(raw_arr, 2, axis=1)
            elif ch > 2 and self.channels == 2:
                raw_arr = raw_arr[:, :2]
        else:
            src_start = int(round(start_frame * (track.sample_rate / float(self.sample_rate))))
            src_count = max(1, int(round(num_frames * (track.sample_rate / float(self.sample_rate)))) + 4)
            raw_arr = handle.read_frames_f32(src_start, src_count)
            if raw_arr.shape[0] == 0:
                return np.zeros((num_frames, self.channels), dtype=np.float32)
            raw_arr = normalize_to_canonical_pcm(
                raw_arr,
                src_rate=track.sample_rate,
                src_channels=max(1, track.channels),
                dst_rate=self.sample_rate,
                dst_channels=self.channels,
            )

        if raw_arr.shape[0] > num_frames:
            return raw_arr[:num_frames]
        if raw_arr.shape[0] < num_frames:
            padded = np.zeros((num_frames, self.channels), dtype=np.float32)
            padded[: raw_arr.shape[0]] = raw_arr
            return padded
        return raw_arr

    def render_block(self, num_frames: int, *, advance: bool = True) -> np.ndarray:
        """Render synchronized mixed audio block across active stems."""
        mix = np.zeros((num_frames, self.channels), dtype=np.float32)
        with self._lock:
            if self._max_frames <= 0 or (advance and not self._is_playing):
                return mix
            if self._position_frame >= self._max_frames:
                if self._loop_enabled and advance:
                    self._position_frame = 0
                else:
                    if advance:
                        self._is_playing = False
                    return mix

            any_solo = any(t.solo for t in self._tracks.values())
            for name, track in self._tracks.items():
                gain = self._effective_gain(track, any_solo)
                if gain <= 1e-6:
                    continue
                chunk = self._read_track_chunk(name, self._position_frame, num_frames)
                mix += chunk * gain

            if advance:
                self._position_frame += num_frames
                if self._position_frame >= self._max_frames:
                    if self._loop_enabled:
                        self._position_frame = 0
                    else:
                        self._is_playing = False
                        self._position_frame = self._max_frames

        np.clip(mix, -1.0, 1.0, out=mix)
        return mix

    def export_mix_streaming(self, out_path: Path | str, *, chunk_frames: int = 48000) -> Path:
        """Export current mute/solo/volume mix cleanly in chunks without duplicating stems in RAM."""
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if self._max_frames <= 0:
                raise ValueError("当前没有可导出的分离音轨。")
            saved_pos = self._position_frame
            saved_playing = self._is_playing
            any_solo = any(t.solo for t in self._tracks.values())
            try:
                with wave.open(str(path), "wb") as out_wf:
                    out_wf.setnchannels(self.channels)
                    out_wf.setsampwidth(2)
                    out_wf.setframerate(self.sample_rate)

                    cursor = 0
                    while cursor < self._max_frames:
                        n = min(chunk_frames, self._max_frames - cursor)
                        mix = np.zeros((n, self.channels), dtype=np.float32)
                        for name, track in self._tracks.items():
                            gain = self._effective_gain(track, any_solo)
                            if gain <= 1e-6:
                                continue
                            mix += self._read_track_chunk(name, cursor, n) * gain
                        np.clip(mix, -1.0, 1.0, out=mix)
                        out_wf.writeframes((mix * 32767.0).astype(np.int16).tobytes())
                        cursor += n
            finally:
                self._position_frame = saved_pos
                self._is_playing = saved_playing
        return path

    def get_stem_waveform_envelope(self, stem_name: str, num_points: int = 240) -> tuple[np.ndarray, np.ndarray]:
        """Compute bounded-cost downsampled waveform min/max envelope via streaming reads."""
        with self._lock:
            track = self._tracks.get(stem_name)
            handle = self._wave_handles.get(stem_name)
            if track is None or handle is None or track.native_total_frames <= 0:
                z = np.zeros(num_points, dtype=np.float32)
                return z, z
            step = max(1, track.native_total_frames // num_points)
            read_per_bin = min(step, 2048)  # Keep UI preview O(1) fast even for 30-min WAVs
            mins = np.zeros(num_points, dtype=np.float32)
            maxs = np.zeros(num_points, dtype=np.float32)
            for i in range(num_points):
                start = i * step
                if start >= track.native_total_frames:
                    break
                chunk = handle.read_frames_f32(start, min(read_per_bin, track.native_total_frames - start))
                if chunk.size == 0:
                    continue
                mono = np.mean(chunk, axis=1)
                mins[i] = float(np.min(mono))
                maxs[i] = float(np.max(mono))
            return mins, maxs

    def _ensure_output_stream(self) -> None:
        if self._stream is not None:
            return
        try:
            import sounddevice as sd  # type: ignore[import-not-found]
        except ImportError:
            return

        def _callback(outdata, frames, _time_info, _status) -> None:
            outdata[:] = self.render_block(frames, advance=True)

        try:
            self._stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                callback=_callback,
            )
            self._stream.start()
        except Exception:
            self._stream = None

    def _close_output_stream(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
