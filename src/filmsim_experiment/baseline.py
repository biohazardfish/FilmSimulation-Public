"""Round 1 file hashes, frozen before Round 2 changes those records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .experiment import (
    FILM_KEY,
    INPUT_SHA256,
    PRINT_KEY,
    PROFILE_SHA256,
    UPSTREAM_COMMIT,
    sha256_file,
    write_json,
)


KEY_OUTPUTS = (
    "intermediate/scene_linear_acescg.exr",
    "intermediate/log_e_film.exr",
    "intermediate/cmy_film.exr",
    "intermediate/log_e_print.exr",
    "intermediate/cmy_print.exr",
    "output/5219_to_2383_linear_acescg.exr",
    "output/virtual_negative_scan_linear_acescg.exr",
    "output/5219_to_2383_display_srgb.tif",
    "output/5219_to_2383_display_srgb.jpg",
    "output/virtual_negative_preview_srgb.jpg",
    "output/validation_curves.png",
    "output/EXPERIMENT_REPORT.md",
    "output/manifest.json",
    "intermediate/fixed_parameters.json",
    "intermediate/raw_metadata.json",
)


def build_round1_baseline(root: Path) -> dict[str, Any]:
    root = root.resolve()
    input_path = root / "input" / "_C5A0880.CR3"
    input_hash = sha256_file(input_path)
    if input_hash != INPUT_SHA256:
        raise RuntimeError(f"Input hash mismatch while freezing Round 1: {input_hash}")
    manifest_path = root / "output" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    recorded = {item["path"]: item["sha256"] for item in manifest["artifacts"]}
    outputs = []
    for relative in KEY_OUTPUTS:
        path = root / relative
        if not path.is_file():
            raise RuntimeError(f"Missing Round 1 artifact: {relative}")
        digest = sha256_file(path)
        prior = recorded.get(relative)
        outputs.append({
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": digest,
            "matches_round1_manifest": prior == digest if prior is not None else None,
        })
    payload = {
        "schema_version": 1,
        "round": 1,
        "purpose": "Traceable hashes of the existing Round 1 input, profiles, and key outputs.",
        "audit": {
            "phases_1_to_3": "complete",
            "round1_G4": "neutral ramp behavior check only; not official-curve or real-film validation",
            "phase_5": "not complete in Round 1",
            "round1_G3": "synthetic bit-exact and repeated RAW decode only; full-resolution simulation was not repeated",
        },
        "upstream": {
            "repository": "https://github.com/andreavolpato/spektrafilm",
            "commit": UPSTREAM_COMMIT,
            "package_version": manifest["shared_provenance"]["upstream"]["package_version"],
        },
        "input": {"path": "input/_C5A0880.CR3", "sha256": input_hash},
        "profiles": {
            FILM_KEY: {"sha256": PROFILE_SHA256[FILM_KEY]},
            PRINT_KEY: {"sha256": PROFILE_SHA256[PRINT_KEY]},
        },
        "key_outputs": outputs,
        "round1_validation_gates": manifest["validation_gates"],
    }
    mismatched = [item["path"] for item in outputs if item["matches_round1_manifest"] is False]
    if mismatched:
        raise RuntimeError(f"Round 1 manifest hashes do not match files: {mismatched}")
    return payload


def write_round1_baseline(root: Path, *, confirm: bool = False) -> dict[str, Any]:
    """Explicitly replace the frozen Round 1 descriptor.

    Ordinary experiments and tests must call :func:`build_round1_baseline`.
    Replacing frozen evidence is intentionally gated behind an explicit flag.
    """
    if not confirm:
        raise RuntimeError(
            "Refusing to replace frozen Round 1 evidence without confirm=True; "
            "use scripts/regenerate_round1_baseline.py with its explicit flag"
        )
    payload = build_round1_baseline(root)
    write_json(root.resolve() / "docs" / "round1_baseline.json", payload)
    return payload
