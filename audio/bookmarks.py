"""Bounded 120s-history A/B loop bookmark storage with automatic ring-buffer rollover pruning."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any, Optional


@dataclass(frozen=True)
class ABBookmark:
    bookmark_id: int
    label: str
    start_abs_frame: int
    end_abs_frame: int


class ABBookmarkManager:
    """Manages bounded A/B practice loop markers referenced against FixedRingBuffer absolute frames."""

    def __init__(self, *, max_bookmarks: int = 12) -> None:
        self.max_bookmarks = max(1, int(max_bookmarks))
        self._lock = threading.RLock()
        self._items: list[ABBookmark] = []
        self._next_id = 1

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def prune_expired(self, oldest_abs_frame: int, *, min_valid_frames: int = 2400) -> int:
        """Drop bookmarks that have completely rolled out of the 120s ring buffer."""
        cutoff = int(oldest_abs_frame) + max(1, int(min_valid_frames))
        with self._lock:
            before = len(self._items)
            self._items = [bm for bm in self._items if bm.end_abs_frame > cutoff]
            return before - len(self._items)

    def add_bookmark(
        self,
        start_abs_frame: int,
        end_abs_frame: int,
        *,
        label: str = "",
        oldest_abs_frame: int = 0,
    ) -> ABBookmark:
        s = int(start_abs_frame)
        e = int(end_abs_frame)
        if e <= s:
            raise ValueError("A/B 书签结束帧必须大于起始帧。")
        with self._lock:
            self.prune_expired(oldest_abs_frame, min_valid_frames=1)
            bid = self._next_id
            self._next_id += 1
            clean_label = " ".join(str(label or "").strip().split())[:40]
            if not clean_label:
                clean_label = f"片段 #{bid}"
            while len(self._items) >= self.max_bookmarks:
                self._items.pop(0)
            bm = ABBookmark(
                bookmark_id=bid,
                label=clean_label,
                start_abs_frame=s,
                end_abs_frame=e,
            )
            self._items.append(bm)
            return bm

    def get_bookmark(
        self,
        bookmark_id: int,
        *,
        oldest_abs_frame: int = 0,
        min_valid_frames: int = 2400,
    ) -> Optional[ABBookmark]:
        with self._lock:
            self.prune_expired(oldest_abs_frame, min_valid_frames=min_valid_frames)
            for bm in self._items:
                if bm.bookmark_id == int(bookmark_id):
                    return bm
            return None

    def remove_bookmark(self, bookmark_id: int) -> bool:
        with self._lock:
            before = len(self._items)
            self._items = [bm for bm in self._items if bm.bookmark_id != int(bookmark_id)]
            return len(self._items) < before

    def list_bookmarks(
        self,
        *,
        oldest_abs_frame: int = 0,
        newest_abs_frame: int = 0,
        sample_rate: int = 48000,
        min_valid_frames: int = 2400,
    ) -> list[dict[str, Any]]:
        sr = float(max(1, int(sample_rate)))
        oldest = int(oldest_abs_frame)
        newest = max(oldest, int(newest_abs_frame))
        with self._lock:
            self.prune_expired(oldest, min_valid_frames=min_valid_frames)
            out: list[dict[str, Any]] = []
            for bm in self._items:
                clamped_s = max(oldest, bm.start_abs_frame)
                clamped_e = min(newest, bm.end_abs_frame) if newest > 0 else bm.end_abs_frame
                if clamped_e <= clamped_s:
                    continue
                start_ago = max(0.0, (newest - clamped_s) / sr) if newest >= clamped_s else 0.0
                end_ago = max(0.0, (newest - clamped_e) / sr) if newest >= clamped_e else 0.0
                dur = (clamped_e - clamped_s) / sr
                ttl = max(0.0, (clamped_e - oldest) / sr)
                out.append(
                    {
                        "bookmark_id": bm.bookmark_id,
                        "label": bm.label,
                        "start_abs_frame": clamped_s,
                        "end_abs_frame": clamped_e,
                        "duration_sec": dur,
                        "start_ago_sec": start_ago,
                        "end_ago_sec": end_ago,
                        "remaining_ttl_sec": ttl,
                    }
                )
            return out
