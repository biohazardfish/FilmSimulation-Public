#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from filmsim_experiment.experiment import write_json, write_text
from filmsim_experiment.published_reference_validation import (
    build_published_reference_validation,
    render_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the offline G4 published-reference validation")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "validation/published_reference_validation.json")
    parser.add_argument("--report", type=Path, default=ROOT / "docs/phase4/G4_PUBLISHED_REFERENCE_VALIDATION.md")
    args = parser.parse_args()
    payload = build_published_reference_validation(args.root)
    write_json(args.output, payload)
    write_text(args.report, render_report(payload))
    print(f"G4 status: {payload['status']}")
    print(f"JSON: {args.output}")
    print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
