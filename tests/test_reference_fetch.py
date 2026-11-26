from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

from filmsim_experiment.phase2.analysis import OFFICIAL_PDFS


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fetch_kodak_references", ROOT / "scripts" / "fetch_kodak_references.py"
)
assert SPEC and SPEC.loader
fetch_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch_module)


def test_fetch_manifest_matches_phase2_pins():
    assert fetch_module.REFERENCES == OFFICIAL_PDFS


def test_fetch_is_hash_pinned_atomic_and_non_destructive(tmp_path):
    payload = b"official-reference-fixture"
    source = tmp_path / "source.pdf"
    source.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()
    destination = tmp_path / "cache" / "reference.pdf"
    assert fetch_module.fetch_reference(destination, source.as_uri(), expected) == "downloaded-and-verified"
    assert destination.read_bytes() == payload
    assert fetch_module.fetch_reference(destination, source.as_uri(), expected) == "verified-existing"
    destination.write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="Existing reference hash mismatch"):
        fetch_module.fetch_reference(destination, source.as_uri(), expected)
    assert destination.read_bytes() == b"tampered"


def test_fetch_rejects_download_hash_mismatch_without_leaving_file(tmp_path):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"unexpected")
    destination = tmp_path / "cache" / "reference.pdf"
    with pytest.raises(RuntimeError, match="Downloaded reference hash mismatch"):
        fetch_module.fetch_reference(destination, source.as_uri(), "0" * 64)
    assert not destination.exists()
    assert not destination.with_name(f".{destination.name}.download").exists()
