"""Settings dialog: Appearance/storage summary, guardrails, turnkey environment bootstrap, and System Status."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
from typing import Any, Optional

from dataclasses import replace

from PySide6 import QtCore, QtGui, QtSvg, QtWidgets

from core.appearance import (
    Appearance,
    FOCUS_STYLES,
    LAYOUTS,
    PRESETS,
    THEME_MODES,
    UI_SURFACE_STYLES,
)
from core.bootstrap_manager import (
    clean_bootstrap_line,
    decode_bootstrap_bytes,
    discover_installed_runtime_pythons,
    get_bootstrap_manager,
)
from core.config import AIConfig, ResourceLimits, TargetHardwareSpec
from core.i18n import LANGUAGES, set_i18n_text, translate_widget_tree
from core.logging import active_log_dir
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
    PYTORCH_CU128_INDEX_URL,
    PYTORCH_DOWNLOAD_GUIDE,
    PYTORCH_INSTALL_COMMAND,
    PYTORCH_OFFICIAL_URL,
    PYTHON_WINDOWS_DOWNLOAD_URL,
    apply_external_ai_probe_to_report,
    probe_external_ai_environment,
    probe_external_midi_environment,
    scan_local_pytorch_installations,
)
from ui.appearance import detect_system_is_dark, set_widget_tone
from ui.help_badge import HelpBadge, install_focus_animations, set_focus_ring_style, wrap_with_help
from ui.acid_style import (
    FramelessDialogChrome,
    SegmentedBatteryProgressBar,
    TelemetryHeader,
    acid_stylesheet,
    get_acid_palette,
    resolve_acid_variant,
)

GITHUB_REPO_URL = "https://github.com/Ceph-learner/ListenScope"
GITHUB_ISSUES_URL = "https://github.com/Ceph-learner/ListenScope/issues"

# Re-exported cleanly for tests & diagnostics backward compatibility
_decode_bootstrap_bytes = decode_bootstrap_bytes
_clean_bootstrap_line = clean_bootstrap_line
_discover_installed_runtime_pythons = discover_installed_runtime_pythons

SETTINGS_CATEGORIES = {
    "appearance": ("外观与布局", "切换工作区、黑夜/白天/跟随系统主题、语言、数据路径与开源项目反馈"),
    "resources": ("资源保护", "配置内存、显存阈值和分轨模型参数"),
    "midi": ("AI 与 MIDI 环境", "扫描本机 PyTorch 或一键自动配置独立 Python 运行环境"),
    "status": ("系统诊断", "查看硬件、捕获能力和运行环境"),
}

SETTINGS_EYEBROWS = {
    "appearance": "CONFIG // 01 · APPEARANCE, STORAGE & COMMUNITY",
    "resources": "CONFIG // 02 · GUARDRAILS & CHUNKING",
    "midi": "CONFIG // 03 · PYTORCH SCANNER & RUNTIMES",
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


def _open_web_url(url: str) -> None:
    QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))


class SettingsDialog(QtWidgets.QDialog):
    """Shows real SystemHardwareReport (`设置 -> 系统状态`), local PyTorch scanner, turnkey environment setup, and ResourceLimits/AIConfig."""

    _probe_finished = QtCore.Signal(object)
    _midi_probe_finished = QtCore.Signal(object)
    _pytorch_scan_finished = QtCore.Signal(object)
    appearance_requested = QtCore.Signal(object)
    appearance_changed = QtCore.Signal(object)
    restart_requested = QtCore.Signal()
    bootstrap_runtimes_ready = QtCore.Signal(str, str)

    def __init__(
        self,
        hardware_report: SystemHardwareReport,
        resource_limits: ResourceLimits,
        ai_config: AIConfig,
        *,
        ai_python_executable: str = "",
        midi_python_executable: str = "",
        appearance: Appearance = Appearance(),
        close_behavior: str = "ask",
        acid_variant: Optional[str] = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("ListenScope 设置")
        self.resize(920, 750)

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
        self._updated_appearance: Appearance = appearance
        self._updated_close_behavior: str = str(close_behavior or "ask").strip().lower()
        if self._updated_close_behavior not in ("ask", "tray", "quit"):
            self._updated_close_behavior = "ask"
        self._verified_ai_probe: Optional[dict[str, Any]] = None
        self._dialog_closed = False
        self._bootstrap_mgr = get_bootstrap_manager()
        self._bootstrap_running = bool(self._bootstrap_mgr.snapshot().get("running", False))
        self._probe_finished.connect(self._on_ai_probe_finished, QtCore.Qt.ConnectionType.QueuedConnection)
        self._midi_probe_finished.connect(self._on_midi_probe_finished, QtCore.Qt.ConnectionType.QueuedConnection)
        self._pytorch_scan_finished.connect(self._on_pytorch_scan_finished, QtCore.Qt.ConnectionType.QueuedConnection)
        self._bootstrap_mgr.state_changed.connect(self._on_bootstrap_state_changed)
        self._bootstrap_mgr.completed.connect(self._on_bootstrap_finished)
        self._bootstrap_signals_connected = True

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._shell_frame = QtWidgets.QFrame(self)
        outer.addWidget(self._shell_frame)

        root = QtWidgets.QVBoxLayout(self._shell_frame)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(12)

        self._header = TelemetryHeader(
            "SYSTEM PREFERENCES // TELEMETRY CONFIG",
            "系统设置与运行环境管理",
            badge_text="PORTABLE // LOCAL",
        )
        self._drag_header = self._header
        self._chrome = FramelessDialogChrome(self, self._shell_frame, self._header, resizable=True)
        self._header.add_right_widget(
            HelpBadge(
                "系统设置总览",
                "• 外观与布局：切换默认酸性遥测浅色白天主题、中/英/韩/日四语、无边框圆角窗口、自定义背景图（非酸性主题）及同级存储目录。\n"
                "• 资源保护：针对 RTX 5060 Ti 8GB 显存与 16GB 内存设定预检护栏与流式分块。\n"
                "• AI 与 MIDI 环境：一键扫描本机已安装的 PyTorch 环境（若未安装自动提供官方下载地址），或一键配置隔离运行时。\n"
                "• 系统诊断：查看真实 GPU、CUDA sm_120、ONNX Runtime 与 WASAPI 捕获能力。",
            )
        )
        self._header.add_right_widget(self._chrome.close_btn)
        root.addWidget(self._header)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(16)
        navigation = QtWidgets.QWidget()
        navigation.setObjectName("settingsNavigation")
        navigation.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground)
        navigation.setFixedWidth(176)
        nav_layout = QtWidgets.QVBoxLayout(navigation)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(5)
        self._nav_group = QtWidgets.QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._category_buttons = {}
        for key, (label, description) in SETTINGS_CATEGORIES.items():
            button = QtWidgets.QPushButton(label)
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

        # Page 1: Appearance, Portable Storage & Open-Source Feedback
        appearance_page = QtWidgets.QWidget()
        appearance_layout = QtWidgets.QVBoxLayout(appearance_page)
        appearance_layout.setContentsMargins(0, 4, 6, 0)
        appearance_layout.setSpacing(12)

        appearance_box = QtWidgets.QGroupBox("APPEARANCE // 当前外观、多语言与壳体配置")
        appearance_form = QtWidgets.QFormLayout(appearance_box)
        appearance_form.setHorizontalSpacing(14)
        appearance_form.setVerticalSpacing(11)
        self._theme_summary = QtWidgets.QLabel()
        self._layout_summary = QtWidgets.QLabel()
        self._font_summary = QtWidgets.QLabel()
        appearance_form.addRow("主题与模式", self._theme_summary)
        appearance_form.addRow("工作区", self._layout_summary)
        appearance_form.addRow("字体与字号", self._font_summary)

        quick_lang_row = QtWidgets.QHBoxLayout()
        quick_lang_row.setSpacing(10)
        self.language_combo = QtWidgets.QComboBox()
        self.language_combo.setProperty("lsKeepItems", True)
        self.language_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        for lang_code, lang_label in LANGUAGES.items():
            self.language_combo.addItem(lang_label, lang_code)
        lang_idx = self.language_combo.findData(appearance.language)
        self.language_combo.setCurrentIndex(max(0, lang_idx))
        self.language_combo.currentIndexChanged.connect(self._on_quick_appearance_changed)

        self.frameless_chk = QtWidgets.QCheckBox("无边框圆角窗口")
        self.frameless_chk.setChecked(bool(appearance.frameless))
        self.frameless_chk.toggled.connect(self._on_quick_appearance_changed)

        quick_lang_row.addWidget(self.language_combo, 1)
        quick_lang_row.addWidget(self.frameless_chk)
        quick_lang_row.addWidget(
            HelpBadge(
                "多语言与无边框圆角窗口",
                "• 界面语言支持简体中文、English、한국어、日本語（内置英文代号保持固定；English 模式下仅显示英文，不重复出现）。\n"
                "• 无边框圆角窗口消除生硬的系统窗口边框，自动适配屏幕分辨率并居中。",
            )
        )
        appearance_form.addRow("界面语言与壳体:", quick_lang_row)

        assist_row = QtWidgets.QHBoxLayout()
        assist_row.setSpacing(10)
        self.help_mode_chk = QtWidgets.QCheckBox("说明模式 (显示 [?] 悬浮说明)")
        self.help_mode_chk.setChecked(bool(appearance.help_mode))
        self.help_mode_chk.toggled.connect(self._on_quick_appearance_changed)
        self.focus_anim_chk = QtWidgets.QCheckBox("交互聚焦动画")
        self.focus_anim_chk.setChecked(bool(appearance.focus_animations))
        self.focus_anim_chk.toggled.connect(self._on_quick_appearance_changed)
        self.focus_style_combo = QtWidgets.QComboBox()
        for fkey, flabel in FOCUS_STYLES.items():
            self.focus_style_combo.addItem(flabel, fkey)
        self.focus_style_combo.setCurrentIndex(max(0, self.focus_style_combo.findData(appearance.focus_style)))
        self.focus_style_combo.setEnabled(bool(appearance.focus_animations))
        self.focus_style_combo.currentIndexChanged.connect(self._on_quick_appearance_changed)
        assist_row.addWidget(self.help_mode_chk)
        assist_row.addWidget(self.focus_anim_chk)
        assist_row.addWidget(self.focus_style_combo)
        assist_row.addStretch(1)
        assist_row.addWidget(
            HelpBadge(
                "说明模式与交互聚焦动画",
                "• 说明模式：开启后在各功能旁显示 [?] 徽标，鼠标悬浮即可即时弹出功能解释；关闭后全局隐藏所有问号并禁止一切悬浮提示。\n"
                "• 交互聚焦动画：支持「极细描边 / 护栏角框 / 底线脉冲」，仅对按钮与下拉框克制绘制（零显存占用）。",
            )
        )
        appearance_form.addRow("交互与聚焦:", assist_row)

        surface_row = QtWidgets.QHBoxLayout()
        surface_row.setSpacing(10)
        self.surface_style_combo = QtWidgets.QComboBox()
        for skey, slabel in UI_SURFACE_STYLES.items():
            self.surface_style_combo.addItem(slabel, skey)
        self.surface_style_combo.setCurrentIndex(max(0, self.surface_style_combo.findData(appearance.ui_surface_style)))
        self.surface_style_combo.currentIndexChanged.connect(self._on_quick_appearance_changed)
        self.close_to_tray_chk = QtWidgets.QCheckBox("点击右上角 × 时最小化到系统托盘")
        self.close_to_tray_chk.setChecked(bool(appearance.close_to_tray))
        self.close_to_tray_chk.toggled.connect(self._on_quick_appearance_changed)
        surface_row.addWidget(self.surface_style_combo)
        surface_row.addWidget(self.close_to_tray_chk, 1)
        appearance_form.addRow("质感与托盘:", surface_row)

        self.close_behavior_combo = QtWidgets.QComboBox()
        self.close_behavior_combo.addItem("每次询问", "ask")
        self.close_behavior_combo.addItem("最小化到托盘", "tray")
        self.close_behavior_combo.addItem("退出程序", "quit")
        cb_idx = self.close_behavior_combo.findData(self._updated_close_behavior)
        self.close_behavior_combo.setCurrentIndex(max(0, cb_idx))
        appearance_form.addRow("关闭按钮行为:", self.close_behavior_combo)

        telem_row = QtWidgets.QHBoxLayout()
        telem_row.setSpacing(10)
        self.telemetry_strength_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.telemetry_strength_slider.setRange(0, 100)
        self.telemetry_strength_slider.setValue(int(appearance.telemetry_animation_strength))
        self.telemetry_strength_slider.valueChanged.connect(self._on_quick_appearance_changed)
        self.telemetry_strength_lbl = QtWidgets.QLabel(f"{int(appearance.telemetry_animation_strength)}%")
        self.telemetry_strength_lbl.setMinimumWidth(36)
        self.music_reactive_chk = QtWidgets.QCheckBox("随音乐高潮动态变化")
        self.music_reactive_chk.setChecked(bool(appearance.music_reactive_animations))
        self.music_reactive_chk.setEnabled(int(appearance.telemetry_animation_strength) > 0)
        self.music_reactive_chk.toggled.connect(self._on_quick_appearance_changed)
        telem_row.addWidget(self.telemetry_strength_slider, 1)
        telem_row.addWidget(self.telemetry_strength_lbl)
        telem_row.addWidget(self.music_reactive_chk)
        telem_row.addWidget(
            HelpBadge(
                "遥测微动画强度与音乐联动",
                "控制点阵、顶部信号条与分段电池进度条的呼吸强度（0% = 完全静态，100% = 饱满动态），并可选是否随音乐音量与高潮起伏；也可点主界面底部 [STATIC_LOCK] 一键冻结。",
            )
        )
        appearance_form.addRow("遥测微动画:", telem_row)

        edit_appearance = QtWidgets.QPushButton("编辑外观与字体…")
        edit_appearance.setObjectName("appearanceEntry")
        edit_appearance.setAutoDefault(False)
        edit_appearance.clicked.connect(lambda: self.appearance_requested.emit(self))
        appearance_form.addRow(
            wrap_with_help(
                edit_appearance,
                "自定义外观与实时预览",
                "默认采用酸性遥测浅色白天主题（锁定标准工业字体与官方配色，字号 11–20px 可调）；切换到其他主题后可自由调节颜色、系统字体并上传自定义背景壁纸。",
            )[0]
        )
        appearance_layout.addWidget(appearance_box)

        storage_box = QtWidgets.QGroupBox("PORTABLE STORAGE // 同级目录保存位置（默认不写入 C 盘）")
        storage_form = QtWidgets.QFormLayout(storage_box)
        storage_form.setVerticalSpacing(6)
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
        self.open_logs_btn = QtWidgets.QPushButton("打开日志目录")
        self.open_logs_btn.setAutoDefault(False)
        self.open_logs_btn.clicked.connect(lambda: _open_directory(active_log_dir()))
        dir_btns.addWidget(open_app_btn)
        dir_btns.addWidget(open_export_btn)
        dir_btns.addWidget(self.open_logs_btn)
        dir_btns.addStretch(1)
        storage_form.addRow(dir_btns)
        appearance_layout.addWidget(storage_box)

        # Open-Source Project Links, Star & Feedback Card
        community_box = QtWidgets.QGroupBox("OPEN SOURCE && FEEDBACK // 开源项目地址与问题反馈")
        community_layout = QtWidgets.QVBoxLayout(community_box)
        community_layout.setSpacing(6)
        community_head = QtWidgets.QHBoxLayout()
        self.community_intro_lbl = QtWidgets.QLabel(
            f"如果 ListenScope 对你的扒谱、贝斯分析或和弦练习有帮助，欢迎前往 GitHub 点个 ⭐ Star 支持！\n"
            f"• 项目仓库: {GITHUB_REPO_URL}  |  问题反馈: {GITHUB_ISSUES_URL} （暂为私有占位，转公开后可直提 Issue）"
        )
        self.community_intro_lbl.setWordWrap(True)
        self.community_intro_lbl.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        community_head.addWidget(self.community_intro_lbl, 1)
        community_head.addWidget(
            HelpBadge(
                "项目仓库与反馈说明",
                "点击下方按钮可在浏览器中直达 GitHub 仓库主页或 Issues 反馈页面，也可一键复制仓库地址分享给朋友。",
            )
        )
        community_layout.addLayout(community_head)

        community_btns = QtWidgets.QHBoxLayout()
        self.open_repo_btn = QtWidgets.QPushButton("⭐ 点个 Star / 项目主页")
        self.open_repo_btn.setObjectName("analysisAction")
        self.open_repo_btn.setAutoDefault(False)
        self.open_repo_btn.clicked.connect(lambda: _open_web_url(GITHUB_REPO_URL))

        self.open_issues_btn = QtWidgets.QPushButton("反馈问题 (GitHub Issues)")
        self.open_issues_btn.setAutoDefault(False)
        self.open_issues_btn.clicked.connect(lambda: _open_web_url(GITHUB_ISSUES_URL))

        self.copy_repo_url_btn = QtWidgets.QPushButton("复制项目链接")
        self.copy_repo_url_btn.setAutoDefault(False)
        self.copy_repo_url_btn.clicked.connect(self._copy_github_url)

        community_btns.addWidget(self.open_repo_btn)
        community_btns.addWidget(self.open_issues_btn)
        community_btns.addWidget(self.copy_repo_url_btn)
        community_btns.addStretch(1)
        community_layout.addLayout(community_btns)
        appearance_layout.addWidget(community_box)

        appearance_layout.addStretch(1)
        self._add_page("appearance", appearance_page, scroll=True)
        self.update_appearance_summary(appearance, _translate=False)

        # Page 2: System Status
        status_tab = QtWidgets.QWidget()
        st_layout = QtWidgets.QVBoxLayout(status_tab)

        target = TargetHardwareSpec()
        target_row = QtWidgets.QHBoxLayout()
        target_lbl = QtWidgets.QLabel(
            f"目标真机基线规格: Windows 10/11 (Build >= {target.min_windows_build_for_process_loopback}) | "
            f"GPU: {target.gpu_name} | 显存: {target.vram_gb}GB VRAM (非 16GB) | 系统内存: {target.ram_gb}GB RAM"
        )
        target_lbl.setWordWrap(True)
        target_lbl.setObjectName("bannerNotice")
        set_widget_tone(target_lbl, "info")
        target_row.addWidget(target_lbl, 1)
        target_row.addWidget(
            HelpBadge(
                "系统诊断表说明",
                "显示当前电脑的操作系统 Build、可用 RAM、NVIDIA 显卡与空闲 VRAM、以及隔离 AI 环境中的 PyTorch CUDA / Blackwell sm_120 支持状态。\n"
                "主界面进程默认不加载 PyTorch（保持轻量低内存），在「AI 与 MIDI 环境」页验证或扫描本机 PyTorch 后此表会同步更新。",
            )
        )
        st_layout.addLayout(target_row)

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

        self._status_diag_actions = QtWidgets.QHBoxLayout()
        self.status_goto_env_btn = QtWidgets.QPushButton("前往 AI 与 MIDI 环境 →")
        self.status_goto_env_btn.setObjectName("analysisAction")
        self.status_goto_env_btn.setAutoDefault(False)
        self.status_goto_env_btn.clicked.connect(lambda: self.open_category("midi"))
        self.status_open_logs_btn = QtWidgets.QPushButton("打开日志目录")
        self.status_open_logs_btn.setAutoDefault(False)
        self.status_open_logs_btn.clicked.connect(lambda: _open_directory(active_log_dir()))
        self._status_diag_actions.addWidget(self.status_goto_env_btn)
        self._status_diag_actions.addWidget(self.status_open_logs_btn)
        self._status_diag_actions.addStretch(1)
        st_layout.addLayout(self._status_diag_actions)

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

        self.demucs_seg_spin = QtWidgets.QSpinBox()
        self.demucs_seg_spin.setRange(4, max(int(s) for s in ai_config.demucs_segment_ladder))
        self.demucs_seg_spin.setSuffix(" s")
        self.demucs_seg_spin.setValue(ai_config.demucs_default_segment_sec)

        self.roformer_chk = QtWidgets.QCheckBox("允许实验性 BS-RoFormer 模型 (仅在 RTX 5060 Ti 8GB 实测峰值通过后手动启用)")
        self.roformer_chk.setChecked(ai_config.allow_experimental_roformer)

        form.addRow(
            "分轨前内存提醒",
            wrap_with_help(
                self.min_ram_spin,
                "分轨前内存提醒阈值",
                "当系统可用内存 (psutil.available) 低于此值时给出黄色提示，但仍允许继续启动分轨（默认 5120 MB）。",
            )[0],
        )
        form.addRow(
            "拒绝新分轨的内存阈值",
            wrap_with_help(
                self.pause_ram_spin,
                "拒绝新分轨阈值",
                "当系统可用内存低于此值时拒绝启动新的 AI 分轨任务，防止系统卡死或浏览器崩溃（默认 3072 MB）。",
            )[0],
        )
        form.addRow(
            "紧急停止的内存阈值",
            wrap_with_help(
                self.crit_ram_spin,
                "紧急停止 (E-STOP) 内存阈值",
                "分轨运行期间若系统可用内存跌破此水位（默认 2048 MB），主程序会立即终止 AI 子进程并回收内存。",
            )[0],
        )
        form.addRow(
            "GPU 2-Stem 最低空闲显存:",
            wrap_with_help(
                self.vram_2s_spin,
                "2 轨快速分离显存预检",
                "启动 2 轨 (人声 + 伴奏 MDX ONNX) 前要求的最低空闲显存（默认 2560 MB）。",
            )[0],
        )
        form.addRow(
            "GPU 4-Stem 最低空闲显存:",
            wrap_with_help(
                self.vram_4s_spin,
                "4 轨精细分离显存预检",
                "启动 4 轨 (人声/鼓/贝斯/其他 HTDemucs) 前要求的最低空闲显存（默认 4300 MB）。",
            )[0],
        )
        form.addRow(
            "桌面/播放器保留最低空闲显存:",
            wrap_with_help(
                self.crit_vram_spin,
                "桌面与音乐播放器保底显存",
                "始终为 Windows 桌面合成器 (DWM)、QQ 音乐/网易云音乐与浏览器预留的显存安全垫（默认 1200 MB）。",
            )[0],
        )
        cfg_outer.addWidget(guard_box)

        chunk_box = QtWidgets.QGroupBox("CHUNKING && MODELS // 流式分块与实验模型")
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
        chunk_form.addRow(
            "高显存模型解锁:",
            wrap_with_help(
                self.roformer_chk,
                "实验性 BS-RoFormer 模型开关",
                "BS-RoFormer 音质细腻但显存开销显著高于 MDX/HTDemucs；默认关闭以保护 8GB 显存，确认空闲显存充足时可手动勾选。",
            )[0],
        )
        cfg_outer.addWidget(chunk_box)

        # Hybrid iGPU + dGPU heterogeneous acceleration (Plan A & Plan B)
        hybrid_box = QtWidgets.QGroupBox("HYBRID GPU OFFLOAD // 集显 + 独显异构协同加速（可选）")
        hybrid_form = QtWidgets.QFormLayout(hybrid_box)
        hybrid_form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        hybrid_form.setHorizontalSpacing(18)
        hybrid_form.setVerticalSpacing(10)

        plan_a_col = QtWidgets.QVBoxLayout()
        plan_a_col.setContentsMargins(0, 0, 0, 0)
        plan_a_col.setSpacing(6)
        self.igpu_dml_chk = QtWidgets.QCheckBox("启用方案 A：核显 DirectML 接管轻量 2-Stem ONNX 分离")
        self.igpu_dml_chk.setChecked(bool(ai_config.igpu_directml_2stem))
        self.igpu_dml_id_spin = QtWidgets.QSpinBox()
        self.igpu_dml_id_spin.setRange(0, 7)
        self.igpu_dml_id_spin.setPrefix("Device ID: ")
        self.igpu_dml_id_spin.setValue(int(ai_config.igpu_directml_device_id))
        self.igpu_dml_id_spin.setEnabled(bool(ai_config.igpu_directml_2stem))
        self.igpu_dml_chk.toggled.connect(self.igpu_dml_id_spin.setEnabled)
        plan_a_sub = QtWidgets.QHBoxLayout()
        plan_a_sub.setSpacing(10)
        plan_a_sub.addWidget(self.igpu_dml_id_spin)
        plan_a_sub.addWidget(
            HelpBadge(
                "方案 A：核显 DirectML + 独显 CUDA 异构分工",
                "• NVIDIA 独显 (cuda:0) 专职重负载 4-Stem HTDemucs 与 MIDI 扒谱。\n"
                "• AMD/Intel 核显通过 onnxruntime-directml (DmlExecutionProvider) 接管轻量 2-Stem MDX-Net ONNX 与准实时人声分离，独显满载或运行游戏时仍可在核显后台完成二轨分离。\n"
                "• 若环境未安装 onnxruntime-directml，会自动安全回退至 CUDA / CPU，不会报错崩溃。",
            )
        )
        plan_a_sub.addStretch(1)
        plan_a_col.addWidget(self.igpu_dml_chk)
        plan_a_col.addLayout(plan_a_sub)
        hybrid_form.addRow("方案 A (异构计算):", plan_a_col)

        plan_b_col = QtWidgets.QVBoxLayout()
        plan_b_col.setContentsMargins(0, 0, 0, 0)
        plan_b_col.setSpacing(6)
        self.gui_offload_chk = QtWidgets.QCheckBox("启用方案 B：GUI 渲染卸载核显 + AI 子进程锁定独显 (CUDA_VISIBLE_DEVICES=0)")
        self.gui_offload_chk.setChecked(bool(ai_config.offload_gui_to_igpu))
        self.open_win_graphics_btn = QtWidgets.QPushButton("Windows 图形设置")
        self.open_win_graphics_btn.setAutoDefault(False)
        self.open_win_graphics_btn.clicked.connect(
            lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl("ms-settings:display-advancedgraphics"))
        )
        plan_b_sub = QtWidgets.QHBoxLayout()
        plan_b_sub.setSpacing(10)
        plan_b_sub.addWidget(self.open_win_graphics_btn)
        plan_b_sub.addWidget(
            HelpBadge(
                "方案 B：图形渲染与 AI 推理物理隔离",
                "• 开启后，后台 AI 子进程将强制绑定 CUDA_VISIBLE_DEVICES=0 (PCI_BUS_ID) 独占 NVIDIA 独显算力。\n"
                "• 点击右侧「Windows 图形设置」可将 ListenScope 主程序设为「节能 (AMD/Intel 核显)」渲染 Qt 界面与 PyQtGraph 波形，彻底杜绝 AI 满载时桌面掉帧。",
            )
        )
        plan_b_sub.addStretch(1)
        plan_b_col.addWidget(self.gui_offload_chk)
        plan_b_col.addLayout(plan_b_sub)
        hybrid_form.addRow("方案 B (渲染隔离):", plan_b_col)
        cfg_outer.addWidget(hybrid_box)

        cfg_outer.addStretch(1)
        self._add_page("resources", cfg_tab, scroll=True)

        # Page 4: Turnkey AI & MIDI Environment + Auto-Bootstrap + Local PyTorch Scanner
        env_tab = QtWidgets.QWidget()
        env_layout = QtWidgets.QVBoxLayout(env_tab)
        env_layout.setContentsMargins(0, 4, 0, 0)
        env_layout.setSpacing(14)

        bootstrap_group = QtWidgets.QGroupBox("TURNKEY BOOTSTRAP // 零配置集成、本机 PyTorch 扫描与一键修复")
        bootstrap_layout = QtWidgets.QVBoxLayout(bootstrap_group)
        bootstrap_layout.setSpacing(6)
        ff_path = find_ffmpeg_executable()
        ff_note = "FFmpeg 已就绪" if ff_path else "FFmpeg 未发现 (WAV 可直接分析)"
        bootstrap_intro = QtWidgets.QLabel(
            f"自动扫描同级 runtime/ai、短路径 m、.venv-ai/.venv-midi 及本机 Conda / 系统 Python 中的 PyTorch（{ff_note}）。"
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

        boot_btns1 = QtWidgets.QHBoxLayout()
        self.scan_pytorch_btn = QtWidgets.QPushButton("扫描本机 PyTorch 环境")
        self.scan_pytorch_btn.setObjectName("analysisAction")
        self.scan_pytorch_btn.setAutoDefault(False)
        self.scan_pytorch_btn.clicked.connect(self._scan_local_pytorch)

        self.setup_all_btn = QtWidgets.QPushButton("一键自动配置 AI + MIDI")
        self.setup_all_btn.setObjectName("analysisAction")
        self.setup_all_btn.setAutoDefault(False)
        self.setup_all_btn.clicked.connect(lambda: self._run_turnkey_bootstrap(skip_ai=False))

        self.setup_midi_only_btn = QtWidgets.QPushButton("仅自动配置 CPU MIDI")
        self.setup_midi_only_btn.setAutoDefault(False)
        self.setup_midi_only_btn.clicked.connect(lambda: self._run_turnkey_bootstrap(skip_ai=True))

        self.cancel_bootstrap_btn = QtWidgets.QPushButton("取消安装")
        self.cancel_bootstrap_btn.setAutoDefault(False)
        self.cancel_bootstrap_btn.setEnabled(False)
        self.cancel_bootstrap_btn.clicked.connect(self._cancel_bootstrap)

        boot_btns1.addWidget(self.scan_pytorch_btn)
        boot_btns1.addWidget(self.setup_all_btn)
        boot_btns1.addWidget(self.setup_midi_only_btn)
        boot_btns1.addWidget(self.cancel_bootstrap_btn)
        boot_btns1.addStretch(1)
        bootstrap_layout.addLayout(boot_btns1)

        boot_btns2 = QtWidgets.QHBoxLayout()
        self.open_pytorch_url_btn = QtWidgets.QPushButton("PyTorch 官方下载页 (pytorch.org)")
        self.open_pytorch_url_btn.setAutoDefault(False)
        self.open_pytorch_url_btn.clicked.connect(lambda: _open_web_url(PYTORCH_OFFICIAL_URL))

        self.open_cu128_url_btn = QtWidgets.QPushButton("CUDA 12.8 Wheel 官方镜像")
        self.open_cu128_url_btn.setAutoDefault(False)
        self.open_cu128_url_btn.clicked.connect(lambda: _open_web_url(PYTORCH_CU128_INDEX_URL))

        self.open_python_url_btn = QtWidgets.QPushButton("Python 3.12 官方下载")
        self.open_python_url_btn.setAutoDefault(False)
        self.open_python_url_btn.clicked.connect(lambda: _open_web_url(PYTHON_WINDOWS_DOWNLOAD_URL))

        boot_btns2.addWidget(self.open_pytorch_url_btn)
        boot_btns2.addWidget(self.open_cu128_url_btn)
        boot_btns2.addWidget(self.open_python_url_btn)
        boot_btns2.addStretch(1)
        bootstrap_layout.addLayout(boot_btns2)

        chk_restart_row = QtWidgets.QHBoxLayout()
        self.auto_install_py_chk = QtWidgets.QCheckBox("缺 Python 3.12/3.11 时自动用 winget 安装")
        self.auto_install_py_chk.setChecked(True)
        self.restart_app_btn = QtWidgets.QPushButton("立即重启 ListenScope 生效")
        self.restart_app_btn.setObjectName("acidPrimaryBtn")
        self.restart_app_btn.setAutoDefault(False)
        self.restart_app_btn.setVisible(False)
        self.restart_app_btn.clicked.connect(self._on_restart_clicked)
        chk_restart_row.addWidget(self.auto_install_py_chk)
        chk_restart_row.addStretch(1)
        chk_restart_row.addWidget(self.restart_app_btn)
        bootstrap_layout.addLayout(chk_restart_row)

        prog_row = QtWidgets.QHBoxLayout()
        prog_row.setSpacing(8)
        self.bootstrap_progress = SegmentedBatteryProgressBar(cells=18)
        self.bootstrap_progress.setRange(0, 100)
        self.bootstrap_progress.setValue(0)
        self.bootstrap_progress.setFixedHeight(22)
        self.bootstrap_progress.setMinimumWidth(220)
        self.bootstrap_meta_lbl = QtWidgets.QLabel("待命：支持多源下载，低速或断流时自动切换高速镜像")
        self.bootstrap_meta_lbl.setObjectName("mutedCaption")
        self.bootstrap_meta_lbl.setWordWrap(True)
        prog_row.addWidget(self.bootstrap_progress)
        prog_row.addWidget(self.bootstrap_meta_lbl, 1)
        bootstrap_layout.addLayout(prog_row)

        self.bootstrap_status_lbl = QtWidgets.QLabel(
            "准备就绪：点击「扫描本机 PyTorch 环境」自动查找电脑已安装的 PyTorch；若未安装可点击「一键自动配置 AI + MIDI」在同级目录自动配置（切换页面不会中断）。"
        )
        self.bootstrap_status_lbl.setWordWrap(True)
        self.bootstrap_status_lbl.setObjectName("bannerNotice")
        self.bootstrap_status_lbl.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        set_widget_tone(self.bootstrap_status_lbl, "info")
        bootstrap_layout.addWidget(self.bootstrap_status_lbl)

        self.bootstrap_log_view = QtWidgets.QPlainTextEdit()
        self.bootstrap_log_view.setObjectName("diagnosticLogStream")
        self.bootstrap_log_view.setReadOnly(True)
        self.bootstrap_log_view.setMaximumBlockCount(150)
        self.bootstrap_log_view.setFixedHeight(104)
        self.bootstrap_log_view.setPlaceholderText("一键环境初始化进度与镜像切换日志将显示在这里...")
        bootstrap_layout.addWidget(self.bootstrap_log_view)
        env_layout.addWidget(bootstrap_group)

        py_row = QtWidgets.QVBoxLayout()
        self.ai_python_edit = QtWidgets.QLineEdit(ai_python_executable)
        self.ai_python_edit.setAccessibleName("AI Worker Python")
        self.ai_python_edit.setPlaceholderText("自动识别 runtime\\ai 或 .venv-ai\\Scripts\\python.exe（也可扫描本机或手动指定）")
        self.browse_ai_py_btn = QtWidgets.QPushButton("浏览...")
        self.browse_ai_py_btn.clicked.connect(self._browse_ai_python)
        self.verify_ai_env_btn = QtWidgets.QPushButton("验证 AI 环境")
        self.verify_ai_env_btn.clicked.connect(self._verify_ai_environment)
        py_row.addWidget(self.ai_python_edit)
        py_row.addLayout(self._environment_actions(self.browse_ai_py_btn, self.verify_ai_env_btn))

        self.ai_probe_result_lbl = QtWidgets.QLabel(
            f"验证 CUDA、ONNX、Demucs 和 FFmpeg。若本机未安装 PyTorch，请访问 {PYTORCH_OFFICIAL_URL} 下载。"
        )
        self.ai_probe_result_lbl.setWordWrap(True)
        self.ai_probe_result_lbl.setObjectName("bannerNotice")
        self.ai_probe_result_lbl.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
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
        self.midi_probe_result_lbl.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        set_widget_tone(self.midi_probe_result_lbl, "info")

        for gtitle, glabel, htitle, hbody, controls, feedback in (
            (
                "AI WORKER // 分轨运行环境 (PyTorch CUDA + ONNX)",
                "AI Worker Python",
                "独立 AI 分轨环境说明",
                "为什么独立隔离？将数 GB 的 PyTorch CUDA 放在独立子进程环境中，平时不启动 AI 分轨时主程序内存极低、零显存占用；分轨结束后子进程退出即可 100% 释放显存。",
                py_row,
                self.ai_probe_result_lbl,
            ),
            (
                "MIDI WORKER // 转录运行环境 (Python 3.11 Basic Pitch CPU)",
                "MIDI Python 3.11",
                "独立 CPU MIDI 环境说明",
                "Spotify Basic Pitch 依赖 TensorFlow 2.15（仅支持 Python 3.11），隔离在独立 CPU 环境中既避免与 PyTorch CUDA 冲突，也不会争抢 8GB 显卡显存。",
                midi_py_row,
                self.midi_probe_result_lbl,
            ),
        ):
            group = QtWidgets.QGroupBox(gtitle)
            section = QtWidgets.QFormLayout(group)
            section.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
            section.setHorizontalSpacing(14)
            section.setVerticalSpacing(10)
            section.addRow(wrap_with_help(QtWidgets.QLabel(glabel), htitle, hbody)[0])
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
        install_focus_animations(self)
        self.apply_skin(appearance, acid_variant=self._acid_variant or "", _translate=False)
        self._sync_bootstrap_ui(self._bootstrap_mgr.snapshot())
        self.open_category("appearance")

    @staticmethod
    def _icon_color(appearance: Appearance, acid_variant: Optional[str]) -> str:
        if acid_variant == "light":
            return get_acid_palette("light").accent_strong
        if acid_variant == "dark":
            return get_acid_palette("dark").accent
        _, _, accent = appearance.effective_colors(system_is_dark=detect_system_is_dark())
        return accent

    def apply_skin(
        self,
        appearance: Appearance,
        *,
        acid_variant: Optional[str] = None,
        _translate: bool = True,
    ) -> None:
        self._appearance = appearance
        self._updated_appearance = appearance
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
        if hasattr(self, "bootstrap_progress"):
            if self._acid_variant in ("light", "dark"):
                p = get_acid_palette(self._acid_variant)
                self.bootstrap_progress.set_theme_colors(
                    accent=p.accent,
                    accent_hi=p.accent_secondary,
                    shell_bg=p.bg_code,
                    shell_border=p.border_strong,
                    empty_cell=p.bg_elevated,
                    text_fg=p.text_primary,
                    is_acid=True,
                )
            else:
                mode = appearance.resolve_theme_mode(system_is_dark=detect_system_is_dark())
                bg, fg, accent = appearance.effective_colors(system_is_dark=detect_system_is_dark())
                is_l = mode == "light"
                self.bootstrap_progress.set_theme_colors(
                    accent=accent,
                    accent_hi=QtGui.QColor(accent).lighter(135).name(),
                    shell_bg=bg,
                    shell_border="#CBD5E1" if is_l else "#475569",
                    empty_cell="#E2E8F0" if is_l else "#1E293B",
                    text_fg=fg,
                    is_acid=False,
                )
        if hasattr(self, "_chrome"):
            if self._acid_variant in ("light", "dark"):
                p = get_acid_palette(self._acid_variant)
                self._chrome.sync_colors(p.text_secondary, "#FFFFFF")
            else:
                _, fg, _ = appearance.effective_colors(system_is_dark=detect_system_is_dark())
                self._chrome.sync_colors(fg, "#FFFFFF")
            self._chrome.apply_frameless(bool(appearance.frameless))
        if self.parent() is None:
            if self._acid_variant in ("light", "dark"):
                self.setStyleSheet(acid_stylesheet(appearance, self._acid_variant))
            else:
                self.setStyleSheet("")
        if hasattr(self, "_theme_summary"):
            self.update_appearance_summary(appearance, _translate=_translate)
        if _translate:
            translate_widget_tree(self, appearance.language)

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

    def update_appearance_summary(self, appearance: Appearance, *, _translate: bool = True) -> None:
        self._appearance = appearance
        self._updated_appearance = appearance
        mode_lbl = THEME_MODES.get(appearance.theme_mode, "白天")
        lang_lbl = LANGUAGES.get(appearance.language, "简体中文")
        self._theme_summary.setText(f"{PRESETS[appearance.preset][0]} · {mode_lbl} · {lang_lbl}")
        self._layout_summary.setText(LAYOUTS[appearance.layout][0])
        font_label = "工业标准字体 (已锁定)" if appearance.is_acid_locked() else (appearance.font_family or "系统默认")
        self._font_summary.setText(f"{font_label} · {appearance.font_size} px")
        sync_widgets = [
            getattr(self, name, None)
            for name in (
                "language_combo",
                "frameless_chk",
                "help_mode_chk",
                "focus_anim_chk",
                "focus_style_combo",
                "surface_style_combo",
                "close_to_tray_chk",
                "telemetry_strength_slider",
                "music_reactive_chk",
            )
        ]
        blockers = [QtCore.QSignalBlocker(w) for w in sync_widgets if w is not None]
        if hasattr(self, "language_combo"):
            idx = self.language_combo.findData(appearance.language)
            if idx >= 0:
                self.language_combo.setCurrentIndex(idx)
        if hasattr(self, "frameless_chk"):
            self.frameless_chk.setChecked(bool(appearance.frameless))
        if hasattr(self, "help_mode_chk"):
            self.help_mode_chk.setChecked(bool(appearance.help_mode))
        if hasattr(self, "focus_anim_chk"):
            self.focus_anim_chk.setChecked(bool(appearance.focus_animations))
        if hasattr(self, "focus_style_combo"):
            fidx = self.focus_style_combo.findData(appearance.focus_style)
            if fidx >= 0:
                self.focus_style_combo.setCurrentIndex(fidx)
            self.focus_style_combo.setEnabled(bool(appearance.focus_animations))
        if hasattr(self, "surface_style_combo"):
            sidx = self.surface_style_combo.findData(appearance.ui_surface_style)
            if sidx >= 0:
                self.surface_style_combo.setCurrentIndex(sidx)
        if hasattr(self, "close_to_tray_chk"):
            self.close_to_tray_chk.setChecked(bool(appearance.close_to_tray))
        if hasattr(self, "telemetry_strength_slider"):
            self.telemetry_strength_slider.setValue(int(appearance.telemetry_animation_strength))
        if hasattr(self, "telemetry_strength_lbl"):
            self.telemetry_strength_lbl.setText(f"{int(appearance.telemetry_animation_strength)}%")
        if hasattr(self, "music_reactive_chk"):
            self.music_reactive_chk.setChecked(bool(appearance.music_reactive_animations))
            self.music_reactive_chk.setEnabled(int(appearance.telemetry_animation_strength) > 0)
        del blockers
        if _translate:
            translate_widget_tree(self, appearance.language)

    def _on_quick_appearance_changed(self, *_args) -> None:
        lang = str(self.language_combo.currentData() or "zh")
        frameless = bool(self.frameless_chk.isChecked())
        help_mode = bool(self.help_mode_chk.isChecked()) if hasattr(self, "help_mode_chk") else True
        focus_anim = bool(self.focus_anim_chk.isChecked()) if hasattr(self, "focus_anim_chk") else True
        focus_style = (
            str(self.focus_style_combo.currentData() or "sleek")
            if hasattr(self, "focus_style_combo")
            else self._appearance.focus_style
        )
        surface_style = (
            str(self.surface_style_combo.currentData() or "tactile")
            if hasattr(self, "surface_style_combo")
            else self._appearance.ui_surface_style
        )
        close_to_tray = (
            bool(self.close_to_tray_chk.isChecked())
            if hasattr(self, "close_to_tray_chk")
            else self._appearance.close_to_tray
        )
        telem_strength = (
            int(self.telemetry_strength_slider.value())
            if hasattr(self, "telemetry_strength_slider")
            else self._appearance.telemetry_animation_strength
        )
        music_reactive = (
            bool(self.music_reactive_chk.isChecked())
            if hasattr(self, "music_reactive_chk")
            else self._appearance.music_reactive_animations
        )
        set_focus_ring_style(focus_style)
        updated = replace(
            self._appearance,
            language=lang,
            frameless=frameless,
            help_mode=help_mode,
            focus_animations=focus_anim,
            focus_style=focus_style,
            ui_surface_style=surface_style,
            close_to_tray=close_to_tray,
            telemetry_animation_strength=telem_strength,
            music_reactive_animations=music_reactive,
        )
        self.update_appearance_summary(updated)
        if hasattr(self, "_chrome"):
            self._chrome.apply_frameless(frameless)
        self.appearance_changed.emit(updated)

    def _copy_github_url(self) -> None:
        cb = QtWidgets.QApplication.clipboard()
        if cb is not None:
            cb.setText(GITHUB_REPO_URL)
        self.copy_repo_url_btn.setText("已复制项目链接 ✓")

    def open_category(self, key: str) -> None:
        self._active_category = key
        self._category_buttons[key].setChecked(True)
        self._pages.setCurrentWidget(self._page_map[key])
        title, subtitle = SETTINGS_CATEGORIES[key]
        self._page_eyebrow.setText(SETTINGS_EYEBROWS.get(key, "CONFIG // TELEMETRY"))
        self._title.setProperty("_ls_orig_text", title)
        self._title.setText(title)
        self._subtitle.setProperty("_ls_orig_text", subtitle)
        self._subtitle.setText(subtitle)
        translate_widget_tree(self, self._appearance.language)

    def focus_midi(self) -> None:
        self.open_category("midi")
        self._page_map["midi"].ensureWidgetVisible(self.midi_python_edit)
        self.midi_python_edit.setFocus()

    def _disconnect_bootstrap_signals(self) -> None:
        if not getattr(self, "_bootstrap_signals_connected", False):
            return
        self._bootstrap_signals_connected = False
        mgr = getattr(self, "_bootstrap_mgr", None)
        if mgr is None:
            return
        for sig, slot in (
            (mgr.state_changed, self._on_bootstrap_state_changed),
            (mgr.completed, self._on_bootstrap_finished),
        ):
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._dialog_closed = True
        self._disconnect_bootstrap_signals()
        if hasattr(self, "_chrome"):
            self._chrome.teardown()
        super().closeEvent(event)

    def done(self, result: int) -> None:  # type: ignore[override]
        self._dialog_closed = True
        self._disconnect_bootstrap_signals()
        if hasattr(self, "_chrome"):
            self._chrome.teardown()
        super().done(result)

    def _refresh_status_alert(self, r: SystemHardwareReport) -> None:
        if not r.gpu_ai_ready or not r.is_windows:
            parts: list[str] = []
            if not r.is_windows:
                parts.append(
                    f"[WARN] 当前在 {r.os_system} 运行：WASAPI Process Loopback 与 RTX 5060 Ti CUDA 未在 Windows 真机验证。"
                )
            if not r.gpu_ai_ready:
                reason = r.gpu_ai_block_reason or "尚未检测到可用的 PyTorch GPU 环境"
                parts.append(
                    f"[WARN] GPU AI 暂未就绪：{reason}。请点击下方按钮前往「AI 与 MIDI 环境」页扫描本机 PyTorch 或一键自动配置。"
                )
            self.status_alert_lbl.setText("\n".join(parts))
            set_widget_tone(self.status_alert_lbl, "warn")
            self.status_alert_lbl.setVisible(True)
        else:
            self.status_alert_lbl.setVisible(False)
            self.status_alert_lbl.setText("")
        if hasattr(self, "status_goto_env_btn"):
            self.status_goto_env_btn.setVisible(not r.gpu_ai_ready)

    def _scan_local_pytorch(self) -> None:
        self.scan_pytorch_btn.setEnabled(False)
        set_widget_tone(self.bootstrap_status_lbl, "info")
        self.bootstrap_status_lbl.setText("[BUSY] 正在扫描本机所有 Python / Conda / 虚拟环境中的 PyTorch 安装情况...")

        def _worker() -> None:
            found = scan_local_pytorch_installations((get_app_root(), get_bundle_root()))
            if not self._dialog_closed:
                try:
                    self._pytorch_scan_finished.emit(found)
                except RuntimeError:
                    pass

        threading.Thread(target=_worker, name="ListenScope-ScanPyTorch", daemon=True).start()

    @QtCore.Slot(object)
    def _on_pytorch_scan_finished(self, results: Any) -> None:
        if self._dialog_closed:
            return
        self.scan_pytorch_btn.setEnabled(True)
        found_list = results if isinstance(results, list) else []
        if not found_list:
            set_widget_tone(self.bootstrap_status_lbl, "warn")
            self.bootstrap_status_lbl.setText(f"[WARN] {PYTORCH_DOWNLOAD_GUIDE}")
            set_widget_tone(self.ai_probe_result_lbl, "warn")
            self.ai_probe_result_lbl.setText(f"[WARN] {PYTORCH_DOWNLOAD_GUIDE}")
            return

        best = found_list[0]
        best_exe = str(best.get("python_executable", "")).strip()
        if best_exe:
            self.ai_python_edit.setText(best_exe)
        summary_lines = [f"[OK] 在本机扫描到 {len(found_list)} 个包含 PyTorch 的 Python 环境（已自动填入最优路径）："]
        for item in found_list[:4]:
            ver = item.get("torch_version", "unknown")
            cuda_ok = "CUDA 可用" if item.get("cuda_available") else "仅 CPU"
            sm120 = ", 支持 sm_120" if item.get("supports_sm_120") else ""
            summary_lines.append(f"• {item.get('python_executable')} -> PyTorch {ver} ({cuda_ok}{sm120})")
        if not best.get("cuda_available"):
            summary_lines.append(
                f"提示：当前扫描到的 PyTorch 不含 CUDA 加速，建议前往 {PYTORCH_OFFICIAL_URL} 或使用 {PYTORCH_CU128_INDEX_URL} 安装 CUDA 12.8 版本。"
            )
        set_widget_tone(self.bootstrap_status_lbl, "ok" if best.get("cuda_available") else "warn")
        self.bootstrap_status_lbl.setText("\n".join(summary_lines))
        if best_exe:
            self._verify_ai_environment()

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
        self._bootstrap_target_root: Optional[Path] = target_root
        ai_venv = target_root / ("runtime\\ai" if getattr(sys, "frozen", False) else ".venv-ai")
        midi_venv = target_root / ("m" if getattr(sys, "frozen", False) else ".venv-midi")
        wheel_dir = self.setup_wheel_dir_edit.text().strip()

        cmd = [
            pwsh_exe,
            "-NoProfile",
            "-NonInteractive",
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
        if hasattr(self, "auto_install_py_chk") and self.auto_install_py_chk.isChecked():
            cmd.append("-AutoInstallPython")
        if wheel_dir:
            cmd.extend(["-CudaWheelDir", wheel_dir])

        proc_env = os.environ.copy()
        proc_env["PYTHONUTF8"] = "1"
        proc_env["PYTHONIOENCODING"] = "utf-8"
        proc_env["NO_COLOR"] = "1"
        proc_env["TERM"] = "dumb"
        proc_env["DOTNET_SYSTEM_CONSOLE_ALLOW_ANSI_COLOR_REDIRECTION"] = "0"

        self._bootstrap_mgr.start(
            cmd=cmd,
            cwd=str(get_bundle_root()),
            env=proc_env,
            target_root=target_root,
            popen_factory=lambda *args, **kwargs: subprocess.Popen(*args, **kwargs),
        )

    def _cancel_bootstrap(self) -> None:
        self._bootstrap_mgr.cancel()
        if hasattr(self, "cancel_bootstrap_btn"):
            self.cancel_bootstrap_btn.setEnabled(False)

    def _on_restart_clicked(self) -> None:
        self.restart_requested.emit()
        self.accept()

    def _sync_bootstrap_ui(self, snap: dict[str, Any]) -> None:
        if self._dialog_closed:
            return
        running = bool(snap.get("running", False))
        self._bootstrap_running = running
        self.setup_all_btn.setEnabled(not running)
        self.setup_midi_only_btn.setEnabled(not running)
        if hasattr(self, "auto_install_py_chk"):
            self.auto_install_py_chk.setEnabled(not running)
        if hasattr(self, "cancel_bootstrap_btn"):
            self.cancel_bootstrap_btn.setEnabled(running)
        if hasattr(self, "bootstrap_progress"):
            self.bootstrap_progress.set_active(running)
            self.bootstrap_progress.setValue(int(snap.get("progress_pct", 0)))
        if hasattr(self, "bootstrap_meta_lbl"):
            stage = str(snap.get("stage", "") or "").strip()
            speed = str(snap.get("speed", "") or "").strip()
            mirror = str(snap.get("mirror", "") or "").strip()
            parts = [p for p in (stage, speed, f"源: {mirror}" if mirror else "") if p]
            set_i18n_text(
                self.bootstrap_meta_lbl,
                " | ".join(parts) if parts else "待命：支持多源下载，低速或断流时自动切换高速镜像",
            )
        tone = str(snap.get("tone", "info") or "info")
        set_widget_tone(self.bootstrap_status_lbl, tone)
        status_text = str(snap.get("status_text", "") or "")
        if status_text:
            self.bootstrap_status_lbl.setText(status_text)
        if hasattr(self, "bootstrap_log_view"):
            logs = snap.get("log_lines") or []
            joined = "\n".join(str(x) for x in logs[-120:])
            if joined != self.bootstrap_log_view.toPlainText():
                self.bootstrap_log_view.setPlainText(joined)
                bar = self.bootstrap_log_view.verticalScrollBar()
                if bar is not None:
                    bar.setValue(bar.maximum())
        if hasattr(self, "restart_app_btn"):
            self.restart_app_btn.setVisible(bool(snap.get("needs_restart_hint", False)) and not running)

    @QtCore.Slot(object)
    def _on_bootstrap_state_changed(self, snap: object) -> None:
        if self._dialog_closed or not isinstance(snap, dict):
            return
        self._sync_bootstrap_ui(snap)

    @QtCore.Slot(bool, str, str, str)
    def _on_bootstrap_finished(self, ok: bool, message: str, ai_py: str, midi_py: str) -> None:
        if self._dialog_closed:
            return
        self._sync_bootstrap_ui(self._bootstrap_mgr.snapshot())
        set_widget_tone(self.bootstrap_status_lbl, "ok" if ok else "error")
        self.bootstrap_status_lbl.setText(message)
        if ok:
            if not ai_py and not midi_py:
                disc_ai, disc_midi = _discover_installed_runtime_pythons(get_app_root())
                fallback_root = getattr(self, "_bootstrap_target_root", None)
                if fallback_root is not None and fallback_root != get_app_root():
                    fb_ai, fb_midi = _discover_installed_runtime_pythons(fallback_root)
                    disc_ai = disc_ai or fb_ai
                    disc_midi = disc_midi or fb_midi
                ai_py = ai_py or disc_ai
                midi_py = midi_py or disc_midi
            cur_ai = self.ai_python_edit.text().strip()
            if ai_py and (not cur_ai or not Path(cur_ai).exists()):
                self.ai_python_edit.setText(ai_py)
                cur_ai = ai_py
            cur_midi = self.midi_python_edit.text().strip()
            if midi_py and (not cur_midi or not Path(cur_midi).exists() or midi_py != cur_midi):
                self.midi_python_edit.setText(midi_py)
                cur_midi = midi_py
            if cur_ai or cur_midi:
                self.bootstrap_runtimes_ready.emit(cur_ai, cur_midi)
            if cur_ai:
                self._verify_ai_environment()
            if cur_midi:
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
            self.ai_probe_result_lbl.setText(f"[ERR] 检测失败: {err}\n{PYTORCH_DOWNLOAD_GUIDE}")
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
            f"PyTorch: {pt.get('version') or '未安装'} (CUDA={pt.get('cuda_available')}, sm_120={pt.get('supports_sm_120')}) | "
            f"ONNX CUDA: {ort.get('cuda_provider_available')}\n"
            f"AI 包: {pkg_summary} | FFmpeg: {ff_txt}\n"
            f"GPU AI 准入: {'READY' if gpu_ready else f'BLOCKED ({block_reason})'}"
        )
        if not pt.get("installed"):
            summary += f"\n\n{PYTORCH_DOWNLOAD_GUIDE}"
        self.ai_probe_result_lbl.setText(summary)
        set_widget_tone(self.ai_probe_result_lbl, "ok" if gpu_ready else "warn")
        if hasattr(self, "bootstrap_status_lbl") and "正在刷新验证环境" in self.bootstrap_status_lbl.text():
            if gpu_ready:
                set_widget_tone(self.bootstrap_status_lbl, "ok")
                self.bootstrap_status_lbl.setText(
                    "[OK] 环境配置与验证全部完成（GPU AI 已就绪），点下方「保存设置」即可立即开始分轨！"
                )
            elif hasattr(self, "restart_app_btn"):
                self.restart_app_btn.setVisible(True)

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
            (
                "PyTorch",
                f"{r.pytorch.version} (CUDA build={r.pytorch.cuda_build})"
                if r.pytorch.installed
                else f"未检测到 (可点击「扫描本机 PyTorch」或前往 {PYTORCH_OFFICIAL_URL} 下载)",
            ),
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
                igpu_directml_2stem=bool(self.igpu_dml_chk.isChecked()),
                igpu_directml_device_id=int(self.igpu_dml_id_spin.value()),
                offload_gui_to_igpu=bool(self.gui_offload_chk.isChecked()),
            )
            entered_py = self.ai_python_edit.text().strip()
            self._updated_ai_python = entered_py
            self._updated_midi_python = self.midi_python_edit.text().strip()
            self._updated_appearance = replace(
                self._appearance,
                language=str(self.language_combo.currentData() or "zh"),
                frameless=bool(self.frameless_chk.isChecked()),
                help_mode=bool(self.help_mode_chk.isChecked()),
                focus_animations=bool(self.focus_anim_chk.isChecked()),
                focus_style=(
                    str(self.focus_style_combo.currentData() or "sleek")
                    if hasattr(self, "focus_style_combo")
                    else self._appearance.focus_style
                ),
                ui_surface_style=(
                    str(self.surface_style_combo.currentData() or "tactile")
                    if hasattr(self, "surface_style_combo")
                    else self._appearance.ui_surface_style
                ),
                close_to_tray=(
                    bool(self.close_to_tray_chk.isChecked())
                    if hasattr(self, "close_to_tray_chk")
                    else self._appearance.close_to_tray
                ),
                telemetry_animation_strength=(
                    int(self.telemetry_strength_slider.value())
                    if hasattr(self, "telemetry_strength_slider")
                    else self._appearance.telemetry_animation_strength
                ),
                music_reactive_animations=(
                    bool(self.music_reactive_chk.isChecked())
                    if hasattr(self, "music_reactive_chk")
                    else self._appearance.music_reactive_animations
                ),
            )
            if hasattr(self, "close_behavior_combo"):
                cb_val = str(self.close_behavior_combo.currentData() or "ask").strip().lower()
                self._updated_close_behavior = cb_val if cb_val in ("ask", "tray", "quit") else "ask"
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
    def updated_appearance(self) -> Appearance:
        return self._updated_appearance

    @property
    def updated_close_behavior(self) -> str:
        return self._updated_close_behavior

    @property
    def verified_ai_probe(self) -> Optional[dict[str, Any]]:
        return self._verified_ai_probe

    @property
    def verified_report(self) -> SystemHardwareReport:
        return self._report

