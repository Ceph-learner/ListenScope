"""Phase 0 CLI tool to probe local hardware/CUDA/ONNX Runtime and write SYSTEM_REPORT.md."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import AudioConfig, ResourceLimits, TargetHardwareSpec
from core.system_probe import generate_system_report_markdown, probe_system


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
        "--json",
        action="store_true",
        help="Print structured JSON hardware probe report to stdout",
    )
    args = parser.parse_args()

    target = TargetHardwareSpec()
    limits = ResourceLimits()
    audio_cfg = AudioConfig()
    report = probe_system(target=target)
    md = generate_system_report_markdown(
        report,
        target=target,
        limits=limits,
        audio_cfg=audio_cfg,
        output_path=args.write_report,
    )

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(md)
        print(f"[Saved] {args.write_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
