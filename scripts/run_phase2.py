#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from filmsim_experiment.experiment import FILM_KEY, PRINT_KEY
from filmsim_experiment.phase2.runner import run_phase2


def _sizes(value: str) -> list[int]:
    try:
        result = [int(item) for item in value.split(",") if item]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("sizes must be comma-separated integers") from exc
    if not result or any(item <= 0 for item in result):
        raise argparse.ArgumentTypeError("sizes must be positive")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run FilmSimulation Phase II physical validation")
    parser.add_argument("--all", action="store_true", required=True, help="run all Phase II validation stages")
    parser.add_argument("--film-profile", default=FILM_KEY)
    parser.add_argument("--print-profile", default=PRINT_KEY)
    parser.add_argument("--sizes", type=_sizes, default=[256, 512, 1024, 2048])
    parser.add_argument("--reference-data", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    manifest = run_phase2(
        ROOT, film_profile=args.film_profile, print_profile=args.print_profile,
        sizes=args.sizes, reference_data=args.reference_data, output_dir=args.output_dir,
    )
    print(f"Phase II status: {manifest['status']}")
    print(f"Manifest: {(args.output_dir or ROOT / 'output/phase2') / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
