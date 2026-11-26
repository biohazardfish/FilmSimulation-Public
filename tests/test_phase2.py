from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from filmsim_experiment.experiment import FILM_KEY, PRINT_KEY
from filmsim_experiment.phase2.analysis import build_phase2_params, profile_spectral_audit, validate_pins
from filmsim_experiment.phase2.benchmark_worker import synthetic_image
from filmsim_experiment.phase2.color_validation import evaluate_color_reference, load_color_reference
from filmsim_experiment.phase2.metrics import curve_metrics, error_metrics, exposure_axis_offset, metric_record, monotonicity
from spektrafilm import digest_params
from spektrafilm.runtime.pipeline import SimulationPipeline


ROOT = Path(__file__).resolve().parents[1]


def test_known_error_and_curve_metrics():
    reference = np.array([0.0, 1.0, 2.0])
    actual = np.array([0.0, 2.0, 2.0])
    errors = error_metrics(actual, reference)
    assert errors["rmse"] == pytest.approx(np.sqrt(1 / 3))
    assert errors["mae"] == pytest.approx(1 / 3)
    assert errors["max_abs"] == 1.0
    x = np.linspace(-2, 2, 101)
    y = 1.2 * x + 3.0
    result = curve_metrics(x, y, y.copy())
    assert result["straight_line_gradient"] == pytest.approx(1.2)
    assert result["reference_error"]["rmse"] == 0.0


def test_exposure_offset_known_answer():
    x = np.linspace(-1, 1, 101)
    reference_x = np.linspace(-2, 2, 401)
    reference_y = 1.0 / (1.0 + np.exp(-reference_x))
    actual = np.interp(x + 0.3, reference_x, reference_y)
    result = exposure_axis_offset(x, actual, reference_x, reference_y)
    assert result["log10_exposure"] == pytest.approx(0.3, abs=0.002)
    assert result["stops"] == pytest.approx(0.3 / np.log10(2), abs=0.01)


def test_monotonicity_and_metric_enums():
    assert monotonicity(np.array([0.0, 1.0, 1.0]), "increasing")["pass"]
    assert not monotonicity(np.array([0.0, 1.0, 0.5]), "increasing")["pass"]
    with pytest.raises(ValueError):
        metric_record("x", quantity="x", status="insufficient", evidence_level="V1")
    with pytest.raises(ValueError):
        metric_record("x", quantity="x", status="pass", evidence_level="V5")


def test_float32_float64_synthetic_pipeline_is_finite_and_close():
    params = digest_params(build_phase2_params(FILM_KEY, PRINT_KEY))
    image32 = synthetic_image(8, np.float32)
    image64 = image32.astype(np.float64)
    first = np.asarray(SimulationPipeline(params).process(image32))
    second = np.asarray(SimulationPipeline(params).process(image64))
    assert first.dtype == np.float64
    assert second.dtype == np.float64
    assert np.isfinite(first).all() and np.isfinite(second).all()
    assert np.allclose(first, second, rtol=0, atol=2e-7)


def test_branch_topology_and_determinism():
    image = np.full((4, 7, 3), 0.18, dtype=np.float32)
    print_pipe = SimulationPipeline(digest_params(build_phase2_params(FILM_KEY, PRINT_KEY, scan_film=False)))
    negative_pipe = SimulationPipeline(digest_params(build_phase2_params(FILM_KEY, PRINT_KEY, scan_film=True)))
    print_labels = [node.label for node in print_pipe._topology]
    negative_labels = [node.label for node in negative_pipe._topology]
    assert "printing.expose" in print_labels and "printing.develop" in print_labels
    assert "scanning.scan_print" in print_labels
    assert "printing.expose" not in negative_labels and "scanning.scan_film" in negative_labels
    a = np.asarray(print_pipe.process(image))
    b = np.asarray(SimulationPipeline(digest_params(build_phase2_params(FILM_KEY, PRINT_KEY))).process(image))
    assert np.array_equal(a, b)


def test_colorspace_and_effect_controls():
    params = build_phase2_params(FILM_KEY, PRINT_KEY)
    assert params.io.input_color_space == "ACEScg"
    assert params.io.output_color_space == "ACEScg"
    assert params.io.input_cctf_decoding is False
    assert params.io.output_cctf_encoding is False
    assert params.camera.auto_exposure is False
    assert params.film_render.grain.active is False
    assert params.film_render.halation.active is False
    assert params.print_render.glare.active is False


def _reference_payload(independent=True):
    return {
        "schema_version": 1,
        "space": "CIELAB",
        "metadata": {
            "stock": "physical test", "batch": "A", "process": "documented",
            "instrument": "spectrophotometer", "measurement_geometry": "0/45",
            "illuminant": "D50", "observer": "CIE 1931 2 degree", "whitepoint": [0.9642, 1.0, 0.8251],
            "independent_of_profiles": independent,
        },
        "samples": [{"sample_id": "gray", "lab": [50.0, 0.0, 0.0]}],
    }


def test_external_color_schema_and_missing_reference(tmp_path):
    assert evaluate_color_reference(None, None)["status"] == "not_evaluable"
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(_reference_payload()), encoding="utf-8")
    payload = load_color_reference(path)
    result = evaluate_color_reference(payload, {"gray": [50.0, 0.0, 0.0]})
    assert result["status"] == "pass"
    assert result["maximum"] == pytest.approx(0.0)
    invalid = _reference_payload()
    del invalid["metadata"]["instrument"]
    path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(ValueError, match="missing"):
        load_color_reference(path)


def test_pins_and_spectral_nan_audit():
    pins = validate_pins(ROOT, FILM_KEY, PRINT_KEY)
    assert pins["upstream_commit"] == "3bb2c2d2801ff68b92019cf1dbcbb133d60832bc"
    assert pins["profiles"][FILM_KEY]["pinned"]
    audit = profile_spectral_audit(digest_params(build_phase2_params(FILM_KEY, PRINT_KEY)))
    assert audit["film"]["arrays"]["channel_density"]["nan_count"] > 0
    assert "zero" in audit["film"]["nan_runtime_semantics"]
