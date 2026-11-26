"""Kodak datasheet source-conformance. Not an independent film measurement.

Curves in the current official PDFs are raster images. Coordinates come from
OCR of axis labels, geometric tick marks, and ink tracing. A curve that fails
those checks is insufficient; coordinates are not guessed by eye.
"""

from __future__ import annotations

import csv
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageOps

from .experiment import FILM_KEY, PRINT_KEY, write_json


CLAIM = (
    "source-conformance against Kodak official technical-data figures. "
    "spektrafilm profiles are themselves derived from public datasheets, so "
    "agreement is not an independent measurement of a physical roll and is "
    "not a real-film Delta E00 or physical validation."
)

# Locked before inspecting residuals. These are curve-shape tolerances, not
# measurement uncertainties of a physical sample.
CHAR_RMSE_MAX = 0.08
CHAR_ABS_MAX = 0.25
SENS_RMSE_MAX = 0.20
SENS_ABS_MAX = 0.55
DYE_RMSE_MAX = 0.08
DYE_ABS_MAX = 0.20

SOURCES = (
    {
        "stock": FILM_KEY,
        "product": "KODAK VISION3 500T Color Negative Film 5219 / 7219",
        "publication": "H-1-5219",
        "url": "https://www.kodak.com/content/pdfs/motion/KODAK-VISION3-500T-5219-7219-technical-information.pdf",
        "filename": "vision3_500t_5219_7219_H-1-5219.pdf",
        "expected_sha256": "6d037d8090373ee50d10bedfff3df14777a575dd107c50edcafc7ec5862d0972",
    },
    {
        "stock": PRINT_KEY,
        "product": "KODAK VISION Color Print Film 2383 / 3383",
        "publication": "H-1-2383",
        "url": "https://www.kodak.com/content/products-brochures/motion-picture/KODAK-VISION-Color-Print-Film-2383-3383-technical-information.pdf",
        "filename": "vision_2383_3383_H-1-2383.pdf",
        "expected_sha256": "a72fa4482ebd891a9ac4a823cafe740e3587c56470f27e4dfd4391f5c3e5a207",
    },
)

_NUMBER = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
_CHANNEL_WORD = {
    "r": "R", "g": "G", "b": "B",
    "yellow": "yellow", "yellow-": "yellow",
    "magenta": "magenta", "magenta-": "magenta",
    "cyan": "cyan", "cyan-": "cyan", "cyan:": "cyan",
}


def judge_numeric(
    rmse: float,
    max_abs: float,
    rmse_limit: float,
    abs_limit: float,
    *,
    prerequisites_ok: bool,
    prerequisite_reason: str,
) -> tuple[str, str]:
    if not prerequisites_ok:
        return "insufficient", prerequisite_reason
    if rmse <= rmse_limit and max_abs <= abs_limit:
        return "pass", "residual is inside the predeclared tolerance"
    return "fail", "residual exceeds the predeclared tolerance"


def fit_axis(pixels: np.ndarray, values: np.ndarray) -> dict[str, float]:
    slope, intercept = np.polyfit(np.asarray(pixels, float), np.asarray(values, float), 1)
    if abs(slope) < 1e-12:
        raise ValueError("axis slope is zero")
    predicted_pixels = (values - intercept) / slope
    residual = predicted_pixels - pixels
    return {
        "slope_value_per_pixel": float(slope),
        "intercept": float(intercept),
        "max_pixel_residual": float(np.max(np.abs(residual))),
        "point_count": int(len(pixels)),
    }


def restore_signed_axis(points: list[dict[str, Any]], direction: str) -> tuple[list[dict[str, Any]], bool]:
    """Restore dropped minus signs when a confident zero and equal spacing require it.

    OCR often reads '-1.0' as '1.0'. The sign is restored only when exactly one
    high-confidence zero exists and the restored series is strictly monotonic
    with nearly uniform label spacing. Otherwise the original readings are kept.
    """
    ordered = sorted(points, key=lambda item: item["pixel"])
    zeros = [item for item in ordered if abs(item["value"]) < 1e-9 and item["conf"] >= 90]
    if len(zeros) != 1 or len(ordered) < 4:
        return ordered, False
    zero_pixel = zeros[0]["pixel"]
    restored: list[dict[str, Any]] = []
    changed = False
    for item in ordered:
        value = float(item["value"])
        original = value
        if direction == "increasing" and item["pixel"] < zero_pixel - 1 and value > 0:
            value = -value
        if direction == "decreasing" and item["pixel"] > zero_pixel + 1 and value > 0:
            value = -value
        changed = changed or value != original
        restored.append({**item, "value": value, "sign_restored": value != original})
    values = [item["value"] for item in restored]
    pixels = [item["pixel"] for item in restored]
    pairs = zip(values, values[1:])
    monotonic = all(b > a for a, b in pairs) if direction == "increasing" else all(b < a for a, b in pairs)
    steps = np.diff(pixels)
    uniform = len(steps) == 0 or float(np.max(steps)) <= 1.35 * float(np.min(steps))
    if not monotonic or not uniform:
        return ordered, False
    return restored, changed


