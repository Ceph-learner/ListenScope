"""Offline harmony recommendation invariants and native dialog behavior."""

from PySide6 import QtWidgets

from analysis.chord_practice import PRACTICE_KEYS, practice_key, recommend_progressions
from analysis.chords import chord_scale_degree
from core.models import KeyEstimate
from ui.chord_practice import ChordPracticeDialog


def test_practice_matches_recent_prefix_and_keeps_diatonic_spelling():
    result = recommend_progressions("F major", ["F", "C7", "Dm"])[0]
    assert result.chords == ("F", "C", "Dm", "Bb")
    assert result.degrees == ("I", "V", "vi", "IV")
    assert result.matched_steps == 3
    result = recommend_progressions("A minor", ["Am", "F", "C", "G"])[0]
    assert result.degrees == ("i", "VI", "III", "VII")
    assert result.matched_steps == 4
    assert practice_key("C# major") == "Db major"


def test_practice_templates_are_valid_in_all_keys_and_ignore_broken_prefixes():
    assert len(PRACTICE_KEYS) == 24
    for key in PRACTICE_KEYS:
        for template in recommend_progressions(key, []):
            assert tuple(chord_scale_degree(chord, key) for chord in template.chords) == template.degrees
    assert not recommend_progressions("Unknown", ["C"])
    interrupted = recommend_progressions("C major", ["C", "F#", "G"])
    assert all(result.matched_steps < 2 for result in interrupted)


def test_practice_dialog_applies_capo_once_and_allows_manual_key():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    high = KeyEstimate("D major", "B minor", "High", 0.9, 0.15)
    dialog = ChordPracticeDialog(["D", "A", "Bm"], high, -2)
    assert dialog._key.currentData() == "C major"
    assert dialog._results.item(0, 1).text() == "C → G → Am → F"
    assert "3 步" in dialog._results.item(0, 2).text()
    key = dialog._key.findData("A minor")
    dialog._key.setCurrentIndex(key)
    dialog._key.activated.emit(key)
    assert "手动" in dialog._status.text()
    dialog.close()

    uncertain = KeyEstimate("D major", "B minor", "Medium", 0.6, 0.04)
    dialog = ChordPracticeDialog(["D", "A", "Bm"], uncertain, 0)
    assert dialog._key.currentData() is None
    assert dialog._results.rowCount() == 0
    key = dialog._key.findData("D major")
    dialog._key.setCurrentIndex(key)
    dialog._key.activated.emit(key)
    assert dialog._results.rowCount() > 0
    dialog.close()
    app.processEvents()
