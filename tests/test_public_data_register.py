from __future__ import annotations

import csv
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validate_public_data_register import (
    DEFAULT_REGISTER,
    DEFAULT_SCHEMA,
    DEFAULT_SEARCH_LOG,
    validate,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_public_data_register.py"


def _copy(tmp_path: Path) -> tuple[Path, Path]:
    register = tmp_path / "evidence_register.csv"
    log = tmp_path / "search_log.csv"
    shutil.copy(DEFAULT_REGISTER, register)
    shutil.copy(DEFAULT_SEARCH_LOG, log)
    return register, log


def _rewrite(path: Path, change) -> None:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = list(reader)
    change(rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _row(rows, entry_id):
    return next(r for r in rows if r["entry_id"] == entry_id)


def test_committed_register_is_valid() -> None:
    errors, summary = validate(DEFAULT_REGISTER, DEFAULT_SCHEMA, DEFAULT_SEARCH_LOG)
    assert errors == []
    assert summary["entries"] <= 60
    assert summary["search_log"]["queries"] <= 50
    assert summary["independent_validation_rows"] == 0


def test_cli_reports_valid() -> None:
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stdout
    assert '"valid": true' in result.stdout


@pytest.mark.parametrize("lineage", ["same_primary_source", "derived_from_spektrafilm", "unknown"])
def test_shared_lineage_cannot_be_independent_validation(tmp_path: Path, lineage: str) -> None:
    register, log = _copy(tmp_path)

    def change(rows):
        row = _row(rows, "PD-042")
        row["evidence_class"] = "INDEPENDENT_PHYSICAL_MEASUREMENT"
        row["values_via"] = "native_numeric"
        row["lineage"] = lineage
        row["permitted_use"] = "independent_validation"

    _rewrite(register, change)
    errors, _ = validate(register, DEFAULT_SCHEMA, log)
    assert any("may not have permitted_use=independent_validation" in e for e in errors)


def test_lineage_steps_required_outside_not_comparable(tmp_path: Path) -> None:
    register, log = _copy(tmp_path)
    _rewrite(register, lambda rows: _row(rows, "PD-040").update(lineage_evidence="looks independent"))
    errors, _ = validate(register, DEFAULT_SCHEMA, log)
    assert any("PD-040" in e and "lacks check a" in e for e in errors)


def test_digitization_without_record_must_be_low(tmp_path: Path) -> None:
    register, log = _copy(tmp_path)
    _rewrite(register, lambda rows: _row(rows, "PD-040").update(credibility="high"))
    errors, _ = validate(register, DEFAULT_SCHEMA, log)
    assert any("PD-040" in e and "§4.1 rule 5" in e for e in errors)


def test_not_evaluable_requires_reason(tmp_path: Path) -> None:
    register, log = _copy(tmp_path)
    _rewrite(register, lambda rows: _row(rows, "PD-024").update(reason=""))
    errors, _ = validate(register, DEFAULT_SCHEMA, log)
    assert any("PD-024" in e and "requires a reason" in e for e in errors)


def test_paywalled_row_has_no_hash(tmp_path: Path) -> None:
    register, log = _copy(tmp_path)
    _rewrite(register, lambda rows: _row(rows, "PD-004").update(sha256="0" * 64))
    errors, _ = validate(register, DEFAULT_SCHEMA, log)
    assert any("PD-004" in e and "must not carry a file hash" in e for e in errors)


def test_found_by_must_reference_logged_query(tmp_path: Path) -> None:
    register, log = _copy(tmp_path)
    _rewrite(register, lambda rows: _row(rows, "PD-001").update(found_by="Q99"))
    errors, _ = validate(register, DEFAULT_SCHEMA, log)
    assert any("Q99" in e for e in errors)


def test_family_query_cap(tmp_path: Path) -> None:
    register, log = _copy(tmp_path)

    def change(rows):
        template = dict(rows[0])
        for i in range(3):
            extra = dict(template, query_id=f"X{i}", family="3_academic_databases", kind="query")
            rows.append(extra)

    _rewrite(log, change)
    errors, _ = validate(register, DEFAULT_SCHEMA, log)
    assert any("3_academic_databases has 13 queries" in e for e in errors)


def test_field_count_mismatch_is_rejected(tmp_path: Path) -> None:
    register, log = _copy(tmp_path)
    with register.open("a", encoding="utf-8", newline="") as handle:
        handle.write("PD-999,5219\n")
    with pytest.raises(ValueError, match="fields, header has"):
        validate(register, DEFAULT_SCHEMA, log)
