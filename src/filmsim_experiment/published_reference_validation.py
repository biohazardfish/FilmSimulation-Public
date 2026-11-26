"""Build the offline G4 published-reference validation record."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

from .experiment import sha256_file


INPUTS = (
    "output/phase2/sensitometry_samples.csv",
    "output/phase2/sensitometry_metrics.json",
    "output/phase2/spectral_profile_audit.json",
    "output/phase2/manifest.json",
    "validation/official_source_conformance.json",
    "validation/uncertainty_metrics.json",
    "validation/fullres_repeat.json",
    "validation/raw_input_provenance.json",
)


def _load_json(root: Path, relative: str) -> Any:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def _step_wedge(root: Path, sensitometry: dict[str, Any]) -> dict[str, Any]:
    with (root / "output/phase2/sensitometry_samples.csv").open(
        "r", encoding="utf-8", newline="",
    ) as handle:
        rows = list(csv.DictReader(handle))
    ev = [float(row["ev"]) for row in rows]
    return {
        "sample_count": len(rows),
        "ev_range": [min(ev), max(ev)],
        "scene_linear_definition": "0 EV = 0.18; scene_linear = 0.18 * 2**EV",
        "channels": sensitometry["channels"],
        "deterministic": sensitometry["deterministic"],
        "interpretation": (
            "Native model-domain step-wedge statistics. cmy_film and cmy_print are model "
            "channel coefficients, not measured Status M or Status A density."
        ),
    }


def _spectral_summary(spectral: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for material in ("film", "print"):
        record = spectral[material]
        arrays: dict[str, Any] = {}
        for name, info in record["arrays"].items():
            total = math.prod(info["shape"])
            arrays[name] = {
                **info,
                "sample_count": total,
                "nan_fraction": info["nan_count"] / total,
            }
        result[material] = {
            "profile_key": record["profile_key"],
            "densitometer": record["densitometer"],
            "reference_illuminant": record["reference_illuminant"],
            "viewing_illuminant": record["viewing_illuminant"],
            "nan_runtime_semantics": record["nan_runtime_semantics"],
            "arrays": arrays,
        }
    return result


def _published_comparisons(source: dict[str, Any]) -> list[dict[str, Any]]:
    comparisons = []
    for item in source["items"]:
        comparisons.append({
            "profile": item["stock"],
            "curve": item["curve"],
            "status": "not_evaluable" if item["status"] == "insufficient" else item["status"],
            "reason": item["reason"],
            "residuals": item.get("residuals"),
            "tolerance": item["tolerance"],
            "conditions": {
                "caption": item["caption"],
                "profile_densitometer": item.get("profile_densitometer"),
                "profile_reference_illuminant": item.get("profile_reference_illuminant"),
                "units": item["units"],
            },
            "source": {
                "publication": item["source_publication"],
                "page": item["source_page"],
                "sha256": item["source_sha256"],
                "url": item["source_url"],
            },
        })
    return comparisons


def build_published_reference_validation(root: Path) -> dict[str, Any]:
    root = root.resolve()
    for relative in INPUTS:
        if not (root / relative).is_file():
            raise RuntimeError(f"missing G4 input: {relative}")
    sensitometry = _load_json(root, "output/phase2/sensitometry_metrics.json")
    spectral = _load_json(root, "output/phase2/spectral_profile_audit.json")
    phase2_manifest = _load_json(root, "output/phase2/manifest.json")
    source = _load_json(root, "validation/official_source_conformance.json")
    uncertainty = _load_json(root, "validation/uncertainty_metrics.json")
    fullres = _load_json(root, "validation/fullres_repeat.json")
    raw_provenance = _load_json(root, "validation/raw_input_provenance.json")
    comparisons = _published_comparisons(source)
    spectral_summary = _spectral_summary(spectral)
    non_evaluable = sum(row["status"] == "not_evaluable" for row in comparisons)
    return {
        "schema_version": 1,
        "gate": "G4 Published-Reference Numerical Validation",
        "status": "complete_with_limitations",
        "physical_fidelity": "not experimentally verified",
        "claim_boundary": (
            "This gate establishes numerical reproducibility, parameter provenance, model-domain "
            "consistency, and documented comparison with available published references. It does "
            "not establish accuracy relative to an independently measured physical film sample."
        ),
        "inputs": {
            relative: {"sha256": sha256_file(root / relative)} for relative in INPUTS
        },
        "parameter_provenance": phase2_manifest["provenance"],
        "raw_input_provenance": {
            "dual_pixel_raw": raw_provenance["capture"]["dual_pixel_raw"],
            "raw_image_count": raw_provenance["container"]["raw_image_count"],
            "auxiliary_dual_pixel_data_used": raw_provenance["decoder"]["auxiliary_dual_pixel_data_used"],
            "evidence": "validation/raw_input_provenance.json",
        },
        "step_wedge": _step_wedge(root, sensitometry),
        "published_comparisons": comparisons,
        "spectral_profiles": spectral_summary,
        "reproducibility": {
            "synthetic_taps": sensitometry["deterministic"],
            "full_resolution_status": fullres["status"],
            "full_resolution_stage_matches": fullres["matches"],
            "parameters_sha256": phase2_manifest["provenance"]["parameters_sha256"],
        },
        "model_sensitivity": uncertainty["model_spread"],
        "unsupported_assumptions": [
            {
                "id": "published_curve_digitization",
                "status": "not_evaluable",
                "quantification": {"not_evaluable": non_evaluable, "total": len(comparisons)},
                "reason": "Published raster traces lack sufficient channel, axis, or measurement-definition comparability.",
            },
            {
                "id": "spectral_nan_to_zero_light",
                "status": "quantified_model_assumption",
                "quantification": {
                    material: {
                        name: {
                            "nan_count": info["nan_count"],
                            "sample_count": info["sample_count"],
                            "nan_fraction": info["nan_fraction"],
                        }
                        for name, info in record["arrays"].items()
                        if info["nan_count"]
                    }
                    for material, record in spectral_summary.items()
                },
                "reason": "Runtime maps NaN transmitted-light samples to zero; this is not measured interpolation.",
            },
            {
                "id": "rgb_to_spectrum_non_uniqueness",
                "status": "quantified_model_sensitivity",
                "quantification": uncertainty["model_spread"],
                "reason": "Difference between runnable reconstruction methods is not error relative to real film.",
            },
            {
                "id": "dpraw_auxiliary_image_unused",
                "status": "not_evaluable",
                "quantification": {"raw_images": raw_provenance["container"]["raw_image_count"], "used": 1},
                "reason": "The effect of unused phase/depth information on the scene-linear input was not evaluated and is not spectral evidence.",
            },
            {
                "id": "independent_real_film_measurement",
                "status": "unavailable_limitation",
                "quantification": None,
                "reason": uncertainty["relative_to_real_film"]["reason"],
            },
        ],
        "gate_decision": {
            "roadmap_task": "FS-P4-03",
            "completed": True,
            "basis": "All available references were assessed; non-comparable evidence remains explicit rather than being scored as pass or zero error.",
            "independent_physical_dataset_required": False,
        },
    }


def render_report(payload: dict[str, Any]) -> str:
    comparisons = "\n".join(
        f"| `{row['profile']}` | {row['curve']} | {row['status']} | {row['reason']} |"
        for row in payload["published_comparisons"]
    )
    step_rows = []
    for channel in ("R", "G", "B"):
        for material in ("film", "print"):
            item = payload["step_wedge"]["channels"][channel][material]
            step_rows.append(
                f"| {material} | {channel} | {item['d_min']:.6f} | {item['d_max']:.6f} | "
                f"{item['straight_line_gradient']:.6f} | {item['monotonicity_vs_scene_ev']['violations']} |"
            )
    spectral_rows = []
    for material in ("film", "print"):
        record = payload["spectral_profiles"][material]
        sensitivity = record["arrays"]["log_sensitivity"]
        density = record["arrays"]["channel_density"]
        base = record["arrays"]["base_density"]
        spectral_rows.append(
            f"| {record['profile_key']} | {record['densitometer']} | "
            f"{sensitivity['nan_count']}/{sensitivity['sample_count']} | "
            f"{density['nan_count']}/{density['sample_count']} ({density['nan_fraction']:.2%}) | "
            f"{base['nan_count']}/{base['sample_count']} ({base['nan_fraction']:.2%}) |"
        )
    assumptions = "\n".join(
        f"- `{item['id']}` — **{item['status']}**：{item['reason']}"
        for item in payload["unsupported_assumptions"]
    )
    spread = payload["model_sensitivity"]
    return f"""# G4 Published-Reference Numerical Validation

