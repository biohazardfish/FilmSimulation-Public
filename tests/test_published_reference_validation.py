from __future__ import annotations

import json
from pathlib import Path

from filmsim_experiment.phase2.analysis import protected_inventory
from filmsim_experiment.published_reference_validation import (
    build_published_reference_validation,
    render_report,
)


ROOT = Path(__file__).resolve().parents[1]


def test_g4_record_is_reproducible_and_keeps_evidence_boundaries() -> None:
    generated = build_published_reference_validation(ROOT)
    committed = json.loads(
        (ROOT / "validation/published_reference_validation.json").read_text()
    )
    assert generated == committed
    assert generated["status"] == "complete_with_limitations"
    assert generated["physical_fidelity"] == "not experimentally verified"
    assert generated["gate_decision"]["completed"] is True
    assert generated["gate_decision"]["independent_physical_dataset_required"] is False


def test_g4_quantifies_available_model_evidence_without_inventing_residuals() -> None:
    payload = build_published_reference_validation(ROOT)
    assert payload["step_wedge"]["sample_count"] == 481
    assert payload["step_wedge"]["ev_range"] == [-6.0, 6.0]
    assert all(payload["step_wedge"]["deterministic"].values())
    assert len(payload["published_comparisons"]) == 6
    assert all(row["status"] == "not_evaluable" for row in payload["published_comparisons"])
    assert all(row["residuals"] is None for row in payload["published_comparisons"])
    assert payload["spectral_profiles"]["film"]["arrays"]["channel_density"]["nan_count"] == 15
    assert payload["spectral_profiles"]["print"]["arrays"]["channel_density"]["nan_count"] == 19
    assert payload["model_sensitivity"]["this_is_not_real_film_error"] is True


def test_g4_report_and_protected_masters() -> None:
    payload = build_published_reference_validation(ROOT)
    report = render_report(payload)
    assert report == (ROOT / "docs/phase4/G4_PUBLISHED_REFERENCE_VALIDATION.md").read_text()
    assert "不代表經實驗驗證的物理真實度" in report
    assert "六組曲線均維持 `not_evaluable`" in report
    public_manifest = ROOT / "PUBLIC_SNAPSHOT_MANIFEST.json"
    if public_manifest.is_file():
        snapshot = json.loads(public_manifest.read_text(encoding="utf-8"))
        assert "output/manifest.json" in snapshot["excluded_paths"]
        assert "docs/round1_baseline.json" in snapshot["excluded_paths"]
        return
    protected = protected_inventory(ROOT)
    missing = [
        path for path, row in protected["files"].items()
        if row["actual_sha256"] is None
    ]
    present = [
        row for row in protected["files"].values()
        if row["actual_sha256"] is not None
    ]
    assert all(row["matches_manifest"] for row in present)
    if missing:
        # Large frozen masters are intentionally absent from a fresh clone.
        # The exact-hash criterion remains enforced when the private evidence
        # bundle is supplied and by scripts/verify_frozen_evidence.py.
        assert all(path.endswith((".exr", ".tif", ".jpg")) for path in missing)
    else:
        assert protected["all_match"] is True
