"""Export the detected onsets as a standalone General MIDI percussion track."""

from math import isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile

import mido

from core.models import DrumsAnalysisResult

from .midi_common import write_cubase_note_spans


def export_drum_midi(drums: DrumsAnalysisResult, destination: Path) -> int:
    """Save the source-relative onsets (Cubase SMF GM channel 9) and return the number of exported hits."""
    if not isfinite(drums.duration_sec) or drums.duration_sec <= 0:
        raise ValueError("鼓轨时长无效。")
    bpm_val = float(drums.estimated_bpm) if drums.estimated_bpm is not None and 30 <= drums.estimated_bpm <= 240 else 120.0
    ticks_per_beat = 480
    tempo = mido.bpm2tempo(bpm_val)
    clip_end = round(mido.second2tick(drums.duration_sec, ticks_per_beat, tempo))
    note_length = max(1, round(mido.second2tick(0.04, ticks_per_beat, tempo)))

    spans: list[tuple[int, int, int, int, int]] = []
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
            spans.append((start, max(start + 1, stop), 9, note, 90))

    if not spans:
        raise ValueError("当前分析没有可导出的鼓点。")

    _out, count = write_cubase_note_spans(
        spans,
        destination,
        track_name="ListenScope Drums (GM)",
        tempo_bpm=bpm_val,
        channel=9,
        program=None,
        time_signature=(4, 4),
        ticks_per_beat=ticks_per_beat,
        end_tick=clip_end,
        include_controller_reset=False,
    )
    return count
