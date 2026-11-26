"""Display-clip measurements. The linear EXR stays the core output."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .experiment import linear_acescg_to_linear_srgb, write_display_jpeg, write_json


def area_downsample(image: np.ndarray, long_edge: int) -> np.ndarray:
    height, width = image.shape[:2]
    factor = max(1, int(np.ceil(max(height, width) / long_edge)))
    height = height // factor * factor
    width = width // factor * factor
    cropped = np.asarray(image[:height, :width])
    channels = cropped.shape[2]
    return cropped.reshape(height // factor, factor, width // factor, factor, channels).mean(axis=(1, 3))


def _block_mean(mask: np.ndarray, bins: int) -> np.ndarray:
    factor = max(1, int(np.ceil(max(mask.shape) / bins)))
    height = mask.shape[0] // factor * factor
    width = mask.shape[1] // factor * factor
    cropped = mask[:height, :width].astype(np.float32)
    return cropped.reshape(height // factor, factor, width // factor, factor).mean(axis=(1, 3))


def quantify_display_clip(linear_acescg: np.ndarray) -> dict[str, Any]:
    linear_srgb = np.asarray(linear_acescg_to_linear_srgb(linear_acescg))
    below = linear_srgb < 0.0
    above = linear_srgb > 1.0
    affected = below.any(axis=2) | above.any(axis=2)
    height, width = affected.shape
    component_count = int(below.size)
    pixel_count = int(affected.size)
    bands = 8
    row_edges = np.linspace(0, height, bands + 1, dtype=int)
    column_edges = np.linspace(0, width, bands + 1, dtype=int)

    def band_means(mask: np.ndarray, edges: np.ndarray, axis: int) -> list[float]:
        values = []
        for index in range(len(edges) - 1):
            piece = mask[edges[index]:edges[index + 1]] if axis == 0 else mask[:, edges[index]:edges[index + 1]]
            values.append(float(piece.mean()) if piece.size else 0.0)
        return values

    return {
        "source": "scene-linear ACEScg converted to linear sRGB with both CCTF flags false",
        "display_range_operation": "hard clip of linear sRGB to [0, 1] before sRGB CCTF",
        "tone_mapper": None,
        "component_count": component_count,
        "pixel_count": pixel_count,
        "clipped_component_count_below_zero": int(below.sum()),
        "clipped_component_count_above_one": int(above.sum()),
        "clipped_component_count": int(below.sum() + above.sum()),
        "clipped_component_fraction": float((below.sum() + above.sum()) / component_count),
        "affected_pixel_count": int(affected.sum()),
        "affected_pixel_fraction": float(affected.sum() / pixel_count),
        "affected_pixel_fraction_below_zero": float(below.any(axis=2).sum() / pixel_count),
        "affected_pixel_fraction_above_one": float(above.any(axis=2).sum() / pixel_count),
        "spatial_distribution": {
            "row_band_affected_fraction": band_means(affected, row_edges, 0),
            "column_band_affected_fraction": band_means(affected, column_edges, 1),
            "below_zero_map": _block_mean(below.any(axis=2), 180),
            "above_one_map": _block_mean(above.any(axis=2), 180),
        },
    }


def smooth_highlight_shoulder(linear_acescg: np.ndarray) -> np.ndarray:
    """Reinhard highlight shoulder. Not an ACES output transform and not the core result.

    Negative linear-sRGB values are still clipped to 0. Highlights approach 1
    instead of being hard-clipped.
    """
    from colour.models import RGB_COLOURSPACE_sRGB

    linear = np.maximum(linear_acescg_to_linear_srgb(linear_acescg), 0.0)
    compressed = linear / (1.0 + linear)
    return RGB_COLOURSPACE_sRGB.cctf_encoding(compressed).astype(np.float32)


def write_display_diagnostics(
    root: Path,
    final_linear: np.ndarray,
    *,
    write_smooth_jpeg: bool = True,
) -> dict[str, Any]:
    stats = quantify_display_clip(final_linear)
    spatial = stats["spatial_distribution"]
    figure, axes = plt.subplots(1, 2, figsize=(10, 4.5), constrained_layout=True)
    for axis, key, title in (
        (axes[0], "below_zero_map", "fraction of pixels with a component < 0"),
        (axes[1], "above_one_map", "fraction of pixels with a component > 1"),
    ):
        image = axis.imshow(spatial[key], cmap="magma", vmin=0.0, vmax=max(0.05, float(np.max(spatial[key]))))
        axis.set_title(title)
        axis.set_axis_off()
        figure.colorbar(image, ax=axis, fraction=0.046)
    figure.suptitle("Hard-clip spatial distribution of the 5219→2383 display conversion")
    map_path = root / "output" / "display_clipping_map.png"
    map_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(map_path, dpi=140)
    plt.close(figure)
    if write_smooth_jpeg:
        smooth = smooth_highlight_shoulder(final_linear)
        write_display_jpeg(
            root / "output" / "5219_to_2383_display_smooth_highlight_shoulder_srgb.jpg",
            smooth,
        )
        del smooth
    published = {key: value for key, value in stats.items() if key != "spatial_distribution"}
    published["spatial_distribution"] = {
        "row_band_affected_fraction": spatial["row_band_affected_fraction"],
        "column_band_affected_fraction": spatial["column_band_affected_fraction"],
        "map": "output/display_clipping_map.png",
        "map_bins": "block means of the full-resolution clip mask; counts above are full resolution",
    }
    published["smooth_highlight_shoulder"] = {
        "path": "output/5219_to_2383_display_smooth_highlight_shoulder_srgb.jpg",
        "formula": "max(linear sRGB, 0) / (1 + max(linear sRGB, 0)), then sRGB CCTF",
        "is_core_output": False,
        "is_aces_output_transform": False,
        "aces_output_transform": "unavailable; this environment has no ACES RRT/ODT for the ACEScg result",
    }
    published["round1_linear_exr_unchanged"] = "output/5219_to_2383_linear_acescg.exr"
    write_json(root / "validation" / "display_diagnostics.json", published)
    return published
