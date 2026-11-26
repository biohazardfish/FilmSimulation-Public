from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "compute_public_data_comparisons.py"
OUTPUT = ROOT / "validation" / "public_data" / "comparisons.json"
REGISTER = ROOT / "validation" / "public_data" / "evidence_register.csv"


@pytest.fixture(scope="module")
def payload() -> dict:
    assert OUTPUT.is_file(), "run scripts/compute_public_data_comparisons.py first or use committed comparisons.json"
    return json.loads(OUTPUT.read_text(encoding="utf-8"))


def test_comparisons_json_matches_register_size(payload: dict) -> None:
    import csv

    with REGISTER.open(encoding="utf-8", newline="") as handle:
        n = sum(1 for _ in csv.DictReader(handle))
    assert payload["summary"]["register_entries"] == n == len(payload["entries"])


def test_four_comparable_entries_only(payload: dict) -> None:
    assert payload["summary"]["compared"] == 4
    assert set(payload["summary"]["comparable_entry_ids"]) == {"PD-001", "PD-018", "PD-042", "PD-048"}
    assert payload["summary"]["independent_validation_comparisons"] == 0


def test_no_independent_validation_rows(payload: dict) -> None:
    compared = [e for e in payload["entries"] if e.get("outcome") == "compared"]
    assert all(e.get("independent_validation") is False for e in compared)
    assert all(e.get("pass_fail") is None for e in compared)


def test_excluded_entries_cite_register_reasons(payload: dict) -> None:
    excluded = [e for e in payload["entries"] if e.get("outcome") in {"not_evaluable", "unavailable"}]
    assert len(excluded) == 54
    for row in excluded:
        assert row["entry_id"].startswith("PD-")
        assert row.get("reason")


def test_script_runs_with_tmp_output(tmp_path: Path) -> None:
    out = tmp_path / "comparisons.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(out), "--cache", str(tmp_path / "cache")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["summary"]["compared"] == 4