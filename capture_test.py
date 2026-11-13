"""Phase 1 Audio Capture + RAM/VRAM Monitor PoC.

Supports:
1. Enumerating audio-producing processes (`--list-procs`, `--all-procs`)
2. Windows WASAPI Process Loopback by `--pid` or `--name` (e.g. QQMusic.exe, chrome.exe, Cubase)
3. Automatic or explicit fallback to System WASAPI Loopback (`--system-loopback` / `--fallback-system`)
   with explicit warning: "其他应用声音可能被混入。"
4. Live RAM / VRAM monitoring via ResourceManager
5. Synthetic non-Windows signal mode (`--simulate sine|silence|switching`) for Linux dev testing
"""

from __future__ import annotations

import argparse
import platform
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audio.capture_base import AudioCaptureBackend
from audio.process_enum import enumerate_audio_processes, resolve_target_pid
from audio.process_loopback import WasapiProcessLoopbackBackend
from audio.system_loopback import (
    SYSTEM_LOOPBACK_WARNING,
    SyntheticSimulationBackend,
    WasapiSystemLoopbackBackend,
)
from core.config import AudioConfig, ResourceLimits
from core.models import CaptureMode
from core.resource_manager import ResourceManager


def _print_processes(include_all: bool = False) -> None:
    procs = enumerate_audio_processes(include_all_running=include_all)
    if not procs:
        print("未检测到活跃音频会话或可用进程。")
        return
    print(f"{'PID':<8} {'进程名':<30} {'状态':<10} {'来源':<15} {'RSS(MB)':>8}  {'父进程'}")
    print("-" * 92)
    for p in procs[:50]:
        parent = f"{p.parent_name}({p.parent_pid})" if p.parent_name and p.parent_pid else "-"
        print(
            f"{p.pid:<8} {p.name[:29]:<30} {p.session_state:<10} "
            f"{p.source:<15} {p.rss_mb:>8.1f}  {parent}"
        )


def _select_process_interactively() -> tuple[Optional[int], Optional[str], bool]:
    """Let user interactively pick an audio process or system loopback fallback."""
    procs = enumerate_audio_processes(include_all_running=False)
    if not procs:
        procs = enumerate_audio_processes(include_all_running=True)[:25]

    print("\n可选音频进程列表：")
    for idx, p in enumerate(procs[:25], start=1):
        print(f"  [{idx:>2}] {p.display_label}")
    print("  [ 0] 系统 WASAPI Loopback (兜底模式：其他应用声音可能被混入)")

    raw = input("\n请输入序号，或直接输入 PID / 进程名 (如 QQMusic.exe): ").strip()
    if raw == "0":
        return None, None, True
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= min(25, len(procs)):
            chosen = procs[idx - 1]
            return chosen.pid, chosen.name, False
        return idx, None, False
    return None, raw, False


def _format_level(linear: float, dbfs: float) -> str:
    return f"{linear:.4f} ({dbfs:>6.1f} dBFS)"


def _run_consumer_drain(
    backend: AudioCaptureBackend,
    stop_event: threading.Event,
    *,
    simulate_slow_consumer_ms: float = 0.0,
) -> None:
    """Drains bounded queue like downstream DSP analysis will in Phase 3."""
    while not stop_event.is_set():
        chunk = backend.read_chunk(timeout=0.1)
        if chunk is not None and simulate_slow_consumer_ms > 0.0:
            time.sleep(simulate_slow_consumer_ms / 1000.0)


