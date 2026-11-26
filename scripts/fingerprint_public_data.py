#!/usr/bin/env python3
"""Numerical lineage fingerprint (FS-P6-01, study definition §4.2 step d).

Compares public 5219/2383 curve datasets against spektrafilm's legacy raw
digitizations (tag v0.2.0-legacy) and the pinned profiles (3bb2c2d). Every
repository is read at a pinned commit through ``git show``, so the output is
reproducible. The script reports agreement only; it is not a model comparison
and computes no FS-P6-02 residuals.
"""

from __future__ import annotations

import argparse
import ast
import csv
import io
import json
import re
import subprocess
from pathlib import Path
from typing import Callable

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / "cache" / "public_data_repos"
DEFAULT_OUTPUT = ROOT / "validation" / "public_data" / "fingerprints.json"

SPEKTRAFILM = {
    "url": "https://github.com/andreavolpato/spektrafilm.git",
    "legacy_commit": "77d448adb7d9562823c4b4e6cb5ba78eeef71452",
    "legacy_tag": "v0.2.0-legacy",
    "profile_commit": "3bb2c2d2801ff68b92019cf1dbcbb133d60832bc",
}
LEGACY_DIRS = {
    "5219": "agx_emulsion/data/film/negative/kodak_vision3_500t",
    "2383": "agx_emulsion/data/paper/kodak_2383",
}
PROFILES = {
    "5219": "src/spektrafilm/data/profiles/kodak_vision3_500t.json",
    "2383": "src/spektrafilm/data/profiles/kodak_2383.json",
}
CANDIDATE_REPOS = {
    "spectral_film_lut": ("https://github.com/JanLohse/spectral_film_lut.git", "a15043f6fe2d365d0c359d22e0868076800916d9"),
    "film_scan_calibration": ("https://github.com/OwlMightyCh/film-scan-calibration.git", "3716966fbc82760ed9be38362519689ff2aca811"),
    "luce_develop": ("https://github.com/dymokomi/luce-develop.git", "a7276fd348d8e3d65022a86fc3fd170d878ed250"),
    "fixer": ("https://github.com/AllastorV/Fixer.git", "c9577b4c1c7e1686ff03832bce735693df7d6036"),
    "polut": ("https://github.com/TomPoczos/PoLUT.git", "8172157b6600394d718ea2091c501805b2108eb5"),
    "moderates_film_simulator": ("https://github.com/Moder4te/moderates-film-simulator.git", "f83a8b5941fb708c59c386e57883a2e20ffe9c6b"),
}

INTER_DIGITIZER_PAIRS = (
    ("5219", "film_scan_calibration", "luce_develop"),
    ("5219", "fixer", "film_scan_calibration"),
    ("5219", "fixer", "luce_develop"),
    ("5219", "moderates_film_simulator", "luce_develop"),
    ("5219", "spectral_film_lut", "luce_develop"),
    ("2383", "fixer", "luce_develop"),
    ("2383", "spectral_film_lut", "luce_develop"),
)

# Curve key: (quantity, channel). Channels: r/g/b for characteristic curves and
# log sensitivity (red-, green-, blue-sensitive layer); c/m/y/mid/min for dyes.
Curves = dict[tuple[str, str], tuple[np.ndarray, np.ndarray]]


def ensure_repo(cache: Path, name: str, url: str, commit: str) -> Path:
    path = cache / name
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--quiet", "--filter=blob:none", "--no-checkout", url, str(path)], check=True)
    have = subprocess.run(["git", "-C", str(path), "cat-file", "-e", f"{commit}^{{commit}}"], capture_output=True)
    if have.returncode != 0:
        subprocess.run(["git", "-C", str(path), "fetch", "--quiet", "origin", commit], check=True)
    return path


