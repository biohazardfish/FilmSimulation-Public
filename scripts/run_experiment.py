#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from filmsim_experiment.experiment import run_experiment


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the fixed FilmSimulation first-round experiment")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--all", action="store_true", help="smoke, decode, full taps, outputs, report")
    modes.add_argument("--smoke-only", action="store_true", help="synthetic validation only")
    modes.add_argument("--decode-only", action="store_true", help="smoke plus controlled RAW decode")
    modes.add_argument("--round2", action="store_true", help="full-resolution repeat, source conformance, phase 5")
    args = parser.parse_args()
    if args.round2:
        from filmsim_experiment.round2 import run_round2
        manifest = run_round2(ROOT)
        print(f"FilmSimulation round 2 status: {manifest['status']}")
        print(f"Round 2 manifest: {ROOT / 'output' / 'round2_manifest.json'}")
        return 0
    mode = "all" if args.all else "decode-only" if args.decode_only else "smoke-only"
    manifest = run_experiment(ROOT, mode=mode)
    print(f"FilmSimulation status: {manifest['status']}")
    print(f"Manifest: {ROOT / 'output' / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
