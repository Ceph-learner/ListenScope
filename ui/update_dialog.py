"""Update available prompt and download/verify progress dialog (Issue #37 R2-2 / R2-3)."""

from __future__ import annotations

import logging
from pathlib import Path
import threading
from typing import Literal, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from core.i18n import get_current_language, set_i18n_text, translate_text, translate_widget_tree
from core.updater import (
    ReleaseInfo,
    UpdateChecksumError,
    UpdateDownloadCancelled,
    detect_install_kind,
    download_and_verify_update,
)

logger = logging.getLogger(__name__)


class UpdateAvailableDialog(QtWidgets.QDialog):
    """Displays new release info, Markdown changelog, and resumable/cancellable download progress."""

    _progress_signal = QtCore.Signal(int, int)
    _finished_signal = QtCore.Signal(str)
    _failed_signal = QtCore.Signal(str)
    _cancelled_signal = QtCore.Signal()

    def __init__(
        self,
        release: ReleaseInfo,
        *,
        current_version: str,
        dest_dir: Path,
        mirror_prefix: str = "",
        install_kind: Optional[Literal["installer", "portable"]] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.release = release
        self.current_version = current_version
        self.dest_dir = Path(dest_dir)
        self.mirror_prefix = mirror_prefix
        self.install_kind: Literal["installer", "portable"] = (
            install_kind if install_kind in ("installer", "portable") else detect_install_kind()
        )
        self.user_action: Literal["later", "skip", "downloaded"] = "later"
        self.downloaded_path: Optional[Path] = None
        self._cancel_event: Optional[threading.Event] = None
        self._download_thread: Optional[threading.Thread] = None

        self.setWindowTitle("发现新版本")
        self.setMinimumSize(520, 380)
        self.resize(580, 440)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        self.header_lbl = QtWidgets.QLabel(f"发现新版本 {release.tag_name}")
        font = self.header_lbl.font()
        font.setPointSize(max(11, font.pointSize() + 2))
        font.setBold(True)
        self.header_lbl.setFont(font)
        root.addWidget(self.header_lbl)

        pub_date = release.published_at[:10] if release.published_at else "-"
        self.meta_lbl = QtWidgets.QLabel(
            f"当前版本: {current_version}  |  最新版本: {release.version}  |  发布日期: {pub_date}"
        )
        self.meta_lbl.setWordWrap(True)
        root.addWidget(self.meta_lbl)

        self.notes_view = QtWidgets.QTextBrowser()
        self.notes_view.setOpenExternalLinks(True)
        notes_md = release.body.strip() or "暂无更新说明。"
        self.notes_view.setMarkdown(notes_md)
        root.addWidget(self.notes_view, 1)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        self.status_lbl = QtWidgets.QLabel("")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setVisible(False)
        root.addWidget(self.status_lbl)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        self.skip_btn = QtWidgets.QPushButton("跳过此版本")
        self.skip_btn.clicked.connect(self._on_skip)
        btn_row.addWidget(self.skip_btn)

        btn_row.addStretch(1)

        self.later_btn = QtWidgets.QPushButton("稍后")
        self.later_btn.clicked.connect(self._on_later)
        btn_row.addWidget(self.later_btn)

        self.cancel_dl_btn = QtWidgets.QPushButton("取消下载")
        self.cancel_dl_btn.setVisible(False)
        self.cancel_dl_btn.clicked.connect(self._on_cancel_download)
        btn_row.addWidget(self.cancel_dl_btn)

        self.update_btn = QtWidgets.QPushButton("立即更新")
        self.update_btn.setObjectName("acidPrimaryBtn")
        self.update_btn.clicked.connect(self._on_start_download)
        btn_row.addWidget(self.update_btn)

        root.addLayout(btn_row)

        self._progress_signal.connect(self._on_progress)
        self._finished_signal.connect(self._on_download_finished)
        self._failed_signal.connect(self._on_download_failed)
        self._cancelled_signal.connect(self._on_download_cancelled)

        translate_widget_tree(self, get_current_language())

    def _on_skip(self) -> None:
        self.user_action = "skip"
        self.accept()

    def _on_later(self) -> None:
        self.user_action = "later"
        self.reject()

    def _on_cancel_download(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
        self.cancel_dl_btn.setEnabled(False)

    def _on_start_download(self) -> None:
        if self._download_thread is not None and self._download_thread.is_alive():
            return
        self._cancel_event = threading.Event()
        self.update_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        self.later_btn.setVisible(False)
        self.cancel_dl_btn.setVisible(True)
        self.cancel_dl_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_lbl.setVisible(True)
        set_i18n_text(self.status_lbl, "正在下载并校验更新包…")

        cancel_ev = self._cancel_event

        def _worker() -> None:
            try:
                path = download_and_verify_update(
                    self.release,
                    dest_dir=self.dest_dir,
                    install_kind=self.install_kind,
                    current_version=self.current_version,
                    mirror_prefix=self.mirror_prefix,
                    progress_cb=lambda cur, tot: self._progress_signal.emit(int(cur), int(tot)),
                    cancel_event=cancel_ev,
                )
                self._finished_signal.emit(str(path))
            except UpdateDownloadCancelled:
                self._cancelled_signal.emit()
            except UpdateChecksumError as exc:
                logger.warning("Update checksum verification failed: %s", exc)
                self._failed_signal.emit(f"更新包 SHA256 校验失败，已删除损坏文件: {exc}")
            except Exception as exc:
                logger.warning("Update download failed: %s", exc)
                self._failed_signal.emit(f"更新下载失败: {exc}")

        self._download_thread = threading.Thread(target=_worker, name="ListenScope-UpdateDownload", daemon=True)
        self._download_thread.start()

    @QtCore.Slot(int, int)
    def _on_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            pct = max(0, min(100, int(downloaded * 100 / total)))
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(pct)
            mb_cur = downloaded / (1024.0 * 1024.0)
            mb_tot = total / (1024.0 * 1024.0)
            set_i18n_text(self.status_lbl, f"正在下载更新包: {mb_cur:.1f} / {mb_tot:.1f} MB ({pct}%)")
        else:
            self.progress_bar.setRange(0, 0)

    @QtCore.Slot(str)
    def _on_download_finished(self, file_path: str) -> None:
        self.downloaded_path = Path(file_path)
        self.user_action = "downloaded"
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.cancel_dl_btn.setVisible(False)
        self.later_btn.setVisible(True)
        set_i18n_text(self.later_btn, "关闭")
        self.update_btn.setVisible(False)
        self.skip_btn.setVisible(False)
        set_i18n_text(self.status_lbl, f"下载完成并通过 SHA256 校验，已保存至: {file_path}")

    @QtCore.Slot(str)
    def _on_download_failed(self, msg: str) -> None:
        self.cancel_dl_btn.setVisible(False)
        self.later_btn.setVisible(True)
        self.update_btn.setEnabled(True)
        self.skip_btn.setEnabled(True)
        set_i18n_text(self.status_lbl, msg)

    @QtCore.Slot()
    def _on_download_cancelled(self) -> None:
        self.cancel_dl_btn.setVisible(False)
        self.later_btn.setVisible(True)
        self.update_btn.setEnabled(True)
        self.skip_btn.setEnabled(True)
        set_i18n_text(self.status_lbl, "已取消下载（支持下次断点续传）。")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        if self._cancel_event is not None:
            self._cancel_event.set()
        super().closeEvent(event)
