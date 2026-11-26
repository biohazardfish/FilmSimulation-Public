from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from filmsim_experiment.experiment import (
    FILM_KEY,
    PRINT_KEY,
    PROFILE_SHA256,
    UPSTREAM_COMMIT,
    build_params,
    serialize_params,
    sha256_file,
    write_json,
)

from .analysis import (
    artifact_inventory,
    build_phase2_params,
    environment_record,
    plot_performance,
    profile_spectral_audit,
    protected_inventory,
    published_reference_metrics,
    run_benchmarks,
    run_sensitometry,
    tile_comparison,
    validate_pins,
)
from .color_validation import evaluate_color_reference, load_color_reference
from .metrics import metric_record
from .reports import write_reports


def _spectral_plot(params, path: Path) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    for row, (title, profile) in enumerate((("5219 / 500T", params.film), ("2383", params.print))):
        wavelength = profile.data.wavelengths
        for index, color in enumerate(("tab:red", "tab:green", "tab:blue")):
            axes[row, 0].plot(wavelength, profile.data.log_sensitivity[:, index], color=color, label=("R", "G", "B")[index])
        for index, color in enumerate(("tab:cyan", "tab:pink", "gold")):
            values = profile.data.channel_density[:, index]
            finite = np.isfinite(values)
            axes[row, 1].plot(wavelength[finite], values[finite], color=color, label=("C", "M", "Y")[index])
        axes[row, 0].set_title(f"{title}: profile log sensitivity")
        axes[row, 1].set_title(f"{title}: channel spectral-density basis")
        for axis in axes[row]:
            axis.set_xlabel("wavelength (nm)"); axis.grid(alpha=0.2); axis.legend()
    figure.suptitle("Pinned profile arrays; not independent measurements")
    figure.savefig(path, dpi=160)
    plt.close(figure)