## 判定

狀態：**complete_with_limitations**。`FS-P4-03` 的離線數值驗證已完成；不需要實體膠片資料集。這個完成狀態只代表可重現性、參數 provenance、模型內部一致性與已發表參考比較均已明示，**不代表經實驗驗證的物理真實度**。

## 模擬 step-wedge

固定 neutral ramp 共 {payload['step_wedge']['sample_count']} 階，範圍 {payload['step_wedge']['ev_range'][0]:.0f} 至 +{payload['step_wedge']['ev_range'][1]:.0f} EV，0 EV 定義為 scene-linear 0.18。下列數字是模型通道係數，不是 Status M／A 實測密度。

| material | channel | min | max | straight-line gradient | monotonic violations |
|---|---|---:|---:|---:|---:|
{chr(10).join(step_rows)}

## Kodak published-reference comparison

| profile | curve | status | reason |
|---|---|---|---|
{comparisons}

六組曲線均維持 `not_evaluable`；沒有把缺失 residual 當成零誤差或 pass。

## 光譜 sensitivity 與 dye-density arrays

兩個 profiles 均覆蓋 380–780 nm、81 個波長點。NaN 統計如下：

| profile | densitometer | sensitivity NaN | channel-density NaN | base-density NaN |
|---|---|---:|---:|---:|
{chr(10).join(spectral_rows)}

Runtime 將相應 transmitted-light NaN samples 設為零光量；這是已量化的模型假設，不是實測補值。

## 可重現性與模型敏感度

- 合成 taps 全部 deterministic：`{all(payload['reproducibility']['synthetic_taps'].values())}`。
- 全解析度重跑：`{payload['reproducibility']['full_resolution_status']}`。
- 固定參數 SHA-256：`{payload['reproducibility']['parameters_sha256']}`。
- Hanatos 2025 對 Mallett 2019：RMSE `{spread['rmse']:.9f}`、max abs `{spread['max_abs']:.9f}`；這只是 spectral reconstruction model spread。
- 輸入是 DPRAW、包含 `{payload['raw_input_provenance']['raw_image_count']}` 個 RAW images；FilmSimulation 只使用預設 image，未使用 auxiliary dual-pixel data。

## 未支持假設與限制

{assumptions}

## Evidence boundary

本 gate 沒有獨立真實 5219／2383 樣片、matched capture 或真實膠片 Delta E00。模型 consistency 與 published-reference source conformance 不得改稱 physical fidelity。
"""
