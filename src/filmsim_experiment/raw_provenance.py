"""Additive RAW-input provenance without rewriting frozen experiment outputs."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

import numpy as np
import rawpy


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_raw_identify(text: str) -> dict[str, Any]:
    """Parse the stable fields needed from ``raw-identify -v`` output."""

    patterns = {
        "raw_image_count": r"^Number of raw images:\s*(\d+)\s*$",
        "full_size": r"^Full size:\s*(\d+)\s*x\s*(\d+)\s*$",
        "image_size": r"^Image size:\s*(\d+)\s*x\s*(\d+)\s*$",
        "output_size": r"^Output size:\s*(\d+)\s*x\s*(\d+)\s*$",
    }
    result: dict[str, Any] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.MULTILINE)
        if not match:
            continue
        values = [int(value) for value in match.groups()]
        result[key] = values[0] if len(values) == 1 else values
    if "raw_image_count" not in result:
        raise ValueError("raw-identify output did not contain a RAW image count")
    return result


def _homebrew_libraw_version(executable: str) -> str | None:
    parts = Path(executable).resolve().parts
    for index, part in enumerate(parts[:-1]):
        if part.lower() == "libraw" and index + 1 < len(parts):
            candidate = parts[index + 1]
            if re.fullmatch(r"\d+(?:\.\d+)+", candidate):
                return candidate
    return None


def _raw_identify(path: Path, executable: str) -> dict[str, Any]:
    resolved = shutil.which(executable)
    if resolved is None:
        return {
            "status": "not_evaluable",
            "reason": f"{executable} is not available",
            "raw_image_count": None,
        }
    try:
        completed = subprocess.run(
            [resolved, "-v", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        parsed = parse_raw_identify(completed.stdout)
    except (OSError, subprocess.CalledProcessError, UnicodeError, ValueError) as exc:
        return {
            "status": "not_evaluable",
            "reason": f"raw-identify probe failed: {exc}",
            "raw_image_count": None,
        }
    return {
        "status": "measured",
        "tool": "raw-identify",
        "libraw_cli_version": _homebrew_libraw_version(resolved) or "not reported",
        **parsed,
    }


def _exiftool(path: Path, executable: str) -> tuple[dict[str, Any], str]:
    version = subprocess.run(
        [executable, "-ver"], check=True, capture_output=True, text=True,
    ).stdout.strip()
    tags = (
        "Make", "Model", "DualPixelRaw", "RecordMode", "Quality",
        "CanonImageWidth", "CanonImageHeight", "SensorWidth", "SensorHeight",
    )
    completed = subprocess.run(
        [executable, "-api", "RequestAll=3", "-j", "-n", *[f"-{tag}" for tag in tags], str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    records = json.loads(completed.stdout)
    if not records:
        raise RuntimeError("ExifTool returned no metadata record")
    return records[0], version


def collect_raw_input_provenance(
    raw_path: Path,
    *,
    display_path: str,
    exiftool_executable: str = "exiftool",
    raw_identify_executable: str = "raw-identify",
) -> dict[str, Any]:
    """Inspect the RAW container and state exactly what the decoder uses."""

    raw_path = raw_path.resolve()
    exif, exiftool_version = _exiftool(raw_path, exiftool_executable)
    raw_probe = _raw_identify(raw_path, raw_identify_executable)
    with rawpy.imread(str(raw_path)) as raw:
        decoder = {
            "raw_type": str(raw.raw_type),
            "raw_pattern": np.asarray(raw.raw_pattern).tolist(),
            "color_description": (
                raw.color_desc.decode("ascii", "replace")
                if isinstance(raw.color_desc, bytes)
                else str(raw.color_desc)
            ),
            "raw_image_visible_shape": list(raw.raw_image_visible.shape),
            "selected_raw_image_index": 0,
            "selection": "LibRaw/rawpy default image (shot_select=0)",
            "auxiliary_dual_pixel_data_used": False,
        }
    dual_pixel_value = exif.get("DualPixelRaw")
    return {
        "schema_version": 1,
        "input": {
            "path": display_path,
            "sha256": _sha256(raw_path),
        },
        "capture": {
            "make": exif.get("Make"),
            "model": exif.get("Model"),
            "record_mode": exif.get("RecordMode"),
            "quality": exif.get("Quality"),
            "dual_pixel_raw": bool(dual_pixel_value) if dual_pixel_value is not None else None,
        },
        "container": raw_probe,
        "decoder": {
            "software": {
                "rawpy": rawpy.__version__,
                "libraw": ".".join(str(value) for value in rawpy.libraw_version),
                "exiftool": exiftool_version,
                "colour-science": importlib.metadata.version("colour-science"),
            },
            **decoder,
        },
        "claim_boundary": (
            "The source is Dual Pixel RAW, but FilmSimulation decodes only LibRaw/rawpy's "
            "default Bayer image. The auxiliary dual-pixel image is not selected, differenced, "
            "or used for depth, viewpoint, resolution, ghosting, or spectral estimation."
        ),
    }
