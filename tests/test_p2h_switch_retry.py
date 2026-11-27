from __future__ import annotations

import logging
from pathlib import Path
import sys
import threading
import time
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_device_names_match_variants() -> None:
    from audio.system_loopback import _device_names_match, _normalize_device_name

    assert _normalize_device_name("  Realtek   Digital  Output [Loopback] ") == "realtek digital output"
    assert _device_names_match("XIBERIA", "XIBERIA") is True
    assert _device_names_match("Realtek Digital Output [Loopback]", "Realtek Digital Output") is True
    assert _device_names_match("realtek digital output [loopback]", "Realtek Digital Output") is True

    # PortAudio 31-char / 63-char truncation prefix match (min normalized len >= 28)
    full_name = "Headphones (Sony WH-1000XM5 Stereo)"
    truncated_pa = "Headphones (Sony WH-1000XM5 St [Loopback]"
    assert len(_normalize_device_name(truncated_pa)) >= 28
    assert _device_names_match(truncated_pa, full_name) is True
    assert _device_names_match(full_name + " [Loopback]", "Headphones (Sony WH-1000XM5 St") is True

    # Empty fallback match
    assert _device_names_match("XIBERIA [Loopback]", "") is True
    assert _device_names_match("", "XIBERIA") is True
    assert _device_names_match("   ", "   ") is True

    # Distinct devices must be rejected
    assert _device_names_match("Speakers", "Speakers (2)") is False
    assert _device_names_match("Speakers [Loopback]", "Speakers (2)") is False
    assert _device_names_match("XIBERIA [Loopback]", "Realtek Digital Output") is False


def test_switch_name_mismatch_retry_succeeds_and_preserves_buffer(caplog) -> None:
    from audio.playback import HistoryABPlayer
    from audio.ring_buffer import FixedRingBuffer
    from audio.system_loopback import WasapiSystemLoopbackBackend

    state = {"dev_id": "dev-xiberia", "dev_name": "XIBERIA"}
    open_calls = {"n": 0}
    pa_events: list[tuple[str, int]] = []
    events_lock = threading.Lock()
    pcm_chunk = (np.ones((960, 2), dtype=np.float32) * 0.1).tobytes()

    class _FakeStream:
        def __init__(self, label: str) -> None:
            self._label = label

        def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
            time.sleep(0.01)
            return pcm_chunk

        def stop_stream(self) -> None:
            with events_lock:
                pa_events.append((f"stop:{self._label}", threading.get_ident()))

        def close(self) -> None:
            with events_lock:
                pa_events.append((f"close:{self._label}", threading.get_ident()))

    class _FakePyAudio:
        paFloat32 = 1
        paInt16 = 8

        def __init__(self) -> None:
            open_calls["n"] += 1
            n = open_calls["n"]
            if n == 1:
                self._name = "XIBERIA"
                self._idx = 1
            elif n == 2:
                # First reopen after switch still returns stale PortAudio device
                self._name = "XIBERIA [Loopback]"
                self._idx = 1
            else:
                self._name = "Realtek Digital Output [Loopback]"
                self._idx = 2
            with events_lock:
                pa_events.append((f"init:{self._name}", threading.get_ident()))

        def get_default_wasapi_loopback(self) -> dict[str, Any]:
            return {
                "index": self._idx,
                "name": self._name,
                "defaultSampleRate": 48000.0,
                "maxInputChannels": 2,
            }

        def open(self, **kwargs) -> _FakeStream:
            return _FakeStream(self._name)

        def terminate(self) -> None:
            with events_lock:
                pa_events.append((f"terminate:{self._name}", threading.get_ident()))

    ring = FixedRingBuffer()
    ab = HistoryABPlayer(ring_buffer=ring)
    backend = WasapiSystemLoopbackBackend(
        pyaudio_factory=_FakePyAudio,
        allow_non_windows=True,
        follow_default_device=True,
        default_device_probe=lambda: (state["dev_id"], state["dev_name"]),
        device_poll_interval_sec=0.05,
        max_switch_name_retries=3,
        switch_retry_backoff_base_sec=0.02,
    )

    with caplog.at_level(logging.INFO):
        backend.start()
        try:
            deadline = time.monotonic() + 1.5
            while ring.available_seconds < 0.06 and time.monotonic() < deadline:
                ch = backend.read_chunk(timeout=0.05)
                if ch is not None:
                    ring.write(ch)
            assert ring.available_seconds >= 0.04
            ab.select_recent_seconds(0.04)
            prev_frames = ring.total_written_frames
            prev_loop = ab.loop_range

            # Trigger switch to Realtek
            state["dev_id"] = "dev-realtek"
            state["dev_name"] = "Realtek Digital Output"

            switch_deadline = time.monotonic() + 2.0
            switched = False
            while time.monotonic() < switch_deadline:
                ch = backend.read_chunk(timeout=0.05)
                if ch is not None:
                    ring.write(ch)
                if backend.get_stats().process_name == "Realtek Digital Output [Loopback]":
                    switched = True
                    break

            assert switched, f"Did not switch after retry; stats={backend.get_stats()}"
            assert open_calls["n"] >= 3
            assert ring.total_written_frames >= prev_frames
            assert ab.loop_range == prev_loop
            assert any(
                "loopback device switch name mismatch (retry 1/3): opened=XIBERIA [Loopback] expected=Realtek Digital Output"
                in r.message
                for r in caplog.records
            )
            assert any(
                "loopback default device changed old=XIBERIA new=Realtek Digital Output [Loopback]" in r.message
                for r in caplog.records
            )
            stats = backend.get_stats()
            assert "Realtek Digital Output [Loopback]" in (stats.device_switch_message or "")
        finally:
            backend.stop()

    # All PortAudio lifecycle calls ran strictly on a single capture thread
    tids = {tid for _, tid in pa_events}
    assert len(tids) == 1
    assert threading.get_ident() not in tids
    assert any(ev == "terminate:XIBERIA [Loopback]" for ev, _ in pa_events)


