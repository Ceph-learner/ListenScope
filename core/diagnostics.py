"""One-click sanitized offline diagnostic bundle exporter (.zip) for Windows troubleshooting."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Optional
import zipfile

from core.config import AIConfig, ResourceLimits, TargetHardwareSpec
from core.logging import BoundedMemoryLogHandler, PerformanceLogger
from core.models import LiveSeparationMetrics, ResourceSnapshot, SystemHardwareReport
from core.paths import find_ffmpeg_executable
from core.system_probe import generate_system_report_markdown


def _sanitize_text(text: str) -> str:
    """Replace user home directory prefix with `~` to avoid leaking local account names."""
    home_str = str(Path.home())
    if not home_str:
        return text
    sanitized = text
    variants = []
    for v in (home_str, home_str.replace("\\", "/"), home_str.replace("/", "\\")):
        if v and v not in variants:
            variants.append(v)
    for variant in variants:
        if len(variant) >= 3:
            sanitized = re.sub(re.escape(variant), "~", sanitized, flags=re.IGNORECASE)
        else:
            sanitized = sanitized.replace(variant, "~")
    return sanitized


def _read_bounded_tail(path: Path, max_bytes: int = 262144) -> bytes:
    limit = max(1024, int(max_bytes))
    size = path.stat().st_size
    if size <= limit:
        return path.read_bytes()
    with path.open("rb") as fh:
        fh.seek(max(0, size - limit))
        data = fh.read()
    # Trim partial leading UTF-8 line when sliced mid-file
    nl = data.find(b"\n")
    header = b"# [truncated older entries; kept newest tail]\n"
    return header + (data[nl + 1 :] if nl != -1 else data)


def export_diagnostic_bundle(
    output_zip_path: Path | str,
    *,
    hardware_report: SystemHardwareReport,
    resource_limits: ResourceLimits,
    ai_config: AIConfig,
    ai_python_executable: str = "",
    midi_python_executable: str = "",
    resource_snapshot: Optional[ResourceSnapshot] = None,
    perf_logger: Optional[PerformanceLogger] = None,
    log_handler: Optional[BoundedMemoryLogHandler] = None,
    settings_path: Optional[Path] = None,
    live_separation_metrics: Optional[LiveSeparationMetrics] = None,
    max_jsonl_bytes: int = 262144,
) -> Path:
    """Bundle hardware report, bounded logs, perf records, and sanitized settings into a compact ZIP."""
    target = Path(output_zip_path)
    if target.suffix.lower() != ".zip":
        target = target.with_suffix(".zip")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_zip = target.with_suffix(".zip.tmp")

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    hw_md = generate_system_report_markdown(
        hardware_report,
        target=TargetHardwareSpec(),
        limits=resource_limits,
    )

    summary_payload: dict[str, Any] = {
        "exported_utc": now_utc,
        "target_hardware": {
            "gpu_name": TargetHardwareSpec().gpu_name,
            "vram_gb": TargetHardwareSpec().vram_gb,
            "ram_gb": TargetHardwareSpec().ram_gb,
            "min_windows_build": TargetHardwareSpec().min_windows_build_for_process_loopback,
        },
        "hardware_report": hardware_report.to_dict(),
        "resource_snapshot": asdict(resource_snapshot) if resource_snapshot is not None else None,
        "resource_limits": asdict(resource_limits),
        "ai_config": asdict(ai_config),
        "ai_python_executable": _sanitize_text(str(ai_python_executable or "")),
        "midi_python_executable": _sanitize_text(str(midi_python_executable or "")),
        "ffmpeg_executable": _sanitize_text(find_ffmpeg_executable() or ""),
    }
    if live_separation_metrics is not None:
        live = live_separation_metrics
        summary_payload["live_separation"] = {
            "active": live.active,
            "rtf": live.rtf,
            "latency_ms": live.latency_ms,
            "buffer_seconds": live.buffer_seconds,
            "max_buffer_seconds": live.max_buffer_seconds,
            "input_drop_events": live.dropped_chunks,
            "playback_rebuffers": live.playback_rebuffers,
            "device_underflows": live.device_underflows,
        }
    summary_json = _sanitize_text(json.dumps(summary_payload, ensure_ascii=False, indent=2, default=str))

    recent_logs = _sanitize_text("\n".join(log_handler.recent())) if log_handler is not None else ""
    perf_recent = (
        _sanitize_text(json.dumps([asdict(r) for r in perf_logger.recent_records()], ensure_ascii=False, indent=2))
        if perf_logger is not None
        else "[]"
    )

    try:
        with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("SYSTEM_REPORT.md", _sanitize_text(hw_md))
            zf.writestr("diagnostic_summary.json", summary_json)
            zf.writestr("recent_logs.txt", recent_logs)
            zf.writestr("performance_recent.json", perf_recent)

            if settings_path is not None and settings_path.exists():
                try:
                    raw_settings = settings_path.read_text(encoding="utf-8", errors="replace")
                    zf.writestr("settings_sanitized.json", _sanitize_text(raw_settings[:65536]))
                except Exception:
                    pass

            if perf_logger is not None and perf_logger.log_dir.exists():
                jsonl_files = sorted(
                    perf_logger.log_dir.glob("ai_perf_*.jsonl"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )[:2]
                for jf in jsonl_files:
                    try:
                        tail_text = _sanitize_text(
                            _read_bounded_tail(jf, max_bytes=max_jsonl_bytes).decode("utf-8", errors="replace")
                        )
                        zf.writestr(f"perf_jsonl/{jf.name}", tail_text)
                    except Exception:
                        pass

        tmp_zip.replace(target)
        return target
    except Exception:
        tmp_zip.unlink(missing_ok=True)
        raise
