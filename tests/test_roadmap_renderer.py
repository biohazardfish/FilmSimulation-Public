from __future__ import annotations

import csv
from pathlib import Path

import pytest

from render_roadmap import (
    RoadmapError,
    file_sha256,
    group_phases,
    load_roadmap,
    next_task_for_phase,
    render_roadmap,
    summarize,
)


ROOT = Path(__file__).resolve().parents[1]
FILM_CSV = ROOT / "roadmap" / "filmsimulation_roadmap.csv"


LEGACY_FIELDS = [
    "id",
    "phase",
    "phase_name",
    "task",
    "start",
    "end",
    "hours_budget",
    "depends_on",
    "deliverable",
    "acceptance",
    "gate",
    "status",
    "source_url",
    "progress_note",
    "next_action",
    "evidence_url",
    "audited_on",
]


def _write_legacy(path: Path, statuses=("completed", "in_progress", "planned")) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEGACY_FIELDS)
        writer.writeheader()
        for index, status in enumerate(statuses):
            writer.writerow(
                {
                    "id": f"T{index + 1}",
                    "phase": f"P{index}",
                    "phase_name": f"Legacy phase {index}",
                    "task": f"Legacy task {index}",
                    "start": f"2026-11-{19 + index:02d}",
                    "end": f"2026-11-{19 + index:02d}",
                    "depends_on": "" if index == 0 else f"T{index}",
                    "deliverable": f"Artifact {index}",
                    "acceptance": f"Check {index}",
                    "gate": f"G{index}",
                    "status": status,
                    "progress_note": "Legacy-compatible note",
                    "next_action": "Continue" if status != "completed" else "Preserve",
                    "evidence_url": f"evidence/{index}.md",
                }
            )


def test_filmsimulation_csv_rows_match_header_width() -> None:
    with FILM_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        header, *rows = list(csv.reader(handle))
    assert rows
    for line, row in enumerate(rows, start=2):
        assert len(row) == len(header), (line, row[0], len(row), len(header))


def test_filmsimulation_schema_and_evidence_paths() -> None:
    roadmap = load_roadmap(FILM_CSV)
    phases = group_phases(roadmap)
    result = summarize(roadmap)

    assert roadmap.project_name == "FilmSimulation"
    assert [phase.phase_id for phase in phases] == ["P1", "P2", "P3", "P4", "P5", "P6"]
    # Counts after Decision 0006 (Film main 04ff02d): FS-P5-03/P6-01/P6-02 completed;
    # FS-P5-02 remains blocked.
    assert result["counts"] == {
        "planned": 0,
        "in_progress": 0,
        "completed": 14,
        "blocked": 1,
    }
    assert result["current_phase"] == "P5"
    assert result["next_gate_phase"] == "P5"
    p4 = phases[3]
    assert p4.name == "Published-Reference Numerical Validation"
    g4 = next(task for task in p4.tasks if task.gate.startswith("G4"))
    assert "published-reference numerical validation" in g4.gate.casefold()
    assert g4.status == "completed"
    assert "限制" in g4.acceptance
    assert "未通過" in g4.acceptance
    p5 = phases[4]
    next_task = next_task_for_phase(p5)
    assert next_task is not None and next_task.task_id == "FS-P5-02"
    assert next_task.status == "blocked"
    assert next_task.evidence_url == "output/ROUND2_REPORT.md"
    action = next_task.next_action
    # Retained evidence paths used by completed P5/P4 closure remain present.
    for relative in (
        "docs/phase4/G4_PUBLISHED_REFERENCE_VALIDATION.md",
        "validation/uncertainty_metrics.json",
        "output/ROUND2_REPORT.md",
    ):
        assert (ROOT / relative).is_file()
    for marker in (
        "實驗室",
        "報價",
        "採購",
        "送片",
        "outreach",
        "quotation",
        "purchase",
        "shipment",
        "樣片",
    ):
        assert marker.casefold() not in action.casefold()
        assert all(marker.casefold() not in task.next_action.casefold() for task in roadmap.tasks)
    p4_curve_audit = next(task for task in roadmap.tasks if task.task_id == "FS-P4-02")
    assert p4_curve_audit.status == "completed"
    assert "not_evaluable" in p4_curve_audit.acceptance
    blocked = [task.task_id for task in roadmap.tasks if task.status == "blocked"]
    assert blocked == ["FS-P5-02"]
    closure = next(task for task in roadmap.tasks if task.task_id == "FS-P5-03")
    assert closure.depends_on == ("FS-P4-03",)
    assert "限制" in closure.acceptance
    assert closure.status == "completed"
    p6 = phases[5]
    assert p6.name == "Public-Data External Comparison"
    assert [task.task_id for task in p6.tasks] == ["FS-P6-01", "FS-P6-02"]
    assert all(task.status == "completed" for task in p6.tasks)
    search, comparison = p6.tasks
    assert search.depends_on == ()
    assert comparison.depends_on == ("FS-P6-01",)
    assert comparison.gate.startswith("G6")
    for task in p6.tasks:
        assert "not_evaluable" in task.acceptance
        assert "unavailable" in task.acceptance
        assert "independent QC" in task.acceptance
    p6_ids = {task.task_id for task in p6.tasks}
    assert all(
        not (set(task.depends_on) & p6_ids)
        for task in roadmap.tasks
        if task.phase != "P6"
    )
    for task in roadmap.tasks:
        assert task.next_action
        assert task.evidence_url
        assert (ROOT / task.evidence_url).exists(), task.evidence_url


