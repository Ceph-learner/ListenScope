"""Phase 0 CLI tool to probe local hardware/CUDA/ONNX Runtime and write SYSTEM_REPORT.md."""

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
from core.system_probe import generate_system_report_markdown, probe_system


def _probe_ai_packages() -> dict[str, dict[str, str | bool | None]]:
    checks = (
        ("demucs", "demucs"),
        ("audio_separator", "audio-separator"),
        ("basic_pitch", "basic-pitch"),
        ("onnxruntime", "onnxruntime-gpu"),
        ("soundfile", "soundfile"),
        ("mido", "mido"),
    )
    out: dict[str, dict[str, str | bool | None]] = {}
    for mod_name, dist_name in checks:
        installed = importlib.util.find_spec(mod_name) is not None
        ver: str | None = None
        if installed:
            for cand in (dist_name, mod_name.replace("_", "-")):
                try:
                    ver = importlib.metadata.version(cand)
                    break
                except Exception:
                    pass
        out[mod_name] = {"installed": installed, "version": ver}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ListenScope Phase 0 hardware, CUDA, PyTorch, and ONNX Runtime check"
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
        help="Include AI separation & Basic Pitch package availability in --json output",
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
    report = probe_system(target=target)
    out_path = None if args.no_write else args.write_report
    md = generate_system_report_markdown(
        report,
        target=target,
        limits=limits,
        audio_cfg=audio_cfg,
        output_path=out_path,
    )

    if args.json:
        payload = report.to_dict()
        if args.check_ai_packages:
            payload["ai_packages"] = _probe_ai_packages()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(md)
        if out_path is not None:
            print(f"[Saved] {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

