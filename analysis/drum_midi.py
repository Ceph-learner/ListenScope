"""Export the detected onsets as a standalone General MIDI percussion track."""

from math import isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile

import mido

from core.models import DrumsAnalysisResult


def export_drum_midi(drums: DrumsAnalysisResult, destination: Path) -> int:
    """Save the source-relative onsets and return the number of exported hits."""
    if not isfinite(drums.duration_sec) or drums.duration_sec <= 0:
        raise ValueError("鼓轨时长无效。")
    bpm = drums.estimated_bpm
    tempo = mido.bpm2tempo(bpm if bpm is not None and 30 <= bpm <= 240 else 120)
    midi = mido.MidiFile(type=0, ticks_per_beat=480)
    track = midi.add_track("ListenScope Drums (GM)")
    track.append(mido.MetaMessage("set_tempo", tempo=tempo))

    ticks_per_beat = midi.ticks_per_beat
    clip_end = round(mido.second2tick(drums.duration_sec, ticks_per_beat, tempo))
    note_length = max(1, round(mido.second2tick(0.04, ticks_per_beat, tempo)))
    events = []
    for note, times in (
        (36, drums.kick_times_sec),
        (38, drums.snare_times_sec),
        (42, drums.hihat_times_sec),
    ):
        starts = sorted({
            round(mido.second2tick(seconds, ticks_per_beat, tempo))
            for seconds in times if isfinite(seconds) and 0 <= seconds < drums.duration_sec
        })
        for index, start in enumerate(starts):
            stop = min(start + note_length, max(clip_end, start + 1))
            if index + 1 < len(starts):
                stop = min(stop, starts[index + 1])
            events.extend(((start, True, note), (stop, False, note)))

    if not events:
        raise ValueError("当前分析没有可导出的鼓点。")

    last_tick = 0
    # Sorting the boolean puts note_off before note_on on the same tick.
    for tick, active, note in sorted(events):
        track.append(mido.Message(
            "note_on" if active else "note_off", channel=9, note=note,
            velocity=90 if active else 0, time=tick - last_tick,
        ))
        last_tick = tick
    track.append(mido.MetaMessage("end_of_track", time=max(0, clip_end - last_tick)))

    path = Path(destination)
    temp_path = None
    try:
        with NamedTemporaryFile(dir=path.parent, suffix=".mid.tmp", delete=False) as stream:
            temp_path = Path(stream.name)
            midi.save(file=stream)
        temp_path.replace(path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return len(events) // 2
