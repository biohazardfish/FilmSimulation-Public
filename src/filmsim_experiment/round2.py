"""Round 2: full-resolution repeat, Kodak source-conformance, and phase 5."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .baseline import build_round1_baseline
from .display_diagnostics import area_downsample, write_display_diagnostics
from .experiment import (
    FILM_KEY,
    PRINT_KEY,
    UPSTREAM_COMMIT,
    display_transform,
    sha256_file,
    write_json,
    write_text,
)
from .reproducibility import run_full_resolution_repeat
from .source_conformance import run_source_conformance
from .uncertainty import G4B_REASON, G4B_STATUS, run_uncertainty, write_uncertainty_artifacts


def _preview(image: np.ndarray) -> np.ndarray:
    encoded, _info = display_transform(image)
    return np.clip(area_downsample(encoded, 900), 0.0, 1.0)


def _write_comparison(root: Path, raw_preview: np.ndarray, negative_preview: np.ndarray, print_preview: np.ndarray, lut: dict[str, Any]) -> None:
    figure, axes = plt.subplots(1, 4, figsize=(14, 4.2), constrained_layout=True)
    panels = (
        (raw_preview, "neutral RAW\nsame display transform"),
        (negative_preview, "virtual negative\nscan_film"),
        (print_preview, "5219 → 2383 print"),
    )
    for axis, (image, title) in zip(axes[:3], panels):
        axis.imshow(np.clip(image, 0.0, 1.0))
        axis.set_title(title)
        axis.set_axis_off()
    axes[3].set_axis_off()
    axes[3].text(
        0.5, 0.5, "LUT\nunavailable\n\n" + lut["reason"],
        ha="center", va="center", wrap=True, fontsize=8,
    )
    axes[3].set_title("LUT")
    figure.suptitle("Same RAW and the Round 1 hard-clip display. LUT is not substituted.")
    path = root / "output" / "round2_comparison.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=140)
    plt.close(figure)


def _g4a(items: list[dict[str, Any]]) -> dict[str, str]:
    return {f"{item['stock']}:{item['curve']}": item["status"] for item in items}


def _g5(comparison_ready: bool, uncertainty: dict[str, Any]) -> str:
    required = ("model_spread", "sensitivity_matrix", "relative_to_real_film")
    if not comparison_ready or any(key not in uncertainty for key in required):
        return "fail"
    if uncertainty["relative_to_real_film"].get("delta_e00") != "not computed":
        return "fail"
    if not uncertainty["model_spread"].get("this_is_not_real_film_error"):
        return "fail"
    return "pass"


def _report(root: Path, baseline: dict[str, Any], repeat: dict[str, Any], conformance: dict[str, Any], uncertainty: dict[str, Any], display: dict[str, Any], gates: dict[str, Any]) -> str:
    item_rows = "\n".join(
        f"| `{item['stock']}` | {item['curve']} | {item['status']} | {item.get('source_page', '—')} | {item.get('reason', '')} |"
        for item in conformance["items"]
    )
    spread = uncertainty["model_spread"]
    methods = ", ".join(uncertainty["spectral_methods"]["ran"])
    repeat_rows = "\n".join(
        f"| `{stage}` | {repeat['matches'][stage]} | {repeat['elapsed_seconds']['pass_1'][stage]:.1f} | {repeat['elapsed_seconds']['pass_2'][stage]:.1f} |"
        for stage in repeat["stages"]
    )
    source_rows = "\n".join(
        f"- {source['product']}，{source['publication']}，{source['publication_date']}，{source['url']}，SHA-256 `{source['sha256']}`"
        for source in conformance["sources"]
    )
    return f"""# FilmSimulation Round 2

## 這是什麼

Round 2 在不改 `input/_C5A0880.CR3`、不改 `upstream/spektrafilm` tracked 內容的前提下，補上 Round 1 的三個缺口：全解析度重跑、Kodak 官方曲線的 source-conformance，以及同一條 RAW 的顯示對照與模型不確定性。

這不是獨立的真實膠片驗證。spektrafilm profile 本身來自公開 datasheet。官方曲線對得上，只表示 profile 與 Kodak 技術資料在所述對齊下的 source-conformance。專案裡沒有受控實測的 5219/2383 樣片，所以 **不計算、也不宣稱真實膠片 Delta E00**。G4b 維持 insufficient。

## 基準

Round 1 的輸入、profile、上游 commit 與關鍵輸出 hash 在 `docs/round1_baseline.json`。上游 commit 仍是 `{UPSTREAM_COMMIT}`。輸入 hash `{baseline['input']['sha256']}`。

## G3 全解析度重跑

兩次各自解碼並跑完 scene、四個 tap、negative scan、final print。比較的是未壓縮像素 SHA-256。第二次的大圖沒有寫成 EXR。

狀態：**{repeat['status']}**

| stage | match | seconds pass 1 | seconds pass 2 |
|---|---|---:|---:|
{repeat_rows}

## G4a 官方資料 source-conformance

只使用 Kodak 官方 PDF：

{source_rows}

曲線在 PDF 裡是光柵圖，不是矢量路徑。座標來自 OCR 與刻度線，追蹤失敗或通道對不上就標 insufficient，不靠目視填座標。容差在看殘差之前已寫死。

| profile | curve | status | page | reason |
|---|---|---|---:|---|
{item_rows}

## G4b

**{G4B_STATUS}**。{G4B_REASON}

## G5 對照與不確定性

三联圖是同一條全解析度 RAW，套與 Round 1 相同的 hard-clip 顯示轉換後縮小的預覽：中性 RAW、virtual negative、5219→2383。LUT：**unavailable**。沒有拿別的 LUT 代替。

