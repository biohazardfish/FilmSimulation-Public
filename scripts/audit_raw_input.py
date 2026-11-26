#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from filmsim_experiment.experiment import INPUT_SHA256, write_json
from filmsim_experiment.raw_provenance import collect_raw_input_provenance


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit RAW input provenance without decoding outputs")
    parser.add_argument("--input", type=Path, default=ROOT / "input/_C5A0880.CR3")
    parser.add_argument("--output", type=Path, default=ROOT / "validation/raw_input_provenance.json")
    parser.add_argument("--raw-identify", default="raw-identify")
    args = parser.parse_args()
    raw_path = args.input.resolve()
    try:
        display_path = str(raw_path.relative_to(ROOT))
    except ValueError:
        display_path = raw_path.name
    payload = collect_raw_input_provenance(
        raw_path,
        display_path=display_path,
        raw_identify_executable=args.raw_identify,
    )
    if raw_path == (ROOT / "input/_C5A0880.CR3").resolve() and payload["input"]["sha256"] != INPUT_SHA256:
        raise RuntimeError("FilmSimulation input hash does not match the pinned CR3")
    write_json(args.output, payload)
    print(f"RAW provenance: {args.output}")
    print(f"Dual Pixel RAW: {payload['capture']['dual_pixel_raw']}")
    print(f"RAW images: {payload['container']['raw_image_count']}")
    print("Auxiliary dual-pixel data used: False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