def git_show(repo: Path, commit: str, path: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{path}"], check=True, capture_output=True, text=True).stdout


def _xy(x, y) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray([np.nan if v is None else v for v in x], dtype=float)
    y = np.asarray([np.nan if v is None else v for v in y], dtype=float)
    keep = np.isfinite(x) & np.isfinite(y)
    order = np.argsort(x[keep])
    return x[keep][order], y[keep][order]


def _dict_curve(points: dict) -> tuple[np.ndarray, np.ndarray]:
    return _xy([float(k) for k in points], list(points.values()))


def load_legacy(repo: Path, product: str) -> Curves:
    base = LEGACY_DIRS[product]
    files = {
        ("characteristic_curve", "r"): "density_curve_r.csv",
        ("characteristic_curve", "g"): "density_curve_g.csv",
        ("characteristic_curve", "b"): "density_curve_b.csv",
        ("spectral_sensitivity", "r"): "log_sensitivity_r.csv",
        ("spectral_sensitivity", "g"): "log_sensitivity_g.csv",
        ("spectral_sensitivity", "b"): "log_sensitivity_b.csv",
        ("spectral_dye_density", "c"): "dye_density_c.csv",
        ("spectral_dye_density", "m"): "dye_density_m.csv",
        ("spectral_dye_density", "y"): "dye_density_y.csv",
        ("spectral_dye_density", "mid"): "dye_density_mid.csv",
        ("spectral_dye_density", "min"): "dye_density_min.csv",
    }
    curves: Curves = {}
    for key, name in files.items():
        try:
            text = git_show(repo, SPEKTRAFILM["legacy_commit"], f"{base}/{name}")
        except subprocess.CalledProcessError:
            continue
        rows = [row for row in csv.reader(io.StringIO(text)) if len(row) >= 2]
        curves[key] = _xy([float(r[0]) for r in rows], [float(r[1]) for r in rows])
    return curves


def load_profile(repo: Path, product: str) -> Curves:
    data = json.loads(git_show(repo, SPEKTRAFILM["profile_commit"], PROFILES[product]))["data"]
    wl = data["wavelengths"]
    logs = np.asarray(data["log_sensitivity"], dtype=float)
    dyes = np.asarray(data["channel_density"], dtype=float)
    dc = np.asarray(data["density_curves"], dtype=float)
    curves: Curves = {}
    for i, ch in enumerate("rgb"):
        curves[("characteristic_curve", ch)] = _xy(data["log_exposure"], dc[:, i])
        curves[("spectral_sensitivity", ch)] = _xy(wl, logs[:, i])
    for i, ch in enumerate("cmy"):
        curves[("spectral_dye_density", ch)] = _xy(wl, dyes[:, i])
    curves[("spectral_dye_density", "mid")] = _xy(wl, data["midscale_neutral_density"])
    if product == "5219":
        curves[("spectral_dye_density", "min")] = _xy(wl, data["base_density"])
    return curves


def _sfl_kwargs(text: str) -> dict:
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "FilmData":
            out = {}
            for kw in node.keywords:
                try:
                    out[kw.arg] = ast.literal_eval(kw.value)
                except ValueError:
                    pass
            return out
    raise ValueError("FilmData call not found")


def _sfl_curves(kw: dict) -> Curves:
    curves: Curves = {}
    for i, ch in enumerate("rgb"):
        curves[("characteristic_curve", ch)] = _dict_curve(kw["sensiometric_curve"][i])
        curves[("spectral_sensitivity", ch)] = _dict_curve(kw["log_sensitivity"][i])
    for i, ch in enumerate("cmy"):
        curves[("spectral_dye_density", ch)] = _dict_curve(kw["spectral_density"][i])
    if kw.get("d_ref_sd"):
        curves[("spectral_dye_density", "mid")] = _dict_curve(kw["d_ref_sd"])
    if kw.get("d_min_sd"):
        curves[("spectral_dye_density", "min")] = _dict_curve(kw["d_min_sd"])
    return curves


def load_spectral_film_lut(repo: Path, commit: str, product: str) -> Curves:
    path = {
        "5219": "src/spectral_film_lut/negative_film/kodak_5219.py",
        "2383": "src/spectral_film_lut/print_film/kodak_2383.py",
    }[product]
    return _sfl_curves(_sfl_kwargs(git_show(repo, commit, path)))


def load_polut(repo: Path, commit: str, product: str) -> Curves:
    if product != "2383":
        return {}
    kw = json.loads(git_show(repo, commit, "film_paper_filter_data/papers/color/for_negatives/kodak_2383.json"))
    return _sfl_curves(kw)


def load_film_scan_calibration(repo: Path, commit: str, product: str) -> Curves:
    if product != "5219":
        return {}
    char = json.loads(git_show(repo, commit, "data/films/V3500T_datasheet_curves.json"))["char_curves"]
    dye = json.loads(git_show(repo, commit, "data/films/Vision3_500T_dye_density.json"))
    sens = json.loads(git_show(repo, commit, "data/films/Vision3_500T_spectral_sensitivity.json"))
    curves: Curves = {}
    for ch in "rgb":
        curves[("characteristic_curve", ch)] = _xy(char["log_exposure"], char["density"][ch.upper()])
    for ch, name in zip("rgb", ("cyan", "magenta", "yellow")):
        curves[("spectral_sensitivity", ch)] = _xy(sens["wavelength_nm"], sens["log_sensitivity"][name])
    shared = dye["shared_full_curves"]
    for ch, name in zip("cmy", ("cyan", "magenta", "yellow")):
        curves[("spectral_dye_density", ch)] = _xy(shared["wavelength_nm"], shared[name])
    curves[("spectral_dye_density", "mid")] = _xy(dye["midscale_neutral"]["wavelength_nm"], dye["midscale_neutral"]["density"])
    curves[("spectral_dye_density", "min")] = _xy(dye["minimum_density"]["wavelength_nm"], dye["minimum_density"]["density"])
    return curves


def load_luce_develop(repo: Path, commit: str, product: str) -> Curves:
    path = {"5219": "dev/film/kodak_vision3_500t_5219.json", "2383": "dev/film/kodak_2383.json"}[product]
    d = json.loads(git_show(repo, commit, path))
    curves: Curves = {}
    for ch, name in zip("rgb", ("red", "green", "blue")):
        curves[("characteristic_curve", ch)] = _xy(d["characteristic"]["log_h"], d["characteristic"][name])
        curves[("spectral_sensitivity", ch)] = _xy(d["sensitivity"]["nm"], d["sensitivity"][name])
    for ch, name in zip("cmy", ("cyan", "magenta", "yellow")):
        curves[("spectral_dye_density", ch)] = _xy(d["dyes"]["nm"], d["dyes"][name])
    if "neutral" in d and isinstance(d["neutral"], dict):
        curves[("spectral_dye_density", "mid")] = _xy(d["neutral"]["nm"], d["neutral"]["density"])
    elif "neutral" in d["dyes"]:
        curves[("spectral_dye_density", "mid")] = _xy(d["dyes"]["nm"], d["dyes"]["neutral"])
    if "d_min" in d:
        curves[("spectral_dye_density", "min")] = _xy(d["d_min"]["nm"], d["d_min"]["density"])
    return curves


def load_fixer(repo: Path, commit: str, product: str) -> Curves:
    path = {"5219": "bake/data/stocks/kodak-vision3-500t.json", "2383": "bake/data/stocks/kodak-2383.json"}[product]
    d = json.loads(git_show(repo, commit, path))
    # 5219 sensitometry is on a camera-stops axis; convert to log10 units so the
    # x-shift search below can align it.
    x_scale = np.log10(2.0) if product == "5219" else 1.0
    curves: Curves = {}
    for ch in "rgb":
        s = d["sensitometry"]["channels"][ch]
        curves[("characteristic_curve", ch)] = _xy(np.asarray(s["x"], dtype=float) * x_scale, s["density"])
        q = d["spectral_sensitivity"]["channels"][ch]
        curves[("spectral_sensitivity", ch)] = _xy(q["wavelength"], q["value"])
    names = {"c": "cyan", "m": "magenta", "y": "yellow", "mid": "midscale_neutral" if product == "5219" else "visual_neutral", "min": "minimum"}
    for ch, name in names.items():
        if name in d["dye_density"]["curves"]:
            q = d["dye_density"]["curves"][name]
            curves[("spectral_dye_density", ch)] = _xy(q["wavelength"], q["value"])
    return curves


def load_moderates(repo: Path, commit: str, product: str) -> Curves:
    if product != "5219":
        return {}
    text = git_show(repo, commit, "core/color/films.js")
    grid = re.search(r"const H_V500T = \[([^\]]*)\]", text).group(1)
    x = [float(v) for v in grid.replace("\n", " ").split(",") if v.strip()]
    block = text[text.index('id: "kodak-vision3-500t"'):]
    block = block[block.index("characteristicCurves"):]
    curves: Curves = {}
    for ch in "rgb":
        values = re.search(ch + r": curve\(H_V500T, \[([^\]]*)\]", block).group(1)
        curves[("characteristic_curve", ch)] = _xy(x, [float(v) for v in values.replace("\n", " ").split(",") if v.strip()])
    return curves


LOADERS: dict[str, Callable[[Path, str, str], Curves]] = {
    "moderates_film_simulator": load_moderates,
    "spectral_film_lut": load_spectral_film_lut,
    "film_scan_calibration": load_film_scan_calibration,
    "luce_develop": load_luce_develop,
    "fixer": load_fixer,
    "polut": load_polut,
}


def _resample(x: np.ndarray, y: np.ndarray, grid: np.ndarray) -> np.ndarray:
    out = np.interp(grid, x, y)
    out[(grid < x[0]) | (grid > x[-1])] = np.nan
    return out


def _stats(diff: np.ndarray) -> dict:
    diff = diff[np.isfinite(diff)]
    if diff.size == 0:
        return {"n": 0, "rms": None, "max_abs": None}
    return {"n": int(diff.size), "rms": round(float(np.sqrt(np.mean(diff**2))), 5), "max_abs": round(float(np.max(np.abs(diff))), 5)}


def compare(candidate: tuple[np.ndarray, np.ndarray], reference: tuple[np.ndarray, np.ndarray], allow_x_shift: bool) -> dict:
    cx, cy = candidate
    rx, ry = reference
    raw = _stats(_resample(cx, cy, rx) - ry)
    exact = float(np.mean([np.min(np.abs(rx - v)) < 1e-4 for v in cx])) if cx.size else 0.0
    best = None
    shifts = np.arange(-2.5, 2.5001, 0.005) if allow_x_shift else np.array([0.0])
    for s in shifts:
        d = _resample(cx + s, cy, rx) - ry
        ok = np.isfinite(d)
        if ok.sum() < max(5, 0.5 * rx.size):
            continue
        off = float(np.mean(d[ok]))
        st = _stats(d - off)
        if best is None or st["rms"] < best["rms"]:
            best = {**st, "x_shift": round(float(s), 3), "y_offset": round(-off, 5)}
    return {"raw": raw, "aligned": best, "exact_x_match_fraction": round(exact, 3)}


def fingerprint(cache: Path) -> dict:
    spk = ensure_repo(cache, "spektrafilm", SPEKTRAFILM["url"], SPEKTRAFILM["legacy_commit"])
    ensure_repo(cache, "spektrafilm", SPEKTRAFILM["url"], SPEKTRAFILM["profile_commit"])
    refs = {p: {"legacy": load_legacy(spk, p), "profile": load_profile(spk, p)} for p in ("5219", "2383")}
    results: dict = {}
    loaded: dict[tuple[str, str], Curves] = {}
    for name, (url, commit) in CANDIDATE_REPOS.items():
        repo = ensure_repo(cache, name, url, commit)
        results[name] = {"url": url, "commit": commit, "products": {}}
        for product in ("5219", "2383"):
            curves = LOADERS[name](repo, commit, product)
            if not curves:
                continue
            loaded[(name, product)] = curves
            per = {}
            for key, cand in sorted(curves.items()):
                if cand[0].size < 3:
                    continue
                shift = key[0] == "characteristic_curve"
                entry = {"n_points": int(cand[0].size)}
                for ref_name, ref in refs[product].items():
                    if key in ref:
                        entry[ref_name] = compare(cand, ref[key], allow_x_shift=shift)
                per[f"{key[0]}:{key[1]}"] = entry
            results[name]["products"][product] = per
    # Digitizer-to-digitizer agreement on the same Kodak figure, as a trace-noise
    # yardstick for judging agreement with the legacy CSVs.
    inter: dict = {}
    for product, a, b in INTER_DIGITIZER_PAIRS:
        ca, cb = loaded.get((a, product)), loaded.get((b, product))
        if not ca or not cb:
            continue
        for key in sorted(set(ca) & set(cb)):
            inter[f"{product}:{a}~{b}:{key[0]}:{key[1]}"] = compare(ca[key], cb[key], allow_x_shift=key[0] == "characteristic_curve")["aligned"]
    return {
        "task": "FS-P6-01",
        "procedure": "docs/phase6/PUBLIC_DATA_STUDY_DEFINITION.md §4.2 step d",
        "reference": SPEKTRAFILM,
        "metrics": {
            "raw": "candidate linearly interpolated onto the reference abscissae inside the overlap; no alignment",
            "aligned": "best x shift (characteristic curves only, ±2.5 in 0.005 steps) plus mean y offset removed; RMS after alignment",
            "exact_x_match_fraction": "fraction of candidate abscissae within 1e-4 of a reference abscissa",
            "profile_note": "profile arrays are re-gridded, D-min subtracted and renormalized by spektrafilm, so only 'aligned' is meaningful against 'profile'",
        },
        "derived_rule": "flag derived_from_spektrafilm when raw RMS against legacy < max(stated digitization error, 0.01) with exact_x_match_fraction >= 0.9",
        "candidates": results,
        "inter_digitizer": inter,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    result = fingerprint(args.cache)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
