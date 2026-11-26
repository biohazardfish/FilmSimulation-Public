"""Phase 5 model spread and a small sensitivity matrix.

Differences here are between runnable spektrafilm settings. They are not
errors relative to a measured piece of film.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .display_diagnostics import area_downsample
from .experiment import WORKING_SPACE, build_params, decode_raw, display_transform, write_json
from spektrafilm import simulate


G4B_STATUS = "insufficient"
G4B_REASON = (
    "No independent controlled measurement of a physical 5219 or 2383 sample "
    "is in this project. Source-conformance is not real-film error, and no "
    "real-film Delta E00 is computed."
)


def spectral_methods_declared(root: Path) -> list[str]:
    source = (
        root / "upstream" / "spektrafilm" / "src" / "spektrafilm" / "runtime" / "stages" / "filming.py"
    ).read_text(encoding="utf-8")
    found = []
    for name in ("hanatos2025", "mallett2019"):
        if f'rgb_to_raw_method == "{name}"' in source:
            found.append(name)
    return found


def lut_comparison(root: Path) -> dict[str, Any]:
    upstream = root / "upstream" / "spektrafilm"
    cubes = sorted(path.relative_to(upstream).as_posix() for path in upstream.rglob("*.cube"))
    threed = sorted(path.relative_to(upstream).as_posix() for path in upstream.rglob("*.3dl"))
    return {
        "status": "unavailable",
        "reason": (
            "This spektrafilm commit does not ship a 5219→2383 LUT whose input and "
            "output domains are stated independently of the spectral pipeline. "
            "settings.use_enlarger_lut and use_scanner_lut are optional caches inside "
            "that same pipeline, not a fair external LUT. No .cube or .3dl file is "
            "used as a substitute."
        ),
        "cube_files": cubes,
        "threedl_files": threed,
        "included_in_comparison": False,
    }


def _simulate(image: np.ndarray, **kwargs: Any) -> np.ndarray:
    result = np.asarray(simulate(image, build_params(**kwargs), digest_params_first=True, print_timings=False))
    if not np.isfinite(result).all():
        raise RuntimeError(f"Non-finite uncertainty result for {kwargs}")
    return result.astype(np.float32)


def _rmse(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.sqrt(np.mean((left.astype(np.float64) - right.astype(np.float64)) ** 2)))


def run_uncertainty(
    root: Path,
    raw_path: Path,
    nominal_scene: np.ndarray,
) -> dict[str, Any]:
    methods = spectral_methods_declared(root)
    if len(methods) < 2:
        raise RuntimeError(f"Expected two runnable spectral methods, found {methods}")
    nominal = area_downsample(nominal_scene, 160).astype(np.float32)
    variants = {"as_shot": nominal}
    for name in ("daylight", "tungsten"):
        print(f"Round 2 white-balance decode: {name}", flush=True)
        decoded, _metadata = decode_raw(raw_path, white_balance=name)
        variants[name] = area_downsample(decoded, 160).astype(np.float32)
        del decoded
    outputs = {}
    for method in methods:
        print(f"Round 2 spectral method: {method}", flush=True)
        outputs[method] = _simulate(nominal, rgb_to_raw_method=method)
    reference = outputs[methods[0]]
    other = outputs[methods[1]]
    spread = other - reference
    matrix = []
    nominal_result = None
    for white_balance, image in variants.items():
        for exposure_ev in (-1.0, 0.0, 1.0):
            for print_exposure in (0.5, 1.0, 2.0):
                result = _simulate(
                    image,
                    rgb_to_raw_method=methods[0],
                    exposure_compensation_ev=exposure_ev,
                    print_exposure=print_exposure,
                )
                record = {
                    "white_balance": white_balance,
                    "negative_exposure_ev": exposure_ev,
                    "print_exposure": print_exposure,
                    "rmse_scene_linear_acescg_versus_nominal": None,
                }
                if white_balance == "as_shot" and exposure_ev == 0.0 and print_exposure == 1.0:
                    nominal_result = result
                matrix.append((record, result))
    if nominal_result is None:
        raise RuntimeError("Nominal sensitivity cell was not run")
    published_matrix = []
    for record, result in matrix:
        record["rmse_scene_linear_acescg_versus_nominal"] = _rmse(result, nominal_result)
        published_matrix.append(record)
        del result
    printer = []
    for shift in (-20.0, 0.0, 20.0):
        result = _simulate(nominal, rgb_to_raw_method=methods[0], y_filter_shift=shift)
        printer.append({
            "y_filter_shift_cc": shift,
            "rmse_scene_linear_acescg_versus_nominal": _rmse(result, nominal_result),
        })
        del result
    payload = {
        "schema_version": 1,
        "sample": {
            "description": "Deterministic area downsample of the full decoded scene to a long edge of 160 px",
            "reason": "Spatial effects are disabled, so this probes the per-pixel color model. It is not the G3 full-resolution hash.",
            "shape": list(nominal.shape),
            "working_space": WORKING_SPACE,
        },
        "spectral_methods": {
            "declared_by_filming_stage": methods,
            "ran": methods,
            "not_a_pipeline_method": (
                "rgb_to_raw_aces_idt exists in utils/conversions.py but filming.py does not select it"
            ),
        },
        "model_spread": {
            "quantity": "scene-linear ACEScg difference between runnable spectral reconstructions",
            "reference_method": methods[0],
            "other_method": methods[1],
            "rmse": _rmse(reference, other),
            "max_abs": float(np.max(np.abs(spread))),
            "mean_abs_per_channel": [float(value) for value in np.mean(np.abs(spread), axis=(0, 1))],
            "this_is_not_real_film_error": True,
        },
        "sensitivity_matrix": published_matrix,
        "printer_light": {
            "control": "enlarger.y_filter_shift in Kodak CC, added to the database neutral yellow filter",
            "samples": printer,
        },
        "relative_to_real_film": {
            "status": G4B_STATUS,
            "delta_e00": "not computed",
            "reason": G4B_REASON,
        },
        "lut": lut_comparison(root),
        "_maps": {
            "spread": np.mean(np.abs(spread), axis=2),
            "nominal_display": display_transform(nominal_result)[0],
        },
    }
    return payload


def write_uncertainty_artifacts(root: Path, payload: dict[str, Any]) -> None:
    maps = payload.pop("_maps")
    matrix = payload["sensitivity_matrix"]
    figure, axes = plt.subplots(1, 4, figsize=(14, 3.6), constrained_layout=True)
    image = axes[0].imshow(maps["spread"], cmap="magma")
    axes[0].set_title(f"model spread |{payload['model_spread']['other_method']} - {payload['model_spread']['reference_method']}|")
    axes[0].set_axis_off()
    figure.colorbar(image, ax=axes[0], fraction=0.046)
    exposures = [-1.0, 0.0, 1.0]
    prints = [0.5, 1.0, 2.0]
    for axis, white_balance in zip(axes[1:], ("as_shot", "daylight", "tungsten")):
        grid = np.zeros((3, 3))
        for record in matrix:
            if record["white_balance"] != white_balance:
                continue
            row = exposures.index(record["negative_exposure_ev"])
            column = prints.index(record["print_exposure"])
            grid[row, column] = record["rmse_scene_linear_acescg_versus_nominal"]
        heat = axis.imshow(grid, cmap="viridis")
        axis.set_xticks(range(3), [str(value) for value in prints])
        axis.set_yticks(range(3), [str(value) for value in exposures])
        axis.set_xlabel("print exposure")
        axis.set_ylabel("negative EV")
        axis.set_title(white_balance)
        figure.colorbar(heat, ax=axis, fraction=0.046)
    figure.suptitle("Model spread and sensitivity. Not real-film Delta E00.")
    figure.savefig(root / "output" / "round2_uncertainty.png", dpi=140)
    plt.close(figure)
    write_json(root / "validation" / "uncertainty_metrics.json", payload)
    del maps
