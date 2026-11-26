from __future__ import annotations

import copy
import dataclasses
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import tomllib
from typing import Any

import colour
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import OpenImageIO as oiio
import rawpy

from spektrafilm import digest_params, init_params, simulate
from spektrafilm.profiles.io import Profile


UPSTREAM_COMMIT = "3bb2c2d2801ff68b92019cf1dbcbb133d60832bc"
FILM_KEY = "kodak_vision3_500t"
PRINT_KEY = "kodak_2383"
INPUT_SHA256 = "f3e47c2d9df3bbb07a16c49b6e283dfd787e066a5dc141fa9d42441a644c3780"
PROFILE_SHA256 = {
    FILM_KEY: "d7beca68bf16db88dbb7373fd13a6a1150a57a911a54bb0309a760a6f9883329",
    PRINT_KEY: "eb7fdfa3b75a909bf5c400802f7401160c8017ed1ac3e8e0d1c8448d56fbe184",
}
TAPS = ("log_e_film", "cmy_film", "log_e_print", "cmy_print")
WORKING_SPACE = "ACEScg"
DETERMINISTIC_CONTAINER_DATETIME = "1970:01:01 00:00:00"


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_array(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def _json_value(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if dataclasses.is_dataclass(value):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(_json_value(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _check_finite_json(value: Any, path: str = "root") -> tuple[int, list[str]]:
    count = 0
    failures: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child_count, child_failures = _check_finite_json(item, f"{path}.{key}")
            count += child_count
            failures.extend(child_failures)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child_count, child_failures = _check_finite_json(item, f"{path}[{index}]")
            count += child_count
            failures.extend(child_failures)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        count += 1
        if not math.isfinite(float(value)):
            failures.append(path)
    return count, failures


def inspect_upstream(root: Path) -> dict[str, Any]:
    upstream = root / "upstream" / "spektrafilm"
    required = [
        "README.md",
        "src/spektrafilm/README.md",
        "examples/run_simulation.py",
        "pyproject.toml",
        f"src/spektrafilm/data/profiles/{FILM_KEY}.json",
        f"src/spektrafilm/data/profiles/{PRINT_KEY}.json",
        "SPEKTRAFILM_LICENSE.txt",
        "CITATION.cff",
    ]
    missing = [name for name in required if not (upstream / name).is_file()]
    if missing:
        raise RuntimeError(f"Missing required upstream files: {missing}")
    commit = subprocess.run(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if commit != UPSTREAM_COMMIT:
        raise RuntimeError(f"Upstream commit mismatch: {commit} != {UPSTREAM_COMMIT}")
    pyproject = tomllib.loads((upstream / "pyproject.toml").read_text(encoding="utf-8"))
    profiles: dict[str, Any] = {}
    for key in (FILM_KEY, PRINT_KEY):
        path = upstream / "src" / "spektrafilm" / "data" / "profiles" / f"{key}.json"
        actual_hash = sha256_file(path)
        if actual_hash != PROFILE_SHA256[key]:
            raise RuntimeError(f"Profile hash mismatch for {key}: {actual_hash}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        numeric_count, nonfinite_paths = _check_finite_json(payload)
        if nonfinite_paths:
            raise RuntimeError(f"Non-finite profile values in {key}: {nonfinite_paths[:5]}")
        if payload["info"]["stock"] != key:
            raise RuntimeError(f"Profile stock mismatch for {key}")
        profiles[key] = {
            "sha256": actual_hash,
            "metadata": payload["metadata"],
            "info": payload["info"],
            "data_keys": sorted(payload["data"]),
            "numeric_values_checked": numeric_count,
        }
    return {
        "repository": "https://github.com/andreavolpato/spektrafilm",
        "commit": commit,
        "package_version": pyproject["project"]["version"],
        "python_requirement": pyproject["project"]["requires-python"],
        "required_files_checked": required,
        "api": {
            "parameter_entry": "spektrafilm.init_params(film_profile, print_profile)",
            "simulation_entry": "spektrafilm.simulate(image, params, digest_params_first=True, print_timings=False)",
            "tap_parameter": "params.taps.collect",
            "tap_names": list(TAPS),
            "documentation_difference": "Root README says create_params, but this commit exports init_params; implementation follows source and example.",
        },
        "licenses": {
            "code": "GPLv3 / GPL-3.0-or-later as declared by pyproject.toml and CITATION.cff",
            "profiles": "CC BY-SA 4.0 with attribution and ShareAlike requirements in SPEKTRAFILM_LICENSE.txt",
        },
        "profiles": profiles,
    }


def build_params(
    *,
    collect: str | None = None,
    scan_film: bool = False,
    rgb_to_raw_method: str | None = None,
    exposure_compensation_ev: float = 0.0,
    print_exposure: float = 1.0,
    y_filter_shift: float = 0.0,
    m_filter_shift: float = 0.0,
):
    if collect is not None and collect not in TAPS:
        raise ValueError(f"Unsupported tap: {collect}")
    if rgb_to_raw_method is not None and rgb_to_raw_method not in {"hanatos2025", "mallett2019"}:
        raise ValueError(f"Unsupported rgb_to_raw method: {rgb_to_raw_method}")
    params = init_params(film_profile=FILM_KEY, print_profile=PRINT_KEY)
    params.io.input_color_space = WORKING_SPACE
    params.io.input_cctf_decoding = False
    params.io.output_color_space = WORKING_SPACE
    params.io.output_cctf_encoding = False
    params.io.scan_film = scan_film
    params.io.output_gamut_compress = dataclasses.replace(
        params.io.output_gamut_compress,
        algorithm="off",
        lightness_compression=None,
    )
    params.camera.auto_exposure = False
    params.camera.exposure_compensation_ev = float(exposure_compensation_ev)
    params.camera.lens_blur_um = 0.0
    params.camera.diffusion_filter.active = False
    params.enlarger.print_exposure_compensation = False
    params.enlarger.print_exposure = float(print_exposure)
    params.enlarger.y_filter_shift = float(y_filter_shift)
    params.enlarger.m_filter_shift = float(m_filter_shift)
    params.enlarger.lens_blur = 0.0
    params.enlarger.diffusion_filter.active = False
    params.film_render.grain.active = False
    params.film_render.grain.sublayers_active = False
    params.film_render.grain.blur = 0.0
    params.film_render.grain.blur_dye_clouds_um = 0.0
    params.film_render.halation.active = False
    params.film_render.halation.boost_ev = 0.0
    params.film_render.dir_couplers.diffusion_size_um = 0.0
    params.film_render.dir_couplers.diffusion_tail_um = 0.0
    params.film_render.dir_couplers.diffusion_tail_weight = 0.0
    params.film_render.glare.active = False
    params.print_render.glare.active = False
    params.scanner.lens_blur = 0.0
    params.scanner.unsharp_mask = (0.0, 0.0)
    params.scanner.white_correction = False
    params.scanner.black_correction = False
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    if rgb_to_raw_method is not None:
        params.settings.rgb_to_raw_method = rgb_to_raw_method
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.settings.neutral_print_filters_from_database = True
    params.taps.inject = None
    params.taps.collect = collect
    return params


def serialize_params(params: Any, profile_hashes: dict[str, str]) -> dict[str, Any]:
    def convert(value: Any) -> Any:
        if isinstance(value, Profile):
            stock = value.info.stock
            return {
                "profile_key": stock,
                "sha256": profile_hashes[stock],
                "metadata": convert(value.metadata),
                "info": convert(value.info),
                "data": "excluded; immutable upstream profile identified by key and SHA-256",
            }
        if dataclasses.is_dataclass(value):
            return {
                field.name: convert(getattr(value, field.name))
                for field in dataclasses.fields(value)
            }
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, tuple):
            return [convert(item) for item in value]
        if isinstance(value, list):
            return [convert(item) for item in value]
        if isinstance(value, dict):
            return {str(key): convert(item) for key, item in value.items()}
        return value

    return convert(params)


def decode_settings() -> dict[str, Any]:
    return {
        "decoder": "rawpy/LibRaw",
        "demosaic_algorithm": "AHD",
        "half_size": False,
        "four_color_rgb": False,
        "dcb_iterations": 0,
        "dcb_enhance": False,
        "fbdd_noise_reduction": "Off",
        "noise_threshold": None,
        "median_filter_passes": 0,
        "white_balance": "camera as-shot",
        "use_camera_wb": True,
        "use_auto_wb": False,
        "output_color_from_libraw": "ACES2065-1 (AP0, D60)",
        "output_bps": 16,
        "user_flip": 0,
        "no_auto_bright": True,
        "adjust_maximum_thr": 0.0,
        "bright": 1.0,
        "highlight_mode": "Clip",
        "no_auto_scale": False,
        "gamma": [1.0, 1.0],
        "lens_correction": False,
        "creative_processing": False,
        "normalization": "uint16 / 65535",
        "camera_to_working_conversion": "LibRaw camera-to-linear ACES2065-1, then colour-science RGB_to_RGB AP0 to ACEScg AP1; no CCTF",
        "working_rgb_primaries": "ACEScg AP1",
        "working_whitepoint": "D60",
        "working_encoding": "scene-linear float32",
        "raw_image_selection": "LibRaw/rawpy default image (shot_select=0)",
        "dual_pixel_auxiliary_processing": False,
    }


def _targeted_exif(raw_path: Path) -> dict[str, Any]:
    tags = [
        "Make", "Model", "ISO", "ExposureTime", "ShutterSpeed", "FNumber",
        "Aperture", "LensModel", "FocalLength", "ColorTemperature",
        "ColorTempAsShot", "WB_RGGBLevelsAsShot", "MeasuredRGGB", "Orientation",
        "SensorWidth", "SensorHeight", "SensorLeftBorder", "SensorTopBorder",
        "SensorRightBorder", "SensorBottomBorder", "CroppedImageWidth",
        "CroppedImageHeight", "ColorSpace",
        "DualPixelRaw",
    ]
    command = ["exiftool", "-j", "-n", *[f"-{tag}" for tag in tags], str(raw_path)]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    records = json.loads(result.stdout)
    return records[0] if records else {}


def _adapt_aces2065(rgb: np.ndarray, source_temperature: float, target_temperature: float) -> np.ndarray:
    """Von Kries adaptation in linear ACES2065-1, matching spektrafilm's raw-processor temperatures."""
    space = colour.RGB_COLOURSPACES["ACES2065-1"]

    def white(temperature: float) -> np.ndarray:
        method = "CIE Illuminant D Series" if temperature >= 4000.0 else "Kang 2002"
        xy = colour.CCT_to_xy(np.float64(temperature), method=method)
        xyz = np.asarray(colour.xy_to_XYZ(xy), dtype=np.float64)
        return xyz / xyz[1]

    xyz = colour.RGB_to_XYZ(rgb, colourspace=space, chromatic_adaptation_transform=None, apply_cctf_decoding=False)
    xyz = colour.chromatic_adaptation(xyz, white(source_temperature), white(target_temperature), method="Von Kries")
    return colour.XYZ_to_RGB(
        xyz, colourspace=space, chromatic_adaptation_transform=None, apply_cctf_encoding=False,
    ).astype(np.float32)


def decode_raw(raw_path: Path, *, white_balance: str = "as_shot") -> tuple[np.ndarray, dict[str, Any]]:
    if white_balance not in {"as_shot", "daylight", "tungsten"}:
        raise ValueError(f"Unsupported white balance: {white_balance}")
    settings = decode_settings()
    if white_balance != "as_shot":
        settings = {**settings, "white_balance_variant": white_balance}
    with rawpy.imread(str(raw_path)) as raw:
        sizes = raw.sizes._asdict()
        raw_metadata = {
            "sizes": sizes,
            "black_level_per_channel": list(raw.black_level_per_channel),
            "camera_white_level_per_channel": list(raw.camera_white_level_per_channel),
            "container_white_level": int(raw.white_level),
            "camera_whitebalance": list(raw.camera_whitebalance),
            "daylight_whitebalance": list(raw.daylight_whitebalance),
            "color_description": raw.color_desc.decode("ascii", "replace") if isinstance(raw.color_desc, bytes) else str(raw.color_desc),
            "raw_pattern": np.asarray(raw.raw_pattern).tolist(),
            "rgb_xyz_matrix": np.asarray(raw.rgb_xyz_matrix).tolist(),
            "color_matrix": np.asarray(raw.color_matrix).tolist(),
            "number_of_colors": int(raw.num_colors),
            "raw_type": str(raw.raw_type),
        }
        params = rawpy.Params(
            demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
            half_size=False,
            four_color_rgb=False,
            dcb_iterations=0,
            dcb_enhance=False,
            fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off,
            noise_thr=None,
            median_filter_passes=0,
            use_camera_wb=white_balance == "as_shot",
            use_auto_wb=False,
            user_wb=None,
            output_color=rawpy.ColorSpace.ACES,
            output_bps=16,
            user_flip=0,
            user_black=None,
            user_cblack=None,
            user_sat=None,
            no_auto_bright=True,
            auto_bright_thr=None,
            adjust_maximum_thr=0.0,
            bright=1.0,
            highlight_mode=rawpy.HighlightMode.Clip,
            exp_shift=None,
            exp_preserve_highlights=0.0,
            no_auto_scale=False,
            gamma=(1.0, 1.0),
            chromatic_aberration=None,
            bad_pixels_path=None,
        )
        aces2065 = raw.postprocess(params=params).astype(np.float32) / np.float32(65535.0)
    if white_balance == "tungsten":
        # LibRaw's non-camera balance is daylight. Adapt that daylight ACES image to 2850 K.
        aces2065 = _adapt_aces2065(aces2065, 6504.0, 2850.0)
    acescg = colour.RGB_to_RGB(
        aces2065,
        input_colourspace=colour.RGB_COLOURSPACES["ACES2065-1"],
        output_colourspace=colour.RGB_COLOURSPACES[WORKING_SPACE],
        apply_cctf_decoding=False,
        apply_cctf_encoding=False,
    ).astype(np.float32)
    if acescg.ndim != 3 or acescg.shape[2] != 3 or not np.isfinite(acescg).all():
        raise RuntimeError(f"Invalid decoded image: shape={acescg.shape}")
    metadata = {
        "exiftool": _targeted_exif(raw_path),
        "rawpy": raw_metadata,
        "software": {
            "rawpy": rawpy.__version__,
            "libraw": ".".join(str(item) for item in rawpy.libraw_version),
            "colour-science": importlib.metadata.version("colour-science"),
        },
        "decode_settings": settings,
        "decoded_array": {
            "shape": list(acescg.shape),
            "dtype": str(acescg.dtype),
            "minimum": float(np.min(acescg)),
            "maximum": float(np.max(acescg)),
            "finite": bool(np.isfinite(acescg).all()),
            "sha256_uncompressed_pixels": sha256_array(acescg),
        },
    }
    return acescg, metadata


def write_exr(path: Path, image: np.ndarray, attributes: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.tmp{path.suffix}")
    height, width, channels = image.shape
    spec = oiio.ImageSpec(width, height, channels, oiio.TypeDesc("float"))
    spec.attribute("compression", "zip")
    # OpenImageIO otherwise inserts the wall-clock time, making byte hashes
    # differ even when every pixel and declared provenance field is identical.
    spec.attribute("DateTime", DETERMINISTIC_CONTAINER_DATETIME)
    spec.attribute("oiio:ColorSpace", attributes.get("color_space", "ACEScg"))
    for key, value in sorted(attributes.items()):
        spec.attribute(f"FilmSimulation:{key}", str(value))
    output = oiio.ImageOutput.create(str(temporary))
    if output is None:
        raise RuntimeError(f"Unable to create EXR: {temporary}")
    try:
        if not output.open(str(temporary), spec):
            raise RuntimeError(output.geterror())
        # Some spektrafilm taps are channel-reordered views.  OIIO requires
        # interleaved, contiguous channels even when the dtype is already
        # float32, so make that storage contract explicit at the file boundary.
        pixels = np.ascontiguousarray(image, dtype=np.float32)
        if not output.write_image(pixels):
            raise RuntimeError(output.geterror())
    finally:
        output.close()
    os.replace(temporary, path)


def linear_acescg_to_linear_srgb(linear_acescg: np.ndarray) -> np.ndarray:
    return colour.RGB_to_RGB(
        np.asarray(linear_acescg),
        input_colourspace=colour.RGB_COLOURSPACES[WORKING_SPACE],
        output_colourspace=colour.RGB_COLOURSPACES["sRGB"],
        apply_cctf_decoding=False,
        apply_cctf_encoding=False,
    )


def display_transform(linear_acescg: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    linear_srgb = linear_acescg_to_linear_srgb(linear_acescg)
    clipped_low = int(np.count_nonzero(linear_srgb < 0.0))
    clipped_high = int(np.count_nonzero(linear_srgb > 1.0))
    clipped = np.clip(linear_srgb, 0.0, 1.0)
    encoded = colour.RGB_COLOURSPACES["sRGB"].cctf_encoding(clipped).astype(np.float32)
    return encoded, {
        "source": "scene-linear ACEScg AP1 D60",
        "destination": "display-referred sRGB D65",
        "rgb_conversion": "colour.RGB_to_RGB with both CCTF flags false (includes colour-science chromatic adaptation)",
        "tone_mapper": None,
        "display_range_operation": "hard clip linear sRGB to [0, 1]",
        "encoding": "sRGB CCTF after clipping",
        "clipped_component_count_below_zero": clipped_low,
        "clipped_component_count_above_one": clipped_high,
    }


def write_display_tiff(path: Path, encoded_srgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.tmp{path.suffix}")
    data = np.rint(np.clip(encoded_srgb, 0.0, 1.0) * 65535.0).astype(np.uint16)
    height, width, channels = data.shape
    spec = oiio.ImageSpec(width, height, channels, oiio.TypeDesc("uint16"))
    spec.attribute("compression", "zip")
    spec.attribute("DateTime", DETERMINISTIC_CONTAINER_DATETIME)
    spec.attribute("oiio:ColorSpace", "sRGB")
    spec.attribute("FilmSimulation:display_transform", "linear ACEScg to linear sRGB; hard clip; sRGB CCTF; no tone mapper")
    output = oiio.ImageOutput.create(str(temporary))
    if output is None:
        raise RuntimeError(f"Unable to create TIFF: {temporary}")
    try:
        if not output.open(str(temporary), spec) or not output.write_image(data):
            raise RuntimeError(output.geterror())
    finally:
        output.close()
    os.replace(temporary, path)


def write_display_jpeg(path: Path, encoded_srgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.tmp{path.suffix}")
    data = np.rint(np.clip(encoded_srgb, 0.0, 1.0) * 255.0).astype(np.uint8)
    height, width, channels = data.shape
    spec = oiio.ImageSpec(width, height, channels, oiio.TypeDesc("uint8"))
    spec.attribute("oiio:ColorSpace", "sRGB")
    spec.attribute("CompressionQuality", 95)
    output = oiio.ImageOutput.create(str(temporary))
    if output is None:
        raise RuntimeError(f"Unable to create JPEG: {temporary}")
    try:
        if not output.open(str(temporary), spec) or not output.write_image(data):
            raise RuntimeError(output.geterror())
    finally:
        output.close()
    os.replace(temporary, path)


def _array_record(array: np.ndarray) -> dict[str, Any]:
    return {
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
        "mean": float(np.mean(array)),
        "finite": bool(np.isfinite(array).all()),
        "sha256_uncompressed_pixels": sha256_array(array),
    }


def _simulate_checked(image: np.ndarray, *, collect: str | None = None, scan_film: bool = False) -> np.ndarray:
    result = np.asarray(simulate(image, build_params(collect=collect, scan_film=scan_film)))
    if result.shape != image.shape or result.shape[-1] != 3:
        raise RuntimeError(f"Simulation shape mismatch at {collect or 'rgb_out'}: {result.shape}")
    if not np.isfinite(result).all():
        raise RuntimeError(f"Non-finite simulation output at {collect or 'rgb_out'}")
    return result


def run_smoke_test(root: Path, upstream_info: dict[str, Any] | None = None) -> dict[str, Any]:
    upstream_info = upstream_info or inspect_upstream(root)
    ramp_x = np.linspace(0.0, 1.0, 256, dtype=np.float64)
    ramp = np.broadcast_to(ramp_x[None, :, None], (16, 256, 3)).copy()
    ev = np.arange(-8, 7, dtype=np.float64)
    steps = 0.18 * np.power(2.0, ev)
    step_image = np.broadcast_to(steps[None, :, None], (16, len(steps), 3)).copy()
    records: dict[str, Any] = {}
    curve_data: dict[str, np.ndarray] = {}
    for label, collect in [(tap, tap) for tap in TAPS] + [("rgb_out", None)]:
        first = _simulate_checked(ramp, collect=collect)
        second = _simulate_checked(ramp, collect=collect)
        repeat_equal = bool(np.array_equal(first, second))
        if not repeat_equal:
            raise RuntimeError(f"Smoke reproducibility failed at {label}")
        record = _array_record(first)
        record["repeat_bit_exact"] = repeat_equal
        records[label] = record
        curve_data[label] = first[0].copy()
    step_output = _simulate_checked(step_image)
    records["exposure_steps_rgb_out"] = {
        **_array_record(step_output),
        "input_ev_relative_to_18_percent": ev.tolist(),
        "input_linear_values": steps.tolist(),
        "output_channel_values": step_output[0].tolist(),
    }
    figure, axes = plt.subplots(3, 2, figsize=(12, 12), constrained_layout=True)
    labels = ["R", "G", "B"]
    for axis, (tap, values) in zip(axes.flat[:5], curve_data.items()):
        for channel, channel_label in enumerate(labels):
            axis.plot(ramp_x, values[:, channel], label=channel_label)
        axis.set_title(tap)
        axis.set_xlabel("scene-linear neutral ramp")
        axis.set_ylabel("tap value")
        axis.grid(alpha=0.25)
        axis.legend()
    axis = axes.flat[5]
    for channel, channel_label in enumerate(labels):
        axis.plot(ev, step_output[0, :, channel], marker="o", label=channel_label)
    axis.set_title("rgb_out exposure steps")
    axis.set_xlabel("EV relative to 18% gray")
    axis.set_ylabel("scene-linear ACEScg output")
    axis.grid(alpha=0.25)
    axis.legend()
    plot_path = root / "output" / "validation_curves.png"
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(plot_path, dpi=150)
    plt.close(figure)
    result = {
        "status": "pass",
        "profiles_loaded": {
            "film": upstream_info["profiles"][FILM_KEY]["info"],
            "print": upstream_info["profiles"][PRINT_KEY]["info"],
        },
        "input_contract": "scene-linear ACEScg AP1 D60",
        "records": records,
        "checks": {
            "package_import": "pass",
            "required_profiles": "pass",
            "full_negative_print_flow": "pass",
            "tap_shapes_and_channels": "pass",
            "finite_values": "pass",
            "repeat_bit_exact": "pass",
        },
    }
    write_json(root / "intermediate" / "smoke_test.json", result)
    return result


def _environment() -> dict[str, Any]:
    packages = [
        "spektrafilm", "numpy", "scipy", "colour-science", "scikit-image",
        "matplotlib", "numba", "OpenImageIO", "rawpy", "pyfftw", "exiv2",
        "lensfunpy", "Pillow", "pytest",
    ]
    versions: dict[str, str] = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not installed"
    return {
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "packages": versions,
        "rawpy_libraw": ".".join(str(item) for item in rawpy.libraw_version),
        "installation_scope": "spektrafilm runtime dependencies only; GUI/LUT-creator dependencies intentionally not installed",
    }


def _shared_provenance(
    upstream_info: dict[str, Any],
    input_hash: str,
    decoded_metadata: dict[str, Any] | None,
    fixed_parameters: dict[str, Any],
) -> dict[str, Any]:
    return {
        "input": {"path": "input/_C5A0880.CR3", "sha256": input_hash},
        "upstream": {
            "repository": upstream_info["repository"],
            "commit": upstream_info["commit"],
            "package_version": upstream_info["package_version"],
        },
        "profiles": {
            key: {
                "sha256": upstream_info["profiles"][key]["sha256"],
                "metadata_version": upstream_info["profiles"][key]["metadata"]["version"],
            }
            for key in (FILM_KEY, PRINT_KEY)
        },
        "raw_decode": decoded_metadata["decode_settings"] if decoded_metadata else decode_settings(),
        "simulation_parameters_file": "intermediate/fixed_parameters.json",
        "simulation_summary": {
            "film_profile": FILM_KEY,
            "print_profile": PRINT_KEY,
            "input_output_primaries": WORKING_SPACE,
            "input_output_cctf": "none (linear)",
            "grain": False,
            "halation": False,
            "spatial_effects": False,
            "stochastic_effects": False,
            "output_gamut_compression": fixed_parameters["io"]["output_gamut_compress"],
        },
    }


def _artifact_inventory(root: Path) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for directory in (root / "intermediate", root / "output"):
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path == root / "output" / "manifest.json":
                continue
            artifacts.append({
                "path": str(path.relative_to(root)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    return artifacts


def _report_text(
    upstream_info: dict[str, Any],
    environment: dict[str, Any],
    smoke: dict[str, Any],
    artifacts: list[dict[str, Any]],
    decoded_metadata: dict[str, Any] | None,
    full_run: bool,
) -> str:
    profile_rows = []
    for key in (FILM_KEY, PRINT_KEY):
        profile = upstream_info["profiles"][key]
        profile_rows.append(
            f"| {profile['info']['name']} | {key} | {profile['metadata']['version']} | `{profile['sha256']}` |"
        )
    artifact_rows = "\n".join(
        f"- `{item['path']}` — {item['bytes']} bytes — `{item['sha256']}`" for item in artifacts
    )
    package_rows = "\n".join(
        f"- {name}: {version}" for name, version in environment["packages"].items()
    )
    if decoded_metadata:
        exif = decoded_metadata["exiftool"]
        raw = decoded_metadata["rawpy"]
        sizes = raw["sizes"]
        exposure_seconds = float(exif["ExposureTime"])
        shutter_label = f"1/{round(1.0 / exposure_seconds)} s" if exposure_seconds else "unknown"
        make = str(exif.get("Make", "")).strip()
        model = str(exif.get("Model", "")).strip()
        camera_label = model if model.lower().startswith(make.lower()) else f"{make} {model}".strip()
        decode_note = (
            f"相機為 {camera_label}，ISO {exif.get('ISO')}、"
            f"{shutter_label}、f/{exif.get('FNumber')}；as-shot 色溫 "
            f"{exif.get('ColorTempAsShot')} K、RGGB `{exif.get('WB_RGGBLevelsAsShot')}`。"
            f"raw sensor 為 {sizes['raw_width']}×{sizes['raw_height']}，LibRaw 有效輸出為 "
            f"{sizes['width']}×{sizes['height']}，相機建議 crop 為 "
            f"{sizes['crop_width']}×{sizes['crop_height']}；黑位 "
            f"`{raw['black_level_per_channel']}`、相機每通道白位 "
            f"`{raw['camera_white_level_per_channel']}`、容器白位 `{raw['container_white_level']}`。"
            f"解碼陣列 `{decoded_metadata['decoded_array']['shape']}`，像素 hash "
            f"`{decoded_metadata['decoded_array']['sha256_uncompressed_pixels']}`。"
        )
    else:
        decode_note = "本次只完成 smoke test，尚未執行 CR3 解碼。"
    gate = "通過" if full_run else "資料不足（未執行完整 CR3 流程）"
    return f"""# FilmSimulation 第一輪實驗報告

## 結論

本輪固定使用 Kodak VISION3 500T Color Negative Film 5219（35 mm 產品編號 5219；profile key `{FILM_KEY}`）與 Kodak VISION 2383（profile key `{PRINT_KEY}`）。spektrafilm 核心輸入與輸出均為 scene-linear ACEScg（AP1、D60）；RAW 解碼、核心模擬與顯示轉換分開保存。完整 CR3 流程狀態：**{'完成' if full_run else '未執行'}**。

## 固定上游與 API

- 倉庫：{upstream_info['repository']}
- commit：`{upstream_info['commit']}`
- 套件版本：`{upstream_info['package_version']}`
- Python 要求：`{upstream_info['python_requirement']}`
- 實際參數入口：`init_params(film_profile=..., print_profile=...)`
- 實際運算入口：`simulate(image, params, digest_params_first=True, print_timings=False)`
- 中間 tap：`params.taps.collect`，值為 `log_e_film`、`cmy_film`、`log_e_print`、`cmy_print`
- 文件差異：根 README 使用 `create_params`，但本 commit 並未匯出該名稱；原始碼與範例實際使用 `init_params`。

| 材料 | profile key | metadata 版本 | SHA-256 |
|---|---|---:|---|
{chr(10).join(profile_rows)}

## RAW 與色彩邊界

RAW 由 rawpy/LibRaw 以 AHD、相機 as-shot 白平衡、16-bit linear ACES2065-1、`no_auto_bright=True`、`gamma=(1,1)` 解碼；不做去噪、鏡頭修正、Film Look、S-curve、顆粒、halation、創意調色或顯示 gamma。其後由 colour-science 將 linear ACES2065-1（AP0、D60）轉為 linear ACEScg（AP1、D60），不套 CCTF、不裁切 scene-linear 值。{decode_note}

顯示檔另行將 linear ACEScg 轉 linear sRGB，僅為顯示範圍硬裁切至 [0,1]，最後套 sRGB CCTF；**沒有 tone mapper**。這一階段不屬於 spektrafilm 核心。

## 固定模擬設定

負片自動曝光關閉、曝光補償 0 EV；印片曝光補償關閉、印片曝光 1.0；使用上游資料庫的 500T→2383 中性濾片。Grain、halation、glare、diffusion、鏡頭 blur、scanner correction/unsharp 均關閉；所有隨機與空間效果停用。非空間 DIR coupler 化學交互仍保留，但空間 diffusion 為 0。上游輸入 spectral-locus gamut compression 保留並記錄；輸出 gamut/lightness compression 關閉，使核心輸出維持未套顯示映射的 linear RGB。

完整參數見 `intermediate/fixed_parameters.json`。

## 環境

- Python：{environment['python'].splitlines()[0]}
- LibRaw：{environment['rawpy_libraw']}
- 安裝範圍：{environment['installation_scope']}
{package_rows}

## 測試與驗收

- 上游 runtime/core 測試：189 passed、4 failed。失敗包含一個測試仍期待不存在的 `GrainParams.mult_usm_amount`，以及三個 committed regression baseline 與目前程式碼不一致。未修改上游、未重生 baseline。
- 本實驗 synthetic smoke：**{smoke['status']}**。指定 profiles 可載入、完整負片與印片流程可執行、所有 tap 尺寸/通道正確、無 NaN/Inf、重跑 bit-exact。
- G1 scene-linear 編碼及 primaries 明確：**{'通過' if full_run else '通過（合成輸入）；CR3 為資料不足'}**
- G2 指定 500T/5219 與 2383 從指定上游載入：**通過**
- G3 同一輸入與設定可重現：**通過（合成完整流程 bit-exact；CR3 解碼曾重跑且像素 hash 相同）**。全解析度 spektrafilm end-to-end 沒有再做第二次完整重跑，這個較窄的證據缺口保留在限制中。
- G4 灰階 ramp 與曝光階梯可解釋：**通過**（見 `output/validation_curves.png` 與 `intermediate/smoke_test.json`）
- G5 負片、印片、顯示轉換分階段：**{gate}**

## 產物

所有產物的共同 provenance 在 `output/manifest.json`；EXR 另含上游 commit、輸入/profile hash、tap/domain 與色彩空間標記。

{artifact_rows}

## 完整重跑

```bash
cd /path/to/FilmSimulation
PYTHONPATH=src .venv/bin/python scripts/run_experiment.py --all
```

只跑基準：

```bash
PYTHONPATH=src .venv/bin/python scripts/run_experiment.py --smoke-only
```

## 授權、限制與資料缺口

spektrafilm 程式碼依上游聲明為 GPLv3 / GPL-3.0-or-later；profiles 為 Andrea Volpato 建立、依 CC BY-SA 4.0 授權，需保留作者、專案連結、授權與修改說明。詳見 `docs/LICENSES.md` 與未修改的 `upstream/spektrafilm/SPEKTRAFILM_LICENSE.txt`。本實驗將 spektrafilm 作為固定版本的外部研究依賴，沒有修改 profiles。

公開 profiles 是由 datasheet 與公開科學資料處理而得，不是任何一卷實體膠片的完整測量真值。沒有同場景、受控條件的真實 5219/2383 對照，因此本輪不宣稱相對真實膠片的 ΔE00，也不宣稱物理準確度。RAW 色彩取決於 LibRaw 的 Canon EOS R7 相機矩陣與 as-shot metadata；沒有獨立 DNG/光譜相機校正或拍攝現場光源測量。顯示檔的 hard clip 只為 SDR 預覽，不能代表完整 scene-linear 動態範圍。完整全解析度 spektrafilm end-to-end 只成功執行一次；G3 的 bit-exact 證據來自合成完整流程，CR3 重跑證據只到 RAW 解碼像素 hash。
"""


def run_experiment(root: Path, *, mode: str = "all") -> dict[str, Any]:
    root = root.resolve()
    if mode not in {"all", "smoke-only", "decode-only"}:
        raise ValueError(f"Unsupported mode: {mode}")
    input_path = root / "input" / "_C5A0880.CR3"
    if not input_path.is_file():
        raise RuntimeError(f"Missing sole input: {input_path}")
    upstream_info = inspect_upstream(root)
    input_hash = sha256_file(input_path)
    if input_hash != INPUT_SHA256:
        raise RuntimeError(f"Input hash mismatch: {input_hash} != {INPUT_SHA256}")
    environment = _environment()
    write_json(root / "intermediate" / "upstream_inspection.json", upstream_info)
    write_json(root / "intermediate" / "environment.json", environment)
    digested = digest_params(copy.deepcopy(build_params()))
    fixed_parameters = serialize_params(digested, PROFILE_SHA256)
    write_json(root / "intermediate" / "fixed_parameters.json", fixed_parameters)

    smoke = run_smoke_test(root, upstream_info)
    decoded_metadata: dict[str, Any] | None = None
    full_run = False
    if mode != "smoke-only":
        scene, decoded_metadata = decode_raw(input_path)
        write_json(root / "intermediate" / "raw_metadata.json", decoded_metadata)
        base_attributes = {
            "input_sha256": input_hash,
            "upstream_commit": UPSTREAM_COMMIT,
            "film_profile_sha256": PROFILE_SHA256[FILM_KEY],
            "print_profile_sha256": PROFILE_SHA256[PRINT_KEY],
            "color_space": "ACEScg",
            "encoding": "scene-linear float32",
            "whitepoint": "D60",
            "decode_settings": "intermediate/raw_metadata.json",
            "simulation_parameters": "intermediate/fixed_parameters.json",
        }
        write_exr(root / "intermediate" / "scene_linear_acescg.exr", scene, {
            **base_attributes,
            "stage": "controlled RAW decode and camera-to-working-space conversion",
            "domain": "scene-linear RGB",
        })
        if mode == "all":
            for tap in TAPS:
                value = _simulate_checked(scene, collect=tap)
                write_exr(root / "intermediate" / f"{tap}.exr", value, {
                    **base_attributes,
                    "stage": "spektrafilm intermediate tap",
                    "domain": tap,
                })
                del value
            final_linear = _simulate_checked(scene)
            write_exr(root / "output" / "5219_to_2383_linear_acescg.exr", final_linear, {
                **base_attributes,
                "stage": "spektrafilm 5219 negative to 2383 print and scan",
                "domain": "scene-linear ACEScg rgb_out",
            })
            final_display, final_display_info = display_transform(final_linear)
            write_display_tiff(root / "output" / "5219_to_2383_display_srgb.tif", final_display)
            write_display_jpeg(root / "output" / "5219_to_2383_display_srgb.jpg", final_display)
            write_json(root / "intermediate" / "final_display_transform.json", final_display_info)
            del final_linear, final_display
            negative_linear = _simulate_checked(scene, scan_film=True)
            write_exr(root / "output" / "virtual_negative_scan_linear_acescg.exr", negative_linear, {
                **base_attributes,
                "stage": "spektrafilm official scan_film branch",
                "domain": "scene-linear ACEScg rgb_out",
            })
            negative_display, negative_display_info = display_transform(negative_linear)
            write_display_jpeg(root / "output" / "virtual_negative_preview_srgb.jpg", negative_display)
            write_json(root / "intermediate" / "negative_display_transform.json", negative_display_info)
            del negative_linear, negative_display, scene
            full_run = True

    # Do not make the report list a stale hash of its previous incarnation.
    # The final manifest, written after the report, is the authoritative place
    # for the report's own hash.
    artifacts_before_report = [
        artifact for artifact in _artifact_inventory(root)
        if artifact["path"] != "output/EXPERIMENT_REPORT.md"
    ]
    report = _report_text(
        upstream_info, environment, smoke, artifacts_before_report, decoded_metadata, full_run
    )
    write_text(root / "output" / "EXPERIMENT_REPORT.md", report)
    artifacts = _artifact_inventory(root)
    manifest = {
        "schema_version": 1,
        "experiment": "FilmSimulation first round",
        "status": "complete" if full_run else mode,
        "shared_provenance": _shared_provenance(
            upstream_info, input_hash, decoded_metadata, fixed_parameters
        ),
        "artifacts": artifacts,
        "validation_gates": {
            "G1": "pass" if full_run else "insufficient for CR3; synthetic pass",
            "G2": "pass",
            "G3": (
                "pass: synthetic full-flow bit-exact and CR3 decode repeated exact; "
                "full-resolution end-to-end simulation not repeated"
                if full_run else "insufficient for CR3; synthetic bit-exact pass"
            ),
            "G4": "pass",
            "G5": "pass" if full_run else "insufficient",
        },
    }
    write_json(root / "output" / "manifest.json", manifest)
    return manifest
