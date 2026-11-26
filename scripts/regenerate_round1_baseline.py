#!/usr/bin/env python3
"""Explicit, owner-controlled regeneration of the frozen Round 1 descriptor."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from filmsim_experiment.baseline import write_round1_baseline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--i-understand-this-replaces-frozen-evidence",
        action="store_true",
        help="required acknowledgement; ordinary verification must not use this command",
    )
    args = parser.parse_args()
    if not args.i_understand_this_replaces_frozen_evidence:
        parser.error("the explicit frozen-evidence acknowledgement flag is required")
    write_round1_baseline(ROOT, confirm=True)
    print(ROOT / "docs" / "round1_baseline.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
