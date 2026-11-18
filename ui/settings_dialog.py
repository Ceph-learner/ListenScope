"""Settings dialog: Appearance/storage summary, guardrails, turnkey environment bootstrap, and System Status."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from typing import Any, Optional

from PySide6 import QtCore, QtGui, QtSvg, QtWidgets

from core.appearance import Appearance, LAYOUTS, PRESETS, THEME_MODES
from core.config import AIConfig, ResourceLimits, TargetHardwareSpec
from core.models import SystemHardwareReport
from core.paths import (
    default_export_dir,
    default_work_dir,
    find_ffmpeg_executable,
    get_app_root,
    get_bundle_root,
    subprocess_no_window_kwargs,
)
from core.system_probe import (
    MIDI_ENV_SETUP_GUIDE,
    apply_external_ai_probe_to_report,
    probe_external_ai_environment,
    probe_external_midi_environment,
)
from ui.appearance import detect_system_is_dark, set_widget_tone
from ui.help_badge import HelpBadge, wrap_with_help
from ui.acid_style import (
    TelemetryHeader,
    acid_stylesheet,
    get_acid_palette,
    resolve_acid_variant,
)

SETTINGS_CATEGORIES = {
    "appearance": ("外观与布局", "切换工作区、黑夜/白天/跟随系统主题、字体字号与数据路径"),
    "resources": ("资源保护", "配置内存、显存阈值和分轨模型参数"),
    "midi": ("AI 与 MIDI 环境", "自动或手动配置两个独立 Python 运行环境"),
    "status": ("系统诊断", "查看硬件、捕获能力和运行环境"),
}

SETTINGS_EYEBROWS = {
    "appearance": "CONFIG // 01 · APPEARANCE & STORAGE",
    "resources": "CONFIG // 02 · GUARDRAILS & CHUNKING",
    "midi": "CONFIG // 03 · RUNTIME ENVIRONMENTS",
    "status": "CONFIG // 04 · HARDWARE DIAGNOSTICS",
}


def _category_icon(name: str, color: str = "#7EE2B8") -> QtGui.QPixmap:
    path = get_bundle_root() / "ui" / "assets" / "settings" / f"{name}.svg"
    try:
        svg = path.read_bytes().replace(b"currentColor", color.encode("ascii"))
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


def _open_directory(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))


def _discover_installed_runtime_pythons(app_root: Path) -> tuple[str, str]:
    """Locate newly bootstrapped AI and MIDI Python executables beside app root or short Windows paths."""
    ai_candidates = [
        app_root / "runtime" / "ai" / "python.exe",
        app_root / "runtime" / "ai" / "Scripts" / "python.exe",
        app_root / "runtimes" / "ai" / "python.exe",
        app_root / "runtimes" / "ai" / "Scripts" / "python.exe",
        app_root / ".venv-ai" / "Scripts" / "python.exe",
        app_root / "runtime" / "ai" / "bin" / "python",
        app_root / ".venv-ai" / "bin" / "python",
    ]
    midi_candidates = [
        app_root / "m" / "python.exe",
        app_root / "m" / "Scripts" / "python.exe",
        app_root / "runtime" / "midi" / "python.exe",
        app_root / "runtime" / "midi" / "Scripts" / "python.exe",
        app_root / "runtimes" / "midi" / "python.exe",
        app_root / "runtimes" / "midi" / "Scripts" / "python.exe",
        app_root / ".venv-midi" / "Scripts" / "python.exe",
        app_root / "m" / "bin" / "python",
        app_root / "runtime" / "midi" / "bin" / "python",
        app_root / ".venv-midi" / "bin" / "python",
    ]
    if sys.platform == "win32":
        for drive in ("D:", "C:", "E:"):
            midi_candidates.append(Path(f"{drive}\\LS-midi\\.venv-midi\\Scripts\\python.exe"))
            midi_candidates.append(Path(f"{drive}\\LS-midi\\m\\Scripts\\python.exe"))

    ai_found = next((str(p) for p in ai_candidates if p.exists()), "")
    midi_found = next((str(p) for p in midi_candidates if p.exists()), "")
    return ai_found, midi_found


class SettingsDialog(QtWidgets.QDialog):
    """Shows real SystemHardwareReport (`设置 -> 系统状态`), turnkey environment setup, and ResourceLimits/AIConfig."""

    _probe_finished = QtCore.Signal(object)
    _midi_probe_finished = QtCore.Signal(object)
    _bootstrap_progress = QtCore.Signal(str)
    _bootstrap_finished = QtCore.Signal(bool, str)
    appearance_requested = QtCore.Signal(object)

    def __init__(
        self,
        hardware_report: SystemHardwareReport,
        resource_limits: ResourceLimits,
        ai_config: AIConfig,
        *,
        ai_python_executable: str = "",
        midi_python_executable: str = "",
        appearance: Appearance = Appearance(),
        acid_variant: Optional[str] = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("ListenScope 设置")
        self.resize(840, 710)

        if acid_variant is not None:
            resolved_variant: Optional[str] = acid_variant or None
        elif parent is not None and hasattr(parent, "_acid_variant"):
            resolved_variant = getattr(parent, "_acid_variant")
        else:
            resolved_variant = resolve_acid_variant(
                appearance,
                system_is_dark=detect_system_is_dark(),
            )

        self._appearance = appearance
        self._acid_variant: Optional[str] = resolved_variant
        self._report = hardware_report
        self._updated_limits: Optional[ResourceLimits] = None
        self._updated_ai_config: Optional[AIConfig] = None
        self._updated_ai_python: str = ai_python_executable
        self._updated_midi_python: str = midi_python_executable
        self._verified_ai_probe: Optional[dict[str, Any]] = None
        self._dialog_closed = False
        self._bootstrap_running = False
        self._probe_finished.connect(self._on_ai_probe_finished, QtCore.Qt.ConnectionType.QueuedConnection)
        self._midi_probe_finished.connect(self._on_midi_probe_finished, QtCore.Qt.ConnectionType.QueuedConnection)
        self._bootstrap_progress.connect(self._on_bootstrap_progress, QtCore.Qt.ConnectionType.QueuedConnection)
        self._bootstrap_finished.connect(self._on_bootstrap_finished, QtCore.Qt.ConnectionType.QueuedConnection)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(12)
        self._header = TelemetryHeader(
            "SYSTEM PREFERENCES // TELEMETRY CONFIG",
            "系统设置与运行环境管理",
            badge_text="PORTABLE // LOCAL",
        )
        root.addWidget(self._header)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(16)
        navigation = QtWidgets.QWidget()
        navigation.setObjectName("settingsNavigation")
        navigation.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground)
        navigation.setFixedWidth(172)
        nav_layout = QtWidgets.QVBoxLayout(navigation)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(5)
        self._nav_group = QtWidgets.QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._category_buttons = {}
        icon_color = self._icon_color(appearance, resolved_variant)
        for key, (label, description) in SETTINGS_CATEGORIES.items():
            button = QtWidgets.QPushButton(QtGui.QIcon(_category_icon(key, color=icon_color)), label)
            button.setObjectName("settingsNavButton")
            button.setAccessibleDescription(description)
            button.setCheckable(True)
            button.setAutoDefault(False)
            button.setMinimumHeight(39)
            button.setIconSize(QtCore.QSize(18, 18))
            button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, key=key: self.open_category(key))
            self._nav_group.addButton(button)
            self._category_buttons[key] = button
            nav_layout.addWidget(button)
        nav_layout.addStretch(1)
        body.addWidget(navigation)

        details = QtWidgets.QVBoxLayout()
        details.setSpacing(6)
        self._page_eyebrow = QtWidgets.QLabel()
        self._page_eyebrow.setObjectName("telemetryEyebrow")
        self._page_eyebrow.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self._title = QtWidgets.QLabel()
        self._title.setObjectName("settingsPageHeading")
        self._title.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self._subtitle = QtWidgets.QLabel()
        self._subtitle.setObjectName("settingsSubtitle")
        self._subtitle.setWordWrap(True)
        self._subtitle.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        details.addWidget(self._page_eyebrow)
        details.addWidget(self._title)
        details.addWidget(self._subtitle)
        self._pages = QtWidgets.QStackedWidget()
        details.addWidget(self._pages, 1)
        self._page_map = {}
        self._active_category = ""
        body.addLayout(details, 1)
        root.addLayout(body, 1)

        # Page 1: Appearance & Portable/Sibling Storage Locations
        appearance_page = QtWidgets.QWidget()
        appearance_layout = QtWidgets.QVBoxLayout(appearance_page)
        appearance_layout.setContentsMargins(0, 4, 0, 0)
        appearance_layout.setSpacing(12)

        appearance_box = QtWidgets.QGroupBox("APPEARANCE // 当前外观与字体配置")
        appearance_form = QtWidgets.QFormLayout(appearance_box)
        appearance_form.setVerticalSpacing(12)
        self._theme_summary = QtWidgets.QLabel()
        self._layout_summary = QtWidgets.QLabel()
        self._font_summary = QtWidgets.QLabel()
        appearance_form.addRow("主题与模式", self._theme_summary)
        appearance_form.addRow("工作区", self._layout_summary)
        appearance_form.addRow("字体与字号", self._font_summary)
        edit_appearance = QtWidgets.QPushButton("编辑外观与字体…")
        edit_appearance.setObjectName("appearanceEntry")
        edit_appearance.setAutoDefault(False)
        edit_appearance.clicked.connect(lambda: self.appearance_requested.emit(self))
        appearance_form.addRow(
            wrap_with_help(
                edit_appearance,
                "自定义外观与实时预览",
                "可切换黑夜 / 白天 / 跟随系统模式，扫描电脑已安装字体并实时预览界面效果；支持一键恢复默认。",
            )[0]
        )
        appearance_layout.addWidget(appearance_box)

        storage_box = QtWidgets.QGroupBox("PORTABLE STORAGE // 同级目录保存位置（默认不写入 C 盘）")
        storage_form = QtWidgets.QFormLayout(storage_box)
        storage_form.setVerticalSpacing(10)
        app_root = get_app_root()
        work_dir = default_work_dir()
        export_dir = default_export_dir()
        self._app_root_lbl = QtWidgets.QLabel(str(app_root))
        self._app_root_lbl.setWordWrap(True)
        self._app_root_lbl.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self._work_dir_lbl = QtWidgets.QLabel(str(work_dir))
        self._work_dir_lbl.setWordWrap(True)
        self._work_dir_lbl.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self._export_dir_lbl = QtWidgets.QLabel(str(export_dir))
        self._export_dir_lbl.setWordWrap(True)
        self._export_dir_lbl.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        storage_form.addRow("应用目录:", self._app_root_lbl)
        storage_form.addRow("工作缓存与设置:", self._work_dir_lbl)
        storage_form.addRow(
            "默认导出目录:",
            wrap_with_help(
                self._export_dir_lbl,
                "同级便携存储机制",
                "只要软件所在目录可写，设置(settings.json)、离线分轨临时目录与 WAV/MIDI 导出均直接放在软件同级目录下，"
                "不主动写入 C 盘；仅当安装目录为只读系统盘时才安全回退至用户目录。",
            )[0],
        )
        dir_btns = QtWidgets.QHBoxLayout()
        open_app_btn = QtWidgets.QPushButton("打开应用目录")
        open_app_btn.setAutoDefault(False)
        open_app_btn.clicked.connect(lambda: _open_directory(app_root))
        open_export_btn = QtWidgets.QPushButton("打开导出目录")
        open_export_btn.setAutoDefault(False)
        open_export_btn.clicked.connect(lambda: _open_directory(export_dir))
        dir_btns.addWidget(open_app_btn)
        dir_btns.addWidget(open_export_btn)
        dir_btns.addStretch(1)
        storage_form.addRow(dir_btns)
        appearance_layout.addWidget(storage_box)
        appearance_layout.addStretch(1)
        self._add_page("appearance", appearance_page, scroll=True)
        self.update_appearance_summary(appearance)

        # Page 2: System Status
        status_tab = QtWidgets.QWidget()
        st_layout = QtWidgets.QVBoxLayout(status_tab)

        target = TargetHardwareSpec()
        target_lbl = QtWidgets.QLabel(
            f"目标真机基线规格: Windows 10/11 (Build >= {target.min_windows_build_for_process_loopback}) | "
            f"GPU: {target.gpu_name} | 显存: {target.vram_gb}GB VRAM (非 16GB) | 系统内存: {target.ram_gb}GB RAM"
        )
        target_lbl.setWordWrap(True)
        target_lbl.setObjectName("bannerNotice")
        set_widget_tone(target_lbl, "info")
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
        self.status_alert_lbl.setObjectName("bannerNotice")
        set_widget_tone(self.status_alert_lbl, "warn")
        st_layout.addWidget(self.status_alert_lbl)
        self._refresh_status_alert(hardware_report)

        self._add_page("status", status_tab)

        # Page 3: ResourceLimits & AIConfig
        cfg_tab = QtWidgets.QWidget()
        cfg_outer = QtWidgets.QVBoxLayout(cfg_tab)
        cfg_outer.setContentsMargins(0, 4, 0, 0)
        cfg_outer.setSpacing(12)

        guard_box = QtWidgets.QGroupBox("GUARDRAILS // 8GB 显存与 16GB 系统内存保护阈值")
        form = QtWidgets.QFormLayout(guard_box)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(11)

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

        self.roformer_chk = QtWidgets.QCheckBox("允许实验性 BS-RoFormer 模型 (仅在 RTX 5060 Ti 8GB 实测峰值通过后手动启用)")
        self.roformer_chk.setChecked(ai_config.allow_experimental_roformer)

        form.addRow("分轨前内存提醒", self.min_ram_spin)
        form.addRow("拒绝新分轨的内存阈值", self.pause_ram_spin)
        form.addRow("紧急停止的内存阈值", self.crit_ram_spin)
        form.addRow("GPU 2-Stem 最低空闲显存 (min_vram_2stem):", self.vram_2s_spin)
        form.addRow("GPU 4-Stem 最低空闲显存 (min_vram_4stem):", self.vram_4s_spin)
        form.addRow("桌面/QQ音乐保留最低空闲显存 (critical_vram_free):", self.crit_vram_spin)
        cfg_outer.addWidget(guard_box)

        chunk_box = QtWidgets.QGroupBox("CHUNKING & MODELS // 流式分块与实验模型")
        chunk_form = QtWidgets.QFormLayout(chunk_box)
        chunk_form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        chunk_form.setHorizontalSpacing(18)
        chunk_form.setVerticalSpacing(11)
        chunk_form.addRow(
            "离线音频流式分块长度:",
            wrap_with_help(
                self.chunk_sec_spin,
                "流式分块与 8GB 显存保护",
                "长音频会切分为固定秒数重叠分块依次送入 AI 子进程，防止 8GB 显存 / 16GB 内存峰值溢出；实测推荐 6.0s。",
            )[0],
        )
        chunk_form.addRow(
            "HTDemucs 4-Stem 模型分段:",
            wrap_with_help(
                self.demucs_seg_spin,
                "HTDemucs 内部模型分段",
                "仅控制 4 轨 HTDemucs 单段推理窗口长度（4–10s，实测默认 6s）。若偶发显存紧张会自动回落，不影响 MDX 二轨。",
            )[0],
        )
        chunk_form.addRow("高显存模型解锁:", self.roformer_chk)
        cfg_outer.addWidget(chunk_box)
        cfg_outer.addStretch(1)
        self._add_page("resources", cfg_tab, scroll=True)

        # Page 4: Turnkey AI & MIDI Environment + Auto-Bootstrap
        env_tab = QtWidgets.QWidget()
        env_layout = QtWidgets.QVBoxLayout(env_tab)
        env_layout.setContentsMargins(0, 4, 0, 0)
        env_layout.setSpacing(14)

        bootstrap_group = QtWidgets.QGroupBox("TURNKEY BOOTSTRAP // 零配置集成与一键修复运行环境")
        bootstrap_layout = QtWidgets.QVBoxLayout(bootstrap_group)
        bootstrap_layout.setSpacing(8)
        ff_path = find_ffmpeg_executable()
        ff_note = f"FFmpeg 已就绪 ({ff_path})" if ff_path else "FFmpeg 未在同级目录或 PATH 中发现（纯 WAV 可直接分析）"
        bootstrap_intro = QtWidgets.QLabel(
            "安装版已自动扫描同级 `runtime/ai`、`m` 短路径环境与 `.venv-ai`/`.venv-midi`。"
            f"当前：{ff_note}。如未打包内置运行时，可点击下方按钮在软件同级目录自动配置。"
        )
        bootstrap_intro.setObjectName("mutedCaption")
        bootstrap_intro.setWordWrap(True)
        bootstrap_layout.addWidget(bootstrap_intro)

        wheel_row = QtWidgets.QHBoxLayout()
        self.setup_wheel_dir_edit = QtWidgets.QLineEdit()
        self.setup_wheel_dir_edit.setPlaceholderText("可选：本地 cu128 wheel 目录（留空则在线安装 PyTorch cu128）")
        self.setup_wheel_browse_btn = QtWidgets.QPushButton("选本地 wheel…")
        self.setup_wheel_browse_btn.setAutoDefault(False)
        self.setup_wheel_browse_btn.clicked.connect(self._browse_wheel_dir)
        wheel_row.addWidget(self.setup_wheel_dir_edit, 1)
        wheel_row.addWidget(self.setup_wheel_browse_btn)
        wheel_row.addWidget(
            HelpBadge(
                "本地 cu128 Wheel 与短路径安装",
                "如果网络下载 2.75GB PyTorch cu128 较慢，可先将匹配版本的 torch/torchaudio/torchvision .whl 放入同一目录后在此选择。\n"
                "MIDI 环境使用短路径 `m` 或 `.venv-midi`，可避免 Windows 长路径限制导致 TensorFlow 2.15 安装失败。",
            )
        )
        bootstrap_layout.addLayout(wheel_row)

        boot_btns = QtWidgets.QHBoxLayout()
        self.setup_all_btn = QtWidgets.QPushButton("一键自动配置 AI + MIDI")
        self.setup_all_btn.setObjectName("analysisAction")
        self.setup_all_btn.setAutoDefault(False)
        self.setup_all_btn.clicked.connect(lambda: self._run_turnkey_bootstrap(skip_ai=False))
        self.setup_midi_only_btn = QtWidgets.QPushButton("仅自动配置 CPU MIDI")
        self.setup_midi_only_btn.setAutoDefault(False)
        self.setup_midi_only_btn.clicked.connect(lambda: self._run_turnkey_bootstrap(skip_ai=True))
        boot_btns.addWidget(self.setup_all_btn)
        boot_btns.addWidget(self.setup_midi_only_btn)
        boot_btns.addStretch(1)
        bootstrap_layout.addLayout(boot_btns)

        self.bootstrap_status_lbl = QtWidgets.QLabel(
            "准备就绪：若安装器已随包内置运行环境，启动时会自动识别，无需手动指定路径。"
        )
        self.bootstrap_status_lbl.setWordWrap(True)
        self.bootstrap_status_lbl.setObjectName("bannerNotice")
        set_widget_tone(self.bootstrap_status_lbl, "info")
        bootstrap_layout.addWidget(self.bootstrap_status_lbl)
        env_layout.addWidget(bootstrap_group)

        py_row = QtWidgets.QVBoxLayout()
        self.ai_python_edit = QtWidgets.QLineEdit(ai_python_executable)
        self.ai_python_edit.setAccessibleName("AI Worker Python")
        self.ai_python_edit.setPlaceholderText("自动识别 runtime\\ai 或 .venv-ai\\Scripts\\python.exe（也可手动指定）")
        self.browse_ai_py_btn = QtWidgets.QPushButton("浏览...")
        self.browse_ai_py_btn.clicked.connect(self._browse_ai_python)
        self.verify_ai_env_btn = QtWidgets.QPushButton("验证 AI 环境")
        self.verify_ai_env_btn.clicked.connect(self._verify_ai_environment)
        py_row.addWidget(self.ai_python_edit)
        py_row.addLayout(self._environment_actions(self.browse_ai_py_btn, self.verify_ai_env_btn))

        self.ai_probe_result_lbl = QtWidgets.QLabel(
            "验证 CUDA、ONNX、Demucs 和 FFmpeg。安装版如内置 runtime/ai 或同级 .venv-ai 会自动加载。"
        )
        self.ai_probe_result_lbl.setWordWrap(True)
        self.ai_probe_result_lbl.setObjectName("bannerNotice")
        set_widget_tone(self.ai_probe_result_lbl, "info")

        midi_py_row = QtWidgets.QVBoxLayout()
        self.midi_python_edit = QtWidgets.QLineEdit(midi_python_executable)
        self.midi_python_edit.setAccessibleName("MIDI Python 3.11")
        self.midi_python_edit.setPlaceholderText("自动识别同级 m / runtime\\midi / .venv-midi\\Scripts\\python.exe")
        self.browse_midi_py_btn = QtWidgets.QPushButton("浏览...")
        self.browse_midi_py_btn.clicked.connect(self._browse_midi_python)
        self.verify_midi_env_btn = QtWidgets.QPushButton("验证 MIDI 环境")
        self.verify_midi_env_btn.clicked.connect(self._verify_midi_environment)
        midi_py_row.addWidget(self.midi_python_edit)
        midi_py_row.addLayout(self._environment_actions(self.browse_midi_py_btn, self.verify_midi_env_btn))

        self.midi_probe_result_lbl = QtWidgets.QLabel(
            "Basic Pitch 使用独立的 Python 3.11 CPU 环境。安装版内置短路径 m/ 或同级 .venv-midi 时会自动启用。"
        )
        self.midi_probe_result_lbl.setWordWrap(True)
        self.midi_probe_result_lbl.setObjectName("bannerNotice")
        set_widget_tone(self.midi_probe_result_lbl, "info")

        for gtitle, glabel, controls, feedback in (
            ("AI WORKER // 分轨运行环境", "AI Worker Python", py_row, self.ai_probe_result_lbl),
            ("MIDI WORKER // 转录运行环境", "MIDI Python 3.11", midi_py_row, self.midi_probe_result_lbl),
        ):
            group = QtWidgets.QGroupBox(gtitle)
            section = QtWidgets.QFormLayout(group)
            section.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
            section.setHorizontalSpacing(14)
            section.setVerticalSpacing(10)
            section.addRow(QtWidgets.QLabel(glabel))
            section.addRow(controls)
            section.addRow(feedback)
            env_layout.addWidget(group)
        env_layout.addStretch(1)

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
        self.apply_skin(appearance, acid_variant=self._acid_variant or "")
        self.open_category("appearance")
        self._category_buttons["appearance"].setFocus()

    @staticmethod
    def _icon_color(appearance: Appearance, acid_variant: Optional[str]) -> str:
        if acid_variant == "light":
            return get_acid_palette("light").accent_strong
        if acid_variant == "dark":
            return get_acid_palette("dark").accent
        _, _, accent = appearance.effective_colors(system_is_dark=detect_system_is_dark())
        return accent

    def apply_skin(self, appearance: Appearance, *, acid_variant: Optional[str] = None) -> None:
        self._appearance = appearance
        if acid_variant is not None:
            self._acid_variant = acid_variant or None
        else:
            self._acid_variant = resolve_acid_variant(
                appearance,
                system_is_dark=detect_system_is_dark(),
            )
        icon_color = self._icon_color(appearance, self._acid_variant)
        for key, btn in self._category_buttons.items():
            btn.setIcon(QtGui.QIcon(_category_icon(key, color=icon_color)))
        if self.parent() is None:
            if self._acid_variant in ("light", "dark"):
                self.setStyleSheet(acid_stylesheet(appearance, self._acid_variant))
            else:
                self.setStyleSheet("")

    def _add_page(self, key: str, widget: QtWidgets.QWidget, *, scroll: bool = False) -> None:
        if scroll:
            widget.setObjectName("settingsScrollPage")
            area = QtWidgets.QScrollArea()
            area.setObjectName("settingsScrollArea")
            area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            area.setWidgetResizable(True)
            area.viewport().setAutoFillBackground(False)
            area.setWidget(widget)
            widget.setAutoFillBackground(False)
            widget = area
        self._page_map[key] = widget
        self._pages.addWidget(widget)

    @staticmethod
    def _environment_actions(browse: QtWidgets.QPushButton, verify: QtWidgets.QPushButton) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(browse)
        row.addWidget(verify)
        return row

    def update_appearance_summary(self, appearance: Appearance) -> None:
        mode_lbl = THEME_MODES.get(appearance.theme_mode, "黑夜")
        self._theme_summary.setText(f"{PRESETS[appearance.preset][0]} · {mode_lbl}")
        self._layout_summary.setText(LAYOUTS[appearance.layout][0])
        font_label = appearance.font_family or "系统默认"
        self._font_summary.setText(f"{font_label} · {appearance.font_size} px")

    def open_category(self, key: str) -> None:
        self._active_category = key
        self._category_buttons[key].setChecked(True)
        self._pages.setCurrentWidget(self._page_map[key])
        title, subtitle = SETTINGS_CATEGORIES[key]
        self._page_eyebrow.setText(SETTINGS_EYEBROWS.get(key, "CONFIG // TELEMETRY"))
        self._title.setText(title)
        self._subtitle.setText(subtitle)

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
                    f"[WARN] 当前在 {r.os_system} 运行：WASAPI Process Loopback 与 RTX 5060 Ti CUDA 未在 Windows 真机验证。\n"
                    + warn_text
                )
            self.status_alert_lbl.setText(warn_text.strip())
            set_widget_tone(self.status_alert_lbl, "warn")
            self.status_alert_lbl.setVisible(True)
        else:
            self.status_alert_lbl.setVisible(False)
            self.status_alert_lbl.setText("")

    def _browse_wheel_dir(self) -> None:
        chosen = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "选择本地 CUDA cu128 Wheel 目录",
            self.setup_wheel_dir_edit.text().strip() or str(get_app_root()),
        )
        if chosen:
            self.setup_wheel_dir_edit.setText(chosen)

    def _run_turnkey_bootstrap(self, *, skip_ai: bool) -> None:
        if self._bootstrap_running:
            return
        if sys.platform != "win32":
            set_widget_tone(self.bootstrap_status_lbl, "warn")
            self.bootstrap_status_lbl.setText(
                "[WARN] 当前非 Windows 系统，不能直接执行 Windows 一键脚本 `scripts/setup_windows.ps1`；"
                "在 Windows 11 本机上点击此按钮即可自动安装到软件同级目录。"
            )
            return

        script_path = get_bundle_root() / "scripts" / "setup_windows.ps1"
        if not script_path.exists():
            script_path = get_app_root() / "scripts" / "setup_windows.ps1"
        if not script_path.exists():
            set_widget_tone(self.bootstrap_status_lbl, "error")
            self.bootstrap_status_lbl.setText(f"[ERR] 找不到初始化脚本: {script_path}")
            return

        pwsh_exe = shutil.which("pwsh") or shutil.which("powershell")
        if not pwsh_exe:
            set_widget_tone(self.bootstrap_status_lbl, "error")
            self.bootstrap_status_lbl.setText("[ERR] 找不到 PowerShell (`pwsh` / `powershell`)。")
            return

        app_root = get_app_root()
        target_root = app_root if os.access(app_root, os.W_OK) else default_work_dir().parent
        target_root.mkdir(parents=True, exist_ok=True)
        ai_venv = target_root / ("runtime\\ai" if getattr(sys, "frozen", False) else ".venv-ai")
        midi_venv = target_root / ("m" if getattr(sys, "frozen", False) else ".venv-midi")
        wheel_dir = self.setup_wheel_dir_edit.text().strip()

        cmd = [
            pwsh_exe,
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-SkipCore",
            "-AiVenvPath",
            str(ai_venv),
            "-MidiVenvPath",
            str(midi_venv),
        ]
        if skip_ai:
            cmd.append("-SkipAI")
        if wheel_dir:
            cmd.extend(["-CudaWheelDir", wheel_dir])

        self._bootstrap_running = True
        self.setup_all_btn.setEnabled(False)
        self.setup_midi_only_btn.setEnabled(False)
        set_widget_tone(self.bootstrap_status_lbl, "info")
        self.bootstrap_status_lbl.setText("[BUSY] 正在执行一键环境初始化，请稍候（将在软件同级目录建立隔离环境）...")

        def _worker() -> None:
            last_lines: list[str] = []
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(get_bundle_root()),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    **subprocess_no_window_kwargs(),
                )
                assert proc.stdout is not None
                for raw_line in proc.stdout:
                    line = raw_line.strip()
                    if line:
                        last_lines.append(line)
                        if len(last_lines) > 8:
                            last_lines = last_lines[-8:]
                        if not self._dialog_closed:
                            try:
                                self._bootstrap_progress.emit("\n".join(last_lines[-3:]))
                            except RuntimeError:
                                pass
                rc = proc.wait()
                if not self._dialog_closed:
                    if rc == 0:
                        self._bootstrap_finished.emit(True, "[OK] 一键环境初始化完成，正在自动识别并验证解释器...")
                    else:
                        tail = "\n".join(last_lines[-4:])
                        self._bootstrap_finished.emit(False, f"[ERR] 初始化失败 (exit={rc}):\n{tail}")
            except Exception as exc:
                if not self._dialog_closed:
                    self._bootstrap_finished.emit(False, f"[ERR] 启动初始化脚本失败: {exc}")

        threading.Thread(target=_worker, name="ListenScope-TurnkeySetup", daemon=True).start()

    @QtCore.Slot(str)
    def _on_bootstrap_progress(self, tail: str) -> None:
        if not self._dialog_closed:
            self.bootstrap_status_lbl.setText(f"[BUSY] 初始化进度:\n{tail}")

    @QtCore.Slot(bool, str)
    def _on_bootstrap_finished(self, ok: bool, message: str) -> None:
        if self._dialog_closed:
            return
        self._bootstrap_running = False
        self.setup_all_btn.setEnabled(True)
        self.setup_midi_only_btn.setEnabled(True)
        set_widget_tone(self.bootstrap_status_lbl, "ok" if ok else "error")
        self.bootstrap_status_lbl.setText(message)
        if ok:
            ai_py, midi_py = _discover_installed_runtime_pythons(get_app_root())
            if ai_py and not self.ai_python_edit.text().strip():
                self.ai_python_edit.setText(ai_py)
            if midi_py:
                self.midi_python_edit.setText(midi_py)
            if self.ai_python_edit.text().strip():
                self._verify_ai_environment()
            if self.midi_python_edit.text().strip():
                self._verify_midi_environment()

    def _browse_ai_python(self) -> None:
        start_dir = (
            str(Path(self.ai_python_edit.text().strip()).parent)
            if self.ai_python_edit.text().strip()
            else str(get_app_root())
        )
        selected, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "选择独立 AI Worker Python 解释器",
            start_dir,
            "Python Executable (python.exe python python3*);;All Files (*)",
        )
        if selected:
            self.ai_python_edit.setText(selected)

    def _browse_midi_python(self) -> None:
        start_dir = (
            str(Path(self.midi_python_edit.text().strip()).parent)
            if self.midi_python_edit.text().strip()
            else str(get_app_root())
        )
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
        set_widget_tone(self.ai_probe_result_lbl, "info")
        self.ai_probe_result_lbl.setText("[BUSY] 正在启动子进程检测 AI Python 环境 (CUDA / sm_120 / ONNX / Demucs / FFmpeg)...")

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
        set_widget_tone(self.midi_probe_result_lbl, "info")
        self.midi_probe_result_lbl.setText(
            "[BUSY] 正在启动子进程检测独立 CPU MIDI 环境 (Basic Pitch / TensorFlow / pkg_resources / mido)..."
        )

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
            self.ai_probe_result_lbl.setText(f"[ERR] 检测失败: {err}")
            set_widget_tone(self.ai_probe_result_lbl, "error")
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
        set_widget_tone(self.ai_probe_result_lbl, "ok" if gpu_ready else "warn")

    @QtCore.Slot(object)
    def _on_midi_probe_finished(self, result: Any) -> None:
        if self._dialog_closed:
            return
        self.verify_midi_env_btn.setEnabled(True)
        if not isinstance(result, dict) or not result.get("ok"):
            err = result.get("error", "未知错误") if isinstance(result, dict) else str(result)
            guide = result.get("setup_guide", MIDI_ENV_SETUP_GUIDE) if isinstance(result, dict) else MIDI_ENV_SETUP_GUIDE
            msg = err if guide in err else f"{err}\n{guide}"
            self.midi_probe_result_lbl.setText(f"[ERR] MIDI 环境不可用: {msg}")
            set_widget_tone(self.midi_probe_result_lbl, "error")
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
        set_widget_tone(self.midi_probe_result_lbl, "ok" if midi_ready else "warn")

    def _populate_status_table(self, r: SystemHardwareReport) -> None:
        gpu0 = r.gpus[0] if r.gpus else None
        rows = [
            ("操作系统", f"{r.os_system} {r.os_release} ({r.architecture})"),
            (
                "Windows Build / WASAPI 进程捕获",
                f"{r.windows_build or 'N/A'} / {'支持' if r.wasapi_process_loopback_supported else '不可用 / 未在 Windows 真机验证'}",
            ),
            (
                "系统 RAM (总量 / 当前可用)",
                f"{r.ram_total_mb / 1024.0:.2f} GB ({r.ram_total_mb:.0f} MB) / {r.ram_available_mb:.0f} MB",
            ),
            ("GPU 型号", gpu0.name if gpu0 else "未检测到 NVIDIA GPU"),
            (
                "VRAM (总量 / 空闲)",
                f"{gpu0.total_vram_mb:.0f} MB / {gpu0.free_vram_mb:.0f} MB"
                if gpu0
                else "N/A (目标真机为 8GB VRAM)",
            ),
            ("NVIDIA Driver / NVML", f"{r.nvidia_driver_version or '未检测到'} / {'可用' if r.nvml_available else '不可用'}"),
            ("PyTorch", f"{r.pytorch.version} (CUDA build={r.pytorch.cuda_build})" if r.pytorch.installed else "未安装 (Core 环境隔离正常)"),
            (
                "torch.cuda.is_available() / Compute Cap",
                f"{'可用' if r.pytorch.cuda_available else '不可用'} / {r.pytorch.compute_capability or 'N/A'}",
            ),
            (
                "RTX 5060 Ti sm_120 支持 / Kernel 测试",
                f"{r.pytorch.supports_sm_120} / {r.pytorch.kernel_smoke_test_passed}",
            ),
            (
                "ONNX Runtime / CUDAExecutionProvider",
                f"{r.onnxruntime.version or '未安装'} / {'存在' if r.onnxruntime.cuda_provider_available else '不存在'} ({r.onnxruntime.providers})",
            ),
            (
                "GPU AI 准入状态 (gpu_ai_ready)",
                f"{'READY' if r.gpu_ai_ready else 'BLOCKED'} {f'({r.gpu_ai_block_reason})' if r.gpu_ai_block_reason else ''}",
            ),
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