def test_legacy_spatial_schema_and_arbitrary_phase_count(tmp_path: Path) -> None:
    csv_path = tmp_path / "spatial_roadmap.csv"
    _write_legacy(csv_path)

    roadmap = load_roadmap(csv_path, project_name="Spatial Photo test dataset")

    assert len(group_phases(roadmap)) == 3
    assert [task.goal for task in roadmap.tasks] == [
        "Legacy task 0",
        "Legacy task 1",
        "Legacy task 2",
    ]
    svg, png = render_roadmap(roadmap, tmp_path / "legacy")
    assert svg.stat().st_size > 10_000
    assert png.stat().st_size > 10_000


def test_invalid_status_and_missing_schema_are_rejected(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.csv"
    invalid.write_text(
        "id,phase,phase_name,goal,deliverable,acceptance,status\n"
        "T1,P1,One,Do it,Thing,Check,done\n",
        encoding="utf-8",
    )
    with pytest.raises(RoadmapError, match="invalid status"):
        load_roadmap(invalid)

    missing = tmp_path / "missing.csv"
    missing.write_text("id,phase,status\nT1,P1,planned\n", encoding="utf-8")
    with pytest.raises(RoadmapError, match="missing required columns"):
        load_roadmap(missing)


def test_status_change_changes_summary_and_rendered_svg(tmp_path: Path) -> None:
    csv_path = tmp_path / "status.csv"
    _write_legacy(csv_path, statuses=("planned",))
    before = load_roadmap(csv_path, project_name="Status mutation")
    before_svg, _ = render_roadmap(before, tmp_path / "before")
    before_hash = file_sha256(before_svg)
    assert summarize(before)["completed"] == 0

    _write_legacy(csv_path, statuses=("completed",))
    after = load_roadmap(csv_path, project_name="Status mutation")
    after_svg, _ = render_roadmap(after, tmp_path / "after")

    assert summarize(after)["completed"] == 1
    assert file_sha256(after_svg) != before_hash


def test_same_input_produces_deterministic_svg(tmp_path: Path) -> None:
    csv_path = tmp_path / "deterministic.csv"
    _write_legacy(csv_path, statuses=("in_progress", "planned"))
    roadmap = load_roadmap(csv_path, project_name="Deterministic render")

    first_svg, _ = render_roadmap(roadmap, tmp_path / "first")
    second_svg, _ = render_roadmap(roadmap, tmp_path / "second")

    assert file_sha256(first_svg) == file_sha256(second_svg)
    assert all(line == line.rstrip() for line in first_svg.read_text().splitlines())


def test_awaiting_review_has_separate_status_and_is_not_complete(tmp_path: Path) -> None:
    csv_path = tmp_path / "review.csv"
    _write_legacy(csv_path, statuses=("planned", "ready_for_review", "completed"))
    roadmap = load_roadmap(csv_path)
    summary = summarize(roadmap)
    assert summary["counts"]["ready_for_review"] == 1
    assert summary["completed"] == 1
    assert summary["current_phase"] == "P1"
    svg, _ = render_roadmap(roadmap, tmp_path / "review")
    assert "AWAITING QC" in svg.read_text()
