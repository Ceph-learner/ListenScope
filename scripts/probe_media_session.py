"""Read-only Windows Media Session (SMTC) & process window title probe for ListenScope.

Used to confirm on target Windows 11 hardware whether QQ Music (or another player) exposes
stable Windows SMTC metadata (Title / Artist / Album / PlaybackStatus / Position) and
how `TrackChangeTracker` distinguishes Pause / Resume / Seek from genuine song switches.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.media_session import (
    MediaSessionSnapshot,
    TrackChangeTracker,
    WindowsMediaSessionReader,
    enumerate_process_window_titles,
    is_python_winrt_smtc_available,
    query_smtc_via_powershell,
)


def _builtin_mock_sequence() -> list[list[MediaSessionSnapshot]]:
    """Deterministic sequence covering Play, Pause, Resume, Seek, Flicker, Unrelated App, and A->B Switch."""
    return [
        # Poll 0: Initial song A playing
        [
            MediaSessionSnapshot(
                source_app_id="QQMusic.exe",
                title="晴天",
                artist="周杰伦",
                album_title="叶惠美",
                playback_status="playing",
                position_sec=12.0,
                duration_sec=269.0,
                is_current_session=True,
                backend="mock",
            )
        ],
        # Poll 1: Same song paused -> NO reset
        [
            MediaSessionSnapshot(
                source_app_id="QQMusic.exe",
                title="晴天",
                artist="周杰伦",
                playback_status="paused",
                position_sec=35.4,
                duration_sec=269.0,
                is_current_session=True,
                backend="mock",
            )
        ],
        # Poll 2: Same song resumed -> NO reset
        [
            MediaSessionSnapshot(
                source_app_id="QQMusic.exe",
                title="晴天",
                artist="周杰伦",
                playback_status="playing",
                position_sec=35.9,
                duration_sec=269.0,
                is_current_session=True,
                backend="mock",
            )
        ],
        # Poll 3: Same song scrubbed backwards (Seek 35.9s -> 10.2s) -> NO reset
        [
            MediaSessionSnapshot(
                source_app_id="QQMusic.exe",
                title="晴天",
                artist="周杰伦",
                playback_status="playing",
                position_sec=10.2,
                duration_sec=269.0,
                is_current_session=True,
                backend="mock",
            )
        ],
        # Poll 4: Transient Changing / blank title flicker -> NO reset
        [
            MediaSessionSnapshot(
                source_app_id="QQMusic.exe",
                title="",
                artist="",
                playback_status="changing",
                is_current_session=True,
                backend="mock",
            )
        ],
        # Poll 5: Unrelated browser session only -> NO reset (baseline kept)
        [
            MediaSessionSnapshot(
                source_app_id="msedge.exe",
                title="Some Video",
                artist="Creator",
                playback_status="playing",
                is_current_session=True,
                backend="mock",
            )
        ],
        # Poll 6: Real switch to Song B (poll 1/2 -> pending_confirmation, NO reset yet)
        [
            MediaSessionSnapshot(
                source_app_id="QQMusic.exe",
                title="七里香",
                artist="周杰伦",
                album_title="七里香",
                playback_status="playing",
                position_sec=0.4,
                duration_sec=299.0,
                is_current_session=True,
                backend="mock",
            )
        ],
        # Poll 7: Real switch to Song B (poll 2/2 -> track_changed, triggered_reset=True)
        [
            MediaSessionSnapshot(
                source_app_id="QQMusic.exe",
                title="七里香",
                artist="周杰伦",
                album_title="七里香",
                playback_status="playing",
                position_sec=0.9,
                duration_sec=299.0,
                is_current_session=True,
                backend="mock",
            )
        ],
    ]


def _load_mock_sequence(mock_path: Path) -> list[list[MediaSessionSnapshot]]:
    raw = json.loads(mock_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Mock sequence JSON must be a list of poll entries")
    seq: list[list[MediaSessionSnapshot]] = []
    for entry in raw:
        items = entry if isinstance(entry, list) else ([entry] if isinstance(entry, dict) else [])
        snaps: list[MediaSessionSnapshot] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            snaps.append(
                MediaSessionSnapshot(
                    source_app_id=str(item.get("source_app_id", "")),
                    title=str(item.get("title", "")),
                    artist=str(item.get("artist", "")),
                    album_title=str(item.get("album_title", "")),
                    playback_status=str(item.get("playback_status", "unknown")),
                    position_sec=float(item["position_sec"]) if item.get("position_sec") is not None else None,
                    duration_sec=float(item["duration_sec"]) if item.get("duration_sec") is not None else None,
                    is_current_session=bool(item.get("is_current_session", False)),
                    backend=str(item.get("backend", "mock")),
                )
            )
        seq.append(snaps)
    return seq


def run_probe(
    *,
    process_name: Optional[str] = "QQMusic.exe",
    duration_sec: float = 0.0,
    interval_sec: float = 0.5,
    confirm_polls: int = 2,
    allow_powershell_fallback: bool = True,
    include_window_titles: bool = True,
    mock_polls: Optional[list[list[MediaSessionSnapshot]]] = None,
) -> dict[str, Any]:
    target_proc = process_name.strip() if isinstance(process_name, str) and process_name.strip() else None
    py_winrt_ok, py_winrt_backend = is_python_winrt_smtc_available()
    tracker = TrackChangeTracker(confirm_polls=confirm_polls, target_process_name=target_proc)

    reader: Optional[WindowsMediaSessionReader] = WindowsMediaSessionReader() if (mock_polls is None and py_winrt_ok) else None
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    backends_used: set[str] = set()
    window_titles_sample: list[dict[str, Any]] = []

    t0 = time.monotonic()
    try:
        if mock_polls is not None:
            for idx, poll_snaps in enumerate(mock_polls):
                backends_used.add("mock")
                dec = tracker.update(poll_snaps)
                events.append(
                    {
                        "poll_index": idx,
                        "t_sec": round(idx * interval_sec, 3),
                        "backend": "mock",
                        "sessions": [asdict(s) for s in poll_snaps],
                        "decision": {
                            "triggered_reset": dec.triggered_reset,
                            "reason": dec.reason,
                            "active_track": dec.active_track.display_label if dec.active_track else None,
                            "previous_track": dec.previous_track.display_label if dec.previous_track else None,
                            "pending_count": dec.pending_count,
                        },
                    }
                )
        else:
            poll_idx = 0
            while True:
                now = time.monotonic()
                snaps: list[MediaSessionSnapshot] = []
                backend_used = "unavailable"
                if reader is not None:
                    snaps, backend_used = reader.query_sessions()
                    if reader.last_error:
                        errors.append(f"winrt: {reader.last_error}")

                if not snaps and allow_powershell_fallback and sys.platform == "win32":
                    ps_snaps, ps_err = query_smtc_via_powershell()
                    if ps_err:
                        errors.append(f"powershell_smtc: {ps_err}")
                    else:
                        snaps = ps_snaps
                        backend_used = "powershell_smtc"

                backends_used.add(backend_used)
                dec = tracker.update(snaps)

                win_titles: list[dict[str, Any]] = []
                if include_window_titles and target_proc and sys.platform == "win32" and (poll_idx == 0 or dec.triggered_reset):
                    try:
                        win_titles = enumerate_process_window_titles(target_proc)
                        if not window_titles_sample and win_titles:
                            window_titles_sample = list(win_titles)
                    except Exception as exc:
                        errors.append(f"enum_windows: {exc}")

                events.append(
                    {
                        "poll_index": poll_idx,
                        "t_sec": round(now - t0, 3),
                        "backend": backend_used,
                        "sessions": [asdict(s) for s in snaps],
                        "window_titles": win_titles,
                        "decision": {
                            "triggered_reset": dec.triggered_reset,
                            "reason": dec.reason,
                            "active_track": dec.active_track.display_label if dec.active_track else None,
                            "previous_track": dec.previous_track.display_label if dec.previous_track else None,
                            "pending_count": dec.pending_count,
                        },
                    }
                )
                poll_idx += 1

                elapsed = time.monotonic() - t0
                if duration_sec <= 0.0 or elapsed >= duration_sec:
                    break
                sleep_s = min(max(0.05, interval_sec), max(0.0, duration_sec - elapsed))
                if sleep_s > 0:
                    time.sleep(sleep_s)
    finally:
        if reader is not None:
            reader.close()

    reset_events = [ev for ev in events if ev["decision"]["triggered_reset"]]
    matched_sessions = [
        ev["sessions"]
        for ev in events
        if ev["decision"]["reason"] != "no_matching_session"
    ]
    return {
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
        "target_process": target_proc,
        "duration_sec": round(time.monotonic() - t0, 3) if mock_polls is None else round(len(events) * interval_sec, 3),
        "confirm_polls": confirm_polls,
        "python_winrt_available": py_winrt_ok,
        "python_winrt_backend": py_winrt_backend,
        "backends_observed": sorted(backends_used),
        "total_polls": len(events),
        "matched_poll_count": len(matched_sessions),
        "reset_count": len(reset_events),
        "reset_events": reset_events,
        "final_active_track": tracker.active_track.display_label if tracker.active_track else None,
        "window_titles_sample": window_titles_sample,
        "errors": sorted(set(errors)),
        "events": events,
    }


def _print_human_summary(report: dict[str, Any]) -> None:
    print("=== ListenScope Read-Only Media Session (SMTC) Probe ===")
    print(
        f"Platform={report['platform']} | Python={report['python_version']} | "
        f"Target={report['target_process'] or '*ALL*'}"
    )
    print(
        f"In-process WinRT SMTC: {report['python_winrt_available']} ({report['python_winrt_backend']}) | "
        f"Backends observed: {report['backends_observed']}"
    )
    print(
        f"Polls={report['total_polls']} | Matched={report['matched_poll_count']} | "
        f"TriggeredResets={report['reset_count']} | FinalTrack={report['final_active_track'] or 'None'}"
    )
    if report["window_titles_sample"]:
        print("Window titles observed:")
        for wt in report["window_titles_sample"][:5]:
            print(f"  - PID={wt['pid']} visible={wt['visible']} title={wt['title']!r}")
    if report["errors"]:
        print("Diagnostics / Errors:")
        for err in report["errors"]:
            print(f"  ! {err}")
    print("Timeline:")
    for ev in report["events"]:
        dec = ev["decision"]
        sess_desc = "; ".join(
            f"{s['source_app_id']}[{s['playback_status']}] {s['title']!r}/{s['artist']!r}"
            + (f" @{s['position_sec']:.1f}s" if s.get("position_sec") is not None else "")
            for s in ev["sessions"]
        ) or "<no sessions>"
        flag = " [RESET!]" if dec["triggered_reset"] else ""
        print(
            f"  #{ev['poll_index']:02d} t={ev['t_sec']:6.2f}s | {dec['reason']}{flag} | "
            f"active={dec['active_track'] or '-'} | {sess_desc}"
        )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="ListenScope Read-Only Windows SMTC & Track-Change Probe")
    parser.add_argument("--process", type=str, default="QQMusic.exe", help="Target process name filter (empty for all)")
    parser.add_argument("--duration", type=float, default=0.0, help="Watch duration in seconds (0 = single snapshot)")
    parser.add_argument("--interval", type=float, default=0.5, help="Poll interval in seconds")
    parser.add_argument("--confirm-polls", type=int, default=2, help="Consecutive polls required before track switch")
    parser.add_argument("--no-powershell-fallback", action="store_true", help="Disable PowerShell WinRT SMTC fallback")
    parser.add_argument("--no-window-titles", action="store_true", help="Skip Win32 EnumWindows title sampling")
    parser.add_argument("--mock-sequence", type=Path, default=None, help="JSON file of mock SMTC poll frames")
    parser.add_argument(
        "--self-test-mock",
        action="store_true",
        help="Run built-in Play/Pause/Resume/Seek/Switch deterministic self-test sequence",
    )
    parser.add_argument("--json", action="store_true", help="Print ASCII-safe structured JSON report")
    args = parser.parse_args(argv)

    mock_polls: Optional[list[list[MediaSessionSnapshot]]] = None
    if args.self_test_mock:
        mock_polls = _builtin_mock_sequence()
    elif args.mock_sequence is not None:
        mock_polls = _load_mock_sequence(args.mock_sequence)

    report = run_probe(
        process_name=args.process,
        duration_sec=args.duration,
        interval_sec=args.interval,
        confirm_polls=args.confirm_polls,
        allow_powershell_fallback=not args.no_powershell_fallback,
        include_window_titles=not args.no_window_titles,
        mock_polls=mock_polls,
    )

    if args.json:
        # Strict ensure_ascii=True avoids UnicodeEncodeError on Windows GBK consoles (PYTHONUTF8=0)
        print(json.dumps(report, ensure_ascii=True, indent=2), flush=True)
    else:
        _print_human_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
