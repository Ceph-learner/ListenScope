"""Phase 9: Spotify Basic Pitch MIDI transcription adapter for separated stems.

Designed to run on isolated stems (bass, guitar, piano, vocals) rather than full mix,
producing standard `.mid` files for import into Cubase or other DAWs.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Optional
import wave

import mido
import numpy as np

from core.models import MidiNoteCandidate, MidiTranscriptionResult

from .chroma import PITCH_CLASSES
from .pitch import PitchEstimator


def _midi_to_name(midi_num: int) -> str:
    return f"{PITCH_CLASSES[midi_num % 12]}{(midi_num // 12) - 1}"


def _read_audio_mono_f32(audio_path: Path, *, max_seconds: float = 120.0) -> tuple[np.ndarray, int]:
    """Read up to `max_seconds` of WAV audio (16/24/32-bit int or IEEE float32) as mono float32."""
    try:
        import soundfile as sf  # type: ignore[import-untyped]

        with sf.SoundFile(str(audio_path), "r") as sf_file:
            sr = int(sf_file.samplerate)
            nframes = min(int(sf_file.frames), max(1, int(sr * max_seconds)))
            data = sf_file.read(nframes, dtype="float32", always_2d=True)
        if data.size == 0:
            return np.empty(0, dtype=np.float32), sr
        return np.mean(np.asarray(data, dtype=np.float32), axis=1), sr
    except Exception:
        with wave.open(str(audio_path), "rb") as wf:
            sr = int(wf.getframerate())
            ch = max(1, int(wf.getnchannels()))
            sw = int(wf.getsampwidth())
            nframes = min(int(wf.getnframes()), max(1, int(sr * max_seconds)))
            raw = wf.readframes(nframes)

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
        else:
            arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        if arr.size == 0:
            return np.empty(0, dtype=np.float32), sr
        arr = arr[: (arr.size // ch) * ch].reshape(-1, ch)
        return np.mean(arr, axis=1), sr


def _write_notes_to_midi(
    notes: list[MidiNoteCandidate],
    output_midi_path: Path,
    *,
    bpm: float = 120.0,
) -> Path:
    output_midi_path.parent.mkdir(parents=True, exist_ok=True)
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)

    tempo = mido.bpm2tempo(max(30.0, min(240.0, bpm)))
    track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))

    events: list[tuple[int, str, int, int]] = []
    for n in notes:
        start_tick = max(0, int(round(mido.second2tick(n.start_sec, 480, tempo))))
        end_tick = max(start_tick + 24, int(round(mido.second2tick(n.end_sec, 480, tempo))))
        vel = max(1, min(127, int(n.velocity)))
        pitch = max(0, min(127, int(n.pitch_midi)))
        events.append((start_tick, "note_on", pitch, vel))
        events.append((end_tick, "note_off", pitch, 0))

    # Sort chronologically; note_off before note_on at identical tick avoids zero-length overlap
    events.sort(key=lambda e: (e[0], 0 if e[1] == "note_off" else 1, e[2]))

    last_tick = 0
    for tick, msg_type, pitch, vel in events:
        delta = max(0, tick - last_tick)
        track.append(mido.Message(msg_type, note=pitch, velocity=vel, time=delta))
        last_tick = tick

    track.append(mido.MetaMessage("end_of_track", time=0))
    mid.save(str(output_midi_path))
    return output_midi_path


def _fallback_monophonic_stem_to_notes(audio_path: Path, *, max_seconds: float = 120.0) -> list[MidiNoteCandidate]:
    """Lightweight CPU monophonic note tracker for testing or Basic Pitch-free Core env."""
    mono, sr = _read_audio_mono_f32(audio_path, max_seconds=max_seconds)
    if mono.size == 0:
        return []

    fft_size = 4096
    hop = 2048
    est = PitchEstimator(sample_rate=sr, fft_size=fft_size)
    win = np.hanning(fft_size).astype(np.float32)

    notes: list[MidiNoteCandidate] = []
    cur_midi: Optional[int] = None
    cur_start: float = 0.0
    cur_conf: float = 0.0
    cur_rms: float = 0.0

    for pos in range(0, max(1, mono.shape[0] - fft_size + 1), hop):
        frame = mono[pos : pos + fft_size]
        if frame.shape[0] < fft_size:
            break
        rms = float(np.sqrt(np.mean(np.square(frame))))
        t_sec = pos / float(sr)
        if rms < 0.01:
            if cur_midi is not None and (t_sec - cur_start) >= 0.08:
                notes.append(
                    MidiNoteCandidate(
                        pitch_midi=cur_midi,
                        note_name=_midi_to_name(cur_midi),
                        start_sec=round(cur_start, 3),
                        end_sec=round(t_sec, 3),
                        velocity=max(30, min(120, int(cur_rms * 200))),
                        confidence=round(cur_conf, 3),
                    )
                )
            cur_midi = None
            continue

        mag = np.abs(np.fft.rfft(frame * win)).astype(np.float32)
        p = est.estimate_from_magnitude(mag, is_silent=False)
        if p.frequency_hz is None or p.confidence < 0.2:
            continue
        midi_num = int(round(69.0 + 12.0 * np.log2(p.frequency_hz / 440.0)))
        if cur_midi is None:
            cur_midi = midi_num
            cur_start = t_sec
            cur_conf = p.confidence
            cur_rms = rms
        elif midi_num != cur_midi:
            if (t_sec - cur_start) >= 0.08:
                notes.append(
                    MidiNoteCandidate(
                        pitch_midi=cur_midi,
                        note_name=_midi_to_name(cur_midi),
                        start_sec=round(cur_start, 3),
                        end_sec=round(t_sec, 3),
                        velocity=max(30, min(120, int(cur_rms * 200))),
                        confidence=round(cur_conf, 3),
                    )
                )
            cur_midi = midi_num
            cur_start = t_sec
            cur_conf = p.confidence
            cur_rms = rms

    if cur_midi is not None:
        end_t = mono.shape[0] / float(sr)
        if (end_t - cur_start) >= 0.08:
            notes.append(
                MidiNoteCandidate(
                    pitch_midi=cur_midi,
                    note_name=_midi_to_name(cur_midi),
                    start_sec=round(cur_start, 3),
                    end_sec=round(end_t, 3),
                    velocity=max(30, min(120, int(cur_rms * 200))),
                    confidence=round(cur_conf, 3),
                )
            )
    return notes


def transcribe_stem_to_midi(
    audio_path: Path | str,
    output_midi_path: Path | str,
    *,
    stem_name: str = "bass",
    allow_full_mix: bool = False,
    allow_cpu_pitch_fallback: bool = False,
) -> MidiTranscriptionResult:
    """Transcribe a separated stem WAV to MIDI using Spotify Basic Pitch (ONNX Runtime).

    Refuses full-mix transcription by default (per Section 20) unless `allow_full_mix=True`.
    """
    src = Path(audio_path)
    out = Path(output_midi_path)
    if not src.exists():
        raise FileNotFoundError(f"音频文件不存在: {src}")

    warning: Optional[str] = None
    if stem_name.lower() in ("mix", "full", "full_mix", "original"):
        if not allow_full_mix:
            raise ValueError(
                "Basic Pitch 建议仅用于分轨后的 bass / vocals / piano / guitar 单轨；"
                "默认禁止直接分析复杂完整混音（传入 allow_full_mix=True 才可强制尝试）。"
            )
        warning = "警告：正在对完整混音进行 MIDI 转录，多乐器叠加可能导致大量误检音符。"

    try:
        from basic_pitch import ICASSP_2022_MODEL_PATH  # type: ignore[import-not-found]
        from basic_pitch.inference import predict  # type: ignore[import-not-found]
    except ImportError as exc:
        if not allow_cpu_pitch_fallback:
            raise RuntimeError(
                "未安装 Spotify `basic-pitch`。请在 AI Worker 环境中安装: pip install basic-pitch[onnx]"
            ) from exc
        notes = _fallback_monophonic_stem_to_notes(src)
        _write_notes_to_midi(notes, out)
        return MidiTranscriptionResult(
            source_stem_name=stem_name,
            output_midi_path=out,
            notes=notes,
            backend_used="cpu_monophonic_fallback_test",
            warning=(warning or "") + "（当前使用测试/Core 轻量单音追踪 fallback，非 Spotify Basic Pitch 模型）",
        )

    # Always pass model_or_model_path explicitly so basic-pitch 0.3.x and 0.4.x+ both work
    _model_output, midi_data, note_events = predict(str(src), model_or_model_path=ICASSP_2022_MODEL_PATH)
    out.parent.mkdir(parents=True, exist_ok=True)
    midi_data.write(str(out))

    candidates: list[MidiNoteCandidate] = []
    for start_s, end_s, pitch_midi, amplitude, _bends in note_events:
        p_int = int(pitch_midi)
        candidates.append(
            MidiNoteCandidate(
                pitch_midi=p_int,
                note_name=_midi_to_name(p_int),
                start_sec=round(float(start_s), 3),
                end_sec=round(float(end_s), 3),
                velocity=max(1, min(127, int(round(float(amplitude) * 127)))),
                confidence=round(float(amplitude), 3),
            )
        )
    return MidiTranscriptionResult(
        source_stem_name=stem_name,
        output_midi_path=out,
        notes=candidates,
        backend_used="basic-pitch",
        warning=warning,
    )


def _cli_main() -> int:
    parser = argparse.ArgumentParser(description="ListenScope Basic Pitch MIDI Transcription CLI")
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output-midi", type=Path, required=True)
    parser.add_argument("--stem-name", type=str, default="bass")
    parser.add_argument("--allow-full-mix", action="store_true")
    parser.add_argument("--allow-cpu-fallback", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    res = transcribe_stem_to_midi(
        args.audio,
        args.output_midi,
        stem_name=args.stem_name,
        allow_full_mix=args.allow_full_mix,
        allow_cpu_pitch_fallback=args.allow_cpu_fallback,
    )
    if args.json:
        payload = asdict(res)
        payload["output_midi_path"] = str(res.output_midi_path) if res.output_midi_path is not None else None
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"MIDI written: {res.output_midi_path} ({len(res.notes)} notes, backend={res.backend_used})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
