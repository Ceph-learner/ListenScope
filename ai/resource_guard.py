"""Chunked audio streaming, WAV inspection, temp cleanup, and OOM detection helpers."""

from __future__ import annotations

from dataclasses import dataclass
import gc
import logging
from pathlib import Path
import shutil
from typing import Callable, Optional
import wave

import numpy as np

from core.config import AIConfig

logger = logging.getLogger(__name__)


@dataclass
class WavMetadata:
    path: Path
    sample_rate: int
    channels: int
    sample_width: int
    total_frames: int
    duration_sec: float
    exceeds_default_history_cap: bool
    resource_estimate_note: str


_SF_SUBTYPE_BYTES = {
    "PCM_U8": 1,
    "PCM_S8": 1,
    "PCM_16": 2,
    "PCM_24": 3,
    "PCM_32": 4,
    "FLOAT": 4,
    "DOUBLE": 8,
}


def inspect_wav_header(wav_path: Path | str, ai_config: Optional[AIConfig] = None) -> WavMetadata:
    """Read WAV header in O(1) without loading PCM into RAM."""
    cfg = ai_config or AIConfig()
    path = Path(wav_path)
    sr = 0
    ch = 0
    sw = 2
    nframes = 0
    try:
        import soundfile as sf  # type: ignore[import-untyped]

        info = sf.info(str(path))
        sr = int(info.samplerate)
        ch = int(info.channels)
        sw = _SF_SUBTYPE_BYTES.get(str(info.subtype).upper(), 2)
        nframes = int(info.frames)
    except Exception:
        with wave.open(str(path), "rb") as wf:
            sr = int(wf.getframerate())
            ch = int(wf.getnchannels())
            sw = int(wf.getsampwidth())
            nframes = int(wf.getnframes())

    duration = nframes / float(max(1, sr))
    exceeds = duration > cfg.default_max_history_ai_seconds
    chunk_bytes_f32 = int(cfg.long_audio_chunk_seconds * sr * ch * 4)
    note = (
        f"音频时长 {duration:.1f}s；将按 {cfg.long_audio_chunk_seconds:.0f}s 分块流式读写 "
        f"(单块 PCM 约 {chunk_bytes_f32 / (1024*1024):.1f} MB，不整首加载进 RAM)"
    )
    if exceeds:
        note = f"⚠️ 长音频提示：{note}；默认历史截取上限为 {cfg.default_max_history_ai_seconds:.0f}s。"

    return WavMetadata(
        path=path,
        sample_rate=sr,
        channels=ch,
        sample_width=sw,
        total_frames=nframes,
        duration_sec=duration,
        exceeds_default_history_cap=exceeds,
        resource_estimate_note=note,
    )


def release_torch_and_memory() -> None:
    """Best-effort tensor + CUDA cache release inside worker process."""
    gc.collect()
    try:
        import torch  # type: ignore[import-not-found]

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            if hasattr(torch.cuda, "ipc_collect"):
                torch.cuda.ipc_collect()
    except Exception:
        pass


def is_oom_exception(exc: BaseException) -> bool:
    msg = str(exc).lower()
    if "out of memory" in msg or "cuda error: out of memory" in msg or "cudnn_status_alloc_failed" in msg:
        return True
    try:
        import torch  # type: ignore[import-not-found]

        oom_cls = getattr(torch.cuda, "OutOfMemoryError", None)
        if oom_cls is not None and isinstance(exc, oom_cls):
            return True
    except Exception:
        pass
    return False


def cleanup_temp_outputs(path: Path | str) -> None:
    p = Path(path)
    if not p.exists():
        return
    try:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)
    except Exception as exc:
        logger.debug("Cleanup temp path failed (%s): %s", p, exc)