def _sha256_file(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    urllib.request.urlretrieve(url, temporary)
    temporary.replace(destination)


def ensure_sources(cache: Path) -> list[dict[str, Any]]:
    cache.mkdir(parents=True, exist_ok=True)
    records = []
    for source in SOURCES:
        path = cache / source["filename"]
        if not path.is_file() or _sha256_file(path) != source["expected_sha256"]:
            _download(source["url"], path)
        digest = _sha256_file(path)
        if digest != source["expected_sha256"]:
            raise RuntimeError(f"Official PDF hash changed for {source['filename']}: {digest}")
        text = subprocess.check_output(["pdftotext", "-layout", str(path), "-"], text=True, stderr=subprocess.DEVNULL)
        info = subprocess.check_output(["pdfinfo", str(path)], text=True, stderr=subprocess.DEVNULL)
        records.append({
            **source,
            "path": str(path),
            "sha256": digest,
            "pdfinfo": info,
            "text": text,
        })
    return records


def _pdf_creation(info: str) -> str | None:
    for line in info.splitlines():
        if line.startswith("CreationDate:"):
            return line.split(":", 1)[1].strip()
    return None


def _published_label(text: str) -> str | None:
    match = re.search(
        r"(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+20\d\d",
        text,
    )
    revised = re.search(r"Revised\s+[0-9]{1,2}-[0-9]{2}", text)
    if not match:
        return None
    label = match.group(0).title()
    if revised:
        label = f"{label}; {revised.group(0)}"
    return label


def _ocr_array(image: np.ndarray, psm: str = "11") -> list[dict[str, Any]]:
    cache = Path(__file__).resolve().parents[2] / "cache" / "kodak_official" / "_ocr"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"page-{psm}.png"
    Image.fromarray(image).save(path)
    completed = subprocess.run(
        ["tesseract", str(path), "stdout", "--psm", psm, "tsv"],
        check=False, capture_output=True, text=True,
    )
    if completed.returncode != 0:
        return []
    rows = []
    for line in completed.stdout.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 12 or not parts[11].strip():
            continue
        confidence = float(parts[10])
        if confidence < 0:
            continue
        left, top, width, height = (int(parts[index]) for index in range(6, 10))
        rows.append({
            "text": parts[11].strip(),
            "conf": confidence,
            "left": left, "top": top, "width": width, "height": height,
            "cx": left + width / 2, "cy": top + height / 2,
        })
    return rows


def _numeric_tokens(words: list[dict[str, Any]], min_conf: float = 75) -> list[dict[str, Any]]:
    tokens = []
    for word in words:
        text = word["text"].strip(";,")
        if word["conf"] < min_conf or not _NUMBER.match(text):
            continue
        tokens.append({**word, "value": float(text), "pixel": word["cx"]})
    return tokens


def _frame(gray: np.ndarray) -> tuple[int, int, int, int] | None:
    dark = gray < 80
    rows = np.where(dark.mean(axis=1) > 0.45)[0]
    cols = np.where(dark.mean(axis=0) > 0.45)[0]
    if len(rows) < 2 or len(cols) < 2:
        return None
    return int(rows[0]), int(rows[-1]), int(cols[0]), int(cols[-1])


def _ticks(gray: np.ndarray, frame: tuple[int, int, int, int], axis: str) -> list[float]:
    top, bottom, left, right = frame
    if axis == "x-above":
        band = gray[max(0, top - 14):top + 3, left:right] < 90
        counts = band.sum(axis=0)
        origin = left
    elif axis == "x-below":
        band = gray[bottom - 2:min(gray.shape[0], bottom + 16), left:right] < 90
        counts = band.sum(axis=0)
        origin = left
    else:
        band = gray[top:bottom, max(0, left - 16):left + 3] < 90
        counts = band.sum(axis=1)
        origin = top
    centers = []
    start = None
    for index, count in enumerate(counts):
        if count >= 3 and start is None:
            start = index
        elif count < 3 and start is not None:
            centers.append(origin + (start + index - 1) / 2)
            start = None
    return centers


def _pair_ticks(labels: list[dict[str, Any]], ticks: list[float]) -> list[dict[str, Any]]:
    if len(ticks) < 4:
        return labels
    used: set[int] = set()
    paired = []
    for label in sorted(labels, key=lambda item: -item["conf"]):
        choices = [
            (abs(tick - label["pixel"]), index, tick)
            for index, tick in enumerate(ticks) if index not in used
        ]
        if not choices:
            continue
        distance, index, tick = min(choices)
        if distance > 30:
            continue
        used.add(index)
        paired.append({**label, "pixel": float(tick), "label_pixel": label["pixel"], "tick_distance": distance})
    return paired


def _dedupe_labels(labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for label in sorted(labels, key=lambda item: -item["conf"]):
        if any(abs(label["pixel"] - other["pixel"]) < 15 for other in kept):
            continue
        kept.append(label)
    return kept


def _accept_one_outlier(labels: list[dict[str, Any]], direction: str) -> dict[str, Any] | None:
    accepted = _accept_axis(labels, direction)
    if accepted is not None or len(labels) < 5:
        return accepted
    best = None
    for index in range(len(labels)):
        trial = _accept_axis(labels[:index] + labels[index + 1:], direction)
        if trial is not None and (best is None or trial["max_pixel_residual"] < best["max_pixel_residual"]):
            best = trial
    return best


def _best_axis(labels: list[dict[str, Any]], ticks: list[float], direction: str) -> dict[str, Any] | None:
    candidates = [
        _accept_one_outlier(labels, direction),
        _accept_one_outlier(_pair_ticks(labels, ticks), direction),
    ]
    valid = [item for item in candidates if item is not None]
    if not valid:
        return None
    return min(valid, key=lambda item: item["max_pixel_residual"])


def _accept_axis(labels: list[dict[str, Any]], direction: str) -> dict[str, Any] | None:
    labels = _dedupe_labels(labels)
    if len(labels) < 4:
        return None
    restored, signs_changed = restore_signed_axis(labels, direction)
    pixels = np.array([item["pixel"] for item in restored], float)
    values = np.array([item["value"] for item in restored], float)
    order = np.argsort(pixels)
    pixels, values = pixels[order], values[order]
    if direction == "increasing" and np.any(np.diff(values) <= 0):
        return None
    if direction == "decreasing" and np.any(np.diff(values) >= 0):
        return None
    try:
        fit = fit_axis(pixels, values)
    except (ValueError, np.linalg.LinAlgError):
        return None
    if fit["max_pixel_residual"] > 12.0:
        return None
    if min(item["conf"] for item in restored) < 75:
        return None
    return {
        **fit,
        "direction": direction,
        "sign_restoration": signs_changed,
        "labels": [
            {"text": item["text"], "value": item["value"], "pixel": item["pixel"], "conf": item["conf"]}
            for item in restored
        ],
    }


def _margin_ocr(gray: np.ndarray, box: tuple[int, int, int, int], scale: int = 4) -> list[dict[str, Any]]:
    top, bottom, left, right = box
    crop = gray[top:bottom, left:right]
    if crop.size == 0:
        return []
    image = Image.fromarray(crop).convert("RGB")
    image = image.resize((image.width * scale, image.height * scale), Image.Resampling.LANCZOS)
    image = ImageOps.expand(image, border=20, fill=(255, 255, 255))
    words = _ocr_array(np.asarray(image), "11")
    mapped = []
    for word in words:
        mapped.append({
            **word,
            "cx": left + (word["cx"] - 20) / scale,
            "cy": top + (word["cy"] - 20) / scale,
        })
    return mapped


def _calibrate(gray: np.ndarray, words: list[dict[str, Any]]) -> dict[str, Any] | None:
    frame = _frame(gray)
    if frame is None:
        return None
    top, bottom, left, right = frame
    height, width = gray.shape
    extra = _margin_ocr(gray, (max(0, top - 50), min(height, top + 5), left, right), 3)
    extra += _margin_ocr(gray, (bottom - 4, min(height, bottom + 55), max(0, left - 20), min(width, right + 20)), 4)
    extra += _margin_ocr(gray, (top, bottom, 0, min(width, left + 8)), 4)
    numbers = _numeric_tokens(words + extra, 75)
    y_labels = []
    for token in numbers:
        if token["cx"] < left - 4 and top - 8 <= token["cy"] <= bottom + 8:
            y_labels.append({**token, "pixel": token["cy"]})
    x_above = []
    x_below = []
    for token in numbers:
        if not (left + 8 <= token["cx"] <= right + 20):
            continue
        item = {**token, "pixel": token["cx"]}
        if top - 45 <= token["cy"] <= top + 4:
            x_above.append(item)
        elif bottom + 4 <= token["cy"] <= bottom + 48:
            x_below.append(item)
    y_axis = _best_axis(y_labels, _ticks(gray, frame, "y"), "decreasing")
    x_candidates = []
    for side, labels in (("x-above", x_above), ("x-below", x_below)):
        accepted = _best_axis(labels, _ticks(gray, frame, side), "increasing")
        if accepted is not None:
            x_candidates.append(accepted)
    if y_axis is None or not x_candidates:
        return None
    x_axis = min(x_candidates, key=lambda item: item["max_pixel_residual"])
    return {"frame": {"top": top, "bottom": bottom, "left": left, "right": right}, "x": x_axis, "y": y_axis}


def _ink(gray: np.ndarray, frame: dict[str, int], words: list[dict[str, Any]]) -> np.ndarray:
    dark = gray < 110
    top, bottom = frame["top"], frame["bottom"]
    left, right = frame["left"], frame["right"]
    grid = np.zeros_like(dark)
    interior = dark[top + 2:bottom - 1, left + 2:right - 1]
    for index, fraction in enumerate(interior.mean(axis=1)):
        if fraction > 0.90:
            grid[top + 2 + index, left:right] = True
    for index, fraction in enumerate(interior.mean(axis=0)):
        if fraction > 0.90:
            grid[top:bottom, left + 2 + index] = True
    ink = dark & ~grid
    for word in words:
        if word["conf"] < 40:
            continue
        y0 = max(0, word["top"] - 2)
        y1 = min(gray.shape[0], word["top"] + word["height"] + 2)
        x0 = max(0, word["left"] - 2)
        x1 = min(gray.shape[1], word["left"] + word["width"] + 2)
        if y1 <= top or y0 >= bottom or x1 <= left or x0 >= right:
            continue
        if (y1 - y0) * (x1 - x0) > 0.15 * (bottom - top) * (right - left):
            continue
        ink[y0:y1, x0:x1] = False
    ink[:top + 2, :] = False
    ink[bottom - 1:, :] = False
    ink[:, :left + 2] = False
    ink[:, right - 1:] = False
    return ink


def _column_runs(ink: np.ndarray, x: int, y_lo: int, y_hi: int) -> list[float]:
    y_lo = max(0, y_lo)
    y_hi = min(ink.shape[0], y_hi)
    column = ink[y_lo:y_hi, x]
    runs = []
    index = 0
    while index < len(column):
        if not column[index]:
            index += 1
            continue
        end = index
        while end < len(column) and column[end]:
            end += 1
        if 1 <= end - index <= 20:
            runs.append(y_lo + (index + end - 1) / 2)
        index = end
    return runs


def _seed(ink: np.ndarray, word: dict[str, Any]) -> tuple[int, int] | None:
    y_center = int(round(word["cy"]))
    x_left = int(word["left"])
    best = None
    for x in range(x_left - 2, max(0, x_left - 55), -1):
        runs = _column_runs(ink, x, y_center - 50, y_center + 50)
        if not runs:
            continue
        y = min(runs, key=lambda value: abs(value - y_center))
        distance = abs(x - x_left) + abs(y - y_center)
        if best is None or distance < best[0]:
            best = (distance, x, int(round(y)))
        if abs(y - y_center) < 18:
            return x, int(round(y))
    if best is None:
        return None
    return best[1], best[2]


def _follow(ink: np.ndarray, seed: tuple[int, int], frame: dict[str, int]) -> np.ndarray:
    samples: dict[int, float] = {}

    def walk(step: int) -> None:
        x, y = seed
        slope = 0.0
        gap = 0
        while frame["left"] + 3 <= x + step <= frame["right"] - 3:
            x_next = x + step
            predicted = y + slope
            runs = _column_runs(ink, x_next, int(predicted - 8), int(predicted + 9))
            if not runs:
                gap += 1
                if gap > 6:
                    break
                x = x_next
                continue
            y_next = min(runs, key=lambda value: abs(value - predicted))
            if abs(y_next - predicted) > 7:
                gap += 1
                if gap > 6:
                    break
                x = x_next
                continue
            slope = y_next - y
            x, y = x_next, y_next
            gap = 0
            samples[x] = y

    samples[seed[0]] = float(seed[1])
    walk(1)
    walk(-1)
    if len(samples) < 20:
        return np.empty((0, 2))
    xs = np.array(sorted(samples), float)
    return np.column_stack((xs, [samples[int(x)] for x in xs]))


def _glyph_letters(gray: np.ndarray, ink: np.ndarray, frame: dict[str, int]) -> list[dict[str, Any]]:
    """Read isolated R/G/B blobs. Letters that touch the curve are not separated."""
    import subprocess
    from scipy import ndimage
    x0 = frame["right"] - 110
    x1 = frame["right"] - 4
    y0 = frame["top"] + 5
    y1 = frame["bottom"] - 5
    if x1 <= x0 or y1 <= y0:
        return []
    labels, count = ndimage.label(ink[y0:y1, x0:x1])
    found = []
    for index in range(1, count + 1):
        ys, xs = np.where(labels == index)
        if not (15 <= len(ys) <= 280):
            continue
        if int(ys.max() - ys.min()) > 36 or int(xs.max() - xs.min()) > 36:
            continue
        cy = y0 + int((ys.min() + ys.max()) / 2)
        cx = x0 + int((xs.min() + xs.max()) / 2)
        patch = gray[max(0, cy - 16):cy + 16, max(0, cx - 14):cx + 14]
        if patch.size == 0:
            continue
        enlarged = Image.fromarray(patch.astype(np.uint8)).resize(
            (patch.shape[1] * 8, patch.shape[0] * 8), Image.Resampling.NEAREST
        )
        enlarged = ImageOps.expand(enlarged, border=24, fill=255)
        temporary = Path(__file__).resolve().parents[2] / "cache" / "kodak_official" / "_ocr" / "glyph.png"
        temporary.parent.mkdir(parents=True, exist_ok=True)
        enlarged.save(temporary)
        completed = subprocess.run(
            ["tesseract", str(temporary), "stdout", "--psm", "10", "-c", "tessedit_char_whitelist=RGB"],
            check=False, capture_output=True, text=True,
        )
        text = completed.stdout.strip()
        if text in {"R", "G", "B"}:
            found.append({
                "text": text, "conf": 90.0, "cx": float(cx), "cy": float(cy),
                "left": cx - 6, "top": cy - 8, "width": 12, "height": 16,
            })
    return found


def _identity_conflict(traces: dict[str, np.ndarray], words: list[dict[str, Any]]) -> str | None:
    positions: dict[str, tuple[float, float]] = {}
    for word in words:
        key = _CHANNEL_WORD.get(word["text"].lower())
        if key is None or word["conf"] < 60:
            continue
        positions.setdefault(key, (word["cx"], word["cy"]))
    for name, trace in traces.items():
        if name not in positions:
            return f"{name} has no OCR label position"
        label_x, label_y = positions[name]
        nearest = int(np.argmin(np.abs(trace[:, 0] - label_x)))
        if abs(trace[nearest, 0] - label_x) > 45 or abs(trace[nearest, 1] - label_y) > 35:
            return f"{name} trace does not pass its own label"
        median_x = float(np.median(trace[:, 0]))
        own = abs(median_x - label_x)
        others = [
            abs(median_x - positions[other][0])
            for other in traces if other != name and other in positions
        ]
        if others and own > min(others) + 20:
            return f"{name} trace is centered nearer another channel label"
    return None


def _trace_channels(
    gray: np.ndarray,
    ink: np.ndarray,
    frame: dict[str, int],
    words: list[dict[str, Any]],
    names: set[str],
) -> dict[str, np.ndarray]:
    traces = {}
    for word in words:
        key = _CHANNEL_WORD.get(word["text"].lower())
        if key not in names or word["conf"] < 60:
            continue
        if not (frame["left"] < word["cx"] < frame["right"] and frame["top"] < word["cy"] < frame["bottom"]):
            continue
        seed = _seed(ink, word)
        if seed is None:
            continue
        traced = _follow(ink, seed, frame)
        if len(traced) < 30:
            continue
        if float(np.ptp(traced[:, 1])) < 8:
            continue
        previous = traces.get(key)
        if previous is None or len(traced) > len(previous):
            traces[key] = traced
    return traces


def _outside_axis_fraction(values: np.ndarray, fit: dict[str, Any]) -> float:
    labels = [item["value"] for item in fit["labels"]]
    low, high = min(labels), max(labels)
    span = max(high - low, 1e-6)
    return float(np.mean((values < low - 0.08 * span) | (values > high + 0.08 * span)))


def _roughness(values: np.ndarray) -> float:
    if len(values) < 15:
        return 1.0
    smooth = np.convolve(values, np.ones(9) / 9.0, mode="valid")
    residual = values[4:-4] - smooth
    return float(np.sqrt(np.mean(residual ** 2)) / max(float(np.ptp(values)), 1e-6))


def _pixels_to_data(trace: np.ndarray, calibration: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    x_fit = calibration["x"]
    y_fit = calibration["y"]
    x_value = x_fit["intercept"] + x_fit["slope_value_per_pixel"] * trace[:, 0]
    y_value = y_fit["intercept"] + y_fit["slope_value_per_pixel"] * trace[:, 1]
    order = np.argsort(x_value)
    return x_value[order], y_value[order]


def _ink_hit_ratio(trace: np.ndarray, gray: np.ndarray) -> float:
    hits = 0
    for x, y in trace:
        yy = int(round(y))
        xx = int(round(x))
        y0, y1 = max(0, yy - 1), min(gray.shape[0], yy + 2)
        x0, x1 = max(0, xx - 1), min(gray.shape[1], xx + 2)
        hits += int(np.any(gray[y0:y1, x0:x1] < 110))
    return hits / max(1, len(trace))


def _load_profile(root: Path, key: str) -> dict[str, Any]:
    path = root / "upstream" / "spektrafilm" / "src" / "spektrafilm" / "data" / "profiles" / f"{key}.json"
    payload = json_load(path)
    data = payload["data"]
    return {
        "info": payload["info"],
        "wavelengths": np.asarray(data["wavelengths"], float),
        "log_sensitivity": np.asarray(data["log_sensitivity"], float),
        "channel_density": np.asarray(data["channel_density"], float),
        "log_exposure": np.asarray(data["log_exposure"], float),
        "density_curves": np.asarray(data["density_curves"], float),
    }


def json_load(path: Path) -> dict[str, Any]:
    import json
    return json.loads(path.read_text(encoding="utf-8"))


def _best_log_shift(
    official_x: np.ndarray,
    official_y: np.ndarray,
    profile_x: np.ndarray,
    profile_y: np.ndarray,
) -> dict[str, Any] | None:
    shifts = np.linspace(-6.0, 6.0, 1201)
    best: dict[str, Any] | None = None
    for shift in shifts:
        query = official_x - shift
        inside = (query >= profile_x[0]) & (query <= profile_x[-1]) & np.isfinite(official_y).all(axis=1)
        if int(inside.sum()) < 30 or float(np.ptp(official_x[inside])) < 1.5:
            continue
        aligned = np.column_stack([
            np.interp(query[inside], profile_x, profile_y[:, channel])
            for channel in range(3)
        ])
        residual = aligned - official_y[inside]
        rmse = float(np.sqrt(np.mean(residual ** 2)))
        if best is None or rmse < best["rmse"]:
            best = {
                "shift_subtracted_from_official_log_exposure": float(shift),
                "rmse": rmse,
                "max_abs": float(np.max(np.abs(residual))),
                "x": official_x[inside],
                "official": official_y[inside],
                "aligned_profile": aligned,
                "overlap_log_exposure": [float(official_x[inside][0]), float(official_x[inside][-1])],
                "sample_count": int(inside.sum()),
            }
    return best


def _sensitivity_alignment(
    official_x: np.ndarray,
    official_y: np.ndarray,
    wavelengths: np.ndarray,
    profile_column: np.ndarray,
) -> dict[str, Any] | None:
    finite = np.isfinite(official_y) & (official_x >= wavelengths[0]) & (official_x <= wavelengths[-1])
    if int(finite.sum()) < 15 or float(np.ptp(official_x[finite])) < 40:
        return None
    profile = np.interp(official_x[finite], wavelengths, profile_column)
    if not np.isfinite(profile).all():
        return None
    offset = float(np.mean(official_y[finite] - profile))
    aligned = profile + offset
    residual = aligned - official_y[finite]
    return {
        "additive_log10_offset_added_to_profile": offset,
        "rmse": float(np.sqrt(np.mean(residual ** 2))),
        "max_abs": float(np.max(np.abs(residual))),
        "x": official_x[finite],
        "official": official_y[finite],
        "aligned_profile": aligned,
        "sample_count": int(finite.sum()),
        "wavelength_span_nm": [float(official_x[finite][0]), float(official_x[finite][-1])],
    }


def _dye_alignment(
    official_x: np.ndarray,
    official_y: np.ndarray,
    wavelengths: np.ndarray,
    profile_column: np.ndarray,
) -> dict[str, Any] | None:
    finite_profile = np.isfinite(profile_column)
    if int(finite_profile.sum()) < 10 or not np.isfinite(official_y).any():
        return None
    if np.nanargmax(official_y) in {0, len(official_y) - 1}:
        return None
    official_peak = float(np.nanmax(official_y))
    profile_peak = float(np.nanmax(profile_column))
    if official_peak <= 0 or profile_peak <= 0:
        return None
    official_norm = official_y / official_peak
    profile_norm = profile_column / profile_peak
    finite = np.isfinite(official_norm) & (official_x >= wavelengths[0]) & (official_x <= wavelengths[-1])
    if int(finite.sum()) < 15 or float(np.ptp(official_x[finite])) < 40:
        return None
    aligned = np.interp(official_x[finite], wavelengths[finite_profile], profile_norm[finite_profile])
    residual = aligned - official_norm[finite]
    return {
        "alignment": "peak-normalize each curve independently; no wavelength shift and no extra density offset",
        "rmse": float(np.sqrt(np.mean(residual ** 2))),
        "max_abs": float(np.max(np.abs(residual))),
        "x": official_x[finite],
        "official": official_norm[finite],
        "aligned_profile": aligned,
        "sample_count": int(finite.sum()),
        "wavelength_span_nm": [float(official_x[finite][0]), float(official_x[finite][-1])],
    }


def _channel_order_note() -> str:
    return (
        "Profile column order follows upstream spektrafilm/utils/plotting.py at this commit: "
        "sensitivity and characteristic-curve columns are R, G, B; spectral-dye columns are C, M, Y. "
        "Kodak's 2383 film-structure text says the blue-sensitive layer forms yellow, the red-sensitive "
        "layer forms cyan, and the green-sensitive layer forms magenta. Sensitivity labels therefore "
        "map yellow-forming→B, magenta-forming→G, cyan-forming→R."
    )


def _figure_kind(words: list[dict[str, Any]]) -> str:
    text = " ".join(word["text"].lower() for word in words)
    if "sensitometric" in text:
        return "characteristic"
    if "sensitivity" in text and "spectral" in text:
        return "spectral_sensitivity"
    if "dye" in text and ("spectral" in text or "density" in text):
        return "spectral_dye_density"
    return "other"


def _extract_images(pdf: Path, destination: Path) -> list[dict[str, Any]]:
    destination.mkdir(parents=True, exist_ok=True)
    listing = subprocess.check_output(["pdfimages", "-list", str(pdf)], text=True)
    images = []
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) < 4 or not parts[0].isdigit():
            continue
        images.append({"page": int(parts[0]), "index": int(parts[1]), "kind": parts[2]})
    prefix = destination / "image"
    subprocess.check_call(["pdfimages", "-png", str(pdf), str(prefix)], stdout=subprocess.DEVNULL)
    paths = sorted(destination.glob("image-*.png"))
    if len(paths) != len(images):
        raise RuntimeError(f"pdfimages count mismatch for {pdf.name}: {len(paths)} files, {len(images)} rows")
    for path, row in zip(paths, images):
        row["path"] = path
    return images


def _caption_fields(words: list[dict[str, Any]]) -> dict[str, str]:
    text = re.sub(r"\s+", " ", " ".join(word["text"] for word in words))
    fields: dict[str, str] = {}
    exposure = re.search(r"Exposure:\s*(.{0,180}?)(?:Process:|$)", text, flags=re.IGNORECASE)
    process = re.search(r"Process:\s*([A-Z0-9-]{2,16})", text)
    criterion = re.search(r"(0\.2\s*>\s*D-min|D\s*=\s*1\.0|D-mins subtracted)", text, flags=re.IGNORECASE)
    if exposure:
        fields["exposure"] = exposure.group(1).strip(" ;")
    if process:
        fields["process"] = process.group(1).strip(" ;")
    if re.search(r"Status\s+A", text, flags=re.IGNORECASE):
        fields["densitometry"] = "Status A"
    elif re.search(r"Status\s+M", text, flags=re.IGNORECASE):
        fields["densitometry"] = "Status M"
    elif re.search(r"Densitometry:?\s*ECN-2", text, flags=re.IGNORECASE):
        fields["densitometry"] = "ECN-2"
    if criterion:
        fields["density_criterion"] = re.sub(r"\s+", "", criterion.group(1))
    return fields


def _compare_item(
    *,
    stock: str,
    kind: str,
    page: int,
    calibration: dict[str, Any],
    traces: dict[str, np.ndarray],
    gray: np.ndarray,
    profile: dict[str, Any],
    caption: dict[str, str],
    source: dict[str, Any],
    words: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    names = {
        "characteristic": {"R": 0, "G": 1, "B": 2},
        "spectral_sensitivity": {"cyan": 0, "magenta": 1, "yellow": 2},
        "spectral_dye_density": {"cyan": 0, "magenta": 1, "yellow": 2},
    }[kind]
    hit_ratios = {name: _ink_hit_ratio(trace, gray) for name, trace in traces.items()}
    missing = [name for name in names if name not in traces]
    poor_hit = [name for name, ratio in hit_ratios.items() if ratio < 0.90]
    axis_reason = None
    y_uncertainty = abs(calibration["y"]["max_pixel_residual"] * calibration["y"]["slope_value_per_pixel"])
    if kind == "spectral_sensitivity" and y_uncertainty > 0.5 * SENS_RMSE_MAX:
        axis_reason = f"y-axis calibration uncertainty {y_uncertainty:.3f} is too large for the tolerance"
    if kind == "spectral_dye_density" and y_uncertainty > 0.5 * DYE_RMSE_MAX:
        axis_reason = f"y-axis calibration uncertainty {y_uncertainty:.3f} is too large for the tolerance"
    base = {
        "stock": stock,
        "curve": kind,
        "source_page": page,
        "source_publication": source["publication"],
        "source_url": source["url"],
        "source_sha256": source["sha256"],
        "publication_date": _published_label(source["text"]),
        "pdf_creation": _pdf_creation(source["pdfinfo"]),
        "caption": caption,
        "profile_densitometer": profile["info"].get("densitometer"),
        "profile_reference_illuminant": profile["info"].get("reference_illuminant"),
        "profile_log_sensitivity_density_over_min": profile["info"].get("log_sensitivity_density_over_min"),
        "channel_order": _channel_order_note(),
        "axis": {
            "x_unit": "log10 exposure (lux-seconds)" if kind == "characteristic" else "wavelength nm",
            "y_unit": "density" if kind != "spectral_sensitivity" else "log10 sensitivity",
            "x_fit": {key: calibration["x"][key] for key in ("slope_value_per_pixel", "intercept", "max_pixel_residual", "sign_restoration")},
            "y_fit": {key: calibration["y"][key] for key in ("slope_value_per_pixel", "intercept", "max_pixel_residual", "sign_restoration")},
            "y_uncertainty_in_axis_units": y_uncertainty,
        },
        "ink_hit_ratio": hit_ratios,
        "claim": CLAIM,
    }
    if missing or poor_hit or axis_reason:
        reason = axis_reason or (
            f"trace incomplete or off the ink; missing={missing or 'none'}; ink_hit_below_0.90={poor_hit or 'none'}"
        )
        base.update({"status": "insufficient", "reason": reason, "tolerance": None, "alignment": None})
        return base, []
    data = {name: _pixels_to_data(traces[name], calibration) for name in names}
    rows: list[dict[str, Any]] = []
    implausible = []
    for name, (x_value, y_value) in data.items():
        outside = _outside_axis_fraction(y_value, calibration["y"])
        rough = _roughness(y_value)
        if outside > 0.08 or rough > 0.12 or len(y_value) < 25:
            implausible.append(f"{name}: outside={outside:.2f}, roughness={rough:.2f}, n={len(y_value)}")
    if implausible:
        base.update({
            "status": "insufficient",
            "reason": "traced curve leaves the labeled axis or is not smooth enough to digitize reliably: " + "; ".join(implausible),
            "alignment": "not applied",
        })
        return base, []
    conflict = _identity_conflict(traces, words)
    if conflict:
        base.update({
            "status": "insufficient",
            "reason": "channel identity is not reliable: " + conflict,
            "alignment": "not applied",
        })
        return base, []
    if kind == "characteristic":
        if str(profile["info"].get("densitometer")) == "status_A" and "status a" in caption.get("densitometry", "").lower():
            densitometer_ok = True
            densitometer_reason = "official caption and profile both say Status A"
        elif str(profile["info"].get("densitometer")) == "status_M" and caption.get("densitometry", "").lower() in {"status m", "m"}:
            densitometer_ok = True
            densitometer_reason = "official caption and profile both say Status M"
        else:
            densitometer_ok = False
            densitometer_reason = (
                f"densitometer not established as the same quantity: profile={profile['info'].get('densitometer')}, "
                f"figure caption={caption.get('densitometry', 'not read')}"
            )
        xs = [data[name][0] for name in ("R", "G", "B")]
        common = np.unique(np.concatenate(xs))
        common.sort()
        official = np.column_stack([
            np.interp(common, data[name][0], data[name][1]) for name in ("R", "G", "B")
        ])
        # Keep samples where every channel was actually traced nearby.
        covered = np.ones(len(common), dtype=bool)
        for name in ("R", "G", "B"):
            covered &= (common >= data[name][0][0]) & (common <= data[name][0][-1])
        common, official = common[covered], official[covered]
        alignment = _best_log_shift(common, official, profile["log_exposure"], profile["density_curves"]) if densitometer_ok else None
        if not densitometer_ok or alignment is None:
            base.update({
                "status": "insufficient",
                "reason": densitometer_reason if not densitometer_ok else "official and profile log-exposure domains do not overlap enough",
                "alignment": "not applied",
                "tolerance": {"rmse": CHAR_RMSE_MAX, "max_abs": CHAR_ABS_MAX, "unit": "density"},
            })
            return base, []
        status, reason = judge_numeric(
            alignment["rmse"], alignment["max_abs"], CHAR_RMSE_MAX, CHAR_ABS_MAX,
            prerequisites_ok=True, prerequisite_reason="",
        )
        base.update({
            "status": status,
            "reason": reason,
            "alignment": "one shared additive log-exposure shift of the profile axis; no density offset",
            "alignment_result": {key: alignment[key] for key in (
                "shift_subtracted_from_official_log_exposure", "rmse", "max_abs", "overlap_log_exposure", "sample_count"
            )},
            "sampling_range": {"log_exposure_lux_seconds": alignment["overlap_log_exposure"], "sample_count": alignment["sample_count"]},
            "tolerance": {"rmse": CHAR_RMSE_MAX, "max_abs": CHAR_ABS_MAX, "unit": "Status density"},
            "reference_condition": caption,
            "series": alignment,
        })
        for index, channel in enumerate(("R", "G", "B")):
            for x_value, official_value, profile_value in zip(
                alignment["x"], alignment["official"][:, index], alignment["aligned_profile"][:, index]
            ):
                rows.append({
                    "stock": stock, "curve": kind, "channel": channel, "x": float(x_value),
                    "official": float(official_value), "profile_aligned": float(profile_value),
                    "residual": float(profile_value - official_value), "status": status,
                })
        return base, rows

    limit = SENS_RMSE_MAX if kind == "spectral_sensitivity" else DYE_RMSE_MAX
    abs_limit = SENS_ABS_MAX if kind == "spectral_sensitivity" else DYE_ABS_MAX
    profile_matrix = profile["log_sensitivity"] if kind == "spectral_sensitivity" else profile["channel_density"]
    series = {}
    rmses = []
    maxes = []
    for name, column in names.items():
        official_x, official_y = data[name]
        if kind == "spectral_sensitivity":
            aligned = _sensitivity_alignment(official_x, official_y, profile["wavelengths"], profile_matrix[:, column])
        else:
            if "peak-normalized" not in source["text"].lower() and stock == FILM_KEY:
                base.update({"status": "insufficient", "reason": "PDF text does not say the dye curves are peak-normalized", "alignment": None})
                return base, []
            if stock == PRINT_KEY:
                base.update({
                    "status": "insufficient",
                    "reason": (
                        "Official 2383 dye curves are normalized to a visual neutral of 1.0 for a xenon-arc "
                        "viewing illuminant. The profile does not record that normalization, so peak-normalization "
                        "would not be the stated condition and a raw residual would mix scale with shape."
                    ),
                    "alignment": "not applied",
                    "tolerance": {"rmse": DYE_RMSE_MAX, "max_abs": DYE_ABS_MAX, "unit": "normalized density"},
                })
                return base, []
            aligned = _dye_alignment(official_x, official_y, profile["wavelengths"], profile_matrix[:, column])
        if aligned is None:
            base.update({
                "status": "insufficient",
                "reason": f"{name} trace does not cover a usable official wavelength span",
                "alignment": None,
            })
            return base, []
        series[name] = aligned
        rmses.append(aligned["rmse"])
        maxes.append(aligned["max_abs"])
    if kind == "spectral_sensitivity":
        criterion = str(profile["info"].get("log_sensitivity_density_over_min"))
        caption_criterion = caption.get("density_criterion", "")
        matches_criterion = (
            (criterion == "0.2" and "0.2" in caption_criterion)
            or (criterion == "1.0" and "1.0" in caption_criterion)
        )
        if not matches_criterion:
            base.update({
                "status": "insufficient",
                "reason": f"density criterion mismatch or unread: profile={criterion}, caption={caption_criterion or 'not read'}",
                "alignment": "not applied",
            })
            return base, []
        densitometer = caption.get("densitometry", "")
        profile_densitometer = str(profile["info"].get("densitometer"))
        expected = {"status_M": "status m", "status_A": "status a"}.get(profile_densitometer)
        if expected is None or densitometer.lower() != expected:
            base.update({
                "status": "insufficient",
                "reason": (
                    f"spectral-sensitivity densitometer is not the profile densitometer: "
                    f"profile={profile_densitometer}, caption={densitometer or 'not read'}"
                ),
                "alignment": "not applied",
            })
            return base, []
    rmse = float(np.mean(rmses))
    max_abs = float(np.max(maxes))
    status, reason = judge_numeric(rmse, max_abs, limit, abs_limit, prerequisites_ok=True, prerequisite_reason="")
    alignment_name = (
        "per-channel additive log10 offset; no wavelength shift"
        if kind == "spectral_sensitivity"
        else "independent peak normalization; no wavelength shift"
    )
    base.update({
        "status": status,
        "reason": reason,
        "alignment": alignment_name,
        "alignment_result": {
            name: {
                key: value for key, value in item.items()
                if key not in {"x", "official", "aligned_profile"}
            }
            for name, item in series.items()
        },
        "rmse_mean_across_channels": rmse,
        "max_abs": max_abs,
        "sampling_range": {name: item.get("wavelength_span_nm") for name, item in series.items()},
        "tolerance": {"rmse": limit, "max_abs": abs_limit, "unit": base["axis"]["y_unit"]},
        "reference_condition": caption,
        "series": series,
    })
    for name, item in series.items():
        for x_value, official_value, profile_value in zip(item["x"], item["official"], item["aligned_profile"]):
            rows.append({
                "stock": stock, "curve": kind, "channel": name, "x": float(x_value),
                "official": float(official_value), "profile_aligned": float(profile_value),
                "residual": float(profile_value - official_value), "status": status,
            })
    return base, rows


def _ensure_item_fields(item: dict[str, Any]) -> dict[str, Any]:
    """Every curve record states page, units, range, alignment, tolerance, and status."""
    kind = item.get("curve")
    axis = item.get("axis") or {}
    item["units"] = item.get("units") or {"x": axis.get("x_unit"), "y": axis.get("y_unit")}
    if not item.get("sampling_range"):
        item["sampling_range"] = (
            "figure axis calibrated; curve samples were not accepted for numeric comparison"
            if axis else "not established"
        )
    if not item.get("alignment"):
        item["alignment"] = "not applied"
    preset = {
        "characteristic": {"rmse": CHAR_RMSE_MAX, "max_abs": CHAR_ABS_MAX, "unit": "density"},
        "spectral_sensitivity": {"rmse": SENS_RMSE_MAX, "max_abs": SENS_ABS_MAX, "unit": "log10 sensitivity"},
        "spectral_dye_density": {"rmse": DYE_RMSE_MAX, "max_abs": DYE_ABS_MAX, "unit": "normalized density"},
    }.get(kind, {})
    tolerance = item.get("tolerance")
    if not isinstance(tolerance, dict):
        item["tolerance"] = {**preset, "scored": False}
    else:
        tolerance.setdefault("scored", item.get("status") in {"pass", "fail"})
    item.setdefault("source_page", None)
    item.setdefault("status", "insufficient")
    return item


def _strip_series(item: dict[str, Any]) -> dict[str, Any]:
    published = {key: value for key, value in item.items() if key != "series"}
    return published


def _plot(items: list[dict[str, Any]], profiles: dict[str, dict[str, Any]], path: Path) -> None:
    figure, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)
    for axis, item in zip(axes.flat, items):
        profile = profiles[item["stock"]]
        title = f"{item['stock']} {item['curve']}\n{item['status']}"
        axis.set_title(title, fontsize=9)
        series = item.get("series")
        if not series:
            axis.text(0.5, 0.5, item.get("reason", "insufficient"), ha="center", va="center", wrap=True, fontsize=8)
            axis.set_axis_off()
            continue
        if item["curve"] == "characteristic":
            for column, channel in enumerate(("R", "G", "B")):
                axis.plot(profile["log_exposure"], profile["density_curves"][:, column], color=channel, alpha=0.35)
            for column, channel in enumerate(("R", "G", "B")):
                axis.plot(series["x"], series["official"][:, column], color=channel, linewidth=1.0)
            axis.set_xlabel("official log exposure")
            axis.set_ylabel("density")
        else:
            for name, payload in series.items():
                axis.plot(payload["x"], payload["official"], label=f"{name} official")
                axis.plot(payload["x"], payload["aligned_profile"], linestyle="--", label=f"{name} profile")
            axis.legend(fontsize=6)
            axis.set_xlabel("wavelength nm")
        axis.grid(alpha=0.25)
    figure.suptitle("Kodak source-conformance (not independent film validation)")
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=120)
    plt.close(figure)


def run_source_conformance(root: Path) -> dict[str, Any]:
    root = root.resolve()
    cache = root / "cache" / "kodak_official"
    sources = ensure_sources(cache)
    profiles = {key: _load_profile(root, key) for key in (FILM_KEY, PRINT_KEY)}
    items: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    expected = {
        (FILM_KEY, "characteristic"),
        (FILM_KEY, "spectral_sensitivity"),
        (FILM_KEY, "spectral_dye_density"),
        (PRINT_KEY, "characteristic"),
        (PRINT_KEY, "spectral_sensitivity"),
        (PRINT_KEY, "spectral_dye_density"),
    }
    found: set[tuple[str, str]] = set()
    for source in sources:
        extracted = _extract_images(Path(source["path"]), cache / source["filename"].replace(".pdf", ""))
        for image in extracted:
            if image["kind"] != "image":
                continue
            rgb = np.asarray(Image.open(image["path"]).convert("RGB"))
            gray = rgb.mean(axis=2)
            words = _ocr_array(rgb, "11")
            kind = _figure_kind(words)
            if kind == "other":
                continue
            found.add((source["stock"], kind))
            calibration = _calibrate(gray, words)
            if calibration is None:
                items.append(_ensure_item_fields({
                    "stock": source["stock"], "curve": kind, "source_page": image["page"],
                    "status": "insufficient",
                    "reason": "axis labels could not be calibrated from OCR and tick geometry",
                    "source_url": source["url"], "source_sha256": source["sha256"],
                    "publication_date": _published_label(source["text"]),
                    "claim": CLAIM,
                }))
                continue
            wanted = {"R", "G", "B"} if kind == "characteristic" else {"cyan", "magenta", "yellow"}
            ink = _ink(gray, calibration["frame"], words)
            if kind == "characteristic":
                words = [*words, *_glyph_letters(gray, ink, calibration["frame"])]
            traces = _trace_channels(gray, ink, calibration["frame"], words, wanted)
            item, item_rows = _compare_item(
                stock=source["stock"], kind=kind, page=image["page"], calibration=calibration,
                traces=traces, gray=gray, profile=profiles[source["stock"]],
                caption=_caption_fields(words), source=source, words=words,
            )
            items.append(_ensure_item_fields(item))
            rows.extend(item_rows)
    for stock, kind in sorted(expected - found):
        items.append(_ensure_item_fields({
            "stock": stock, "curve": kind, "status": "unavailable",
            "reason": "no embedded figure with this title was found in the official PDF",
            "claim": CLAIM,
        }))
    items = sorted(items, key=lambda item: (item["stock"], item["curve"]))
    validation = root / "validation"
    validation.mkdir(parents=True, exist_ok=True)
    _plot(items, profiles, validation / "source_curve_overlay.png")
    residual_path = validation / "source_curve_residuals.csv"
    with residual_path.open("w", encoding="utf-8", newline="") as handle:
        fields = [
            "stock", "curve", "channel", "x", "official", "profile_aligned", "residual", "status",
            "source_page", "x_unit", "y_unit", "sampling_range", "alignment",
            "tolerance_rmse", "tolerance_max_abs", "tolerance_scored",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        if not rows:
            for item in items:
                units = item.get("units") or {}
                tolerance = item.get("tolerance") or {}
                writer.writerow({
                    "stock": item.get("stock", ""),
                    "curve": item.get("curve", ""),
                    "channel": "",
                    "x": "",
                    "official": "",
                    "profile_aligned": "",
                    "residual": "",
                    "status": item.get("status", ""),
                    "source_page": item.get("source_page", ""),
                    "x_unit": units.get("x", ""),
                    "y_unit": units.get("y", ""),
                    "sampling_range": item.get("sampling_range", ""),
                    "alignment": item.get("alignment", ""),
                    "tolerance_rmse": tolerance.get("rmse", ""),
                    "tolerance_max_abs": tolerance.get("max_abs", ""),
                    "tolerance_scored": tolerance.get("scored", ""),
                })
    payload = {
        "schema_version": 1,
        "claim": CLAIM,
        "not_independent_physical_validation": True,
        "real_film_delta_e00": "not computed",
        "method": (
            "Embedded images were extracted with poppler pdfimages. They are raster XObjects, "
            "not vector curve paths; rendering the page at a higher DPI would only interpolate "
            "the same pixels. Axis values come from Tesseract OCR plus geometric tick pairing. "
            "Minus signs dropped by OCR are restored only by the documented zero-anchor rule. "
            "Curve ink is traced from the OCR channel label. Failed traces stay insufficient."
        ),
        "tolerances": {
            "characteristic_density": {"rmse": CHAR_RMSE_MAX, "max_abs": CHAR_ABS_MAX},
            "spectral_sensitivity_log10": {"rmse": SENS_RMSE_MAX, "max_abs": SENS_ABS_MAX},
            "spectral_dye_peak_normalized": {"rmse": DYE_RMSE_MAX, "max_abs": DYE_ABS_MAX},
        },
        "sources": [
            {
                "product": source["product"],
                "publication": source["publication"],
                "url": source["url"],
                "sha256": source["sha256"],
                "publication_date": _published_label(source["text"]),
                "pdf_creation": _pdf_creation(source["pdfinfo"]),
            }
            for source in sources
        ],
        "items": [_strip_series(item) for item in items],
    }
    write_json(validation / "official_source_conformance.json", payload)
    return payload
