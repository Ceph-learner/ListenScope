"""Windows Media Session (SMTC) inspection & guarded track-change detection for ListenScope.

Designed conservatively around Windows 11 QQ Music / WASAPI process capture:
- Uses in-process PyWinRT (`winrt-Windows.Media.Control`, or legacy `winsdk`) when available on Windows.
- Keeps SMTC strictly optional and read-only: missing WinRT bindings or disabled player SMTC never blocks capture
  or disables the manual 「换歌重置 (和弦/调性/BPM)」 button.
- Implements debounced `TrackChangeTracker` so same-track Pause, Resume, Seek/Scrub, transient empty metadata,
  playback_status=Changing flickers, and unrelated apps never falsely clear chord/key/BPM history.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import json
import logging
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Optional, Sequence

import psutil

logger = logging.getLogger(__name__)

_PLAYBACK_STATUS_NAMES = {
    0: "closed",
    1: "opened",
    2: "changing",
    3: "stopped",
    4: "playing",
    5: "paused",
}

_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\ufeff]+")
_WHITESPACE_RE = re.compile(r"\s+")
_TOKEN_SPLIT_RE = re.compile(r"[!\\/.:\-_]+")


def normalize_track_text(text: Optional[str]) -> str:
    """Normalize metadata strings cleanly for comparison across polls."""
    if not text:
        return ""
    cleaned = _ZERO_WIDTH_RE.sub("", str(text))
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def _normalize_playback_status(raw_status: Any) -> str:
    if raw_status is None:
        return "unknown"
    if isinstance(raw_status, str):
        val = raw_status.strip().lower()
        return val if val else "unknown"
    name = getattr(raw_status, "name", None)
    if isinstance(name, str) and name.strip():
        return name.strip().lower()
    try:
        idx = int(raw_status)
        return _PLAYBACK_STATUS_NAMES.get(idx, "unknown")
    except Exception:
        return "unknown"


def _timedelta_to_seconds(raw_val: Any) -> Optional[float]:
    if raw_val is None:
        return None
    if isinstance(raw_val, timedelta):
        sec = float(raw_val.total_seconds())
        return sec if sec >= 0.0 else None
    total_fn = getattr(raw_val, "total_seconds", None)
    if callable(total_fn):
        try:
            sec = float(total_fn())
            return sec if sec >= 0.0 else None
        except Exception:
            return None
    if isinstance(raw_val, (int, float)):
        val = float(raw_val)
        return val if val >= 0.0 else None
    return None


@dataclass(frozen=True)
class MediaSessionSnapshot:
    """Point-in-time snapshot of a Windows SMTC media session."""

    source_app_id: str = ""
    title: str = ""
    artist: str = ""
    album_title: str = ""
    playback_status: str = "unknown"
    position_sec: Optional[float] = None
    duration_sec: Optional[float] = None
    is_current_session: bool = False
    backend: str = "none"
    pid: Optional[int] = None
    window_title: Optional[str] = None


@dataclass(frozen=True)
class MediaTrackIdentity:
    """Canonical track identity used to distinguish real song switches from Pause/Resume/Seek."""

    title: str
    artist: str = ""
    album_title: str = ""
    source_app_id: str = ""

    @property
    def is_valid(self) -> bool:
        return bool(normalize_track_text(self.title))

    @property
    def title_norm(self) -> str:
        return normalize_track_text(self.title).casefold()

    @property
    def artist_norm(self) -> str:
        return normalize_track_text(self.artist).casefold()

    @property
    def album_norm(self) -> str:
        return normalize_track_text(self.album_title).casefold()

    @property
    def display_label(self) -> str:
        t = normalize_track_text(self.title)
        a = normalize_track_text(self.artist)
        if t and a:
            return f"{t} — {a}"
        return t or a or "-"

    def same_track_as(self, other: Optional[MediaTrackIdentity]) -> bool:
        if other is None or not self.is_valid or not other.is_valid:
            return False
        if self.title_norm != other.title_norm:
            return False
        # Tolerate one side transiently missing artist metadata while keeping real artist changes distinct
        if self.artist_norm and other.artist_norm and self.artist_norm != other.artist_norm:
            return False
        return True

    def merged_with(self, newer: MediaTrackIdentity) -> MediaTrackIdentity:
        """Retain richer non-empty metadata when identical track updates piecemeal."""
        return MediaTrackIdentity(
            title=normalize_track_text(newer.title) or normalize_track_text(self.title),
            artist=normalize_track_text(newer.artist) or normalize_track_text(self.artist),
            album_title=normalize_track_text(newer.album_title) or normalize_track_text(self.album_title),
            source_app_id=newer.source_app_id or self.source_app_id,
        )


@dataclass(frozen=True)
class TrackTrackerDecision:
    """Deterministic verdict emitted on each SMTC poll by `TrackChangeTracker`."""

    triggered_reset: bool
    reason: str
    active_track: Optional[MediaTrackIdentity] = None
    previous_track: Optional[MediaTrackIdentity] = None
    selected_session: Optional[MediaSessionSnapshot] = None
    pending_count: int = 0
    confirm_polls: int = 2


def identity_from_snapshot(snap: MediaSessionSnapshot) -> MediaTrackIdentity:
    return MediaTrackIdentity(
        title=normalize_track_text(snap.title),
        artist=normalize_track_text(snap.artist),
        album_title=normalize_track_text(snap.album_title),
        source_app_id=normalize_track_text(snap.source_app_id),
    )


def match_session_to_process(source_app_id: str, target_process_name: Optional[str]) -> bool:
    """Match Windows SMTC SourceAppUserModelId against target process name (e.g. QQMusic.exe)."""
    if not target_process_name:
        return True
    proc_clean = target_process_name.strip().lower()
    if not proc_clean:
        return True
    proc_stem = Path(proc_clean.replace("\\", "/")).stem
    if not proc_stem:
        return False
    proc_exe = f"{proc_stem}.exe"

    app_clean = (source_app_id or "").strip().lower()
    if not app_clean:
        return False
    app_tail = Path(app_clean.replace("\\", "/")).name
    app_stem = Path(app_tail).stem
    if app_clean == proc_clean or app_tail == proc_exe or app_stem == proc_stem:
        return True
    if proc_exe in app_clean:
        return True
    tokens = {tok for tok in _TOKEN_SPLIT_RE.split(app_clean) if tok}
    if proc_stem in tokens:
        return True
    if len(proc_stem) >= 4 and proc_stem in app_stem:
        return True
    return False


def select_relevant_session(
    sessions: Sequence[MediaSessionSnapshot],
    *,
    target_process_name: Optional[str] = None,
) -> Optional[MediaSessionSnapshot]:
    """Select the single SMTC session relevant to the active ListenScope capture target."""
    if not sessions:
        return None

    if target_process_name:
        candidates = [s for s in sessions if match_session_to_process(s.source_app_id, target_process_name)]
    else:
        candidates = list(sessions)

    if not candidates:
        return None

    status_rank = {
        "playing": 0,
        "paused": 1,
        "opened": 2,
        "stopped": 3,
        "unknown": 4,
        "changing": 5,
        "closed": 6,
    }

    def _score(s: MediaSessionSnapshot) -> tuple[int, int, int]:
        has_title = 0 if normalize_track_text(s.title) else 1
        cur_rank = 0 if s.is_current_session else 1
        st_rank = status_rank.get(s.playback_status, 4)
        return (has_title, st_rank, cur_rank)

    return sorted(candidates, key=_score)[0]


class TrackChangeTracker:
    """Guarded state machine distinguishing real song switches from Pause/Resume/Seek."""

    def __init__(
        self,
        *,
        confirm_polls: int = 2,
        target_process_name: Optional[str] = None,
    ) -> None:
        self.confirm_polls = max(1, int(confirm_polls))
        self.target_process_name = target_process_name
        self._baseline: Optional[MediaTrackIdentity] = None
        self._pending_track: Optional[MediaTrackIdentity] = None
        self._pending_count: int = 0
        self._last_playback_status: str = "unknown"
        self._last_position_sec: Optional[float] = None
        self._last_session: Optional[MediaSessionSnapshot] = None

    @property
    def active_track(self) -> Optional[MediaTrackIdentity]:
        return self._baseline

    @property
    def last_session(self) -> Optional[MediaSessionSnapshot]:
        return self._last_session

    def reset(self, *, target_process_name: Optional[str] = None) -> None:
        if target_process_name is not None or self.target_process_name is not None:
            self.target_process_name = target_process_name
        self._baseline = None
        self._pending_track = None
        self._pending_count = 0
        self._last_playback_status = "unknown"
        self._last_position_sec = None
        self._last_session = None

    def set_target_process(self, target_process_name: Optional[str]) -> None:
        norm = target_process_name.strip() if isinstance(target_process_name, str) and target_process_name.strip() else None
        if norm != self.target_process_name:
            self.reset(target_process_name=norm)

    def update(
        self,
        sessions: Sequence[MediaSessionSnapshot] | Optional[MediaSessionSnapshot],
    ) -> TrackTrackerDecision:
        if sessions is None:
            seq: list[MediaSessionSnapshot] = []
        elif isinstance(sessions, MediaSessionSnapshot):
            seq = [sessions]
        else:
            seq = list(sessions)

        selected = select_relevant_session(seq, target_process_name=self.target_process_name)
        if selected is None:
            return TrackTrackerDecision(
                triggered_reset=False,
                reason="no_matching_session",
                active_track=self._baseline,
                selected_session=None,
                pending_count=0,
                confirm_polls=self.confirm_polls,
            )

        self._last_session = selected
        status = (selected.playback_status or "unknown").lower()
        if status in ("changing", "closed"):
            return TrackTrackerDecision(
                triggered_reset=False,
                reason="transient_empty_or_changing",
                active_track=self._baseline,
                selected_session=selected,
                pending_count=self._pending_count,
                confirm_polls=self.confirm_polls,
            )

        cand = identity_from_snapshot(selected)
        if not cand.is_valid:
            return TrackTrackerDecision(
                triggered_reset=False,
                reason="transient_empty_or_changing",
                active_track=self._baseline,
                selected_session=selected,
                pending_count=self._pending_count,
                confirm_polls=self.confirm_polls,
            )

        if self._baseline is None:
            self._baseline = cand
            self._pending_track = None
            self._pending_count = 0
            self._last_playback_status = status
            self._last_position_sec = selected.position_sec
            return TrackTrackerDecision(
                triggered_reset=False,
                reason="initial_baseline",
                active_track=self._baseline,
                selected_session=selected,
                pending_count=0,
                confirm_polls=self.confirm_polls,
            )

        if cand.same_track_as(self._baseline):
            self._baseline = self._baseline.merged_with(cand)
            self._pending_track = None
            self._pending_count = 0

            reason = "same_track"
            prev_st = self._last_playback_status
            prev_pos = self._last_position_sec
            cur_pos = selected.position_sec

            if status == "paused" and prev_st != "paused":
                reason = "same_track_paused"
            elif status == "playing" and prev_st == "paused":
                reason = "same_track_resumed"
            elif prev_pos is not None and cur_pos is not None:
                if cur_pos < prev_pos - 1.5 or (cur_pos - prev_pos) > 5.0:
                    reason = "same_track_seek"

            self._last_playback_status = status
            self._last_position_sec = cur_pos
            return TrackTrackerDecision(
                triggered_reset=False,
                reason=reason,
                active_track=self._baseline,
                selected_session=selected,
                pending_count=0,
                confirm_polls=self.confirm_polls,
            )

        # Candidate track differs from current baseline -> debounce for `confirm_polls` consecutive reads
        if self._pending_track is not None and cand.same_track_as(self._pending_track):
            self._pending_track = self._pending_track.merged_with(cand)
            self._pending_count += 1
        else:
            self._pending_track = cand
            self._pending_count = 1

        if self._pending_count >= self.confirm_polls:
            prev_track = self._baseline
            self._baseline = self._pending_track
            self._pending_track = None
            self._pending_count = 0
            self._last_playback_status = status
            self._last_position_sec = selected.position_sec
            return TrackTrackerDecision(
                triggered_reset=True,
                reason="track_changed",
                active_track=self._baseline,
                previous_track=prev_track,
                selected_session=selected,
                pending_count=0,
                confirm_polls=self.confirm_polls,
            )

        return TrackTrackerDecision(
            triggered_reset=False,
            reason="pending_confirmation",
            active_track=self._baseline,
            selected_session=selected,
            pending_count=self._pending_count,
            confirm_polls=self.confirm_polls,
        )


def is_python_winrt_smtc_available() -> tuple[bool, str]:
    """Check whether in-process Python WinRT bindings for Windows.Media.Control are importable."""
    if sys.platform != "win32":
        return False, "non_windows"
    try:
        import winrt.windows.media.control  # type: ignore[import-not-found]  # noqa: F401

        return True, "winrt_smtc"
    except ImportError:
        pass
    try:
        import winsdk.windows.media.control  # type: ignore[import-not-found]  # noqa: F401

        return True, "winsdk_smtc"
    except ImportError:
        return False, "unavailable"


def _import_winrt_control_module() -> tuple[Optional[Any], str]:
    try:
        import winrt.windows.media.control as wmc  # type: ignore[import-not-found]

        return wmc, "winrt_smtc"
    except ImportError:
        pass
    try:
        import winsdk.windows.media.control as wmc  # type: ignore[import-not-found]

        return wmc, "winsdk_smtc"
    except ImportError:
        return None, "unavailable"


def _iter_winrt_vector(vec: Any) -> list[Any]:
    if vec is None:
        return []
    try:
        return list(vec)
    except TypeError:
        size = int(getattr(vec, "size", 0))
        return [vec.get_at(i) for i in range(size)]


async def _async_query_winrt_sessions(wmc: Any, backend_name: str) -> list[MediaSessionSnapshot]:
    mgr = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
    cur_sess = None
    try:
        cur_sess = mgr.get_current_session()
    except Exception:
        cur_sess = None
    cur_app_id = normalize_track_text(getattr(cur_sess, "source_app_user_model_id", "")) if cur_sess else ""

    raw_sessions = _iter_winrt_vector(mgr.get_sessions())
    snapshots: list[MediaSessionSnapshot] = []
    for idx, sess in enumerate(raw_sessions):
        app_id = ""
        try:
            app_id = normalize_track_text(getattr(sess, "source_app_user_model_id", ""))
        except Exception:
            app_id = ""

        status = "unknown"
        try:
            pb_info = sess.get_playback_info()
            status = _normalize_playback_status(getattr(pb_info, "playback_status", None))
        except Exception:
            status = "unknown"

        title = ""
        artist = ""
        album = ""
        try:
            props = await sess.try_get_media_properties_async()
            if props is not None:
                title = normalize_track_text(getattr(props, "title", ""))
                artist = normalize_track_text(getattr(props, "artist", ""))
                album = normalize_track_text(getattr(props, "album_title", ""))
        except Exception:
            pass

        pos_sec: Optional[float] = None
        dur_sec: Optional[float] = None
        try:
            tl = sess.get_timeline_properties()
            if tl is not None:
                start_s = _timedelta_to_seconds(getattr(tl, "start_time", None)) or 0.0
                end_s = _timedelta_to_seconds(getattr(tl, "end_time", None))
                pos_raw = _timedelta_to_seconds(getattr(tl, "position", None))
                if pos_raw is not None:
                    pos_sec = round(max(0.0, pos_raw - start_s), 3)
                if end_s is not None and end_s > start_s:
                    dur_sec = round(end_s - start_s, 3)
        except Exception:
            pass

        is_cur = False
        if cur_sess is not None:
            try:
                is_cur = bool(sess == cur_sess)
            except Exception:
                is_cur = False
            if not is_cur and cur_app_id and app_id == cur_app_id and idx == 0:
                is_cur = True

        snapshots.append(
            MediaSessionSnapshot(
                source_app_id=app_id,
                title=title,
                artist=artist,
                album_title=album,
                playback_status=status,
                position_sec=pos_sec,
                duration_sec=dur_sec,
                is_current_session=is_cur,
                backend=backend_name,
            )
        )
    return snapshots


class WindowsMediaSessionReader:
    """Thread-confined WinRT SMTC poller that owns one reusable asyncio event loop."""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_error: Optional[str] = None

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def query_sessions(self) -> tuple[list[MediaSessionSnapshot], str]:
        if sys.platform != "win32":
            return [], "non_windows"

        wmc, backend_name = _import_winrt_control_module()
        if wmc is None:
            return [], "unavailable"

        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()

        try:
            coro = asyncio.wait_for(_async_query_winrt_sessions(wmc, backend_name), timeout=2.5)
            sessions = self._loop.run_until_complete(coro)
            self._last_error = None
            return sessions, backend_name
        except Exception as exc:
            self._last_error = str(exc)
            logger.debug("SMTC WinRT query error (%s): %s", backend_name, exc)
            return [], backend_name

    def close(self) -> None:
        if self._loop is not None and not self._loop.is_closed():
            try:
                self._loop.close()
            except Exception:
                pass
        self._loop = None


_PS_SMTC_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType=WindowsRuntime] | Out-Null
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]
function Await-WinRt($Op, $Type) {
    $netTask = $asTaskGeneric.MakeGenericMethod($Type).Invoke($null, @($Op))
    $netTask.Wait() | Out-Null
    return $netTask.Result
}
$mgr = Await-WinRt ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
$cur = $mgr.GetCurrentSession()
$curId = if ($cur) { [string]$cur.SourceAppUserModelId } else { '' }
$out = @()
foreach ($s in $mgr.GetSessions()) {
    $appId = [string]$s.SourceAppUserModelId
    $pb = $s.GetPlaybackInfo()
    $st = if ($pb) { [string]$pb.PlaybackStatus } else { 'Unknown' }
    $title = ''; $artist = ''; $album = ''
    try {
        $mp = Await-WinRt ($s.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
        if ($mp) {
            $title = [string]$mp.Title
            $artist = [string]$mp.Artist
            $album = [string]$mp.AlbumTitle
        }
    } catch {}
    $pos = $null; $dur = $null
    try {
        $tl = $s.GetTimelineProperties()
        if ($tl) {
            $startS = $tl.StartTime.TotalSeconds
            $endS = $tl.EndTime.TotalSeconds
            $pos = [Math]::Round([Math]::Max(0.0, $tl.Position.TotalSeconds - $startS), 3)
            if ($endS -gt $startS) { $dur = [Math]::Round($endS - $startS, 3) }
        }
    } catch {}
    $out += [pscustomobject]@{
        source_app_id = $appId
        title = $title
        artist = $artist
        album_title = $album
        playback_status = $st.ToLowerInvariant()
        position_sec = $pos
        duration_sec = $dur
        is_current_session = ($appId -eq $curId -and $curId -ne '')
    }
}
$json = ConvertTo-Json -InputObject @($out) -Depth 4 -Compress
[Console]::OutputEncoding = [System.Text.Encoding]::ASCII
Write-Output $json
"""


