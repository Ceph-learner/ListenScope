"""Settings dialog: Phase 0 System Status hardware inspector + ResourceLimits/AIConfig editor."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Any, Optional

from PySide6 import QtCore, QtGui, QtSvg, QtWidgets

from core.config import AIConfig, ResourceLimits, TargetHardwareSpec
from core.models import SystemHardwareReport
from core.paths import get_bundle_root
from core.system_probe import (
    MIDI_ENV_SETUP_GUIDE,
    apply_external_ai_probe_to_report,
    probe_external_ai_environment,
    probe_external_midi_environment,
)

SETTINGS_CATEGORIES = {
    "appearance": ("外观与布局", "切换三套工作区，调整配色与字号"),
    "resources": ("资源保护", "配置内存、显存阈值和分轨模型参数"),
    "midi": ("AI 与 MIDI 环境", "选择两个独立的 Python 解释器，分别验证"),
    "status": ("系统诊断", "查看硬件、捕获能力和运行环境"),
}


def _category_icon(name: str) -> QtGui.QPixmap:
    path = get_bundle_root() / "ui" / "assets" / "settings" / f"{name}.svg"
    try:
        svg = path.read_bytes().replace(b"currentColor", b"#a9ead7")
    except OSError:
        return QtGui.QPixmap()
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg))
    pixmap = QtGui.QPixmap(44, 44)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return pixmap


class SettingsDialog(QtWidgets.QDialog):
    """Shows real SystemHardwareReport (`设置 -> 系统状态`) and configurable guardrails."""

    _probe_finished = QtCore.Signal(object)
    _midi_probe_finished = QtCore.Signal(object)
    appearance_requested = QtCore.Signal(object)

    def __init__(
        self,
        hardware_report: SystemHardwareReport,
        resource_limits: ResourceLimits,
        ai_config: AIConfig,
        *,
        ai_python_executable: str = "",
        midi_python_executable: str = "",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("ListenScope 设置")
        self.resize(820, 690)

        self._report = hardware_report
        self._updated_limits: Optional[ResourceLimits] = None
        self._updated_ai_config: Optional[AIConfig] = None
        self._updated_ai_python: str = ai_python_executable
        self._updated_midi_python: str = midi_python_executable
        self._verified_ai_probe: Optional[dict[str, Any]] = None
        self._dialog_closed = False
        self._probe_finished.connect(self._on_ai_probe_finished, QtCore.Qt.ConnectionType.QueuedConnection)
        self._midi_probe_finished.connect(self._on_midi_probe_finished, QtCore.Qt.ConnectionType.QueuedConnection)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 16)
        root.setSpacing(14)
        heading = QtWidgets.QHBoxLayout()
        self._back = QtWidgets.QPushButton("← 所有分类")
        self._back.clicked.connect(lambda: self.open_category("home"))
        heading.addWidget(self._back, alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
        heading_labels = QtWidgets.QVBoxLayout()
        heading_labels.setSpacing(4)
        self._title = QtWidgets.QLabel()
        self._title.setObjectName("settingsHeading")
        self._subtitle = QtWidgets.QLabel()
        self._subtitle.setObjectName("settingsSubtitle")
        self._subtitle.setWordWrap(True)
        heading_labels.addWidget(self._title)
        heading_labels.addWidget(self._subtitle)
        heading.addLayout(heading_labels, 1)
        root.addLayout(heading)
        self._pages = QtWidgets.QStackedWidget()
        root.addWidget(self._pages, 1)
        self._page_map = {}
        self._category_buttons = {}
        self._active_category = "home"
        home = QtWidgets.QWidget()
        home_layout = QtWidgets.QVBoxLayout(home)
        home_layout.setContentsMargins(0, 2, 0, 4)
        self._category_grid = QtWidgets.QGridLayout()
        self._category_grid.setSpacing(12)
        home_layout.addLayout(self._category_grid)
        home_layout.addStretch(1)
        self._add_page("home", home, scroll=True)
        for key, (label, description) in SETTINGS_CATEGORIES.items():
            self._category_buttons[key] = self._make_category_button(key, label, description)

        # Tab 1: System Status (Prompt Section 3 explicit requirement)
        status_tab = QtWidgets.QWidget()
        st_layout = QtWidgets.QVBoxLayout(status_tab)

        target = TargetHardwareSpec()
        target_lbl = QtWidgets.QLabel(
            f"目标真机基线规格: Windows 10/11 (Build >= {target.min_windows_build_for_process_loopback}) | "
            f"GPU: {target.gpu_name} | 显存: {target.vram_gb}GB VRAM (非 16GB) | 系统内存: {target.ram_gb}GB RAM"
        )
        target_lbl.setWordWrap(True)
        target_lbl.setStyleSheet("padding: 8px; background: #1C2026; border: 1px solid #2C323C; border-radius: 6px; font-weight: 600;")
        st_layout.addWidget(target_lbl)

        self.status_table = QtWidgets.QTableWidget(0, 2)
        self.status_table.setHorizontalHeaderLabels(["检测项", "当前环境实测状态"])
        self.status_table.horizontalHeader().setStretchLastSection(True)
        self.status_table.setColumnWidth(0, 250)
        self.status_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self._populate_status_table(hardware_report)
        st_layout.addWidget(self.status_table, 1)

        self.status_alert_lbl = QtWidgets.QLabel("")
        self.status_alert_lbl.setWordWrap(True)
        self.status_alert_lbl.setStyleSheet("padding: 8px; background: #4D3800; color: #FFD166; border: 1px solid #F5A623; border-radius: 6px;")
        st_layout.addWidget(self.status_alert_lbl)
        self._refresh_status_alert(hardware_report)

        self._add_page("status", status_tab)

        # Tab 2: ResourceLimits & AIConfig
        cfg_tab = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(cfg_tab)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        env_tab = QtWidgets.QWidget()
        env_layout = QtWidgets.QVBoxLayout(env_tab)
        env_layout.setContentsMargins(0, 4, 0, 0)
        env_layout.setSpacing(14)

        self.min_ram_spin = QtWidgets.QDoubleSpinBox()
        self.min_ram_spin.setRange(2560, 32768)
        self.min_ram_spin.setSuffix(" MB")
        self.min_ram_spin.setValue(resource_limits.min_ram_before_ai_mb)

        self.pause_ram_spin = QtWidgets.QDoubleSpinBox()
        self.pause_ram_spin.setRange(1536, 16384)
        self.pause_ram_spin.setSuffix(" MB")
        self.pause_ram_spin.setValue(resource_limits.pause_ram_before_ai_mb)

        self.crit_ram_spin = QtWidgets.QDoubleSpinBox()
        self.crit_ram_spin.setRange(512, 8192)
        self.crit_ram_spin.setSuffix(" MB")
        self.crit_ram_spin.setValue(resource_limits.critical_ram_mb)

        self.vram_2s_spin = QtWidgets.QDoubleSpinBox()
        self.vram_2s_spin.setRange(1024, 7800)
        self.vram_2s_spin.setSuffix(" MB")
        self.vram_2s_spin.setValue(resource_limits.min_vram_2stem_mb)

        self.vram_4s_spin = QtWidgets.QDoubleSpinBox()
        self.vram_4s_spin.setRange(2048, 7800)
        self.vram_4s_spin.setSuffix(" MB")
        self.vram_4s_spin.setValue(resource_limits.min_vram_4stem_mb)

        self.crit_vram_spin = QtWidgets.QDoubleSpinBox()
        self.crit_vram_spin.setRange(256, 4096)
        self.crit_vram_spin.setSuffix(" MB")
        self.crit_vram_spin.setValue(resource_limits.critical_vram_free_mb)

        self.chunk_sec_spin = QtWidgets.QDoubleSpinBox()
        self.chunk_sec_spin.setRange(2.0, 45.0)
        self.chunk_sec_spin.setSuffix(" s")
        self.chunk_sec_spin.setValue(ai_config.long_audio_chunk_seconds)
        self.chunk_sec_spin.setToolTip(
            "离线音频流式分块长度（RTX 5060 Ti 8GB + 16GB RAM 实测默认 6.0s；保留用户已保存自定义设置）。"
        )

        self.demucs_seg_spin = QtWidgets.QSpinBox()
        self.demucs_seg_spin.setRange(4, max(int(s) for s in ai_config.demucs_segment_ladder))
        self.demucs_seg_spin.setSuffix(" s")
        self.demucs_seg_spin.setValue(ai_config.demucs_default_segment_sec)
        self.demucs_seg_spin.setToolTip(
            "HTDemucs 4-Stem 内部模型分段时长（实测默认 6s）；与离线流式分块分开设置，且不影响 MDX 内部 segment_size=256。"
        )

        py_row = QtWidgets.QHBoxLayout()
        self.ai_python_edit = QtWidgets.QLineEdit(ai_python_executable)
        self.ai_python_edit.setPlaceholderText("留空使用当前 Python；建议 Windows 分环境打包时填写 .venv-ai\\Scripts\\python.exe")
        self.browse_ai_py_btn = QtWidgets.QPushButton("浏览...")
        self.browse_ai_py_btn.clicked.connect(self._browse_ai_python)
        self.verify_ai_env_btn = QtWidgets.QPushButton("验证 AI 环境")
        self.verify_ai_env_btn.clicked.connect(self._verify_ai_environment)
        py_row.addWidget(self.ai_python_edit, 1)
        py_row.addWidget(self.browse_ai_py_btn)
        py_row.addWidget(self.verify_ai_env_btn)

        self.ai_probe_result_lbl = QtWidgets.QLabel(
            "验证 CUDA、ONNX、Demucs 和 FFmpeg。留空时使用当前 Python。"
        )
        self.ai_probe_result_lbl.setWordWrap(True)
        self.ai_probe_result_lbl.setStyleSheet("padding: 6px; background: #1C2026; border: 1px solid #2C323C; border-radius: 5px; color: #D7DCE2;")

        midi_py_row = QtWidgets.QHBoxLayout()
        self.midi_python_edit = QtWidgets.QLineEdit(midi_python_executable)
        self.midi_python_edit.setPlaceholderText("建议填写 Python 3.11 独立环境: .venv-midi\\Scripts\\python.exe")
        self.browse_midi_py_btn = QtWidgets.QPushButton("浏览...")
        self.browse_midi_py_btn.clicked.connect(self._browse_midi_python)
        self.verify_midi_env_btn = QtWidgets.QPushButton("验证 MIDI 环境")
        self.verify_midi_env_btn.clicked.connect(self._verify_midi_environment)
        midi_py_row.addWidget(self.midi_python_edit, 1)
        midi_py_row.addWidget(self.browse_midi_py_btn)
        midi_py_row.addWidget(self.verify_midi_env_btn)

        self.midi_probe_result_lbl = QtWidgets.QLabel(
            "Basic Pitch 使用独立的 Python 3.11 CPU 环境。缺少可用环境时，单轨转录会标明所用的轻量算法。"
        )
        self.midi_probe_result_lbl.setWordWrap(True)
        self.midi_probe_result_lbl.setStyleSheet("padding: 6px; background: #1C2026; border: 1px solid #2C323C; border-radius: 5px; color: #D7DCE2;")

        self.roformer_chk = QtWidgets.QCheckBox("允许实验性 BS-RoFormer 模型 (仅在 RTX 5060 Ti 8GB 实测峰值通过后手动启用)")
        self.roformer_chk.setChecked(ai_config.allow_experimental_roformer)

        form.addRow("分轨前内存提醒", self.min_ram_spin)
        form.addRow("拒绝新分轨的内存阈值", self.pause_ram_spin)
        form.addRow("紧急停止的内存阈值", self.crit_ram_spin)
        form.addRow("GPU 2-Stem 最低空闲显存 (min_vram_2stem):", self.vram_2s_spin)
        form.addRow("GPU 4-Stem 最低空闲显存 (min_vram_4stem):", self.vram_4s_spin)
        form.addRow("桌面/QQ音乐保留最低空闲显存 (critical_vram_free):", self.crit_vram_spin)
        form.addRow("离线音频流式分块长度 (long_audio_chunk_seconds):", self.chunk_sec_spin)
        form.addRow("HTDemucs 4-Stem 模型分段 (demucs_default_segment_sec):", self.demucs_seg_spin)
        for title, label, controls, feedback in (
            ("分轨环境", "AI Worker Python", py_row, self.ai_probe_result_lbl),
            ("转录环境", "MIDI Python 3.11", midi_py_row, self.midi_probe_result_lbl),
        ):
            group = QtWidgets.QGroupBox(title)
            section = QtWidgets.QFormLayout(group)
            section.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
            section.setHorizontalSpacing(14)
            section.setVerticalSpacing(10)
            section.addRow(label, controls)
            section.addRow(feedback)
            env_layout.addWidget(group)
        env_layout.addStretch(1)
        form.addRow("高显存模型解锁:", self.roformer_chk)

        self._add_page("resources", cfg_tab, scroll=True)
        self._add_page("midi", env_tab, scroll=True)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        save = btns.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        save.setText("保存设置")
        save.setObjectName("settingsSave")
        save.setAutoDefault(False)
        save.setDefault(False)
        btns.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText("取消")
        root.addWidget(btns)

        self._orig_limits = resource_limits
        self._orig_ai_cfg = ai_config
        self._arrange_categories()
        self.open_category("home")

    def _add_page(self, key: str, widget: QtWidgets.QWidget, *, scroll: bool = False) -> None:
        if scroll:
            area = QtWidgets.QScrollArea()
            area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            area.setWidgetResizable(True)
            area.setWidget(widget)
            widget = area
        self._page_map[key] = widget
        self._pages.addWidget(widget)

    def _make_category_button(self, key: str, title: str, summary: str) -> QtWidgets.QPushButton:
        button = QtWidgets.QPushButton()
        button.setObjectName("settingsCategory")
        button.setAccessibleName(title)
        button.setAccessibleDescription(summary)
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.setAutoDefault(False)
        button.setMinimumHeight(102)
        button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        row = QtWidgets.QHBoxLayout(button)
        row.setContentsMargins(16, 15, 14, 15)
        row.setSpacing(12)
        icon = QtWidgets.QLabel()
        icon.setObjectName("settingsCategoryIcon")
        icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(38, 38)
        icon.setPixmap(_category_icon(key))
        row.addWidget(icon)
        text = QtWidgets.QVBoxLayout()
        text.setSpacing(5)
        name = QtWidgets.QLabel(title)
        name.setObjectName("settingsCategoryTitle")
        description = QtWidgets.QLabel(summary)
        description.setObjectName("settingsSubtitle")
        description.setWordWrap(True)
        text.addWidget(name)
        text.addWidget(description)
        row.addLayout(text, 1)
        arrow = QtWidgets.QLabel("›")
        arrow.setObjectName("settingsCategoryArrow")
        row.addWidget(arrow)
        for label in (icon, name, description, arrow):
            label.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        button.clicked.connect(lambda _checked=False: self.open_category(key))
        return button

    def _arrange_categories(self) -> None:
        columns = 2 if self.width() >= 630 else 1
        if columns == getattr(self, "_category_columns", None):
            return
        self._category_columns = columns
        for index, button in enumerate(self._category_buttons.values()):
            self._category_grid.removeWidget(button)
            self._category_grid.addWidget(button, index // columns, index % columns)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_category_buttons"):
            self._arrange_categories()

    def open_category(self, key: str) -> None:
        if key == "appearance":
            self.appearance_requested.emit(self)
            return
        previous = self._active_category
        self._active_category = key
        self._pages.setCurrentWidget(self._page_map[key])
        self._back.setVisible(key != "home")
        title, subtitle = SETTINGS_CATEGORIES.get(key, ("设置", "选择要查看或调整的类别。"))
        self._title.setText(title)
        self._subtitle.setText(subtitle)
        if key == "home":
            self._category_buttons.get(previous, self._category_buttons["appearance"]).setFocus()
        else:
            self._back.setFocus()

    def focus_midi(self) -> None:
        self.open_category("midi")
        self._page_map["midi"].ensureWidgetVisible(self.midi_python_edit)
        self.midi_python_edit.setFocus()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._dialog_closed = True
        super().closeEvent(event)

    def done(self, result: int) -> None:  # type: ignore[override]
        self._dialog_closed = True
        super().done(result)

    def _refresh_status_alert(self, r: SystemHardwareReport) -> None:
        if not r.gpu_ai_ready or not r.is_windows:
            warn_text = r.gpu_ai_block_reason or ""
            if not r.is_windows:
                warn_text = (
                    f"⚠️ 当前在 {r.os_system} 运行：WASAPI Process Loopback 与 RTX 5060 Ti CUDA 未在 Windows 真机验证。\n"
                    + warn_text
                )
            self.status_alert_lbl.setText(warn_text.strip())
            self.status_alert_lbl.setVisible(True)
        else:
            self.status_alert_lbl.setVisible(False)
            self.status_alert_lbl.setText("")

    def _browse_ai_python(self) -> None:
        start_dir = str(Path(self.ai_python_edit.text().strip()).parent) if self.ai_python_edit.text().strip() else str(Path.cwd())
        selected, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "选择独立 AI Worker Python 解释器",
            start_dir,
            "Python Executable (python.exe python python3*);;All Files (*)",
        )
        if selected:
            self.ai_python_edit.setText(selected)

    def _browse_midi_python(self) -> None:
        start_dir = str(Path(self.midi_python_edit.text().strip()).parent) if self.midi_python_edit.text().strip() else str(Path.cwd())
        selected, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "选择独立 CPU MIDI Python 解释器 (建议 Python 3.11 .venv-midi)",
            start_dir,
            "Python Executable (python.exe python python3*);;All Files (*)",
        )
        if selected:
            self.midi_python_edit.setText(selected)

    def _verify_ai_environment(self) -> None:
        target_py = self.ai_python_edit.text().strip()
        self.verify_ai_env_btn.setEnabled(False)
        self.ai_probe_result_lbl.setText("⏳ 正在启动子进程检测 AI Python 环境 (CUDA / sm_120 / ONNX / Demucs / FFmpeg)...")

        def _worker() -> None:
            res = probe_external_ai_environment(target_py)
            if not self._dialog_closed:
                try:
                    self._probe_finished.emit(res)
                except RuntimeError:
                    pass

        threading.Thread(target=_worker, name="ListenScope-VerifyAIEnv", daemon=True).start()

    def _verify_midi_environment(self) -> None:
        target_py = self.midi_python_edit.text().strip()
        self.verify_midi_env_btn.setEnabled(False)
        self.midi_probe_result_lbl.setText("⏳ 正在启动子进程检测独立 CPU MIDI 环境 (Basic Pitch / TensorFlow / pkg_resources / mido)...")

        def _worker() -> None:
            res = probe_external_midi_environment(target_py)
            if not self._dialog_closed:
                try:
                    self._midi_probe_finished.emit(res)
                except RuntimeError:
                    pass

        threading.Thread(target=_worker, name="ListenScope-VerifyMidiEnv", daemon=True).start()

    @QtCore.Slot(object)
    def _on_ai_probe_finished(self, result: Any) -> None:
        if self._dialog_closed:
            return
        self.verify_ai_env_btn.setEnabled(True)
        if not isinstance(result, dict) or not result.get("ok"):
            self._verified_ai_probe = None
            err = result.get("error", "未知错误") if isinstance(result, dict) else str(result)
            self.ai_probe_result_lbl.setText(f"❌ 检测失败: {err}")
            self.ai_probe_result_lbl.setStyleSheet(
                "padding: 6px; background: #4D1D1D; color: #FF9B9B; border: 1px solid #E03E3E; border-radius: 5px;"
            )
            return

        self._verified_ai_probe = dict(result)
        self._report = apply_external_ai_probe_to_report(self._report, result)
        self._populate_status_table(self._report)
        self._refresh_status_alert(self._report)

        pt = result.get("pytorch") or {}
        ort = result.get("onnxruntime") or {}
        pkgs = result.get("ai_packages") or {}
        tools = result.get("tools") or {}
        ff_info = tools.get("ffmpeg") or {}
        gpu_ready = bool(self._report.gpu_ai_ready)
        block_reason = self._report.gpu_ai_block_reason or ""

        def _fmt_pkg(name: str, info: Any) -> str:
            d = info or {}
            if d.get("installed"):
                return f"{name}=OK"
            if d.get("optional"):
                return f"{name}=OPT(独立MIDI)"
            return f"{name}=MISS"

        pkg_summary = ", ".join(_fmt_pkg(k, v) for k, v in pkgs.items())
        ff_txt = f"OK ({ff_info.get('path')})" if ff_info.get("installed") else "MISS (仅 WAV 可直读)"
        summary = (
            f"Python: {result.get('python_executable')}\n"
            f"PyTorch: {pt.get('version') or 'N/A'} (CUDA={pt.get('cuda_available')}, sm_120={pt.get('supports_sm_120')}) | "
            f"ONNX CUDA: {ort.get('cuda_provider_available')}\n"
            f"AI 包: {pkg_summary} | FFmpeg: {ff_txt}\n"
            f"GPU AI 准入: {'READY' if gpu_ready else f'BLOCKED ({block_reason})'}"
        )
        self.ai_probe_result_lbl.setText(summary)
        if gpu_ready:
            self.ai_probe_result_lbl.setStyleSheet(
                "padding: 6px; background: #1B4D3E; color: #7EE2B8; border: 1px solid #2EC27E; border-radius: 5px;"
            )
        else:
            self.ai_probe_result_lbl.setStyleSheet(
                "padding: 6px; background: #4D3800; color: #FFD166; border: 1px solid #F5A623; border-radius: 5px;"
            )

    @QtCore.Slot(object)
    def _on_midi_probe_finished(self, result: Any) -> None:
        if self._dialog_closed:
            return
        self.verify_midi_env_btn.setEnabled(True)
        if not isinstance(result, dict) or not result.get("ok"):
            err = result.get("error", "未知错误") if isinstance(result, dict) else str(result)
            guide = result.get("setup_guide", MIDI_ENV_SETUP_GUIDE) if isinstance(result, dict) else MIDI_ENV_SETUP_GUIDE
            msg = err if guide in err else f"{err}\n{guide}"
            self.midi_probe_result_lbl.setText(f"❌ MIDI 环境不可用: {msg}")
            self.midi_probe_result_lbl.setStyleSheet(
                "padding: 6px; background: #4D1D1D; color: #FF9B9B; border: 1px solid #E03E3E; border-radius: 5px;"
            )
            return

        pkgs = result.get("midi_packages") or {}
        pkg_summary = ", ".join(
            f"{k}={'OK' if (v or {}).get('installed') else 'MISS'}"
            for k, v in pkgs.items()
        )
        midi_ready = bool(result.get("midi_ready"))
        block_reason = str(result.get("midi_block_reason") or "")
        summary = (
            f"Python: {result.get('python_executable')} (ver={result.get('python_version') or 'N/A'})\n"
            f"MIDI 包: {pkg_summary}\n"
            f"Basic Pitch CPU 准入: {'READY' if midi_ready else f'BLOCKED ({block_reason})'}"
        )
        self.midi_probe_result_lbl.setText(summary)
        if midi_ready:
            self.midi_probe_result_lbl.setStyleSheet(
                "padding: 6px; background: #1B4D3E; color: #7EE2B8; border: 1px solid #2EC27E; border-radius: 5px;"
            )
        else:
            self.midi_probe_result_lbl.setStyleSheet(
                "padding: 6px; background: #4D3800; color: #FFD166; border: 1px solid #F5A623; border-radius: 5px;"
            )

    def _populate_status_table(self, r: SystemHardwareReport) -> None:
        gpu0 = r.gpus[0] if r.gpus else None
        rows = [
            ("操作系统", f"{r.os_system} {r.os_release} ({r.architecture})"),
            ("Windows Build / WASAPI 进程捕获", f"{r.windows_build or 'N/A'} / {'支持' if r.wasapi_process_loopback_supported else '不可用 / 未在 Windows 真机验证'}"),
            ("系统 RAM (总量 / 当前可用)", f"{r.ram_total_mb / 1024.0:.2f} GB ({r.ram_total_mb:.0f} MB) / {r.ram_available_mb:.0f} MB"),
            ("GPU 型号", gpu0.name if gpu0 else "未检测到 NVIDIA GPU"),
            ("VRAM (总量 / 空闲)", f"{gpu0.total_vram_mb:.0f} MB / {gpu0.free_vram_mb:.0f} MB" if gpu0 else "N/A (目标真机为 8GB VRAM)"),
            ("NVIDIA Driver / NVML", f"{r.nvidia_driver_version or '未检测到'} / {'可用' if r.nvml_available else '不可用'}"),
            ("PyTorch", f"{r.pytorch.version} (CUDA build={r.pytorch.cuda_build})" if r.pytorch.installed else "未安装 (Core 环境隔离正常)"),
            ("torch.cuda.is_available() / Compute Cap", f"{'可用' if r.pytorch.cuda_available else '不可用'} / {r.pytorch.compute_capability or 'N/A'}"),
            ("RTX 5060 Ti sm_120 支持 / Kernel 测试", f"{r.pytorch.supports_sm_120} / {r.pytorch.kernel_smoke_test_passed}"),
            ("ONNX Runtime / CUDAExecutionProvider", f"{r.onnxruntime.version or '未安装'} / {'存在' if r.onnxruntime.cuda_provider_available else '不存在'} ({r.onnxruntime.providers})"),
            ("GPU AI 准入状态 (gpu_ai_ready)", f"{'READY' if r.gpu_ai_ready else 'BLOCKED'} {f'({r.gpu_ai_block_reason})' if r.gpu_ai_block_reason else ''}"),
        ]
        self.status_table.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            self.status_table.setItem(i, 0, QtWidgets.QTableWidgetItem(k))
            self.status_table.setItem(i, 1, QtWidgets.QTableWidgetItem(v))

    def _on_accept(self) -> None:
        try:
            self._updated_limits = ResourceLimits(
                max_main_process_ram_mb=self._orig_limits.max_main_process_ram_mb,
                warn_main_process_ram_mb=self._orig_limits.warn_main_process_ram_mb,
                min_ram_before_ai_mb=float(self.min_ram_spin.value()),
                pause_ram_before_ai_mb=float(self.pause_ram_spin.value()),
                critical_ram_mb=float(self.crit_ram_spin.value()),
                min_vram_2stem_mb=float(self.vram_2s_spin.value()),
                min_vram_4stem_mb=float(self.vram_4s_spin.value()),
                critical_vram_free_mb=float(self.crit_vram_spin.value()),
                max_concurrent_ai_jobs=1,
                max_loaded_models=1,
                monitor_history_maxlen=self._orig_limits.monitor_history_maxlen,
            )
            self._updated_ai_config = AIConfig(
                default_max_history_ai_seconds=self._orig_ai_cfg.default_max_history_ai_seconds,
                long_audio_chunk_seconds=float(self.chunk_sec_spin.value()),
                long_audio_overlap_seconds=self._orig_ai_cfg.long_audio_overlap_seconds,
                demucs_jobs=1,
                demucs_shifts=1,
                demucs_overlap=self._orig_ai_cfg.demucs_overlap,
                demucs_default_segment_sec=int(self.demucs_seg_spin.value()),
                demucs_segment_ladder=self._orig_ai_cfg.demucs_segment_ladder,
                mdx_batch_size=self._orig_ai_cfg.mdx_batch_size,
                mdx_segment_size=self._orig_ai_cfg.mdx_segment_size,
                mdx_overlap=self._orig_ai_cfg.mdx_overlap,
                worker_graceful_cancel_timeout_sec=self._orig_ai_cfg.worker_graceful_cancel_timeout_sec,
                max_oom_retries=self._orig_ai_cfg.max_oom_retries,
                allow_experimental_roformer=bool(self.roformer_chk.isChecked()),
                live_chunk_seconds=self._orig_ai_cfg.live_chunk_seconds,
                live_overlap_seconds=self._orig_ai_cfg.live_overlap_seconds,
                live_max_buffer_seconds=self._orig_ai_cfg.live_max_buffer_seconds,
            )
            entered_py = self.ai_python_edit.text().strip()
            self._updated_ai_python = entered_py
            self._updated_midi_python = self.midi_python_edit.text().strip()
            if self._verified_ai_probe is not None and str(self._verified_ai_probe.get("python_executable", "")) != entered_py:
                self._verified_ai_probe = None
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "参数无效", str(exc))
            return
        self.accept()

    @property
    def updated_limits(self) -> Optional[ResourceLimits]:
        return self._updated_limits

    @property
    def updated_ai_config(self) -> Optional[AIConfig]:
        return self._updated_ai_config

    @property
    def updated_ai_python(self) -> str:
        return self._updated_ai_python

    @property
    def updated_midi_python(self) -> str:
        return self._updated_midi_python

    @property
    def verified_ai_probe(self) -> Optional[dict[str, Any]]:
        return self._verified_ai_probe

    @property
    def verified_report(self) -> SystemHardwareReport:
        return self._report