def run_phase2(
    root: Path,
    *,
    film_profile: str = FILM_KEY,
    print_profile: str = PRINT_KEY,
    sizes: list[int] | None = None,
    reference_data: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    out = (output_dir or (root / "output/phase2")).resolve()
    docs = root / "docs/phase2"
    out.mkdir(parents=True, exist_ok=True)
    docs.mkdir(parents=True, exist_ok=True)
    sizes = sizes or [256, 512, 1024, 2048]

    before = protected_inventory(root)
    if not before["all_match"]:
        raise RuntimeError("Phase I or existing Round 2 integrity failed before Phase II")
    pins = validate_pins(root, film_profile, print_profile)
    params = build_phase2_params(film_profile, print_profile)
    profile_hashes = {key: row["sha256"] for key, row in pins["profiles"].items() if isinstance(row, dict) and "sha256" in row}
    write_json(out / "fixed_parameters.json", serialize_params(params, profile_hashes))
    params_hash = sha256_file(out / "fixed_parameters.json")

    print("Phase II: sensitometry", flush=True)
    sens = run_sensitometry(root, out, film_profile, print_profile)
    write_json(out / "sensitometry_metrics.json", sens)
    digested = __import__("spektrafilm", fromlist=["digest_params"]).digest_params(build_phase2_params(film_profile, print_profile))
    spectral = profile_spectral_audit(digested)
    write_json(out / "spectral_profile_audit.json", spectral)
    _spectral_plot(digested, out / "spectral_profiles.png")

    published = published_reference_metrics(root)
    uncertainty = json.loads((root / "validation/uncertainty_metrics.json").read_text(encoding="utf-8"))
    model_spread = uncertainty["model_spread"]
    metrics = list(sens["metrics"]) + published
    metrics.append(metric_record(
        "B.rgb_to_spectrum.model_spread", quantity=model_spread["quantity"], status="pass", evidence_level="V1",
        value={key: model_spread[key] for key in ("rmse", "max_abs", "mean_abs_per_channel")}, unit="scene-linear ACEScg",
        reference=f"{model_spread['reference_method']} versus {model_spread['other_method']}", independent=False,
        reason="method sensitivity only; explicitly not error relative to real film",
    ))

    reference = load_color_reference(reference_data) if reference_data else None
    color = evaluate_color_reference(reference, None)
    metrics.append(metric_record(
        "B.color.independent_delta_e00", quantity="CIEDE2000 against independent real-film measurements",
        status=color["status"], evidence_level=color["evidence_level"], value=None, unit="Delta E00",
        independent=bool(reference and reference["metadata"]["independent_of_profiles"]), reason=color["reason"],
    ))

    print("Phase II: performance benchmarks", flush=True)
    bench = run_benchmarks(root, sizes)
    write_json(out / "performance_benchmarks.json", bench)
    plot_performance(bench, out / "performance_scaling.png")
    for row in bench["results"]:
        metrics.append(metric_record(
            f"C.performance.{row['size']}.{row['branch']}.determinism",
            quantity="repeated benchmark output determinism", status="pass" if row["deterministic"] and row["finite"] else "fail",
            evidence_level="V1", value={"hashes": row["deterministic_hashes"], "finite": row["finite"]}, unit="boolean",
            conditions={"size": row["size"], "branch": row["branch"], "repeats": row["repeats"]},
        ))
    for row in bench["deferred"]:
        metrics.append(metric_record(
            f"C.performance.{row.get('size')}.{row.get('branch', 'both')}", quantity="requested performance benchmark",
            status="not_evaluable", evidence_level="V1", reason=row["reason"],
        ))

    print("Phase II: tile comparison", flush=True)
    tile = tile_comparison(1024)
    write_json(out / "tile_comparison.json", tile)
    for branch in ("negative", "print"):
        metrics.append(metric_record(
            f"C.tile.{branch}", quantity="whole-frame versus 2x2 tile numerical agreement", status="pass" if tile[branch]["finite"] else "fail",
            evidence_level="V1", value={key: tile[branch][key] for key in ("bit_exact", "rmse", "mae", "max_abs")},
            unit="scene-linear ACEScg", conditions={"spatial_effects": False, "stochastic_effects": False, "size": 1024},
            reason="a pass only establishes the restricted per-pixel configuration, not general bit-exact tiling",
        ))

    env = environment_record()
    write_json(out / "environment.json", env)
    write_json(docs / "METRICS.json", {"schema_version": 1, "evidence_levels": {
        "V1": "computational consistency", "V2": "published reference agreement",
        "V3": "independent physical measurement", "V4": "end-to-end photographic validation",
    }, "no_overall_authenticity_score": True, "metrics": metrics})

    after = protected_inventory(root)
    test_results_path = out / "test_results.json"
    test_results = json.loads(test_results_path.read_text(encoding="utf-8")) if test_results_path.is_file() else None
    integrity = {
        "before": before, "after": after,
        "all_match": before["all_match"] and after["all_match"],
        "unchanged_during_phase2": before["files"] == after["files"],
        "test_results": test_results,
    }
    write_json(out / "phase1_integrity_before_after.json", integrity)
    if not integrity["all_match"] or not integrity["unchanged_during_phase2"]:
        raise RuntimeError("protected Phase I/Round 2 artifacts changed")

    report_paths = write_reports(
        root, docs, metrics=metrics, sens=sens, spectral=spectral, pins=pins, published=published,
        bench=bench, tile=tile, color=color, integrity=integrity,
    )
    manifest_path = out / "manifest.json"
    artifact_paths = [path for path in out.iterdir() if path.is_file() and path != manifest_path] + report_paths + [docs / "METRICS.json"]
    manifest = {
        "schema_version": 1,
        "experiment": "FilmSimulation Phase II Physical Fidelity Benchmark",
        "status": "complete" if not any(row["status"] == "fail" for row in metrics) else "complete_with_findings",
        "evidence_policy": "V1 does not establish V2-V4; no overall authenticity percentage",
        "provenance": {
            "input_sha256": pins["input_sha256"], "upstream_commit": UPSTREAM_COMMIT,
            "profiles": pins["profiles"], "official_pdfs": pins["official_pdfs"],
            "parameters_sha256": params_hash, "environment": env,
        },
        "metric_status_counts": {status: sum(row["status"] == status for row in metrics) for status in ("pass", "fail", "not_evaluable")},
        "artifacts": artifact_inventory(root, artifact_paths),
    }
    write_json(manifest_path, manifest)
    return manifest