def query_smtc_via_powershell(*, timeout_sec: float = 5.0) -> tuple[list[MediaSessionSnapshot], Optional[str]]:
    """On-demand CLI diagnostic fallback using Windows PowerShell 5.1 WinRT projection."""
    if sys.platform != "win32":
        return [], "non_windows"
    from .paths import subprocess_no_window_kwargs

    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _PS_SMTC_SCRIPT],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
            **subprocess_no_window_kwargs(),
        )
    except Exception as exc:
        return [], str(exc)

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return [], f"powershell exit={proc.returncode}: {err[:240]}"

    raw_txt = (proc.stdout or "").strip()
    if not raw_txt:
        return [], None
    try:
        parsed = json.loads(raw_txt)
    except Exception as exc:
        return [], f"powershell invalid json: {exc} ({raw_txt[:160]})"

    if isinstance(parsed, dict):
        items = [parsed]
    elif isinstance(parsed, list):
        items = parsed
    else:
        return [], None

    out: list[MediaSessionSnapshot] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        out.append(
            MediaSessionSnapshot(
                source_app_id=normalize_track_text(row.get("source_app_id")),
                title=normalize_track_text(row.get("title")),
                artist=normalize_track_text(row.get("artist")),
                album_title=normalize_track_text(row.get("album_title")),
                playback_status=_normalize_playback_status(row.get("playback_status")),
                position_sec=float(row["position_sec"]) if row.get("position_sec") is not None else None,
                duration_sec=float(row["duration_sec"]) if row.get("duration_sec") is not None else None,
                is_current_session=bool(row.get("is_current_session", False)),
                backend="powershell_smtc",
            )
        )
    return out, None


