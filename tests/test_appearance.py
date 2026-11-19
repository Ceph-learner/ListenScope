"""Appearance settings and rendering regressions for the Qt desktop."""

import json
from dataclasses import replace

from PySide6 import QtCore, QtWidgets

from core.appearance import Appearance
from core.settings_store import load_settings, save_settings
from main import ListenScopeController
from ui.appearance import AppearanceDialog, appearance_stylesheet
from ui.main_window import DARK_STYLESHEET
from ui.spectrum_widget import ANALYSIS_VIEWS


def test_appearance_load_and_round_trip_preserve_schema_two(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema_version": 2, "metronome_bpm": 144}), encoding="utf-8")
    settings = load_settings(path)
    assert settings.appearance == Appearance()
    assert settings.appearance.layout == "split"
    assert settings.appearance.analysis_layout == "monitor"
    assert Appearance.from_mapping({"analysis_layout": "invalid"}).analysis_layout == "monitor"
    assert Appearance.from_mapping({"layout": "invalid"}).layout == "split"
    settings.appearance = Appearance.from_mapping({
        "preset": "lenso", "font_size": 500, "background": "#abcdef",
        "accent": "bad", "scope": "panels", "dispersion": -5,
        "strength": True, "softness": 81, "layout": "practice", "analysis_layout": "history",
    })
    save_settings(settings, path)
    restored = load_settings(path)
    assert restored.schema_version == 2
    assert restored.metronome_bpm == 144
    assert restored.appearance == Appearance(
        "lenso", 20, "#ABCDEF", "", "", "panels", 45, 81, 0, "practice", "history", theme_mode="light"
    )


def test_appearance_sample_isolated_from_parent_and_scopes_are_painted_only():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    original = Appearance()
    parent = QtWidgets.QWidget()
    parent.setStyleSheet(appearance_stylesheet(DARK_STYLESHEET, original))
    old_style = parent.styleSheet()
    dialog = AppearanceDialog(original, DARK_STYLESHEET, parent)
    dialog._layout.setCurrentIndex(dialog._layout.findData("practice"))
    dialog._analysis_layout.setCurrentIndex(dialog._analysis_layout.findData("history"))
    dialog._presets.buttons()[1].click()
    assert dialog.values().preset == "lenso"
    assert dialog.values().layout == "practice"
    assert dialog.values().analysis_layout == "history"
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


def test_native_layouts_keep_ab_selection_and_zoom(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    controller = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path)
    try:
        window = controller.window
        mixer = window.mixer_widget
        assert window.appearance.layout == "split"
        assert mixer._workspace_splitter.orientation() == QtCore.Qt.Orientation.Horizontal
        plot = window.history_overview_plot
        region = window.ab_region
        region.setRegion((-35, -15))
        plot.setXRange(-45, -5, padding=0)
        mixer.analysis_tabs.setCurrentIndex(2)
        for layout in ("workbench", "practice", "split"):
            window.apply_appearance(replace(window.appearance, layout=layout))
            workspace = window._workspace_layout
            assert (workspace.indexOf(window._history_box) < workspace.indexOf(window.tabs)) == (layout == "practice")
            splitter = mixer._workspace_splitter
            expected = QtCore.Qt.Orientation.Vertical if layout == "workbench" else QtCore.Qt.Orientation.Horizontal
            assert splitter.orientation() == expected
            assert (splitter.widget(0) is mixer.analysis_tabs) == (layout == "practice")
            assert mixer.analysis_tabs.currentIndex() == 2
            assert window.history_overview_plot is plot and window.ab_region is region
            assert tuple(region.getRegion()) == (-35, -15)
            assert plot.viewRange()[0] == [-45, -5]
        window.zoom_history(0.5)
        assert plot.viewRange()[0] == [-35, -15]
        window.history_reset.click()
        assert plot.viewRange()[0] == [-120, 0]
    finally:
        controller.shutdown()
        controller.window.close()
        app.processEvents()


def test_analysis_views_keep_live_plot_data_and_show_real_frequency(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    controller = ListenScopeController(use_mock_ai_for_demo=True, work_dir=tmp_path)
    try:
        window = controller.window
        panel = window.spectrum_widget
        controller.analysis_worker.stop()
        snap = controller.analysis_worker.analyze_latest_once()
        snap = replace(snap, log_freqs_hz=[55.0, 110.0, 220.0], log_spectrum_db=[-48.0, -30.0, -60.0])
        panel.update_analysis(snap)
        assert panel._log_curve.xData.tolist() == snap.log_freqs_hz
        curves = [panel._log_curve, panel._fft_curve]
        panel.fft_plot.setXRange(2, 3, padding=0)
        for value, (positions, _rows, _columns) in ANALYSIS_VIEWS.items():
            window.apply_appearance(replace(window.appearance, analysis_layout=value))
            assert panel.view_combo.currentData() == value
            for card, position in zip(panel._chart_cards, positions):
                assert panel._plot_grid.getItemPosition(panel._plot_grid.indexOf(card)) == position
            assert [panel._log_curve, panel._fft_curve] == curves
            assert panel.fft_plot.viewRange()[0] == [2, 3]
        index = panel.view_combo.findData("frequency")
        panel.view_combo.setCurrentIndex(index)
        panel.view_combo.activated.emit(index)
        assert window.appearance.analysis_layout == "frequency"
        assert load_settings(controller._settings_path).appearance.analysis_layout == "frequency"
        assert panel.level_meter.value() == 0
        assert panel.pitch_detail.text() == "等待有效音高"
    finally:
        controller.shutdown()
        controller.window.close()
        app.processEvents()
