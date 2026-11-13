"""Bounded diagnostic logging and local AI performance logging under logs/performance/."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import threading
from typing import Optional

from .models import AIJobRequest, AIJobResult


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
