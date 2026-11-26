#!/usr/bin/env python3
"""Validate a FilmSimulation Phase 4 physical-measurement dataset.

The validator checks structure, provenance, mappings, and numeric integrity. It
does not compare the measurements with the model and never produces a physical
accuracy score.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence


DENSITY_FIELDS = (
    "run_id",
    "sample_id",
    "material",
    "batch_id",
    "strip_id",
    "step_id",
    "nominal_log_exposure",
    "measured_log_exposure",
    "exposure_unit",
    "densitometry_status",
    "channel",
    "density",
    "repeat_id",
    "instrument_id",
)
PRINT_MAP_FIELDS = (
    "run_id",
    "negative_sample_id",
    "print_sample_id",
    "printer_light_r",
    "printer_light_g",
    "printer_light_b",
    "printer_exposure",
    "exposure_unit",
)
SPECTRAL_FIELDS = (
    "run_id",
    "sample_id",
    "material",
    "batch_id",
    "strip_id",
    "step_id",
    "wavelength_nm",
    "transmittance",
    "repeat_id",
    "instrument_id",
)
CSV_FILES = {
    "density.csv": DENSITY_FIELDS,
    "print_map.csv": PRINT_MAP_FIELDS,
    "spectral_transmittance.csv": SPECTRAL_FIELDS,
}
MATERIALS = {"5219", "2383"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _placeholder(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return not stripped or stripped.startswith("REQUIRED_") or stripped == "YYYY-MM-DD"
    return False


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _valid_date(value: Any) -> bool:
    if not isinstance(value, str) or _placeholder(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _nested(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _require_text(payload: dict[str, Any], paths: Iterable[str], errors: list[str]) -> None:
    for path in paths:
        if _placeholder(_nested(payload, path)):
            errors.append(f"manifest: missing required value {path}")


def _load_csv(path: Path, expected: tuple[str, ...], errors: list[str]) -> list[dict[str, str]]:
    if not path.is_file():
        errors.append(f"missing required file: {path.name}")
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            actual = tuple(reader.fieldnames or ())
            if actual != expected:
                errors.append(
                    f"{path.name}: header mismatch; expected {list(expected)}, got {list(actual)}"
                )
                return []
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        errors.append(f"{path.name}: cannot read CSV: {exc}")
        return []
    if not rows:
        errors.append(f"{path.name}: no data rows")
    return rows


def _row_required(row: dict[str, str], fields: Iterable[str], label: str,
                  row_number: int, errors: list[str]) -> bool:
    missing = [field for field in fields if _placeholder(row.get(field))]
    if missing:
        errors.append(f"{label} row {row_number}: missing values {', '.join(missing)}")
        return False
    return True


def _validate_manifest(manifest: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    if manifest.get("schema_version") != 1:
        errors.append("manifest: schema_version must be 1")
    if manifest.get("project") != "FilmSimulation":
        errors.append("manifest: project must be FilmSimulation")
    if manifest.get("measurement_scope") != "independent_physical_validation":
        errors.append(
            "manifest: measurement_scope must be independent_physical_validation"
        )
    _require_text(
        manifest,
        (
            "run_id",
            "film.stock",
            "film.batch_id",
            "film.format",
            "print.stock",
            "print.batch_id",
            "print.format",
            "sensitometer.instrument_id",
            "sensitometer.calibration_id",
            "sensitometer.step_wedge_id",
            "sensitometer.exposure_unit",
            "sensitometer.measurement_uncertainty",
            "processes.negative.run_id",
            "processes.negative.chemistry_lot",
            "processes.negative.deviations",
            "processes.print.run_id",
            "processes.print.chemistry_lot",
            "processes.print.deviations",
            "printer.instrument_id",
            "printer.run_id",
            "printer.light_unit",
            "printer.exposure_unit",
            "densitometers.status_m.instrument_id",
            "densitometers.status_m.calibration_id",
            "densitometers.status_m.measurement_uncertainty",
            "densitometers.status_a.instrument_id",
            "densitometers.status_a.calibration_id",
            "densitometers.status_a.measurement_uncertainty",
            "spectrophotometer.instrument_id",
            "spectrophotometer.calibration_id",
            "spectrophotometer.measurement_uncertainty",
        ),
        errors,
    )
    if _nested(manifest, "film.material") != "5219":
        errors.append("manifest: film.material must be 5219")
    if _nested(manifest, "print.material") != "2383":
        errors.append("manifest: print.material must be 2383")
    if _nested(manifest, "film.format") != "35 mm" or _nested(manifest, "print.format") != "35 mm":
        errors.append("manifest: film and print format must be 35 mm")
    if _finite(_nested(manifest, "sensitometer.illuminant_cct_k")) != 3200.0:
        errors.append("manifest: sensitometer illuminant_cct_k must be 3200")
    if _nested(manifest, "processes.negative.name") != "ECN-2":
        errors.append("manifest: negative process name must be ECN-2")
    if _nested(manifest, "processes.print.name") != "ECP-2D":
        errors.append("manifest: print process name must be ECP-2D")
    for process in ("negative", "print"):
        for field in ("time_seconds", "temperature_c"):
            if _finite(_nested(manifest, f"processes.{process}.{field}")) is None:
                errors.append(f"manifest: processes.{process}.{field} must be finite")
    for path in (
        "sensitometer.calibration_date",
        "densitometers.status_m.calibration_date",
        "densitometers.status_a.calibration_date",
        "spectrophotometer.calibration_date",
    ):
        if not _valid_date(_nested(manifest, path)):
            errors.append(f"manifest: {path} must be an ISO date")
    low = _finite(_nested(manifest, "spectrophotometer.native_wavelength_min_nm"))
    high = _finite(_nested(manifest, "spectrophotometer.native_wavelength_max_nm"))
    if low is None or low > 380:
        errors.append("manifest: spectrophotometer native range must begin at or below 380 nm")
    if high is None or high < 780:
        errors.append("manifest: spectrophotometer native range must end at or above 780 nm")
    for field in ("native_sampling_interval_nm", "spectral_bandwidth_nm"):
        value = _finite(_nested(manifest, f"spectrophotometer.{field}"))
        if value is None or value <= 0:
            errors.append(f"manifest: spectrophotometer.{field} must be positive")
    return {
        "run_id": manifest.get("run_id"),
        "film_batch": _nested(manifest, "film.batch_id"),
        "print_batch": _nested(manifest, "print.batch_id"),
        "status_m_instrument": _nested(manifest, "densitometers.status_m.instrument_id"),
        "status_a_instrument": _nested(manifest, "densitometers.status_a.instrument_id"),
        "spectral_instrument": _nested(manifest, "spectrophotometer.instrument_id"),
        "negative_exposure_unit": _nested(manifest, "sensitometer.exposure_unit"),
        "print_exposure_unit": _nested(manifest, "printer.exposure_unit"),
    }


def _validate_hashes(root: Path, manifest: dict[str, Any], errors: list[str]) -> None:
    files = manifest.get("files")
    if not isinstance(files, dict):
        errors.append("manifest: files must be an object")
        return
    for name in CSV_FILES:
        entry = files.get(name)
        expected = entry.get("sha256") if isinstance(entry, dict) else None
        if _placeholder(expected):
            errors.append(f"manifest: files.{name}.sha256 is required")
            continue
        path = root / name
        if path.is_file() and str(expected).lower() != sha256_file(path):
            errors.append(f"{name}: SHA-256 does not match manifest")


def _validate_density(rows: list[dict[str, str]], context: dict[str, Any],
                      errors: list[str]) -> dict[str, tuple[str, str, str, str]]:
    identities: set[tuple[str, ...]] = set()
    sample_info: dict[str, tuple[str, str, str, str]] = {}
    channels: dict[str, set[str]] = defaultdict(set)
    for row_number, row in enumerate(rows, start=2):
        if not _row_required(row, DENSITY_FIELDS, "density.csv", row_number, errors):
            continue
        for field in ("nominal_log_exposure", "measured_log_exposure", "density"):
            number = _finite(row[field])
            if number is None:
                errors.append(f"density.csv row {row_number}: {field} must be finite")
            elif field == "density" and number < 0:
                errors.append(f"density.csv row {row_number}: density must be nonnegative")
        material = row["material"]
        if material not in MATERIALS:
            errors.append(f"density.csv row {row_number}: invalid material {material!r}")
            continue
        expected_batch = context["film_batch"] if material == "5219" else context["print_batch"]
        if row["batch_id"] != expected_batch:
            errors.append(f"density.csv row {row_number}: batch_id disagrees with manifest")
        expected_status = "status_M" if material == "5219" else "status_A"
        if row["densitometry_status"] != expected_status:
            errors.append(
                f"density.csv row {row_number}: {material} requires {expected_status}"
            )
        expected_instrument = (
            context["status_m_instrument"] if material == "5219" else context["status_a_instrument"]
        )
        if row["instrument_id"] != expected_instrument:
            errors.append(f"density.csv row {row_number}: instrument_id disagrees with manifest")
        expected_unit = (
            context["negative_exposure_unit"] if material == "5219" else context["print_exposure_unit"]
        )
        if row["exposure_unit"] != expected_unit:
            errors.append(f"density.csv row {row_number}: exposure_unit disagrees with manifest")
        if row["channel"] not in {"R", "G", "B"}:
            errors.append(f"density.csv row {row_number}: channel must be R, G, or B")
        identity = (
            row["run_id"], row["sample_id"], row["strip_id"], row["step_id"],
            row["repeat_id"], row["channel"],
        )
        if identity in identities:
            errors.append(f"density.csv row {row_number}: duplicate row identity")
        identities.add(identity)
        metadata = (material, row["batch_id"], row["strip_id"], row["step_id"])
        previous = sample_info.setdefault(row["sample_id"], metadata)
        if previous != metadata:
            errors.append(f"density.csv row {row_number}: sample metadata conflict")
        channels[row["sample_id"]].add(row["channel"])
        if row["run_id"] != context["run_id"]:
            errors.append(f"density.csv row {row_number}: run_id disagrees with manifest")
    for sample_id, observed in channels.items():
        if observed != {"R", "G", "B"}:
            errors.append(f"density.csv: sample {sample_id} must contain RGB channels")
    return sample_info


def _validate_spectral(rows: list[dict[str, str]], context: dict[str, Any],
                       density_samples: dict[str, tuple[str, str, str, str]],
                       errors: list[str]) -> dict[str, tuple[float, float]]:
    identities: set[tuple[str, ...]] = set()
    sample_info: dict[str, tuple[str, str, str, str]] = {}
    wavelengths: dict[str, list[float]] = defaultdict(list)
    for row_number, row in enumerate(rows, start=2):
        if not _row_required(row, SPECTRAL_FIELDS, "spectral_transmittance.csv", row_number, errors):
            continue
        wavelength = _finite(row["wavelength_nm"])
        transmittance = _finite(row["transmittance"])
        if wavelength is None:
            errors.append(f"spectral_transmittance.csv row {row_number}: wavelength_nm must be finite")
        if transmittance is None:
            errors.append(f"spectral_transmittance.csv row {row_number}: transmittance must be finite")
        elif not 0 <= transmittance <= 1:
            errors.append(
                f"spectral_transmittance.csv row {row_number}: transmittance must be within 0..1"
            )
        material = row["material"]
        if material not in MATERIALS:
            errors.append(f"spectral_transmittance.csv row {row_number}: invalid material")
            continue
        expected_batch = context["film_batch"] if material == "5219" else context["print_batch"]
        if row["batch_id"] != expected_batch:
            errors.append(
                f"spectral_transmittance.csv row {row_number}: batch_id disagrees with manifest"
            )
        if row["instrument_id"] != context["spectral_instrument"]:
            errors.append(
                f"spectral_transmittance.csv row {row_number}: instrument_id disagrees with manifest"
            )
        if row["run_id"] != context["run_id"]:
            errors.append(
                f"spectral_transmittance.csv row {row_number}: run_id disagrees with manifest"
            )
        identity = (
            row["run_id"], row["sample_id"], row["strip_id"], row["step_id"],
            row["repeat_id"], row["wavelength_nm"],
        )
        if identity in identities:
            errors.append(f"spectral_transmittance.csv row {row_number}: duplicate row identity")
        identities.add(identity)
        metadata = (material, row["batch_id"], row["strip_id"], row["step_id"])
        previous = sample_info.setdefault(row["sample_id"], metadata)
        if previous != metadata:
            errors.append(f"spectral_transmittance.csv row {row_number}: sample metadata conflict")
        if wavelength is not None:
            wavelengths[row["sample_id"]].append(wavelength)
    if set(sample_info) != set(density_samples):
        missing_spectral = sorted(set(density_samples) - set(sample_info))
        missing_density = sorted(set(sample_info) - set(density_samples))
        if missing_spectral:
            errors.append(f"spectral data missing for density samples: {', '.join(missing_spectral)}")
        if missing_density:
            errors.append(f"density data missing for spectral samples: {', '.join(missing_density)}")
    for sample_id in set(sample_info) & set(density_samples):
        if sample_info[sample_id] != density_samples[sample_id]:
            errors.append(f"sample {sample_id}: density and spectral metadata disagree")
    coverage: dict[str, tuple[float, float]] = {}
    for sample_id, values in wavelengths.items():
        low, high = min(values), max(values)
        coverage[sample_id] = (low, high)
        if low > 380 or high < 780:
            errors.append(
                f"spectral_transmittance.csv: sample {sample_id} must cover 380 through 780 nm"
            )
    return coverage


def _validate_print_map(rows: list[dict[str, str]], context: dict[str, Any],
                        samples: dict[str, tuple[str, str, str, str]], errors: list[str]) -> None:
    identities: set[tuple[str, str]] = set()
    print_ids: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        if not _row_required(row, PRINT_MAP_FIELDS, "print_map.csv", row_number, errors):
            continue
        for field in ("printer_light_r", "printer_light_g", "printer_light_b", "printer_exposure"):
            if _finite(row[field]) is None:
                errors.append(f"print_map.csv row {row_number}: {field} must be finite")
        negative_id = row["negative_sample_id"]
        print_id = row["print_sample_id"]
        if samples.get(negative_id, (None, None))[0] != "5219":
            errors.append(f"print_map.csv row {row_number}: negative_sample_id must resolve to 5219")
        if samples.get(print_id, (None, None))[0] != "2383":
            errors.append(f"print_map.csv row {row_number}: print_sample_id must resolve to 2383")
        identity = (negative_id, print_id)
        if identity in identities or print_id in print_ids:
            errors.append(f"print_map.csv row {row_number}: duplicate mapping identity")
        identities.add(identity)
        print_ids.add(print_id)
        if row["run_id"] != context["run_id"]:
            errors.append(f"print_map.csv row {row_number}: run_id disagrees with manifest")
        if row["exposure_unit"] != context["print_exposure_unit"]:
            errors.append(f"print_map.csv row {row_number}: exposure_unit disagrees with manifest")
    expected_prints = {sample_id for sample_id, info in samples.items() if info[0] == "2383"}
    if print_ids != expected_prints:
        missing = sorted(expected_prints - print_ids)
        extra = sorted(print_ids - expected_prints)
        if missing:
            errors.append(f"print_map.csv: unmapped 2383 samples: {', '.join(missing)}")
        if extra:
            errors.append(f"print_map.csv: unknown print samples: {', '.join(extra)}")


def validate_dataset(dataset_dir: Path | str) -> dict[str, Any]:
    """Return a JSON-serializable validation report without changing the dataset."""

    root = Path(dataset_dir)
    errors: list[str] = []
    manifest_path = root / "manifest.json"
    manifest: dict[str, Any] = {}
    if not manifest_path.is_file():
        errors.append("missing required file: manifest.json")
    else:
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                manifest = loaded
            else:
                errors.append("manifest.json: root must be an object")
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"manifest.json: cannot read JSON: {exc}")

    context = _validate_manifest(manifest, errors)
    rows = {
        name: _load_csv(root / name, fields, errors)
        for name, fields in CSV_FILES.items()
    }
    _validate_hashes(root, manifest, errors)
    density_samples = _validate_density(rows["density.csv"], context, errors)
    coverage = _validate_spectral(
        rows["spectral_transmittance.csv"], context, density_samples, errors
    )
    _validate_print_map(rows["print_map.csv"], context, density_samples, errors)

    material_counts = defaultdict(int)
    for sample_metadata in density_samples.values():
        material_counts[sample_metadata[0]] += 1
    return {
        "schema_version": 1,
        "dataset": str(root),
        "status": "valid" if not errors else "invalid",
        "errors": errors,
        "counts": {
            "density_rows": len(rows["density.csv"]),
            "spectral_rows": len(rows["spectral_transmittance.csv"]),
            "print_mappings": len(rows["print_map.csv"]),
            "samples_5219": material_counts["5219"],
            "samples_2383": material_counts["2383"],
            "spectral_samples": len(coverage),
        },
        "note": "Structural and provenance validation only; no physical accuracy score is computed.",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("--report", type=Path, help="also write the JSON report to this path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = validate_dataset(args.dataset_dir)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    return 0 if report["status"] == "valid" else 2


if __name__ == "__main__":
    raise SystemExit(main())

