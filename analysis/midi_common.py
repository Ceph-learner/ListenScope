"""Shared Standard MIDI File (SMF) normalization helpers for Steinberg Cubase compatibility."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Optional

import mido

_VALID_MAJOR_KEY_SIGS = {
    "C": "C",
    "G": "G",
    "D": "D",
    "A": "A",
    "E": "E",
    "B": "B",
    "CB": "Cb",
    "F#": "F#",
    "GB": "Gb",
    "C#": "C#",
    "DB": "Db",
    "F": "F",
    "BB": "Bb",
    "EB": "Eb",
    "AB": "Ab",
    # Enharmonic canonical equivalents for keys outside standard circle-of-fifths key signatures
    "G#": "Ab",
    "D#": "Eb",
    "A#": "Bb",
}

_VALID_MINOR_KEY_SIGS = {
    "A": "Am",
    "E": "Em",
    "B": "Bm",
    "F#": "F#m",
    "C#": "C#m",
    "G#": "G#m",
    "D#": "D#m",
    "EB": "Ebm",
    "A#": "A#m",
    "BB": "Bbm",
    "D": "Dm",
    "G": "Gm",
    "C": "Cm",
    "F": "Fm",
    "AB": "Abm",
    # Enharmonic canonical equivalents
    "DB": "C#m",
    "GB": "F#m",
}

_KEY_PARSE_RE = re.compile(r"^\s*([A-Ga-g][#b♯♭]?)\s*(major|minor|m|maj|大调|小调)?\s*$", re.IGNORECASE)


def to_mido_key_signature(key_label: Optional[str]) -> Optional[str]:
    """Convert ListenScope key strings (`'F# minor'`, `'Db major'`, `'C 大调'`) into mido canonical key_signature names."""
    raw = (key_label or "").strip()
    if not raw or raw in ("-", "Unknown", "Insufficient", "Silent"):
        return None
    m = _KEY_PARSE_RE.match(raw)
    if not m:
        return None
    tonic = m.group(1).replace("♯", "#").replace("♭", "b").strip()
    tonic_key = tonic[0].upper() + tonic[1:].upper() if len(tonic) > 1 else tonic.upper()
    # Keep flat lower 'b' canonicalization only for dictionary lookup uppercase keys
    mode_raw = (m.group(2) or "major").lower()
    is_minor = mode_raw in ("minor", "m", "小调")
    cand = _VALID_MINOR_KEY_SIGS.get(tonic_key) if is_minor else _VALID_MAJOR_KEY_SIGS.get(tonic_key)
    if not cand:
        return None
    try:
        mido.MetaMessage("key_signature", key=cand, time=0)
    except Exception:
        return None
    return cand


def gm_program_for_stem(stem_name: str) -> tuple[int, Optional[int]]:
    """Return `(midi_channel, gm_program_or_None)` suitable for Cubase GM track mapping."""
    low = (stem_name or "").strip().lower()
    if "drum" in low or "perc" in low or "kick" in low or "snare" in low:
        return 9, None
    if "bass" in low:
        return 0, 33  # Electric Bass (finger)
    if "guitar" in low or "other" in low:
        return 0, 25  # Acoustic Guitar (steel)
    if "vocal" in low or "voice" in low or "melody" in low:
        return 0, 52  # Choir Aahs / Lead melody
    return 0, 0  # Acoustic Grand Piano


def _ascii_track_name(name: str, fallback: str = "ListenScope") -> str:
    cleaned = "".join(ch if 32 <= ord(ch) <= 126 else "_" for ch in str(name or "")).strip()
    return cleaned[:64] or fallback


def sanitize_time_signature(numerator: int = 4, denominator: int = 4) -> tuple[int, int]:
    num = max(1, min(16, int(numerator)))
    den = int(denominator)
    if den not in (1, 2, 4, 8, 16):
        den = 4
    return num, den


def append_cubase_header_events(
    track: mido.MidiTrack,
    *,
    track_name: str,
    tempo_bpm: float,
    channel: int = 0,
    program: Optional[int] = 0,
    time_signature: tuple[int, int] = (4, 4),
    key_signature: Optional[str] = None,
    include_controller_reset: bool = True,
) -> int:
    """Append Cubase-compliant tick-0 header metadata cleanly and return integer microsecond tempo."""
    safe_bpm = max(20.0, min(300.0, float(tempo_bpm)))
    tempo = int(mido.bpm2tempo(safe_bpm))
    num, den = sanitize_time_signature(*time_signature)

    track.append(mido.MetaMessage("track_name", name=_ascii_track_name(track_name), time=0))
    track.append(
        mido.MetaMessage(
            "time_signature",
            numerator=num,
            denominator=den,
            clocks_per_click=24,
            notated_32nd_notes_per_beat=8,
            time=0,
        )
    )
    track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))

    mido_key = to_mido_key_signature(key_signature)
    if mido_key is not None:
        track.append(mido.MetaMessage("key_signature", key=mido_key, time=0))

    if channel != 9 and include_controller_reset:
        # Reset All Controllers + Sustain Off + Center Pitch Wheel prevents Cubase stuck controllers
        track.append(mido.Message("control_change", channel=channel, control=121, value=0, time=0))
        track.append(mido.Message("control_change", channel=channel, control=64, value=0, time=0))
        track.append(mido.Message("pitchwheel", channel=channel, pitch=0, time=0))
    if channel != 9 and program is not None:
        track.append(mido.Message("program_change", channel=channel, program=max(0, min(127, int(program))), time=0))
    return tempo


def write_cubase_note_spans(
    spans: Iterable[tuple[int, int, int, int, int]],
    destination: Path | str,
    *,
    track_name: str = "ListenScope Track",
    tempo_bpm: float = 120.0,
    channel: int = 0,
    program: Optional[int] = 0,
    time_signature: tuple[int, int] = (4, 4),
    key_signature: Optional[str] = None,
    ticks_per_beat: int = 480,
    end_tick: Optional[int] = None,
    include_controller_reset: bool = True,
) -> tuple[Path, int]:
    """Write overlap-free note spans `(start_tick, end_tick, channel, pitch, velocity)` as SMF type 0 atomically."""
    midi = mido.MidiFile(type=0, ticks_per_beat=int(ticks_per_beat))
    track = mido.MidiTrack()
    midi.tracks.append(track)

    append_cubase_header_events(
        track,
        track_name=track_name,
        tempo_bpm=tempo_bpm,
        channel=channel,
        program=program,
        time_signature=time_signature,
        key_signature=key_signature,
        include_controller_reset=include_controller_reset,
    )

    normalized_spans: list[tuple[int, int, int, int, int]] = []
    for s_tick, e_tick, ch, pitch, vel in spans:
        st = max(0, int(s_tick))
        et = max(st + 1, int(e_tick))
        c = max(0, min(15, int(ch)))
        n = max(0, min(127, int(pitch)))
        v = max(1, min(127, int(vel)))
        normalized_spans.append((st, et, c, n, v))

    # Prevent overlapping same-(channel, pitch) spans (Cubase splits/truncates overlapping duplicate notes)
    normalized_spans.sort(key=lambda item: (item[2], item[3], item[0], item[1]))
    deduped: list[tuple[int, int, int, int, int]] = []
    for st, et, c, n, v in normalized_spans:
        if deduped and deduped[-1][2] == c and deduped[-1][3] == n:
            ps, pe, pc, pn, pv = deduped[-1]
            if st < pe:
                if st > ps:
                    deduped[-1] = (ps, st, pc, pn, pv)
                    deduped.append((st, max(st + 1, et), c, n, v))
                else:
                    # Identical start tick on same note: keep longer/stronger hit
                    deduped[-1] = (ps, max(pe, et), pc, pn, max(pv, v))
                continue
        deduped.append((st, et, c, n, v))

    # Sort events chronologically with note_off (kind=0) strictly before note_on (kind=1) at equal tick
    events: list[tuple[int, int, int, int, int]] = []
    for st, et, c, n, v in deduped:
        events.append((st, 1, c, n, v))
        events.append((et, 0, c, n, 0))
    events.sort(key=lambda e: (e[0], e[1], e[2], e[3]))

    last_tick = 0
    for tick, kind, ch, note, vel in events:
        msg_type = "note_on" if kind == 1 else "note_off"
        track.append(mido.Message(msg_type, channel=ch, note=note, velocity=vel, time=tick - last_tick))
        last_tick = tick

    eot_tick = last_tick if end_tick is None else max(last_tick, int(end_tick))
    track.append(mido.MetaMessage("end_of_track", time=max(0, eot_tick - last_tick)))

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Optional[Path] = None
    try:
        with NamedTemporaryFile(dir=path.parent, suffix=".mid.tmp", delete=False) as stream:
            temp_path = Path(stream.name)
            midi.save(file=stream)
        temp_path.replace(path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return path, len(deduped)


def normalize_midi_file_for_cubase(
    midi_path: Path | str,
    *,
    track_name: str = "ListenScope MIDI",
    stem_name: str = "bass",
    default_bpm: float = 120.0,
    time_signature: tuple[int, int] = (4, 4),
    key_signature: Optional[str] = None,
) -> Path:
    """Normalize an arbitrary `.mid` file (e.g. Basic Pitch pretty_midi output) for reliable Cubase import."""
    src = Path(midi_path)
    mid = mido.MidiFile(str(src))
    tpb = max(24, int(mid.ticks_per_beat or 480))
    target_tpb = 480
    scale = target_tpb / float(tpb)

    bpm = float(default_bpm)
    num, den = sanitize_time_signature(*time_signature)
    channel, default_prog = gm_program_for_stem(stem_name)

    spans: list[tuple[int, int, int, int, int]] = []
    for tr in mid.tracks:
        abs_tick = 0
        active: dict[tuple[int, int], tuple[int, int]] = {}
        for msg in tr:
            abs_tick += int(msg.time)
            t_scaled = max(0, int(round(abs_tick * scale)))
            if msg.is_meta:
                if msg.type == "set_tempo" and bpm == default_bpm:
                    try:
                        bpm = max(20.0, min(300.0, float(mido.tempo2bpm(msg.tempo))))
                    except Exception:
                        pass
                elif msg.type == "time_signature":
                    num, den = sanitize_time_signature(msg.numerator, msg.denominator)
                continue

            if msg.type == "note_on" and msg.velocity > 0:
                ch = channel if msg.channel != 9 else 9
                key = (ch, int(msg.note))
                if key in active:
                    prev_s, prev_v = active.pop(key)
                    if t_scaled > prev_s:
                        spans.append((prev_s, t_scaled, ch, key[1], prev_v))
                active[key] = (t_scaled, max(1, min(127, int(msg.velocity))))
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                ch = channel if msg.channel != 9 else 9
                key = (ch, int(msg.note))
                if key in active:
                    prev_s, prev_v = active.pop(key)
                    spans.append((prev_s, max(prev_s + 1, t_scaled), ch, key[1], prev_v))

        for (ch, note), (prev_s, prev_v) in active.items():
            spans.append((prev_s, prev_s + 120, ch, note, prev_v))

    out_path, _count = write_cubase_note_spans(
        spans,
        src,
        track_name=track_name,
        tempo_bpm=bpm,
        channel=channel,
        program=default_prog,
        time_signature=(num, den),
        key_signature=key_signature,
        ticks_per_beat=target_tpb,
    )
    return out_path