光譜重建只跑這個 commit 的 `filming.py` 真正分支：{methods}。`rgb_to_raw_aces_idt` 不是可選 pipeline 方法，沒有拿來充數。

模型 spread（scene-linear ACEScg RMSE，{spread['reference_method']} 對 {spread['other_method']}）：**{spread['rmse']:.6f}**。這是兩種重建之間的差，不是相對真實膠片的誤差。

敏感度矩陣在空間效果關閉後的 160 px 長邊面積縮圖上跑白平衡、負片曝光和 print exposure，另有 yellow printer-light CC。數字在 `validation/uncertainty_metrics.json`。

顯示 hard clip 的全解析度計數在 `validation/display_diagnostics.json`。受影響像素比例 {display['affected_pixel_fraction']:.6f}，被裁切的 component 比例 {display['clipped_component_fraction']:.6f}。線性 EXR 沒有改寫。平滑高光版本是 `output/5219_to_2383_display_smooth_highlight_shoulder_srgb.jpg`，公式為 `max(x,0)/(1+max(x,0))` 後接 sRGB CCTF，不是 ACES，也不是核心輸出。ACES Output Transform 在這個環境不可用。

## 閘門

- G3：{gates['G3']}
- G4a：逐項，見上表
- G4b：{gates['G4b']}
- G5：{gates['G5']}

## 重跑

```bash
cd {root}
PYTHONPATH=src .venv/bin/python scripts/run_experiment.py --round2
PYTHONPATH=src .venv/bin/python -m pytest tests -q
```

## 仍然不足

- G4b 沒有獨立受控實測。
- 官方曲線多數無法在通道、密度計或軸校準都成立時完成數值比較；insufficient 的項目沒有被改判成 pass。
- 5219 sensitometric 圖的密度計文字是 ECN-2，profile 是 status_M，同一份 PDF 沒有把兩者寫成同一件事。
- 光譜曲線會交叉，標籤又壓在線上，可靠分通道的追蹤沒有成立。
- 敏感度矩陣是縮圖上的模型響應，不是全解析度，也不是真實膠片誤差。
- 沒有公平的 5219→2383 LUT。
- 平滑顯示仍會把負的 linear sRGB 夾到 0；它不取代 Round 1 的 hard-clip TIFF/JPEG。
"""


def _inventory(root: Path, paths: list[str]) -> list[dict[str, Any]]:
    records = []
    for relative in paths:
        path = root / relative
        records.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return records


def run_round2(root: Path) -> dict[str, Any]:
    root = root.resolve()
    print("Round 2 baseline", flush=True)
    # Round 2 consumes the frozen descriptor but must never rewrite it.
    baseline = build_round1_baseline(root)
    print("Round 2 source-conformance", flush=True)
    conformance = run_source_conformance(root)
    previews: dict[str, np.ndarray] = {}

    def keep_scene(scene: np.ndarray) -> None:
        previews["raw"] = _preview(scene)
        previews["scene"] = scene

    def keep_final(final: np.ndarray) -> None:
        previews["print"] = _preview(final)
        print("Round 2 display diagnostics", flush=True)
        previews["display"] = write_display_diagnostics(root, final)

    def keep_negative(negative: np.ndarray) -> None:
        previews["negative"] = _preview(negative)

    repeat = run_full_resolution_repeat(
        root / "input" / "_C5A0880.CR3",
        on_first_scene=keep_scene,
        on_first_final=keep_final,
        on_first_negative=keep_negative,
    )
    scene = previews.pop("scene")
    print("Round 2 uncertainty", flush=True)
    uncertainty = run_uncertainty(root, root / "input" / "_C5A0880.CR3", scene)
    del scene
    lut = uncertainty["lut"]
    _write_comparison(root, previews["raw"], previews["negative"], previews["print"], lut)
    write_uncertainty_artifacts(root, uncertainty)
    display = previews["display"]
    gates = {
        "G3": repeat["status"],
        "G4a": _g4a(conformance["items"]),
        "G4b": G4B_STATUS,
        "G5": "fail",
    }
    comparison_ready = (root / "output" / "round2_comparison.png").is_file() and (root / "output" / "round2_uncertainty.png").is_file()
    gates["G5"] = _g5(comparison_ready, uncertainty)
    report = _report(root, baseline, repeat, conformance, uncertainty, display, gates)
    write_text(root / "output" / "ROUND2_REPORT.md", report)
    write_json(root / "validation" / "fullres_repeat.json", repeat)
    artifacts = _inventory(root, [
        "docs/round1_baseline.json",
        "validation/official_source_conformance.json",
        "validation/source_curve_overlay.png",
        "validation/source_curve_residuals.csv",
        "validation/fullres_repeat.json",
        "validation/uncertainty_metrics.json",
        "validation/display_diagnostics.json",
        "output/round2_comparison.png",
        "output/round2_uncertainty.png",
        "output/display_clipping_map.png",
        "output/5219_to_2383_display_smooth_highlight_shoulder_srgb.jpg",
        "output/ROUND2_REPORT.md",
    ])
    manifest = {
        "schema_version": 1,
        "experiment": "FilmSimulation round 2",
        "claim": "source-conformance and model spread; not independent real-film validation",
        "upstream_commit": UPSTREAM_COMMIT,
        "profiles": {"film": FILM_KEY, "print": PRINT_KEY},
        "status": "complete",
        "validation_gates": gates,
        "g3": {"status": repeat["status"], "matches": repeat["matches"]},
        "artifacts": artifacts,
    }
    write_json(root / "output" / "round2_manifest.json", manifest)
    return manifest
