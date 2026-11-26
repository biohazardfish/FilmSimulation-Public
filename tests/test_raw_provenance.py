from __future__ import annotations

import json
from pathlib import Path

from filmsim_experiment.experiment import INPUT_SHA256, decode_settings
from filmsim_experiment.raw_provenance import (
    collect_raw_input_provenance,
    parse_raw_identify,
)


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "input/_C5A0880.CR3"


def test_raw_identify_parser_extracts_multi_image_provenance() -> None:
    parsed = parse_raw_identify(
        "Number of raw images: 2\nFull size: 7128 x 4732\n"
        "Image size: 6984 x 4660\nOutput size: 6984 x 4660\n"
    )
    assert parsed == {
        "raw_image_count": 2,
        "full_size": [7128, 4732],
        "image_size": [6984, 4660],
        "output_size": [6984, 4660],
    }


def test_committed_dpraw_provenance_matches_input_and_decoder_boundary() -> None:
    payload = json.loads((ROOT / "validation/raw_input_provenance.json").read_text())
    assert payload["input"]["sha256"] == INPUT_SHA256
    assert payload["capture"]["dual_pixel_raw"] is True
    assert payload["container"]["raw_image_count"] == 2
    assert payload["decoder"]["selected_raw_image_index"] == 0
    assert payload["decoder"]["auxiliary_dual_pixel_data_used"] is False
    assert payload["decoder"]["raw_type"] == "RawType.Flat"


def test_missing_raw_identify_is_not_a_decode_blocker() -> None:
    payload = collect_raw_input_provenance(
        RAW,
        display_path="input/_C5A0880.CR3",
        raw_identify_executable="filmsimulation-command-that-does-not-exist",
    )
    assert payload["capture"]["dual_pixel_raw"] is True
    assert payload["container"]["status"] == "not_evaluable"
    assert payload["container"]["raw_image_count"] is None
    assert payload["decoder"]["auxiliary_dual_pixel_data_used"] is False


def test_future_decode_settings_make_dpraw_selection_explicit() -> None:
    settings = decode_settings()
    assert settings["raw_image_selection"].endswith("shot_select=0)")
    assert settings["dual_pixel_auxiliary_processing"] is False
