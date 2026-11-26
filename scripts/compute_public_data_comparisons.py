#!/usr/bin/env python3
"""FS-P6-02: reproducible numerical comparisons for the public-data register.

Reads validation/public_data/evidence_register.csv, computes residuals only for
rows marked comparable (usable_for_residuals=true), and records every other row
as not_evaluable or unavailable with register entry IDs. Does not modify G4,
FS-P4 historical verdicts, or METRICS.json.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTER = ROOT / "validation" / "public_data" / "evidence_register.csv"
DEFAULT_OUTPUT = ROOT / "validation" / "public_data" / "comparisons.json"
DEFAULT_CACHE = ROOT / "cache" / "public_data_repos"

_FINGERPRINT_PATH = ROOT / "scripts" / "fingerprint_public_data.py"
_spec = importlib.util.spec_from_file_location("fingerprint_public_data", _FINGERPRINT_PATH)
fp = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(fp)

LAD_AIM_STATUS_A = {"r": 1.09, "g": 1.06, "b": 1.03}
APD_MATRIX_COMMIT = "3716966fbc82760ed9be38362519689ff2aca811"
APD_MATRIX_PATH = "data/standards/StatusM_to_APD_S-2008-002_AnnexC.json"
STOCK_KEY = "Eastman Kodak 5219"

ENTRY_LOADERS: dict[str, tuple[str, str]] = {
    "PD-042": ("film_scan_calibration", "5219"),
    "PD-048": ("moderates_film_simulator", "5219"),
}


def _load_register(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _metric_record(
    *,
    entry_id: str,
    label: str,
    evidence_class: str,
    lineage: str,
    permitted_use: str,
    evidence_level: str,
    quantity: str,
    outcome: str,
    conditions: dict[str, Any],
    results: list[dict[str, Any]] | None = None,
    reason: str | None = None,
    uncertainty: Any = None,
) -> dict[str, Any]:
    return {
        "entry_id": entry_id,
        "outcome": outcome,
        "label": label,
        "evidence_class": evidence_class,
        "lineage": lineage,
        "permitted_use": permitted_use,
        "evidence_level": evidence_level,
        "quantity": quantity,
        "conditions": conditions,
        "results": results or [],
        "uncertainty": uncertainty,
        "reason": reason,
        "pass_fail": None,
        "independent_validation": False,
    }


def _compare_pd001(cache: Path, profile_5219: fp.Curves) -> dict[str, Any]:
    fsc = fp.ensure_repo(cache, "film_scan_calibration", fp.CANDIDATE_REPOS["film_scan_calibration"][0], APD_MATRIX_COMMIT)
    raw = fp.git_show(fsc, APD_MATRIX_COMMIT, APD_MATRIX_PATH)
    stock = json.loads(raw)["stocks"][STOCK_KEY]
    matrix = np.asarray(stock["matrix"], dtype=float)
    offset = np.asarray(stock["offset"], dtype=float)
    log_exp = profile_5219[("characteristic_curve", "r")][0]
    n = int(log_exp.size)
    if n < 3:
        raise RuntimeError("profile 5219 characteristic curves too sparse for PD-001")
    step = max(1, n // 12)
    along: list[dict[str, Any]] = []
    for idx in range(0, n, step):
        triplet = np.array([profile_5219[("characteristic_curve", c)][1][idx] for c in "rgb"])
        apd_pt = matrix @ triplet + offset
        along.append(
            {
                "log_exposure": round(float(log_exp[idx]), 5),
                "status_m_rgb": [round(float(v), 5) for v in triplet],
                "apd_rgb": [round(float(v), 5) for v in apd_pt],
            }
        )
    mid = n // 2
    status_m = np.array([profile_5219[("characteristic_curve", c)][1][mid] for c in "rgb"])
    apd = matrix @ status_m + offset
    return _metric_record(
        entry_id="PD-001",
        label="implementation cross-check",
        evidence_class="DERIVED_OR_SIMULATED_DATA",
        lineage="unknown",
        permitted_use="implementation_crosscheck",
        evidence_level="V2",
        quantity="density_conversion",
        outcome="compared",
        conditions={
            "source": "S-2008-002 Annex C via film-scan-calibration",
            "commit": APD_MATRIX_COMMIT,
            "densitometry_input": "Status M (profile characteristic_curve densities treated as Status M samples)",
            "densitometry_output": "Academy Printing Density (APD)",
            "model_note": "spektrafilm profile does not implement APD; this records the Academy transform applied to pinned profile samples",
        },
        results=[
            {
                "comparison": "academy_matrix_applied_to_profile_status_m",
                "matrix": stock["matrix"],
                "offset": [round(float(v), 5) for v in offset],
                "example_triplet_status_m": [round(float(v), 5) for v in status_m],
                "example_triplet_apd": [round(float(v), 5) for v in apd],
                "along_curve_samples": along,
            }
        ],
        uncertainty={
            "academy_fit_residuals_5219": stock.get("residuals"),
            "interpretation": "Academy least-squares fit errors on unpublished patch spectra; not a model residual",
        },
    )


def _compare_pd018(profile_2383: fp.Curves) -> dict[str, Any]:
    dc_key = ("characteristic_curve", "g")
    if dc_key not in profile_2383:
        raise RuntimeError("2383 profile missing characteristic curves")
    log_exp, curves = profile_2383[("characteristic_curve", "r")]
    dens = np.stack([profile_2383[("characteristic_curve", ch)][1] for ch in "rgb"], axis=1)
    target = np.array([LAD_AIM_STATUS_A["r"], LAD_AIM_STATUS_A["g"], LAD_AIM_STATUS_A["b"]])
    dist = np.linalg.norm(dens - target, axis=1)
    j = int(np.argmin(dist))
    model_rgb = dens[j]
    residual = model_rgb - target
    return _metric_record(
        entry_id="PD-018",
        label="manufacturer cross-check",
        evidence_class="MANUFACTURER_PUBLISHED_MEASUREMENT",
        lineage="same_primary_source",
        permitted_use="source_conformance",
        evidence_level="V2",
        quantity="lad_aim",
        outcome="compared",
        conditions={
            "published": "Kodak H-61B LAD Status A aim for 2383/3383",
            "process": "ECP-2D",
            "densitometry_reference": "Status A",
            "densitometry_model": "profile density_curves (model channel coefficients; not Status A)",
            "alignment": f"nearest profile sample to published aim (log_exposure index {j})",
        },
        results=[
            {
                "comparison": "lad_aim_vs_nearest_profile_density",
                "reference_status_a_rgb": [LAD_AIM_STATUS_A[c] for c in "rgb"],
                "profile_rgb_at_nearest": [round(float(v), 5) for v in model_rgb],
                "residual_rgb": [round(float(v), 5) for v in residual],
                "rmse": round(float(np.sqrt(np.mean(residual**2))), 5),
                "mae": round(float(np.mean(np.abs(residual))), 5),
                "max_abs": round(float(np.max(np.abs(residual))), 5),
                "log_exposure": round(float(log_exp[j]), 5),
            }
        ],
        uncertainty={
            "densitometry_mismatch": "Published values are Status A; profile curves are not Status A without a declared conversion",
            "interpretation": "Source-conformance proximity only; not physical print measurement",
        },
    )


def _digitization_vs_profile(
    entry_id: str,
    loader_name: str,
    product: str,
    cache: Path,
    profile: fp.Curves,
    row: dict[str, str],
) -> dict[str, Any]:
    url, commit = fp.CANDIDATE_REPOS[loader_name]
    repo = fp.ensure_repo(cache, loader_name, url, commit)
    curves = fp.LOADERS[loader_name](repo, commit, product)
    per_curve: list[dict[str, Any]] = []
    for key, cand in sorted(curves.items()):
        if cand[0].size < 3 or key not in profile:
            continue
        stats = fp.compare(cand, profile[key], allow_x_shift=key[0] == "characteristic_curve")
        aligned = stats.get("aligned") or {}
        per_curve.append(
            {
                "curve": f"{key[0]}:{key[1]}",
                "n_points": int(cand[0].size),
                "aligned_rms": aligned.get("rms"),
                "aligned_max_abs": aligned.get("max_abs"),
                "x_shift": aligned.get("x_shift"),
                "y_offset": aligned.get("y_offset"),
                "reference": "pinned spektrafilm profile (3bb2c2d)",
            }
        )
    return _metric_record(
        entry_id=entry_id,
        label="digitization uncertainty",
        evidence_class=row["evidence_class"],
        lineage=row["lineage"],
        permitted_use=row["permitted_use"],
        evidence_level="V2",
        quantity=row["quantity"],
        outcome="compared",
        conditions={
            "digitizer": loader_name,
            "commit": commit,
            "reference": "pinned profile density_curves / log_sensitivity / channel_density",
            "alignment": "x-shift search for characteristic_curve; mean y-offset removed",
        },
        results=per_curve,
        uncertainty={
            "inter_digitizer_yardstick_D": "0.0006–0.0007 RMS between film-scan-calibration and luce-develop (fingerprints.json)",
            "profile_note": "profile arrays are re-gridded and D-min processed; aligned RMS is the meaningful metric",
        },
    )


def _excluded(row: dict[str, str]) -> dict[str, Any]:
    status = row["status"]
    outcome = "unavailable" if status == "unavailable" else "not_evaluable"
    return {
        "entry_id": row["entry_id"],
        "outcome": outcome,
        "evidence_class": row["evidence_class"],
        "lineage": row["lineage"],
        "permitted_use": row["permitted_use"],
        "status_in_register": status,
        "usable_for_residuals": row["usable_for_residuals"] == "true",
        "reason": row["reason"].strip() or row.get("credibility_reason", ""),
        "product": row["product"],
        "quantity": row["quantity"],
    }


def compute(register_path: Path, cache: Path) -> dict[str, Any]:
    rows = _load_register(register_path)
    by_id = {r["entry_id"]: r for r in rows}
    spk = fp.ensure_repo(cache, "spektrafilm", fp.SPEKTRAFILM["url"], fp.SPEKTRAFILM["profile_commit"])
    profiles = {
        "5219": fp.load_profile(spk, "5219"),
        "2383": fp.load_profile(spk, "2383"),
    }
    entries: list[dict[str, Any]] = []
    comparable_ids = {r["entry_id"] for r in rows if r["usable_for_residuals"] == "true" and r["status"] == "comparable"}

    if "PD-001" in comparable_ids:
        entries.append(_compare_pd001(cache, profiles["5219"]))
    if "PD-018" in comparable_ids:
        entries.append(_compare_pd018(profiles["2383"]))
    for entry_id, (loader, product) in ENTRY_LOADERS.items():
        if entry_id in comparable_ids:
            entries.append(_digitization_vs_profile(entry_id, loader, product, cache, profiles[product], by_id[entry_id]))

    compared_ids = {e["entry_id"] for e in entries}
    for row in rows:
        if row["entry_id"] not in compared_ids:
            entries.append(_excluded(row))

    entries.sort(key=lambda e: e["entry_id"])
    compared = [e for e in entries if e.get("outcome") == "compared"]
    excluded_ne = sum(1 for e in entries if e.get("outcome") == "not_evaluable")
    excluded_un = sum(1 for e in entries if e.get("outcome") == "unavailable")

    return {
        "task": "FS-P6-02",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "register": str(register_path.relative_to(ROOT)),
        "procedure": "docs/phase6/PUBLIC_DATA_STUDY_DEFINITION.md §6",
        "command": "python3 scripts/compute_public_data_comparisons.py",
        "reference_profiles": fp.SPEKTRAFILM,
        "summary": {
            "register_entries": len(rows),
            "compared": len(compared),
            "not_evaluable": excluded_ne,
            "unavailable": excluded_un,
            "independent_validation_comparisons": 0,
            "comparable_entry_ids": sorted(compared_ids),
        },
        "fs_p4_historical": {
            "note": "Six historical FS-P4 published_comparison not_evaluable rows are unchanged by this task",
            "modified": False,
        },
        "independent_physical_validation": {
            "status": "unavailable",
            "reason": "Register has zero INDEPENDENT_PHYSICAL_MEASUREMENT with lineage=none (FS-P6-01 QC)",
        },
        "entries": entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", type=Path, default=DEFAULT_REGISTER)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    payload = compute(args.register, args.cache)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())