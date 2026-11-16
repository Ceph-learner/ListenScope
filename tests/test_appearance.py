"""Appearance settings and rendering regressions for the Qt desktop."""

import json

from PySide6 import QtWidgets

from core.appearance import Appearance
from core.settings_store import load_settings, save_settings
from ui.appearance import AppearanceDialog, appearance_stylesheet
from ui.main_window import DARK_STYLESHEET


def test_appearance_load_and_round_trip_preserve_schema_two(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema_version": 2, "metronome_bpm": 144}), encoding="utf-8")
    settings = load_settings(path)
    assert settings.appearance == Appearance()
    settings.appearance = Appearance.from_mapping({
        "preset": "lenso", "font_size": 500, "background": "#abcdef",
        "accent": "bad", "scope": "panels", "dispersion": -5,
        "strength": True, "softness": 81,
    })
    save_settings(settings, path)
    restored = load_settings(path)
    assert restored.schema_version == 2
    assert restored.metronome_bpm == 144
    assert restored.appearance == Appearance("lenso", 16, "#ABCDEF", "", "", "panels", 45, 81, 0)


def test_appearance_sample_isolated_from_parent_and_scopes_are_painted_only():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    original = Appearance()
    parent = QtWidgets.QWidget()
    parent.setStyleSheet(appearance_stylesheet(DARK_STYLESHEET, original))
    old_style = parent.styleSheet()
    dialog = AppearanceDialog(original, DARK_STYLESHEET, parent)
    dialog._presets.buttons()[1].click()
    assert dialog.values().preset == "lenso"
    dialog._colors["accent"].setText("#123456")
    dialog._scope.setCurrentIndex(dialog._scope.findData("panels"))
    assert "#123456" in dialog._sample.styleSheet()
    assert "QGroupBox, QFrame[trackCard=true]" in dialog._sample.styleSheet()
    dialog._scope.setCurrentIndex(dialog._scope.findData("off"))
    assert "qlineargradient" not in dialog._sample.styleSheet()
    assert not dialog.findChildren(QtWidgets.QGraphicsEffect)
    dialog.reject()
    assert parent.styleSheet() == old_style
    app.processEvents()
