from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from filmsim_experiment.baseline import write_round1_baseline
from filmsim_experiment.display_diagnostics import quantify_display_clip, smooth_highlight_shoulder
from filmsim_experiment.experiment import build_params
from filmsim_experiment.reproducibility import STAGES, g3_status
from filmsim_experiment.round2 import _g5
from filmsim_experiment.source_conformance import judge_numeric, restore_signed_axis
from filmsim_experiment.uncertainty import G4B_REASON, G4B_STATUS, lut_comparison, spectral_methods_declared
from spektrafilm import simulate


ROOT = Path(__file__).resolve().parents[1]


def test_round1_baseline_descriptor_is_read_only():
    baseline_path = ROOT / "docs" / "round1_baseline.json"
    if baseline_path.is_file():
        import json
        payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    else:
        manifest = ROOT / "PUBLIC_SNAPSHOT_MANIFEST.json"
        assert manifest.is_file()
        import json
        public_record = json.loads(manifest.read_text(encoding="utf-8"))
        assert "docs/round1_baseline.json" in public_record["excluded_paths"]
        return
    assert payload["upstream"]["commit"] == "3bb2c2d2801ff68b92019cf1dbcbb133d60832bc"
    assert payload["audit"]["phase_5"] == "not complete in Round 1"
    assert all(item["matches_round1_manifest"] is not False for item in payload["key_outputs"])


def test_round1_baseline_regeneration_requires_explicit_confirmation():
    with pytest.raises(RuntimeError, match="confirm=True"):
        write_round1_baseline(ROOT)


def test_sign_restoration_only_when_spacing_requires_it():
    points = [
        {"pixel": 10, "value": 1.0, "conf": 95, "text": "1.0"},
        {"pixel": 20, "value": 0.0, "conf": 96, "text": "0.0"},
        {"pixel": 30, "value": 1.0, "conf": 95, "text": "1.0"},
        {"pixel": 40, "value": 2.0, "conf": 95, "text": "2.0"},
        {"pixel": 50, "value": 3.0, "conf": 95, "text": "3.0"},
    ]
    restored, changed = restore_signed_axis(points, "decreasing")
    assert changed is True
    assert [item["value"] for item in restored] == [1.0, 0.0, -1.0, -2.0, -3.0]
    already = restore_signed_axis(
        [{"pixel": 10 + 10 * index, "value": value, "conf": 95, "text": str(value)} for index, value in enumerate((1, 0, -1, -2, -3))],
        "decreasing",
    )
    assert already[1] is False


def test_numeric_judge_does_not_pass_when_prerequisites_fail():
    status, _reason = judge_numeric(0.01, 0.01, 0.08, 0.25, prerequisites_ok=False, prerequisite_reason="densitometer")
    assert status == "insufficient"
    status, _reason = judge_numeric(0.2, 0.3, 0.08, 0.25, prerequisites_ok=True, prerequisite_reason="")
    assert status == "fail"
    status, _reason = judge_numeric(0.01, 0.02, 0.08, 0.25, prerequisites_ok=True, prerequisite_reason="")
    assert status == "pass"


def test_g3_passes_only_when_every_full_resolution_stage_matches():
    matches = {stage: True for stage in STAGES}
    assert g3_status(matches) == "pass"
    matches["final_print"] = False
    assert g3_status(matches) == "fail"
    del matches["scene"]
    assert g3_status(matches) == "fail"


def test_g4b_stays_insufficient_and_g5_needs_both_products():
    assert G4B_STATUS == "insufficient"
    assert "Delta E00" in G4B_REASON
    uncertainty = {
        "model_spread": {"this_is_not_real_film_error": True},
        "sensitivity_matrix": [],
        "relative_to_real_film": {"delta_e00": "not computed"},
    }
    assert _g5(False, uncertainty) == "fail"
    assert _g5(True, uncertainty) == "pass"


def test_clip_counts_and_smooth_shoulder_are_not_the_hard_clip():
    image = np.array([[[-0.4, 0.2, 3.0]]], dtype=np.float32)
    stats = quantify_display_clip(image)
    assert stats["pixel_count"] == 1
    assert stats["clipped_component_count_below_zero"] >= 1
    assert stats["clipped_component_count_above_one"] >= 1
    assert stats["affected_pixel_count"] == 1
    smooth = smooth_highlight_shoulder(image)
    assert smooth.shape == image.shape
    assert float(smooth.max()) < 1.0
    assert float(smooth.min()) >= 0.0


def test_only_two_pipeline_spectral_methods_run_and_lut_is_unavailable():
    methods = spectral_methods_declared(ROOT)
    assert methods == ["hanatos2025", "mallett2019"]
    image = np.full((4, 4, 3), 0.18, dtype=np.float32)
    for method in methods:
        params = build_params(rgb_to_raw_method=method)
        result = np.asarray(simulate(image, params, digest_params_first=True, print_timings=False))
        assert result.shape == image.shape
        assert np.isfinite(result).all()
    with pytest.raises(ValueError):
        build_params(rgb_to_raw_method="not-a-real-method")
    lut = lut_comparison(ROOT)
    assert lut["status"] == "unavailable"
    assert lut["included_in_comparison"] is False
    assert lut["cube_files"] == []
