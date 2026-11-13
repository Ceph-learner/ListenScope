"""Phase 0 CLI tool to probe local hardware/CUDA/ONNX Runtime, AI/MIDI packages, and write SYSTEM_REPORT.md."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import AudioConfig, ResourceLimits, TargetHardwareSpec
from core.paths import find_ffmpeg_executable
from core.system_probe import generate_system_report_markdown, probe_system


def _probe_pkg_table(
    checks: tuple[tuple[str, str, bool], ...],
) -> dict[str, dict[str, str | bool | None]]:
    out: dict[str, dict[str, str | bool | None]] = {}
    for mod_name, dist_name, optional in checks:
        installed = importlib.util.find_spec(mod_name) is not None
        ver: str | None = None
        if installed:
            for cand in (dist_name, mod_name.replace("_", "-")):
                try:
                    ver = importlib.metadata.version(cand)
                    break
                except Exception:
                    pass
        entry: dict[str, str | bool | None] = {"installed": installed, "version": ver}
        if optional:
            entry["optional"] = True
        out[mod_name] = entry
    return out


def _probe_ai_packages() -> dict[str, dict[str, str | bool | None]]:
    return _probe_pkg_table(
        (
            ("demucs", "demucs", False),
            ("audio_separator", "audio-separator", False),
            ("audioread", "audioread", False),
            # Basic Pitch moved to isolated Python 3.11 CPU MIDI env (requirements-midi.txt)
            ("basic_pitch", "basic-pitch", True),
            ("onnxruntime", "onnxruntime-gpu", False),
            ("soundfile", "soundfile", False),
            ("mido", "mido", False),
        )
    )


def _probe_midi_packages() -> dict[str, dict[str, str | bool | None]]:
    return _probe_pkg_table(
        (
            ("basic_pitch", "basic-pitch", False),
            ("tensorflow", "tensorflow", False),
            ("pkg_resources", "setuptools", False),
            ("psutil", "psutil", False),
            ("mido", "mido", False),
            ("numpy", "numpy", False),
            ("scipy", "scipy", False),
            ("soundfile", "soundfile", False),
        )
    )


def _probe_tools() -> dict[str, dict[str, str | bool | None]]:
    ff = find_ffmpeg_executable()
    return {
        "ffmpeg": {
            "installed": bool(ff),
            "path": ff,
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ListenScope Phase 0 hardware, CUDA, ONNX Runtime, AI/MIDI env check"
    )
    parser.add_argument(
        "--write-report",
        nargs="?",
        const=ROOT / "SYSTEM_REPORT.md",
        default=ROOT / "SYSTEM_REPORT.md",
        type=Path,
        help="Path to write SYSTEM_REPORT.md (default: ./SYSTEM_REPORT.md)",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write SYSTEM_REPORT.md to disk",
    )
    parser.add_argument(
        "--check-ai-packages",
        action="store_true",
        help="Include AI separation package availability in --json output",
    )
    parser.add_argument(
        "--check-midi-packages",
        action="store_true",
        help="Include CPU Basic Pitch MIDI package availability in --json output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON hardware probe report to stdout",
    )
    args = parser.parse_args()

    target = TargetHardwareSpec()
    limits = ResourceLimits()
    audio_cfg = AudioConfig()
    out_path = None if args.no_write else args.write_report
    ipc_out = sys.stdout
    if args.json:
        sys.stdout = sys.stderr
    try:
        report = probe_system(target=target)
        md = generate_system_report_markdown(
            report,
            target=target,
            limits=limits,
            audio_cfg=audio_cfg,
            output_path=out_path,
        )

        if args.json:
            payload = report.to_dict()
            payload["tools"] = _probe_tools()
            if args.check_ai_packages:
                payload["ai_packages"] = _probe_ai_packages()
            if args.check_midi_packages:
                payload["midi_packages"] = _probe_midi_packages()
            print(json.dumps(payload, indent=2), file=ipc_out, flush=True)
        else:
            print(md)
            ff = find_ffmpeg_executable()
            print(f"[FFmpeg] {ff or '未找到 (请将 ffmpeg.exe 放入 PATH 或工作目录，仅 non-WAV/部分后端需要)'}")
            if out_path is not None:
                print(f"[Saved] {out_path}")
    finally:
        sys.stdout = ipc_out
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
