from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import colour
import numpy as np


REQUIRED_METADATA = {
    "stock",
    "batch",
    "process",
    "instrument",
    "measurement_geometry",
    "illuminant",
    "observer",
    "whitepoint",
    "independent_of_profiles",
}


def load_color_reference(path: Path | str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("external color reference schema_version must be 1")
    if payload.get("space") != "CIELAB":
        raise ValueError("external color reference space must be CIELAB")
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    missing = sorted(REQUIRED_METADATA - set(metadata))
    if missing:
        raise ValueError(f"missing color-reference metadata: {missing}")
    samples = payload.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("samples must be a non-empty list")
    seen: set[str] = set()
    for sample in samples:
        sample_id = sample.get("sample_id")
        lab = sample.get("lab")
        if not isinstance(sample_id, str) or not sample_id or sample_id in seen:
            raise ValueError("sample_id must be unique non-empty text")
        seen.add(sample_id)
        if not isinstance(lab, list) or len(lab) != 3 or not np.isfinite(lab).all():
            raise ValueError(f"invalid Lab value for {sample_id}")
    return payload


def evaluate_color_reference(
    reference: dict[str, Any] | None,
    simulated_lab: Mapping[str, list[float] | np.ndarray] | None,
) -> dict[str, Any]:
    if reference is None:
        return {"status": "not_evaluable", "evidence_level": "V3", "reason": "no independent color measurement dataset supplied"}
    metadata = reference["metadata"]
    if not metadata["independent_of_profiles"]:
        return {"status": "not_evaluable", "evidence_level": "V2", "reason": "reference is not independent of profile construction"}
    if not simulated_lab:
        return {"status": "not_evaluable", "evidence_level": "V3", "reason": "no matched simulated samples supplied"}
    values = []
    missing = []
    for sample in reference["samples"]:
        sample_id = sample["sample_id"]
        if sample_id not in simulated_lab:
            missing.append(sample_id)
            continue
        measured = np.asarray(sample["lab"], dtype=np.float64)
        simulated = np.asarray(simulated_lab[sample_id], dtype=np.float64)
        if simulated.shape != (3,) or not np.isfinite(simulated).all():
            raise ValueError(f"invalid simulated Lab value for {sample_id}")
        values.append(float(colour.difference.delta_E_CIE2000(measured, simulated)))
    if missing or not values:
        return {"status": "not_evaluable", "evidence_level": "V3", "reason": f"unmatched sample IDs: {missing}"}
    array = np.asarray(values)
    return {
        "status": "pass",
        "evidence_level": "V3",
        "metric": "CIEDE2000",
        "unit": "Delta E00",
        "count": int(array.size),
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "p95": float(np.percentile(array, 95)),
        "maximum": float(np.max(array)),
        "conditions": {
            key: metadata[key]
            for key in ("illuminant", "observer", "whitepoint", "instrument", "measurement_geometry")
        },
    }
