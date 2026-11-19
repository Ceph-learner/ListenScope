"""Bounded diagnostic logging and local AI performance logging under logs/performance/."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import threading
from typing import Any, Optional

from .models import AIJobRequest, AIJobResult
from .paths import default_work_dir

_FILE_HANDLER_LOCK = threading.Lock()
_ACTIVE_FILE_HANDLER: Optional[RotatingFileHandler] = None
_ACTIVE_LOG_DIR: Optional[Path] = None
_PREV_QT_MSG_HANDLER: Any = None
_QT_HANDLER_INSTALLED = False


def _qt_msg_handler(mode: Any, _ctx: Any, message: Any) -> None:
    """Module-level Qt message forwarder so C++ Qt hooks never depend on a local closure."""
    try:
        from PySide6 import QtCore

        msg_txt = str(message or "").strip()
        if not msg_txt:
            return
        qt_logger = logging.getLogger("listenscope.qt")
        if mode == QtCore.QtMsgType.QtCriticalMsg or mode == QtCore.QtMsgType.QtFatalMsg:
            qt_logger.error("%s", msg_txt)
        elif mode == QtCore.QtMsgType.QtWarningMsg:
            qt_logger.warning("%s", msg_txt)
    except Exception:
        pass


def resolve_log_dir(work_dir: Optional[Path | str] = None) -> Path:
    """Return bounded log directory (`work_dir/logs` or sibling `logs` avoiding `C:` when app root writable)."""
    base = Path(work_dir) if work_dir is not None else default_work_dir()
    if work_dir is None or base == Path("workspace_outputs"):
        return base.parent / "logs" if base.name == "workspace_outputs" else base / "logs"
    return base / "logs"


def active_log_dir() -> Path:
    if _ACTIVE_LOG_DIR is not None:
        return _ACTIVE_LOG_DIR
    return resolve_log_dir()


def setup_application_file_logging(log_dir: Optional[Path | str] = None) -> Path:
    """Install bounded UTF-8 rotating file logging (3MB x 4) and exception/Qt warning capture."""
    global _ACTIVE_FILE_HANDLER, _ACTIVE_LOG_DIR, _PREV_QT_MSG_HANDLER, _QT_HANDLER_INSTALLED
    target_dir = Path(log_dir) if log_dir is not None else resolve_log_dir()
    with _FILE_HANDLER_LOCK:
        target_dir.mkdir(parents=True, exist_ok=True)
        _ACTIVE_LOG_DIR = target_dir
        log_file = target_dir / "listenscope.log"
        root_logger = logging.getLogger()

        if _ACTIVE_FILE_HANDLER is not None:
            try:
                existing_base = Path(_ACTIVE_FILE_HANDLER.baseFilename).resolve()
            except Exception:
                existing_base = None
            if existing_base == log_file.resolve():
                return log_file
            try:
                root_logger.removeHandler(_ACTIVE_FILE_HANDLER)
                _ACTIVE_FILE_HANDLER.close()
            except Exception:
                pass
            _ACTIVE_FILE_HANDLER = None

        handler = RotatingFileHandler(
            log_file,
            maxBytes=3 * 1024 * 1024,
            backupCount=4,
            encoding="utf-8",
            delay=True,
        )
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] [%(threadName)s] %(name)s: %(message)s")
        )
        root_logger.addHandler(handler)
        if root_logger.level > logging.INFO:
            root_logger.setLevel(logging.INFO)
        _ACTIVE_FILE_HANDLER = handler

        # Capture unhandled main-thread / worker-thread exceptions cleanly into logs
        app_logger = logging.getLogger("listenscope.runtime")
        orig_excepthook = getattr(sys, "_ls_orig_excepthook", sys.excepthook)
        if not hasattr(sys, "_ls_orig_excepthook"):
            setattr(sys, "_ls_orig_excepthook", orig_excepthook)

        def _ls_excepthook(exc_type, exc_value, exc_tb) -> None:
            app_logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
            orig_excepthook(exc_type, exc_value, exc_tb)

        sys.excepthook = _ls_excepthook

        if hasattr(threading, "excepthook"):
            orig_thread_hook = getattr(threading, "_ls_orig_excepthook", threading.excepthook)
            if not hasattr(threading, "_ls_orig_excepthook"):
                setattr(threading, "_ls_orig_excepthook", orig_thread_hook)

            def _ls_thread_hook(args) -> None:
                app_logger.error(
                    "Unhandled thread exception in %s",
                    getattr(args, "thread", None),
                    exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
                )
                orig_thread_hook(args)

            threading.excepthook = _ls_thread_hook

        if not _QT_HANDLER_INSTALLED:
            try:
                from PySide6 import QtCore

                _PREV_QT_MSG_HANDLER = QtCore.qInstallMessageHandler(_qt_msg_handler)
                _QT_HANDLER_INSTALLED = True
            except Exception:
                pass

        return log_file


def teardown_application_file_logging() -> None:
    """Flush and close the active rotating log handler cleanly during shutdown."""
    global _ACTIVE_FILE_HANDLER, _PREV_QT_MSG_HANDLER, _QT_HANDLER_INSTALLED
    with _FILE_HANDLER_LOCK:
        if _QT_HANDLER_INSTALLED:
            try:
                from PySide6 import QtCore

                QtCore.qInstallMessageHandler(_PREV_QT_MSG_HANDLER)
            except Exception:
                pass
            _PREV_QT_MSG_HANDLER = None
            _QT_HANDLER_INSTALLED = False
        if _ACTIVE_FILE_HANDLER is not None:
            try:
                logging.getLogger().removeHandler(_ACTIVE_FILE_HANDLER)
                _ACTIVE_FILE_HANDLER.flush()
                _ACTIVE_FILE_HANDLER.close()
            except Exception:
                pass
            _ACTIVE_FILE_HANDLER = None


class BoundedMemoryLogHandler(logging.Handler):
    """Logging handler with fixed max capacity so UI/log buffers never grow unbounded."""

    def __init__(self, maxlen: int = 500) -> None:
        super().__init__()
        self._records: deque[str] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        with self._lock:
            self._records.append(msg)

    def recent(self) -> list[str]:
        with self._lock:
            return list(self._records)


@dataclass
class PerformanceRecord:
    timestamp_utc: str
    task_id: str
    model_name: str
    model_architecture: str
    input_duration_sec: float
    chunk_size_sec: float
    segment: int
    overlap: float
    device: str
    start_ram_mb: float
    peak_ram_mb: float
    end_ram_mb: float
    start_vram_mb: Optional[float]
    peak_vram_mb: Optional[float]
    end_vram_mb: Optional[float]
    processing_time_sec: float
    rtf: Optional[float]
    oom_occurred: bool
    fallback_used: bool
    status: str
    error: Optional[str] = None


class PerformanceLogger:
    """Writes local AI separation performance records to logs/performance/ (never auto-uploaded)."""

    def __init__(self, log_dir: Path | str = Path("logs/performance"), history_maxlen: int = 200) -> None:
        self.log_dir = Path(log_dir)
        self._lock = threading.Lock()
        self._recent: deque[PerformanceRecord] = deque(maxlen=history_maxlen)

    def log_job(self, req: AIJobRequest, res: AIJobResult) -> Path:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        rec = PerformanceRecord(
            timestamp_utc=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            task_id=req.task_id,
            model_name=res.model_id or req.model_id,
            model_architecture=res.architecture or "unknown",
            input_duration_sec=round(res.input_duration_sec, 3),
            chunk_size_sec=round(req.chunk_seconds, 3),
            segment=req.segment_seconds,
            overlap=req.overlap,
            device=res.device_used,
            start_ram_mb=round(res.start_ram_mb, 2),
            peak_ram_mb=round(res.peak_ram_mb, 2),
            end_ram_mb=round(res.end_ram_mb, 2),
            start_vram_mb=round(res.start_vram_mb, 2) if res.start_vram_mb is not None else None,
            peak_vram_mb=round(res.peak_vram_mb, 2) if res.peak_vram_mb is not None else None,
            end_vram_mb=round(res.end_vram_mb, 2) if res.end_vram_mb is not None else None,
            processing_time_sec=round(res.elapsed_sec, 3),
            rtf=round(res.rtf, 4) if res.rtf is not None else None,
            oom_occurred=res.oom_occurred,
            fallback_used=res.fallback_used,
            status=res.state.value,
            error=res.error,
        )
        out_file = self.log_dir / f"ai_perf_{now.strftime('%Y%m%d')}.jsonl"
        line = json.dumps(asdict(rec), ensure_ascii=False)
        with self._lock:
            self._recent.append(rec)
            with open(out_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return out_file

    def recent_records(self) -> list[PerformanceRecord]:
        with self._lock:
            return list(self._recent)
