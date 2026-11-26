from __future__ import annotations

import argparse
import hashlib
import json
import resource

import numpy as np

from filmsim_experiment.experiment import build_params
from spektrafilm import digest_params
from spektrafilm.runtime.pipeline import SimulationPipeline


def synthetic_image(size: int, dtype=np.float32) -> np.ndarray:
    x = np.linspace(0.01, 1.5, size, dtype=dtype)
    y = np.linspace(0.05, 1.0, size, dtype=dtype)[:, None]
    base = np.clip(x[None, :] * y, 0.0, None)
    return np.stack((base, base * dtype(0.91), base * dtype(1.07)), axis=-1)


def array_hash(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def run(size: int, branch: str, repeats: int) -> dict:
    scan_film = branch == "negative"
    params = digest_params(build_params(scan_film=scan_film))
    warm = SimulationPipeline(params)
    warm.process(synthetic_image(64))
    image = synthetic_image(size)
    timings = []
    totals = []
    hashes = []
    output = None
    pipeline = SimulationPipeline(params)
    for _ in range(repeats):
        output = np.asarray(pipeline.process(image))
        timings.append({key: float(value) for key, value in pipeline.get_timings().items()})
        totals.append(float(pipeline.get_total_elapsed_time()))
        hashes.append(array_hash(output))
    assert output is not None
    rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return {
        "size": size,
        "branch": branch,
        "repeats": repeats,
        "stage_timings_seconds": timings,
        "total_seconds": totals,
        "median_total_seconds": float(np.median(totals)),
        "peak_rss_bytes": rss,
        "peak_rss_method": "resource.getrusage(RUSAGE_SELF).ru_maxrss; bytes on macOS",
        "input_dtype": str(image.dtype),
        "output_dtype": str(output.dtype),
        "input_bytes": int(image.nbytes),
        "output_bytes": int(output.nbytes),
        "output_shape": list(output.shape),
        "finite": bool(np.isfinite(output).all()),
        "deterministic_hashes": hashes,
        "deterministic": len(set(hashes)) == 1,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--branch", choices=("negative", "print"), required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(run(args.size, args.branch, args.repeats), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