def _decode_pcm_bytes(raw: bytes, sample_width: int, channels: int) -> np.ndarray:
    if not raw:
        return np.empty((0, channels), dtype=np.float32)
    if sample_width == 2:
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 3:
        raw_u8 = np.frombuffer(raw, dtype=np.uint8)
        usable_b = (raw_u8.size // 3) * 3
        triplets = raw_u8[:usable_b].reshape(-1, 3).astype(np.int32)
        signed = triplets[:, 0] | (triplets[:, 1] << 8) | (triplets[:, 2] << 16)
        signed = np.where(signed & 0x800000, signed - 0x1000000, signed)
        arr = signed.astype(np.float32) / 8388608.0
    elif sample_width == 4:
        arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif sample_width == 1:
        arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width} bytes")
    usable = (arr.size // channels) * channels
    return arr[:usable].reshape(-1, channels)


def stream_chunked_separation(
    input_wav_path: Path | str,
    output_dir: Path | str,
    stem_names: tuple[str, ...],
    separate_chunk_fn: Callable[[np.ndarray, int], dict[str, np.ndarray]],
    *,
    chunk_seconds: float = 20.0,
    overlap_seconds: float = 1.0,
    cancel_check: Optional[Callable[[], bool]] = None,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
) -> dict[str, str]:
    """Stream-read long WAV chunk by chunk, run separation, and stream-write stem WAVs.

    Never materializes the full song PCM or all full-length stems simultaneously in RAM.
    """
    src_path = Path(input_wav_path)
    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    sf_file = None
    in_wf = None
    try:
        try:
            import soundfile as sf  # type: ignore[import-untyped]

            sf_file = sf.SoundFile(str(src_path), "r")
            sr = int(sf_file.samplerate)
            ch = int(sf_file.channels)
            sw = 4
            total_frames = int(sf_file.frames)
        except Exception:
            if sf_file is not None:
                try:
                    sf_file.close()
                except Exception:
                    pass
                sf_file = None
            in_wf = wave.open(str(src_path), "rb")
            sr = int(in_wf.getframerate())
            ch = int(in_wf.getnchannels())
            sw = int(in_wf.getsampwidth())
            total_frames = int(in_wf.getnframes())

        chunk_frames = max(sr, int(round(chunk_seconds * sr)))
        overlap_frames = max(0, min(chunk_frames // 4, int(round(overlap_seconds * sr))))
        total_chunks = max(1, (total_frames + chunk_frames - 1) // chunk_frames)

        out_paths = {name: out_root / f"{src_path.stem}_{name}.wav" for name in stem_names}
        out_wfs = {}
        try:
            for name, p in out_paths.items():
                wf = wave.open(str(p), "wb")
                wf.setnchannels(2 if ch >= 2 else 1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                out_wfs[name] = wf

            for idx in range(total_chunks):
                if cancel_check is not None and cancel_check():
                    raise InterruptedError("Cancelled during chunked separation")

                core_start = idx * chunk_frames
                core_end = min(total_frames, core_start + chunk_frames)
                pad_left = min(core_start, overlap_frames)
                pad_right = min(total_frames - core_end, overlap_frames)

                read_start = core_start - pad_left
                read_len = (core_end - core_start) + pad_left + pad_right
                if sf_file is not None:
                    sf_file.seek(read_start)
                    pcm = np.asarray(sf_file.read(read_len, dtype="float32", always_2d=True), dtype=np.float32)
                else:
                    assert in_wf is not None
                    in_wf.setpos(read_start)
                    raw = in_wf.readframes(read_len)
                    pcm = _decode_pcm_bytes(raw, sw, ch)

                if not np.all(np.isfinite(pcm)):
                    pcm = np.nan_to_num(pcm, nan=0.0, posinf=1.0, neginf=-1.0)
                if pcm.shape[1] == 1:
                    pcm = np.repeat(pcm, 2, axis=1)
                elif pcm.shape[1] > 2:
                    pcm = pcm[:, :2]

                stems = separate_chunk_fn(pcm, sr)
                core_len = core_end - core_start
                for name in stem_names:
                    stem_arr = stems[name]
                    trimmed = stem_arr[pad_left : pad_left + core_len]
                    if ch == 1 and trimmed.shape[1] == 2:
                        trimmed = np.mean(trimmed, axis=1, keepdims=True)
                    pcm_i16 = (np.clip(trimmed, -1.0, 1.0) * 32767.0).astype(np.int16)
                    out_wfs[name].writeframes(pcm_i16.tobytes())

                if progress_cb is not None:
                    progress_cb(idx + 1, total_chunks, f"分块处理 {idx + 1}/{total_chunks}")

                # Drop chunk references immediately before next iteration
                del pcm, stems
        finally:
            for wf in out_wfs.values():
                try:
                    wf.close()
                except Exception:
                    pass
    finally:
        for h in (sf_file, in_wf):
            if h is not None:
                try:
                    h.close()
                except Exception:
                    pass

    return {name: str(path) for name, path in out_paths.items()}
