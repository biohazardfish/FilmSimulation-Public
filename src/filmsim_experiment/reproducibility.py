"""Two full-resolution passes. Only hashes, times, and pass/fail are kept."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .experiment import TAPS, build_params, decode_raw, sha256_array
from spektrafilm import simulate


STAGES = ("scene", *TAPS, "negative_scan", "final_print")


def g3_status(matches: dict[str, bool]) -> str:
    if any(stage not in matches for stage in STAGES):
        return "fail"
    if all(matches[stage] for stage in STAGES):
        return "pass"
    return "fail"


def _simulate(image: np.ndarray, **kwargs: Any) -> np.ndarray:
    result = np.asarray(simulate(image, build_params(**kwargs), digest_params_first=True, print_timings=False))
    if result.shape != image.shape or not np.isfinite(result).all():
        raise RuntimeError(f"Invalid full-resolution result for {kwargs}")
    return result


def run_full_resolution_repeat(
    raw_path: Path,
    *,
    on_first_scene: Callable[[np.ndarray], None] | None = None,
    on_first_final: Callable[[np.ndarray], None] | None = None,
    on_first_negative: Callable[[np.ndarray], None] | None = None,
) -> dict[str, Any]:
    passes: list[dict[str, str]] = []
    timings: list[dict[str, float]] = []
    for index in (1, 2):
        print(f"Round 2 full-resolution pass {index}/2", flush=True)
        hashes: dict[str, str] = {}
        elapsed: dict[str, float] = {}
        started = time.perf_counter()
        scene, _metadata = decode_raw(raw_path)
        hashes["scene"] = sha256_array(scene)
        elapsed["scene"] = time.perf_counter() - started
        if index == 1 and on_first_scene is not None:
            on_first_scene(scene)
        for tap in TAPS:
            started = time.perf_counter()
            value = _simulate(scene, collect=tap)
            hashes[tap] = sha256_array(value)
            elapsed[tap] = time.perf_counter() - started
            del value
            print(f"  pass {index} {tap} {elapsed[tap]:.1f}s", flush=True)
        started = time.perf_counter()
        final = _simulate(scene)
        hashes["final_print"] = sha256_array(final)
        elapsed["final_print"] = time.perf_counter() - started
        print(f"  pass {index} final_print {elapsed['final_print']:.1f}s", flush=True)
        if index == 1 and on_first_final is not None:
            on_first_final(final)
        del final
        started = time.perf_counter()
        negative = _simulate(scene, scan_film=True)
        hashes["negative_scan"] = sha256_array(negative)
        elapsed["negative_scan"] = time.perf_counter() - started
        print(f"  pass {index} negative_scan {elapsed['negative_scan']:.1f}s", flush=True)
        if index == 1 and on_first_negative is not None:
            on_first_negative(negative)
        del negative, scene
        passes.append(hashes)
        timings.append(elapsed)
    matches = {stage: passes[0][stage] == passes[1][stage] for stage in STAGES}
    status = g3_status(matches)
    return {
        "status": status,
        "stages": list(STAGES),
        "pass_1_sha256_uncompressed_pixels": passes[0],
        "pass_2_sha256_uncompressed_pixels": passes[1],
        "elapsed_seconds": {"pass_1": timings[0], "pass_2": timings[1]},
        "matches": matches,
        "retained_second_copy": False,
        "evidence": "uncompressed float pixel SHA-256 of two separate full-resolution runs",
    }
