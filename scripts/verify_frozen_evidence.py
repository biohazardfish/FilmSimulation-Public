#!/usr/bin/env python3
"""Explicitly verify every private frozen master against its exact hash."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from filmsim_experiment.phase2.analysis import protected_inventory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-private-artifacts",
        action="store_true",
        help="required acknowledgement that the private evidence bundle is present",
    )
    args = parser.parse_args()
    if not args.require_private_artifacts:
        parser.error("--require-private-artifacts is required")
    result = protected_inventory(ROOT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["all_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