def enumerate_process_window_titles(target_process_name: str = "QQMusic.exe") -> list[dict[str, Any]]:
    """Read-only diagnostic helper inspecting Win32 window titles for a target process name."""
    if sys.platform != "win32":
        return []

    target_norm = target_process_name.strip().lower()
    target_stem = Path(target_norm).stem
    matching_pids: dict[int, str] = {}
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pname = (proc.info.get("name") or "").strip()
            plower = pname.lower()
            if not plower:
                continue
            if plower == target_norm or Path(plower).stem == target_stem or (len(target_stem) >= 4 and target_stem in plower):
                matching_pids[int(proc.info["pid"])] = pname
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError):
            continue

    if not matching_pids:
        return []

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    results: list[dict[str, Any]] = []

    def _callback(hwnd: int, _lparam: int) -> bool:
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) not in matching_pids:
            return True
        length = int(user32.GetWindowTextLengthW(hwnd))
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = normalize_track_text(buf.value)
        if not title:
            return True
        results.append(
            {
                "pid": int(pid.value),
                "process_name": matching_pids[int(pid.value)],
                "hwnd": int(hwnd),
                "visible": bool(user32.IsWindowVisible(hwnd)),
                "title": title,
            }
        )
        return True

    user32.EnumWindows(EnumWindowsProc(_callback), 0)
    results.sort(key=lambda r: (0 if r["visible"] else 1, r["pid"], -len(r["title"])))
    return results
