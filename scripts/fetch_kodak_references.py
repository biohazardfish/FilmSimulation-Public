#!/usr/bin/env python3
"""Fetch hash-pinned Kodak references from official URLs without vendoring them."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import sys
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
REFERENCES = {
    "5219": {
        "path": "cache/kodak_official/vision3_500t_5219_7219_H-1-5219.pdf",
        "sha256": "6d037d8090373ee50d10bedfff3df14777a575dd107c50edcafc7ec5862d0972",
        "url": "https://www.kodak.com/content/pdfs/motion/KODAK-VISION3-500T-5219-7219-technical-information.pdf",
    },
    "2383": {
        "path": "cache/kodak_official/vision_2383_3383_H-1-2383.pdf",
        "sha256": "a72fa4482ebd891a9ac4a823cafe740e3587c56470f27e4dfd4391f5c3e5a207",
        "url": "https://www.kodak.com/content/products-brochures/motion-picture/KODAK-VISION-Color-Print-Film-2383-3383-technical-information.pdf",
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_reference(destination: Path, url: str, expected_sha256: str) -> str:
    destination = destination.resolve()
    if destination.is_file():
        actual = sha256_file(destination)
        if actual != expected_sha256:
            raise RuntimeError(
                f"Existing reference hash mismatch at {destination}: {actual}"
            )
        return "verified-existing"
    if destination.exists():
        raise RuntimeError(f"Reference destination is not a regular file: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.download")
    if temporary.exists():
        raise RuntimeError(f"Refusing to overwrite partial download: {temporary}")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "FilmSimulation reproducibility bootstrap"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("xb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        actual = sha256_file(temporary)
        if actual != expected_sha256:
            raise RuntimeError(
                f"Downloaded reference hash mismatch for {url}: {actual}"
            )
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return "downloaded-and-verified"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    for key, record in REFERENCES.items():
        status = fetch_reference(
            root / record["path"], record["url"], record["sha256"]
        )
        print(f"Kodak {key}: {status} ({record['sha256']})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
