from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import OpenImageIO as oiio

from filmsim_experiment.experiment import (
    DETERMINISTIC_CONTAINER_DATETIME,
    FILM_KEY,
    PRINT_KEY,
    PROFILE_SHA256,
    build_params,
    display_transform,
    inspect_upstream,
    serialize_params,
    write_exr,
    write_display_tiff,
)


ROOT = Path(__file__).resolve().parents[1]


def test_required_profiles_and_hashes_are_exact():
    info = inspect_upstream(ROOT)
    assert info["commit"] == "3bb2c2d2801ff68b92019cf1dbcbb133d60832bc"
    assert info["profiles"][FILM_KEY]["sha256"] == PROFILE_SHA256[FILM_KEY]
    assert info["profiles"][PRINT_KEY]["sha256"] == PROFILE_SHA256[PRINT_KEY]
    assert info["profiles"][FILM_KEY]["info"]["name"] == "Kodak Vision3 500T"
    assert info["profiles"][PRINT_KEY]["info"]["name"] == "Kodak Vision 2383"


def test_fixed_params_keep_core_linear_and_disable_spatial_random_effects():
    params = build_params()
    assert params.film.info.stock == FILM_KEY
    assert params.print.info.stock == PRINT_KEY
    assert params.io.input_color_space == "ACEScg"
    assert params.io.output_color_space == "ACEScg"
    assert params.io.input_cctf_decoding is False
    assert params.io.output_cctf_encoding is False
    assert params.io.output_gamut_compress.algorithm == "off"
    assert params.io.output_gamut_compress.lightness_compression is None
    assert params.camera.auto_exposure is False
    assert params.enlarger.print_exposure_compensation is False
    assert params.film_render.grain.active is False
    assert params.film_render.halation.active is False
    assert params.print_render.glare.active is False
    assert params.film_render.dir_couplers.active is True
    assert params.film_render.dir_couplers.diffusion_size_um == 0.0
    assert params.debug.deactivate_spatial_effects is True
    assert params.debug.deactivate_stochastic_effects is True


def test_parameter_serialization_excludes_profile_arrays():
    payload = serialize_params(build_params(), PROFILE_SHA256)
    assert payload["film"]["profile_key"] == FILM_KEY
    assert payload["film"]["data"].startswith("excluded")
    assert payload["print"]["profile_key"] == PRINT_KEY
    assert "density_curves" not in str(payload["film"]["data"])
    assert len(str(payload)) < 30000


def test_display_transform_is_separate_deterministic_and_bounded():
    sample = np.array([[[-0.2, 0.18, 2.0], [0.5, 0.5, 0.5]]], dtype=np.float32)
    first, first_info = display_transform(sample)
    second, second_info = display_transform(copy.deepcopy(sample))
    assert np.array_equal(first, second)
    assert first_info == second_info
    assert np.isfinite(first).all()
    assert float(first.min()) >= 0.0
    assert float(first.max()) <= 1.0
    assert first_info["tone_mapper"] is None
    assert first_info["clipped_component_count_below_zero"] > 0
    assert first_info["clipped_component_count_above_one"] > 0


def test_exr_writer_accepts_noncontiguous_channel_views(tmp_path):
    source = np.arange(4 * 5 * 3, dtype=np.float32).reshape(4, 5, 3)
    noncontiguous = source[:, :, ::-1]
    assert noncontiguous.flags.c_contiguous is False
    destination = tmp_path / "tap.exr"
    write_exr(destination, noncontiguous, {"domain": "test", "color_space": "ACEScg"})
    assert destination.is_file()
    assert destination.stat().st_size > 0


def test_exr_and_tiff_container_hashes_are_deterministic(tmp_path):
    source = np.arange(4 * 5 * 3, dtype=np.float32).reshape(4, 5, 3) / 60.0
    exr_a = tmp_path / "a.exr"
    exr_b = tmp_path / "b.exr"
    tif_a = tmp_path / "a.tif"
    tif_b = tmp_path / "b.tif"
    attributes = {"domain": "test", "color_space": "ACEScg"}
    write_exr(exr_a, source, attributes)
    write_exr(exr_b, source.copy(), attributes)
    write_display_tiff(tif_a, source)
    write_display_tiff(tif_b, source.copy())
    assert exr_a.read_bytes() == exr_b.read_bytes()
    assert tif_a.read_bytes() == tif_b.read_bytes()
    for path in (exr_a, tif_a):
        image_input = oiio.ImageInput.open(str(path))
        assert image_input is not None
        try:
            assert image_input.spec().getattribute("DateTime") == DETERMINISTIC_CONTAINER_DATETIME
        finally:
            image_input.close()