def run_capture_session(
    backend: AudioCaptureBackend,
    resource_mgr: ResourceManager,
    *,
    duration_sec: Optional[float] = None,
    simulate_slow_consumer_ms: float = 0.0,
) -> int:
    stop_event = threading.Event()

    def _sig_handler(_signum, _frame) -> None:
        stop_event.set()

    prev_int = signal.getsignal(signal.SIGINT)
    prev_term = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    consumer_thread = threading.Thread(
        target=_run_consumer_drain,
        args=(backend, stop_event),
        kwargs={"simulate_slow_consumer_ms": simulate_slow_consumer_ms},
        name="ListenScope-PoCConsumer",
        daemon=True,
    )

    try:
        backend.start()
        consumer_thread.start()
        start_time = time.monotonic()
        print("\n开始捕获 (按 Ctrl+C 停止)...\n")

        while not stop_event.is_set():
            stats = backend.get_stats()
            resource_mgr.update_runtime_state(
                audio_queue_size=stats.queue_size,
                audio_queue_maxsize=stats.queue_maxsize,
            )
            res = resource_mgr.sample()

            vram_str = (
                f"{res.vram_used_mb:.0f}/{res.vram_total_mb:.0f} MB (空闲 {res.vram_free_mb:.0f} MB)"
                if res.vram_total_mb is not None and res.vram_free_mb is not None and res.vram_used_mb is not None
                else "N/A (未检测到 GPU)"
            )
            silence_tag = "静音/暂停" if stats.is_silent else "有音频信号"
            mode_label = stats.mode.value

            print(
                f"[{time.strftime('%H:%M:%S')}] "
                f"Mode={mode_label} | PID={stats.pid if stats.pid is not None else '-'} | "
                f"Proc={stats.process_name} | {stats.sample_rate}Hz/{stats.channels}ch | "
                f"RMS={_format_level(stats.rms_linear, stats.rms_dbfs)} | "
                f"Peak={_format_level(stats.peak_linear, stats.peak_dbfs)} [{silence_tag}] | "
                f"FPS={stats.frames_per_sec:>7.1f} | "
                f"Underrun={stats.buffer_underruns} Overrun={stats.buffer_overruns} "
                f"Q={stats.queue_size}/{stats.queue_maxsize} | "
                f"MainRAM={res.main_ram_mb:.1f}MB AvailRAM={res.system_ram_available_mb:.0f}MB | "
                f"VRAM={vram_str} | Status={res.status.value}"
            )
            if stats.warning_message:
                print(f"    [提示] {stats.warning_message}")
            if stats.last_error:
                print(f"    [状态/错误] {stats.last_error}")

            if not stats.is_running:
                print("\n捕获后端已停止。")
                break

            if duration_sec is not None and (time.monotonic() - start_time) >= duration_sec:
                print(f"\n达到预设测试时长 {duration_sec:.1f}s，准备停止捕获...")
                break

            stop_event.wait(timeout=1.0)
    except KeyboardInterrupt:
        print("\n收到中断信号，正在停止捕获...")
    finally:
        stop_event.set()
        backend.stop()
        if consumer_thread.is_alive():
            consumer_thread.join(timeout=2.0)
        signal.signal(signal.SIGINT, prev_int)
        signal.signal(signal.SIGTERM, prev_term)

    final_stats = backend.get_stats()
    print(
        f"\n捕获结束摘要: TotalFrames={final_stats.total_frames}, "
        f"Underruns={final_stats.buffer_underruns}, Overruns={final_stats.buffer_overruns}, "
        f"Running={final_stats.is_running}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capture_test.py",
        description="ListenScope Phase 1 Audio Capture + RAM/VRAM Monitor PoC",
    )
    parser.add_argument("--list-procs", action="store_true", help="列出正在产生音频的进程并退出")
    parser.add_argument("--all-procs", action="store_true", help="与 --list-procs 配合，显示全部运行中进程")
    parser.add_argument("--pid", type=int, help="目标进程 PID")
    parser.add_argument("--name", type=str, help="目标进程名（例如 QQMusic.exe, chrome.exe, Cubase）")
    parser.add_argument(
        "--system-loopback",
        action="store_true",
        help="直接使用系统 WASAPI Loopback 模式（会提示其他应用声音可能被混入）",
    )
    parser.add_argument(
        "--fallback-system",
        action="store_true",
        help="若 Process Loopback 不可用，自动回退到系统 WASAPI Loopback",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="运行指定秒数后自动停止（不传则持续运行直至 Ctrl+C）",
    )
    parser.add_argument(
        "--resample-quality",
        choices=["best", "medium", "fast"],
        default="best",
        help="ProcTap 重采样质量（仅当驱动格式非 48kHz/float32 时触发）",
    )
    parser.add_argument(
        "--simulate",
        choices=["sine", "silence", "switching"],
        default=None,
        help="非 Windows 开发环境合成信号模拟模式（不会伪装为 Windows WASAPI）",
    )
    parser.add_argument(
        "--slow-consumer-ms",
        type=float,
        default=0.0,
        help="测试用：模拟消费端处理延迟(ms)以验证有界队列 overrun 保护",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.list_procs:
        _print_processes(include_all=args.all_procs)
        return 0

    audio_cfg = AudioConfig()
    limits = ResourceLimits()

    with ResourceManager(limits=limits) as resource_mgr:
        if args.simulate is not None:
            print("🧪 启动合成信号模拟模式（非 Windows 真机 WASAPI 验证）。")
            backend: AudioCaptureBackend = SyntheticSimulationBackend(
                pattern=args.simulate,
                audio_config=audio_cfg,
            )
            return run_capture_session(
                backend,
                resource_mgr,
                duration_sec=args.duration,
                simulate_slow_consumer_ms=args.slow_consumer_ms,
            )

        if platform.system() != "Windows":
            print(
                f"当前系统为 {platform.system()}，Windows WASAPI Process Loopback 未在 Windows 真机验证。\n"
                "提示：在当前非 Windows 环境请使用 `python capture_test.py --simulate switching --duration 5` "
                "验证 PCM/队列/RMS/ResourceManager；在 Windows 10/11 PC 上可直接用 `--name QQMusic.exe` 或 `--pid`。",
                file=sys.stderr,
            )
            return 2

        use_system_loopback = args.system_loopback
        target_pid = args.pid
        target_name = args.name

        if not use_system_loopback and target_pid is None and target_name is None:
            target_pid, target_name, use_system_loopback = _select_process_interactively()

        if use_system_loopback:
            print(SYSTEM_LOOPBACK_WARNING)
            backend = WasapiSystemLoopbackBackend(audio_config=audio_cfg)
            return run_capture_session(
                backend,
                resource_mgr,
                duration_sec=args.duration,
                simulate_slow_consumer_ms=args.slow_consumer_ms,
            )

        resolved_pid, resolved_name, note = resolve_target_pid(
            pid=target_pid,
            process_name=target_name,
        )
        if note:
            print(f"[进程解析] {note}")

        proc_backend = WasapiProcessLoopbackBackend(
            pid=resolved_pid,
            process_name=resolved_name,
            audio_config=audio_cfg,
            resample_quality=args.resample_quality,
        )
        try:
            return run_capture_session(
                proc_backend,
                resource_mgr,
                duration_sec=args.duration,
                simulate_slow_consumer_ms=args.slow_consumer_ms,
            )
        except RuntimeError as exc:
            if args.fallback_system:
                print(f"[回退] Process Loopback 不可用 ({exc})。\n{SYSTEM_LOOPBACK_WARNING}", file=sys.stderr)
                sys_backend = WasapiSystemLoopbackBackend(audio_config=audio_cfg)
                return run_capture_session(
                    sys_backend,
                    resource_mgr,
                    duration_sec=args.duration,
                    simulate_slow_consumer_ms=args.slow_consumer_ms,
                )
            print(f"错误: {exc}\n提示: 可加 --fallback-system 或 --system-loopback 尝试系统 Loopback。", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
