from __future__ import annotations

import copy
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from filmsim_experiment.experiment import (
    FILM_KEY,
    INPUT_SHA256,
    PRINT_KEY,
    PROFILE_SHA256,
    UPSTREAM_COMMIT,
    build_params,
    serialize_params,
    sha256_array,
    sha256_file,
    write_json,
)
from spektrafilm import digest_params
from spektrafilm.model.develop import develop_print_morph, develop_simple
from spektrafilm.profiles.io import load_profile
from spektrafilm.runtime.pipeline import SimulationPipeline

from .benchmark_worker import synthetic_image
from .color_validation import evaluate_color_reference, load_color_reference
from .metrics import curve_metrics, error_metrics, metric_record, monotonicity


EV = np.linspace(-6.0, 6.0, 481, dtype=np.float64)
CHANNELS = ("R", "G", "B")
PHYSICAL_RAM_BYTES = 48 * 1024**3
OFFICIAL_PDFS = {
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


def build_phase2_params(film_key: str, print_key: str, *, scan_film: bool = False):
    params = build_params(scan_film=scan_film)
    if film_key != FILM_KEY:
        params.film = load_profile(film_key)
    if print_key != PRINT_KEY:
        params.print = load_profile(print_key)
    return params


def protected_inventory(root: Path) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for manifest_name in ("output/manifest.json", "output/round2_manifest.json"):
        manifest = json.loads((root / manifest_name).read_text(encoding="utf-8"))
        for artifact in manifest.get("artifacts", []):
            path = root / artifact["path"]
            actual = sha256_file(path) if path.is_file() else None
            records[artifact["path"]] = {
                "expected_sha256": artifact["sha256"],
                "actual_sha256": actual,
                "matches_manifest": actual == artifact["sha256"],
            }
    known = {
        "output/EXPERIMENT_REPORT.md": "2333cca80818902b1f1e538534eec7f0db47ea9fd5a02ca7206623bf49d0e526",
        "output/manifest.json": "ad00fbd78c669fff78e8e9f73e8a0c90a8687875858c33634a91541dac7503fd",
        "intermediate/fixed_parameters.json": "08b1cf63781ceb490d54a77b674b782092c022e601ae7c284b17ad62a0ec47c2",
        "scripts/run_experiment.py": "bbad5bad7f9864007eca0c61b7f9b8d4df53ea830ea4fa5a0bc8cc6d49f2fff2",
        "output/ROUND2_REPORT.md": "f548b1c2ea9453ba0dec9e13dab7cef2e61346eb7f5129d31f9597b75b34a4bf",
        "validation/official_source_conformance.json": "5a79bad4917d80f5cc333a3c355466fb58cb630e0a81986b09c3018a7ccd4ba8",
    }
    for relative, expected in known.items():
        actual = sha256_file(root / relative)
        records[relative] = {"expected_sha256": expected, "actual_sha256": actual, "matches_manifest": actual == expected}
    return {"files": records, "all_match": all(row["matches_manifest"] for row in records.values())}


def validate_pins(root: Path, film_key: str, print_key: str) -> dict[str, Any]:
    commit = subprocess.run(
        ["git", "-C", str(root / "upstream/spektrafilm"), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if commit != UPSTREAM_COMMIT:
        raise RuntimeError(f"upstream commit mismatch: {commit}")
    if sha256_file(root / "input/_C5A0880.CR3") != INPUT_SHA256:
        raise RuntimeError("input CR3 hash changed")
    profile_rows = {}
    for key in (film_key, print_key):
        path = root / f"upstream/spektrafilm/src/spektrafilm/data/profiles/{key}.json"
        if not path.is_file():
            raise RuntimeError(f"profile not found: {key}")
        actual = sha256_file(path)
        expected = PROFILE_SHA256.get(key)
        if expected is not None and actual != expected:
            raise RuntimeError(f"profile hash mismatch: {key}")
        profile_rows[key] = {"sha256": actual, "expected_sha256": expected, "pinned": expected is not None}
    if (film_key, print_key) != (FILM_KEY, PRINT_KEY):
        profile_rows["warning"] = "alternative profiles are utility mode only; the official Phase II report uses the pinned 5219/2383 pair"
    pdfs = {}
    for key, spec in OFFICIAL_PDFS.items():
        actual = sha256_file(root / spec["path"])
        if actual != spec["sha256"]:
            raise RuntimeError(f"official Kodak PDF hash mismatch: {key}")
        pdfs[key] = {**spec, "actual_sha256": actual}
    return {"upstream_commit": commit, "input_sha256": INPUT_SHA256, "profiles": profile_rows, "official_pdfs": pdfs}


def _tap_set(params) -> dict[str, np.ndarray]:
    pipeline = SimulationPipeline(digest_params(params))
    ramp = np.repeat((0.18 * 2.0**EV)[None, :, None], 3, axis=2)
    taps = {"rgb_in": ramp}
    for tap in ("rgb_pre", "log_e_film", "cmy_film", "log_e_print", "cmy_print", "rgb_out"):
        try:
            taps[tap] = np.asarray(pipeline.process(ramp, collect=tap))
        except RuntimeError:
            continue
    return taps


def run_sensitometry(root: Path, out: Path, film_key: str, print_key: str) -> dict[str, Any]:
    print_taps = _tap_set(build_phase2_params(film_key, print_key, scan_film=False))
    negative_taps = _tap_set(build_phase2_params(film_key, print_key, scan_film=True))
    required = {"rgb_in", "rgb_pre", "log_e_film", "cmy_film", "log_e_print", "cmy_print", "rgb_out"}
    if set(print_taps) != required or "rgb_out" not in negative_taps:
        raise RuntimeError("pipeline did not expose the required taps")
    arrays = {f"print_{key}": value for key, value in print_taps.items()}
    arrays.update({f"negative_{key}": value for key, value in negative_taps.items()})
    arrays["ev"] = EV
    arrays["scene_linear_reference"] = 0.18 * 2.0**EV
    np.savez_compressed(out / "sensitometry_taps.npz", **arrays)

    csv_path = out / "sensitometry_samples.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        names = ["ev", "scene_linear"]
        for tap in ("log_e_film", "cmy_film", "log_e_print", "cmy_print"):
            names += [f"{tap}_{channel}" for channel in CHANNELS]
        names += [f"negative_rgb_{channel}" for channel in CHANNELS]
        names += [f"print_rgb_{channel}" for channel in CHANNELS]
        writer = csv.writer(handle)
        writer.writerow(names)
        for i, ev in enumerate(EV):
            row: list[Any] = [ev, 0.18 * 2.0**ev]
            for tap in ("log_e_film", "cmy_film", "log_e_print", "cmy_print"):
                row.extend(print_taps[tap][0, i].tolist())
            row.extend(negative_taps["rgb_out"][0, i].tolist())
            row.extend(print_taps["rgb_out"][0, i].tolist())
            writer.writerow(row)

    params = digest_params(build_phase2_params(film_key, print_key))
    normalized_film_curves = params.film.data.density_curves - np.nanmin(params.film.data.density_curves, axis=0)
    film_reference = develop_simple(
        print_taps["log_e_film"], params.film.data.log_exposure,
        normalized_film_curves, params.film_render.density_curve_gamma,
    )
    print_reference = develop_print_morph(
        print_taps["log_e_print"], params.print.data.log_exposure,
        params.print.data.density_curves_model, params.print_render.density_curves_morph,
        profile_type=params.print.info.type,
    )
    channels: dict[str, Any] = {}
    metrics: list[dict[str, Any]] = []
    for index, channel in enumerate(CHANNELS):
        film_x = print_taps["log_e_film"][0, :, index]
        film_y = print_taps["cmy_film"][0, :, index]
        print_x = print_taps["log_e_print"][0, :, index]
        print_y = print_taps["cmy_print"][0, :, index]
        film_curve = curve_metrics(film_x, film_y, film_reference[0, :, index])
        print_curve = curve_metrics(print_x, print_y, print_reference[0, :, index])
        film_mono = monotonicity(film_y, "increasing", atol=1e-9)
        print_mono = monotonicity(print_y, "decreasing", atol=1e-9)
        channels[channel] = {
            "film": {**film_curve, "monotonicity_vs_scene_ev": film_mono},
            "print": {**print_curve, "monotonicity_vs_scene_ev": print_mono},
        }
        metrics.extend([
            metric_record(
                f"A.film.{channel}.dir_active_deviation", quantity="DIR-active film channel coefficient minus no-DIR normalized profile characteristic",
                channel=channel, value=film_curve["reference_error"], unit="model channel coefficient",
                status="not_evaluable", evidence_level="V1",
                reference="pinned no-DIR profile characteristic evaluated at runtime log_e_film",
                conditions={"DIR_couplers": "active, spatial diffusion zero"}, independent=False,
                reason="descriptive model delta only; no documented acceptance tolerance, and this is not Status M physical density",
            ),
            metric_record(
                f"A.print.{channel}.profile_internal_error", quantity="print channel-coefficient agreement with profile parametric curve",
                channel=channel, value=print_curve["reference_error"], unit="model channel coefficient",
                status="pass" if print_curve["reference_error"]["max_abs"] < 1e-12 else "fail", evidence_level="V1",
                reference="pinned print density_curves_model evaluated at runtime log_e_print",
                independent=False, reason="computational consistency only; not Status A physical density",
            ),
            metric_record(
                f"A.film.{channel}.curve_statistics", quantity="film sensitometric curve statistics in native model domain",
                channel=channel,
                value={key: film_curve[key] for key in (
                    "d_min", "d_max", "density_span", "straight_line_gradient", "straight_line_intercept",
                    "straight_line_samples", "toe_deviation_rmse_from_straight_line", "shoulder_deviation_rmse_from_straight_line",
                )},
                unit="model channel coefficient and coefficient per log10 relative exposure",
                status="pass", evidence_level="V1", independent=False,
                conditions={"straight_line_region": "20-80% of observed channel span", "toe": "<20%", "shoulder": ">80%"},
                reason="native-domain descriptive statistics; not an external physical density score",
            ),
            metric_record(
                f"A.print.{channel}.curve_statistics", quantity="print sensitometric curve statistics in native model domain",
                channel=channel,
                value={key: print_curve[key] for key in (
                    "d_min", "d_max", "density_span", "straight_line_gradient", "straight_line_intercept",
                    "straight_line_samples", "toe_deviation_rmse_from_straight_line", "shoulder_deviation_rmse_from_straight_line",
                )},
                unit="model channel coefficient and coefficient per log10 relative exposure",
                status="pass", evidence_level="V1", independent=False,
                conditions={"straight_line_region": "20-80% of observed channel span", "toe": "<20%", "shoulder": ">80%"},
                reason="native-domain descriptive statistics; not an external physical density score",
            ),
            metric_record(
                f"A.film.{channel}.monotonicity", quantity="film response monotonicity versus scene EV", channel=channel,
                value=film_mono, unit="count", status="pass" if film_mono["pass"] else "fail", evidence_level="V1",
            ),
            metric_record(
                f"A.print.{channel}.monotonicity", quantity="print density response direction versus scene EV", channel=channel,
                value=print_mono, unit="count", status="pass" if print_mono["pass"] else "fail", evidence_level="V1",
            ),
        ])
    finite = {name: bool(np.isfinite(value).all()) for name, value in arrays.items()}
    repeat = _tap_set(build_phase2_params(film_key, print_key, scan_film=False))
    deterministic = {name: sha256_array(value) == sha256_array(repeat[name]) for name, value in print_taps.items()}
    metrics.append(metric_record(
        "A.pipeline.finite", quantity="finite outputs at all synthetic taps", value=finite, unit="boolean",
        status="pass" if all(finite.values()) else "fail", evidence_level="V1",
    ))
    metrics.append(metric_record(
        "A.pipeline.deterministic", quantity="exact repeat pixel hashes", value=deterministic, unit="boolean",
        status="pass" if all(deterministic.values()) else "fail", evidence_level="V1",
    ))

    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    for i, color in enumerate(("tab:red", "tab:green", "tab:blue")):
        axes[0, 0].plot(EV, print_taps["log_e_film"][0, :, i], color=color, label=CHANNELS[i])
        axes[0, 1].plot(EV, print_taps["cmy_film"][0, :, i], color=color)
        axes[1, 0].plot(EV, print_taps["log_e_print"][0, :, i], color=color)
        axes[1, 1].plot(EV, print_taps["cmy_print"][0, :, i], color=color)
    titles = (
        "Film relative log10 layer exposure (not lux-seconds)",
        "Film model channel coefficients (not measured Status M)",
        "Print relative log10 layer exposure (not lux-seconds)",
        "Print model channel coefficients (not measured Status A)",
    )
    for axis, title in zip(axes.flat, titles):
        axis.set_title(title)
        axis.set_xlabel("relative scene exposure (EV; 0 = ACEScg 0.18)")
        axis.grid(alpha=0.2)
    axes[0, 0].legend()
    fig.savefig(out / "sensitometric_response.png", dpi=160)
    plt.close(fig)
    return {
        "reference_definition": "scene-linear ACEScg neutral 0.18 * 2**EV; relative scale only",
        "ev": {"minimum": -6.0, "maximum": 6.0, "step": 0.025, "samples": 481},
        "channels": channels,
        "finite": finite,
        "deterministic": deterministic,
        "metrics": metrics,
        "tap_summary": {
            branch: {
                tap: {"shape": list(array.shape), "dtype": str(array.dtype), "minimum": float(np.min(array)), "maximum": float(np.max(array))}
                for tap, array in taps.items()
            }
            for branch, taps in (("print", print_taps), ("negative", negative_taps))
        },
    }


def profile_spectral_audit(params) -> dict[str, Any]:
    result = {}
    for label, profile in (("film", params.film), ("print", params.print)):
        arrays = {}
        for name in ("wavelengths", "log_sensitivity", "channel_density", "base_density", "midscale_neutral_density"):
            value = np.asarray(getattr(profile.data, name))
            finite = np.isfinite(value)
            arrays[name] = {
                "shape": list(value.shape), "dtype": str(value.dtype), "nan_count": int(np.isnan(value).sum()),
                "finite_count": int(finite.sum()),
                "finite_min": float(np.min(value[finite])) if finite.any() else None,
                "finite_max": float(np.max(value[finite])) if finite.any() else None,
            }
        result[label] = {
            "profile_key": profile.info.stock, "densitometer": profile.info.densitometer,
            "reference_illuminant": profile.info.reference_illuminant,
            "viewing_illuminant": profile.info.viewing_illuminant, "arrays": arrays,
            "nan_runtime_semantics": "density_to_light replaces NaN transmitted-light samples with zero",
        }
    return result


def published_reference_metrics(root: Path) -> list[dict[str, Any]]:
    source = json.loads((root / "validation/official_source_conformance.json").read_text(encoding="utf-8"))
    rows = []
    for item in source["items"]:
        status = "pass" if item["status"] == "pass" else "fail" if item["status"] == "fail" else "not_evaluable"
        rows.append(metric_record(
            f"B.kodak.{item['stock']}.{item['curve']}", quantity=f"Kodak published {item['curve']} agreement",
            status=status, evidence_level="V2", value=item.get("metrics"), unit=item.get("tolerance", {}).get("unit"),
            reference={"publication": item["source_publication"], "page": item["source_page"], "sha256": item["source_sha256"], "url": item["source_url"]},
            independent=False, conditions=item.get("caption", {}), normalization=item.get("alignment"),
            uncertainty=item.get("axis", {}).get("y_uncertainty_in_axis_units"), reason=item.get("reason"),
        ))
    for stock in (FILM_KEY, PRINT_KEY):
        for kind in ("granularity", "modulation_transfer"):
            rows.append(metric_record(
                f"B.kodak.{stock}.{kind}", quantity=f"Kodak published {kind} agreement", status="not_evaluable",
                evidence_level="V2", independent=False,
                reason="the deterministic Phase II configuration disables grain/spatial effects and exposes no model quantity measured under the Kodak aperture/MTF conditions",
            ))
    return rows


def run_benchmarks(root: Path, sizes: list[int]) -> dict[str, Any]:
    requested = sorted(set(sizes))
    results = []
    deferred = []
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    completed_1024 = []
    for size in requested:
        if size == 2048:
            if len(completed_1024) != 2:
                deferred.append({"size": size, "reason": "2048 requires successful 1024 measurements for both branches"})
                continue
            predicted = max(row["peak_rss_bytes"] for row in completed_1024) * 4
            if predicted >= PHYSICAL_RAM_BYTES * 0.5:
                deferred.append({"size": size, "reason": f"4x 1024 peak-RSS extrapolation {predicted} exceeds 50% of 48 GiB"})
                continue
        for branch in ("negative", "print"):
            command = [sys.executable, "-m", "filmsim_experiment.phase2.benchmark_worker", "--size", str(size), "--branch", branch, "--repeats", "3"]
            completed = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
            if completed.returncode != 0:
                deferred.append({"size": size, "branch": branch, "reason": completed.stderr[-2000:]})
                continue
            row = json.loads(completed.stdout.strip().splitlines()[-1])
            results.append(row)
            if size == 1024:
                completed_1024.append(row)
    return {"hardware": {"platform": platform.platform(), "physical_ram_bytes": PHYSICAL_RAM_BYTES}, "results": results, "deferred": deferred}


def tile_comparison(size: int = 1024) -> dict[str, Any]:
    image = synthetic_image(size)
    output: dict[str, Any] = {"size": size, "tiles": "2x2", "configuration": "spatial, stochastic, auto-exposure and scanner corrections disabled"}
    half = size // 2
    for branch, scan_film in (("negative", True), ("print", False)):
        params = digest_params(build_params(scan_film=scan_film))
        full = np.asarray(SimulationPipeline(copy.deepcopy(params)).process(image))
        tiled = np.empty_like(full)
        for y0 in (0, half):
            for x0 in (0, half):
                tile = image[y0:y0 + half, x0:x0 + half]
                tiled[y0:y0 + half, x0:x0 + half] = SimulationPipeline(copy.deepcopy(params)).process(tile)
        diff = tiled - full
        output[branch] = {
            "full_sha256": sha256_array(full), "tiled_sha256": sha256_array(tiled),
            "bit_exact": bool(np.array_equal(full, tiled)), "rmse": float(np.sqrt(np.mean(diff**2))),
            "mae": float(np.mean(np.abs(diff))), "max_abs": float(np.max(np.abs(diff))),
            "finite": bool(np.isfinite(full).all() and np.isfinite(tiled).all()),
        }
    output["general_blockers"] = [
        "auto-exposure uses image-global statistics", "highlight boost uses an image-global maximum",
        "crop/rescale changes sampling geometry", "DIR diffusion crosses tile boundaries when enabled",
        "halation, diffusion, blur, glare and unsharp mask require spatial neighborhoods",
        "grain is stochastic and needs a globally stable random-field policy",
    ]
    return output


def plot_performance(bench: dict[str, Any], path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    for branch, color in (("negative", "tab:orange"), ("print", "tab:blue")):
        rows = sorted((row for row in bench["results"] if row["branch"] == branch), key=lambda row: row["size"])
        if rows:
            axes[0].plot([row["size"] for row in rows], [row["median_total_seconds"] for row in rows], marker="o", label=branch, color=color)
            axes[1].plot([row["size"] for row in rows], [row["peak_rss_bytes"] / 1024**3 for row in rows], marker="o", label=branch, color=color)
    axes[0].set(xlabel="square image edge (px)", ylabel="median runtime (s)", title="End-to-end runtime")
    axes[1].set(xlabel="square image edge (px)", ylabel="peak RSS (GiB)", title="Subprocess peak resident memory")
    for axis in axes:
        axis.grid(alpha=0.2); axis.legend()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def environment_record() -> dict[str, Any]:
    packages = {}
    for name in ("spektrafilm", "numpy", "scipy", "colour-science", "scikit-image", "matplotlib", "opt-einsum", "numba", "OpenImageIO", "pyfftw", "rawpy", "pytest"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {"python": sys.version, "platform": platform.platform(), "packages": packages}


def artifact_inventory(root: Path, paths: list[Path]) -> list[dict[str, Any]]:
    records = []
    for path in sorted(set(paths)):
        if path.is_file():
            records.append({"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return records
