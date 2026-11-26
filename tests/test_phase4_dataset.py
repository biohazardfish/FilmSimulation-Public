from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from scripts.validate_phase4_dataset import (
    DENSITY_FIELDS,
    PRINT_MAP_FIELDS,
    SPECTRAL_FIELDS,
    sha256_file,
    validate_dataset,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_phase4_dataset.py"


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _rows(root: Path, name: str) -> list[dict[str, str]]:
    with (root / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _rehash(root: Path) -> None:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name in ("density.csv", "print_map.csv", "spectral_transmittance.csv"):
        manifest["files"][name]["sha256"] = sha256_file(root / name)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _dataset(root: Path) -> Path:
    root.mkdir()
    density_rows: list[dict[str, object]] = []
    for sample_id, material, batch, status, instrument in (
        ("N-01", "5219", "5219-BATCH", "status_M", "DENS-M"),
        ("P-01", "2383", "2383-BATCH", "status_A", "DENS-A"),
    ):
        for channel, value in zip("RGB", (0.4, 0.5, 0.6), strict=True):
            density_rows.append(
                {
                    "run_id": "G4-RUN-01",
                    "sample_id": sample_id,
                    "material": material,
                    "batch_id": batch,
                    "strip_id": f"{material}-STRIP-01",
                    "step_id": "STEP-01",
                    "nominal_log_exposure": -1.0,
                    "measured_log_exposure": -0.98,
                    "exposure_unit": (
                        "log10_lux_seconds" if material == "5219" else "relative_print_exposure"
                    ),
                    "densitometry_status": status,
                    "channel": channel,
                    "density": value,
                    "repeat_id": "R1",
                    "instrument_id": instrument,
                }
            )
    spectral_rows: list[dict[str, object]] = []
    for sample_id, material, batch in (
        ("N-01", "5219", "5219-BATCH"),
        ("P-01", "2383", "2383-BATCH"),
    ):
        for wavelength, value in ((380, 0.3), (580, 0.2), (780, 0.1)):
            spectral_rows.append(
                {
                    "run_id": "G4-RUN-01",
                    "sample_id": sample_id,
                    "material": material,
                    "batch_id": batch,
                    "strip_id": f"{material}-STRIP-01",
                    "step_id": "STEP-01",
                    "wavelength_nm": wavelength,
                    "transmittance": value,
                    "repeat_id": "R1",
                    "instrument_id": "SPEC-01",
                }
            )
    map_rows = [
        {
            "run_id": "G4-RUN-01",
            "negative_sample_id": "N-01",
            "print_sample_id": "P-01",
            "printer_light_r": 25,
            "printer_light_g": 25,
            "printer_light_b": 25,
            "printer_exposure": 1.0,
            "exposure_unit": "relative_print_exposure",
        }
    ]
    _write_csv(root / "density.csv", DENSITY_FIELDS, density_rows)
    _write_csv(root / "print_map.csv", PRINT_MAP_FIELDS, map_rows)
    _write_csv(root / "spectral_transmittance.csv", SPECTRAL_FIELDS, spectral_rows)
    manifest = {
        "schema_version": 1,
        "run_id": "G4-RUN-01",
        "project": "FilmSimulation",
        "measurement_scope": "independent_physical_validation",
        "film": {
            "material": "5219",
            "stock": "KODAK VISION3 500T Color Negative Film 5219",
            "batch_id": "5219-BATCH",
            "format": "35 mm",
        },
        "print": {
            "material": "2383",
            "stock": "KODAK VISION Color Print Film 2383",
            "batch_id": "2383-BATCH",
            "format": "35 mm",
        },
        "sensitometer": {
            "instrument_id": "SENS-01",
            "calibration_id": "CAL-SENS-01",
            "calibration_date": "2026-11-01",
            "illuminant_cct_k": 3200,
            "step_wedge_id": "WEDGE-01",
            "exposure_unit": "log10_lux_seconds",
            "measurement_uncertainty": "reported by lab",
        },
        "processes": {
            "negative": {
                "name": "ECN-2",
                "run_id": "ECN2-01",
                "time_seconds": 180,
                "temperature_c": 41.1,
                "chemistry_lot": "CHEM-N",
                "deviations": "none",
            },
            "print": {
                "name": "ECP-2D",
                "run_id": "ECP2D-01",
                "time_seconds": 120,
                "temperature_c": 36.7,
                "chemistry_lot": "CHEM-P",
                "deviations": "none",
            },
        },
        "printer": {
            "instrument_id": "PRINTER-01",
            "run_id": "PRINT-EXPOSURE-01",
            "light_unit": "printer_light_units",
            "exposure_unit": "relative_print_exposure",
        },
        "densitometers": {
            "status_m": {
                "instrument_id": "DENS-M",
                "calibration_id": "CAL-M",
                "calibration_date": "2026-11-01",
                "measurement_uncertainty": "reported by lab",
            },
            "status_a": {
                "instrument_id": "DENS-A",
                "calibration_id": "CAL-A",
                "calibration_date": "2026-11-01",
                "measurement_uncertainty": "reported by lab",
            },
        },
        "spectrophotometer": {
            "instrument_id": "SPEC-01",
            "calibration_id": "CAL-SPEC",
            "calibration_date": "2026-11-01",
            "native_wavelength_min_nm": 380,
            "native_wavelength_max_nm": 780,
            "native_sampling_interval_nm": 5,
            "spectral_bandwidth_nm": 5,
            "measurement_uncertainty": "reported by lab",
        },
        "files": {
            name: {"sha256": sha256_file(root / name)}
            for name in ("density.csv", "print_map.csv", "spectral_transmittance.csv")
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return root


def test_valid_dataset_has_descriptive_counts_and_no_accuracy_score(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "valid")
    report = validate_dataset(root)
    assert report["status"] == "valid", report["errors"]
    assert report["counts"] == {
        "density_rows": 6,
        "spectral_rows": 6,
        "print_mappings": 1,
        "samples_5219": 1,
        "samples_2383": 1,
        "spectral_samples": 2,
    }
    assert all("score" not in key.lower() for key in report)


def test_missing_calibration_is_invalid(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "missing-calibration")
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["densitometers"]["status_m"]["calibration_id"] = ""
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report = validate_dataset(root)
    assert report["status"] == "invalid"
    assert any("status_m.calibration_id" in error for error in report["errors"])


def test_wrong_densitometry_status_is_invalid(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "wrong-status")
    rows = _rows(root, "density.csv")
    rows[0]["densitometry_status"] = "status_A"
    _write_csv(root / "density.csv", DENSITY_FIELDS, rows)
    _rehash(root)
    assert any("5219 requires status_M" in error for error in validate_dataset(root)["errors"])


def test_broken_print_mapping_is_invalid(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "broken-map")
    rows = _rows(root, "print_map.csv")
    rows[0]["negative_sample_id"] = "UNKNOWN"
    _write_csv(root / "print_map.csv", PRINT_MAP_FIELDS, rows)
    _rehash(root)
    assert any("negative_sample_id" in error for error in validate_dataset(root)["errors"])


def test_nonfinite_value_is_invalid(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "nonfinite")
    rows = _rows(root, "density.csv")
    rows[0]["density"] = "NaN"
    _write_csv(root / "density.csv", DENSITY_FIELDS, rows)
    _rehash(root)
    assert any("density must be finite" in error for error in validate_dataset(root)["errors"])


def test_duplicate_identity_is_invalid(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "duplicate")
    rows = _rows(root, "density.csv")
    rows.append(dict(rows[0]))
    _write_csv(root / "density.csv", DENSITY_FIELDS, rows)
    _rehash(root)
    assert any("duplicate row identity" in error for error in validate_dataset(root)["errors"])


def test_insufficient_spectral_coverage_is_invalid(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "coverage")
    rows = _rows(root, "spectral_transmittance.csv")
    for row in rows:
        if row["sample_id"] == "N-01" and row["wavelength_nm"] == "380":
            row["wavelength_nm"] = "400"
    _write_csv(root / "spectral_transmittance.csv", SPECTRAL_FIELDS, rows)
    _rehash(root)
    assert any("must cover 380 through 780" in error for error in validate_dataset(root)["errors"])


def test_hash_mismatch_is_invalid(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "hash")
    with (root / "density.csv").open("a", encoding="utf-8") as handle:
        handle.write("\n")
    assert any("SHA-256" in error for error in validate_dataset(root)["errors"])


def test_cli_exit_codes_and_report_file(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "cli")
    report_path = tmp_path / "report.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(root), "--report", str(report_path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "valid"
    assert json.loads(report_path.read_text())["status"] == "valid"

    (root / "density.csv").unlink()
    invalid = subprocess.run(
        [sys.executable, str(SCRIPT), str(root)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert invalid.returncode == 2
    assert json.loads(invalid.stdout)["status"] == "invalid"