def test_switch_name_mismatch_exhausted_reverts_endpoint_id_and_recovers_on_next_poll(caplog) -> None:
    from audio.ring_buffer import FixedRingBuffer
    from audio.system_loopback import WasapiSystemLoopbackBackend

    state = {"dev_id": "dev-xiberia", "dev_name": "XIBERIA"}
    open_calls = {"n": 0}
    reverted_ep_ids: list[str | None] = []
    pa_tids: set[int] = set()
    tid_lock = threading.Lock()
    pcm_chunk = (np.ones((960, 2), dtype=np.float32) * 0.1).tobytes()

    class _FakeStream:
        def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
            with tid_lock:
                pa_tids.add(threading.get_ident())
            time.sleep(0.01)
            return pcm_chunk

        def stop_stream(self) -> None:
            with tid_lock:
                pa_tids.add(threading.get_ident())

        def close(self) -> None:
            with tid_lock:
                pa_tids.add(threading.get_ident())

    class _FakePyAudio:
        paFloat32 = 1
        paInt16 = 8

        def __init__(self) -> None:
            with tid_lock:
                pa_tids.add(threading.get_ident())
            open_calls["n"] += 1
            n = open_calls["n"]
            if n == 1:
                self._name = "XIBERIA"
                self._idx = 1
            elif n <= 5:
                # Initial reopen + 3 retries (first 4 reopens) still return stale old device
                self._name = "XIBERIA [Loopback]"
                self._idx = 1
            else:
                self._name = "Realtek Digital Output [Loopback]"
                self._idx = 2

        def get_default_wasapi_loopback(self) -> dict[str, Any]:
            return {
                "index": self._idx,
                "name": self._name,
                "defaultSampleRate": 48000.0,
                "maxInputChannels": 2,
            }

        def open(self, **kwargs) -> _FakeStream:
            return _FakeStream()

        def terminate(self) -> None:
            with tid_lock:
                pa_tids.add(threading.get_ident())

    backend_holder: dict[str, WasapiSystemLoopbackBackend] = {}

    def _probe() -> tuple[str, str]:
        be = backend_holder.get("backend")
        if be is not None and open_calls["n"] >= 5:
            with be._lock:
                cur_id = be._current_endpoint_id
            if cur_id == "dev-xiberia":
                reverted_ep_ids.append(cur_id)
        return (state["dev_id"], state["dev_name"])

    ring = FixedRingBuffer()
    backend = WasapiSystemLoopbackBackend(
        pyaudio_factory=_FakePyAudio,
        allow_non_windows=True,
        follow_default_device=True,
        default_device_probe=_probe,
        device_poll_interval_sec=0.06,
        max_switch_name_retries=3,
        switch_retry_backoff_base_sec=0.02,
    )
    backend_holder["backend"] = backend

    with caplog.at_level(logging.INFO):
        backend.start()
        try:
            deadline = time.monotonic() + 1.5
            while ring.available_seconds < 0.05 and time.monotonic() < deadline:
                ch = backend.read_chunk(timeout=0.05)
                if ch is not None:
                    ring.write(ch)
            assert ring.available_seconds >= 0.04
            prev_frames = ring.total_written_frames

            # Switch Windows default device; first 4 reopens return XIBERIA [Loopback], 5th reopen recovers
            state["dev_id"] = "dev-realtek"
            state["dev_name"] = "Realtek Digital Output"

            recover_deadline = time.monotonic() + 3.0
            recovered = False
            while time.monotonic() < recover_deadline:
                ch = backend.read_chunk(timeout=0.05)
                if ch is not None:
                    ring.write(ch)
                if backend.get_stats().process_name == "Realtek Digital Output [Loopback]":
                    recovered = True
                    break

            assert recovered, f"Did not recover on next watcher poll; open_calls={open_calls['n']}, stats={backend.get_stats()}"
            assert backend.is_running is True
            assert open_calls["n"] >= 6
            assert ring.total_written_frames > prev_frames
            assert "dev-xiberia" in reverted_ep_ids

            msgs = [r.message for r in caplog.records]
            assert any("name mismatch (retry 1/3)" in m for m in msgs)
            assert any("name mismatch (retry 2/3)" in m for m in msgs)
            assert any("name mismatch (retry 3/3)" in m for m in msgs)
            assert any(
                "loopback device switch still mismatched after 3 retries (opened=XIBERIA [Loopback] expected=Realtek Digital Output); reverting endpoint_id"
                in m
                for m in msgs
            )
            assert not any("new=XIBERIA [Loopback]" in m for m in msgs)
            assert any(
                "loopback default device changed old=XIBERIA [Loopback] new=Realtek Digital Output [Loopback]" in m
                for m in msgs
            )
            stats = backend.get_stats()
            assert "Realtek Digital Output [Loopback]" in (stats.device_switch_message or "")
            assert stats.last_error is None
        finally:
            backend.stop()

    assert len(pa_tids) == 1
    assert threading.get_ident() not in pa_tids
