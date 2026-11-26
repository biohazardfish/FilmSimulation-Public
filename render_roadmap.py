#!/usr/bin/env python3
"""Render a status-driven project roadmap from CSV as SVG and PNG.

The renderer intentionally treats explicit task status as the sole source of
progress. Dates are displayed as planning context only; Git history is not
used. Both the legacy Spatial Photo ``task`` column and the generic ``goal``
column are accepted.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import textwrap
from collections import Counter, OrderedDict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch


VALID_STATUSES = ("planned", "in_progress", "ready_for_review", "completed", "blocked")
STATUS_LABELS = {
    "planned": "PLANNED / 計劃中",
    "in_progress": "IN PROGRESS / 進行中",
    "ready_for_review": "AWAITING QC / 待審查",
    "completed": "COMPLETED / 已完成",
    "blocked": "BLOCKED / 受阻",
}
STATUS_COLORS = {
    "planned": "#778397",
    "in_progress": "#147D74",
    "ready_for_review": "#6C5796",
    "completed": "#2563A8",
    "blocked": "#B4513C",
}
NAVY = "#10203B"
TEXT = "#26364C"
SUB = "#667489"
LINE = "#DCE4EC"
BG = "#F5F8FB"


class RoadmapError(ValueError):
    """Raised when roadmap input is structurally invalid."""


@dataclass(frozen=True)
class Task:
    task_id: str
    phase: str
    phase_name: str
    goal: str
    start: date | None
    end: date | None
    deliverable: str
    acceptance: str
    status: str
    evidence_url: str
    next_action: str
    depends_on: tuple[str, ...]
    gate: str
    progress_note: str
    source_url: str


@dataclass(frozen=True)
class Roadmap:
    project_name: str
    project_summary: str
    tasks: tuple[Task, ...]


@dataclass(frozen=True)
class Phase:
    phase_id: str
    name: str
    tasks: tuple[Task, ...]

    @property
    def completed_count(self) -> int:
        return sum(task.status == "completed" for task in self.tasks)

    @property
    def status(self) -> str:
        statuses = {task.status for task in self.tasks}
        if statuses == {"completed"}:
            return "completed"
        if "in_progress" in statuses:
            return "in_progress"
        if "ready_for_review" in statuses:
            return "ready_for_review"
        if "blocked" in statuses:
            return "blocked"
        return "planned"

    @property
    def gates(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(task.gate for task in self.tasks if task.gate))


def _parse_date(value: str, field: str, row_number: int) -> date | None:
    value = value.strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RoadmapError(
            f"row {row_number}: {field} must be ISO YYYY-MM-DD, got {value!r}"
        ) from exc


def _split_dependencies(value: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in value.replace(";", ",").split(",")
        if item.strip()
    )


def load_roadmap(
    csv_path: Path | str,
    *,
    project_name: str | None = None,
    project_summary: str | None = None,
) -> Roadmap:
    """Load and validate a generic or legacy roadmap CSV."""

    path = Path(csv_path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or ())
        required = {"id", "phase", "phase_name", "deliverable", "acceptance", "status"}
        missing = sorted(required - headers)
        if missing:
            raise RoadmapError(f"missing required columns: {', '.join(missing)}")
        if not ({"goal", "task"} & headers):
            raise RoadmapError("missing required goal column: provide 'goal' or legacy 'task'")
        rows = list(reader)

    if not rows:
        raise RoadmapError("roadmap CSV contains no tasks")

    tasks: list[Task] = []
    ids: set[str] = set()
    phase_names: dict[str, str] = {}
    for row_number, row in enumerate(rows, start=2):
        task_id = (row.get("id") or "").strip()
        phase = (row.get("phase") or "").strip()
        phase_name = (row.get("phase_name") or "").strip()
        goal = (row.get("goal") or row.get("task") or "").strip()
        deliverable = (row.get("deliverable") or "").strip()
        acceptance = (row.get("acceptance") or "").strip()
        status = (row.get("status") or "").strip()
        missing_values = [
            name
            for name, value in (
                ("id", task_id),
                ("phase", phase),
                ("phase_name", phase_name),
                ("goal/task", goal),
                ("deliverable", deliverable),
                ("acceptance", acceptance),
                ("status", status),
            )
            if not value
        ]
        if missing_values:
            raise RoadmapError(
                f"row {row_number}: empty required values: {', '.join(missing_values)}"
            )
        if task_id in ids:
            raise RoadmapError(f"row {row_number}: duplicate task id {task_id!r}")
        if status not in VALID_STATUSES:
            raise RoadmapError(
                f"row {row_number}: invalid status {status!r}; "
                f"expected one of {', '.join(VALID_STATUSES)}"
            )
        previous_name = phase_names.setdefault(phase, phase_name)
        if previous_name != phase_name:
            raise RoadmapError(
                f"row {row_number}: phase {phase!r} has conflicting names"
            )
        start = _parse_date(row.get("start") or "", "start", row_number)
        end = _parse_date(row.get("end") or "", "end", row_number)
        if (start is None) != (end is None):
            raise RoadmapError(
                f"row {row_number}: start and end must both be set or both be blank"
            )
        if start and end and end < start:
            raise RoadmapError(f"row {row_number}: end date precedes start date")
        ids.add(task_id)
        tasks.append(
            Task(
                task_id=task_id,
                phase=phase,
                phase_name=phase_name,
                goal=goal,
                start=start,
                end=end,
                deliverable=deliverable,
                acceptance=acceptance,
                status=status,
                evidence_url=(row.get("evidence_url") or "").strip(),
                next_action=(row.get("next_action") or "").strip(),
                depends_on=_split_dependencies(row.get("depends_on") or ""),
                gate=(row.get("gate") or "").strip(),
                progress_note=(row.get("progress_note") or "").strip(),
                source_url=(row.get("source_url") or "").strip(),
            )
        )

    for task in tasks:
        unknown = sorted(set(task.depends_on) - ids)
        if unknown:
            raise RoadmapError(
                f"task {task.task_id}: unknown dependencies: {', '.join(unknown)}"
            )

    first = rows[0]
    resolved_name = (
        project_name
        or (first.get("project_name") or "").strip()
        or path.stem.replace("_", " ").title()
    )
    resolved_summary = (
        project_summary
        if project_summary is not None
        else (first.get("project_summary") or "").strip()
    )
    return Roadmap(resolved_name, resolved_summary, tuple(tasks))


def group_phases(roadmap: Roadmap) -> tuple[Phase, ...]:
    grouped: OrderedDict[str, list[Task]] = OrderedDict()
    for task in roadmap.tasks:
        grouped.setdefault(task.phase, []).append(task)
    return tuple(
        Phase(phase_id, tasks[0].phase_name, tuple(tasks))
        for phase_id, tasks in grouped.items()
    )


def summarize(roadmap: Roadmap) -> dict[str, object]:
    phases = group_phases(roadmap)
    counts = Counter(task.status for task in roadmap.tasks)
    current = next((phase for phase in phases if phase.status == "in_progress"), None)
    if current is None:
        current = next((phase for phase in phases if phase.status == "ready_for_review"), None)
    if current is None:
        current = next((phase for phase in phases if phase.status != "completed"), phases[-1])
    next_gate_phase = next(
        (phase for phase in phases if phase.status != "completed" and phase.gates), None
    )
    return {
        "counts": {
            status: counts.get(status, 0)
            for status in VALID_STATUSES
            if status != "ready_for_review" or counts[status]
        },
        "completed": counts.get("completed", 0),
        "total": len(roadmap.tasks),
        "current_phase": current.phase_id,
        "current_phase_name": current.name,
        "next_gate_phase": next_gate_phase.phase_id if next_gate_phase else "",
        "next_gate": " / ".join(next_gate_phase.gates) if next_gate_phase else "",
    }


def next_task_for_phase(phase: Phase) -> Task | None:
    """Prefer active work over an earlier blocked or merely planned task."""

    return next(
        (task for task in phase.tasks if task.status == "in_progress"),
        None,
    ) or next((task for task in phase.tasks if task.status != "completed"), None)


def _font_family() -> str:
    candidates = (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    )
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            font_manager.fontManager.addfont(str(path))
            return font_manager.FontProperties(fname=str(path)).get_name()
    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in ("Noto Sans CJK TC", "Noto Sans CJK SC", "Arial Unicode MS"):
        if name in available:
            return name
    return "DejaVu Sans"


def _wrap(value: str, width: int) -> list[str]:
    if not value:
        return ["—"]
    lines: list[str] = []
    for paragraph in value.splitlines() or [value]:
        lines.extend(
            textwrap.wrap(
                paragraph,
                width=width,
                break_long_words=False,
                break_on_hyphens=False,
            )
            or [""]
        )
    return lines


def _compact_items(items: Iterable[str], *, limit: int = 6) -> str:
    values = [item for item in items if item]
    shown = values[:limit]
    result = " • ".join(shown)
    if len(values) > limit:
        result += f" • +{len(values) - limit} more"
    return result or "—"


def _schedule_label(tasks: Sequence[Task]) -> str:
    dated = [task for task in tasks if task.start and task.end]
    unscheduled = len(tasks) - len(dated)
    if not dated:
        return f"No fixed dates · {unscheduled} unscheduled"
    start = min(task.start for task in dated if task.start)
    end = max(task.end for task in dated if task.end)
    suffix = f" · {unscheduled} unscheduled" if unscheduled else ""
    return f"{start.isoformat()} → {end.isoformat()}{suffix}"


def _rounded(ax, x: float, y: float, width: float, height: float, color: str, *,
             edge: str | None = None, radius: float = 0.8, linewidth: float = 0.8):
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        facecolor=color,
        edgecolor=edge or color,
        linewidth=linewidth,
    )
    ax.add_patch(patch)
    return patch


def _draw_lines(ax, x: float, y: float, lines: Sequence[str], *, size: float = 9,
                color: str = TEXT, weight: str = "normal", line_height: float = 1.35,
                ha: str = "left") -> float:
    for index, line in enumerate(lines):
        ax.text(
            x,
            y - index * line_height,
            line,
            fontsize=size,
            color=color,
            fontweight=weight,
            ha=ha,
            va="top",
        )
    return y - len(lines) * line_height


def render_roadmap(
    roadmap: Roadmap,
    output_base: Path | str,
    *,
    dpi: int = 170,
) -> tuple[Path, Path]:
    """Render one roadmap to ``output_base.svg`` and ``output_base.png``."""

    family = _font_family()
    plt.rcParams.update(
        {
            "font.family": family,
            "axes.unicode_minus": False,
            # Portable paths preserve CJK glyphs when the viewer lacks the font.
            "svg.fonttype": "path",
            # Stable element IDs prevent no-op workflow_dispatch commits.
            "svg.hashsalt": "generic-roadmap-renderer-v1",
        }
    )
    phases = group_phases(roadmap)
    summary = summarize(roadmap)

    achievements = _compact_items(
        task.deliverable for task in roadmap.tasks if task.status == "completed"
    )
    outstanding = _compact_items(
        task.goal for task in roadmap.tasks if task.status != "completed"
    )
    achievement_lines = _wrap(achievements, 72)
    current_text = f"{summary['current_phase']} · {summary['current_phase_name']}"
    next_gate = summary["next_gate"] or "No outstanding gate defined"
    right_lines = _wrap(
        f"Current: {current_text}\nNext: {next_gate}\nOpen: {outstanding}", 72
    )
    summary_lines = max(len(achievement_lines), len(right_lines), 2)
    summary_height = 5.0 + summary_lines * 1.25

    phase_layout: list[tuple[Phase, list[str], list[str], list[str], list[str], float]] = []
    for phase in phases:
        completed_lines = _wrap(
            _compact_items(
                (task.goal for task in phase.tasks if task.status == "completed"),
                limit=99,
            ),
            82,
        )
        open_lines = _wrap(
            _compact_items(
                (task.goal for task in phase.tasks if task.status != "completed"),
                limit=99,
            ),
            82,
        )
        gate_lines = _wrap(" / ".join(phase.gates) or "Gate not defined", 56)
        next_task = next_task_for_phase(phase)
        next_lines = _wrap(next_task.next_action if next_task else "Acceptance gate achieved", 56)
        content_lines = max(len(completed_lines) + len(open_lines), len(gate_lines) + len(next_lines))
        row_height = max(10.5, 5.2 + content_lines * 1.25)
        phase_layout.append(
            (phase, completed_lines, open_lines, gate_lines, next_lines, row_height)
        )

    header_height = 10.0
    footer_height = 3.5
    gap = 1.2
    total_height = (
        header_height + summary_height + footer_height + sum(item[-1] + gap for item in phase_layout)
    )
    figure_height = max(10.5, total_height * 0.235)
    fig, ax = plt.subplots(figsize=(17.2, figure_height), dpi=150)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, total_height)
    ax.axis("off")

    cursor = total_height - 2.0
    _rounded(ax, 3, cursor - 7.0, 94, 7.0, NAVY, radius=1.2, linewidth=0)
    ax.text(5, cursor - 2.0, roadmap.project_name, fontsize=23, color="white",
            fontweight="bold", va="top")
    subtitle = roadmap.project_summary or "Human-directed · Machine-rendered roadmap"
    ax.text(5, cursor - 5.1, subtitle, fontsize=9.5, color="#D7E0EC", va="top")
    status_text = "  ·  ".join(
        f"{status}: {count}" for status, count in summary["counts"].items()
    )
    ax.text(95, cursor - 2.0, f"{summary['completed']}/{summary['total']} tasks completed",
            fontsize=11, color="white", fontweight="bold", va="top", ha="right")
    ax.text(95, cursor - 4.6, status_text, fontsize=8.2, color="#D7E0EC", va="top", ha="right")
    cursor -= header_height

    panel_y = cursor - summary_height + 1.0
    panel_h = summary_height - 1.0
    _rounded(ax, 3, panel_y, 46, panel_h, "#E3EEF9", radius=1.0, linewidth=0)
    _rounded(ax, 51, panel_y, 46, panel_h, "#E7F1EE", radius=1.0, linewidth=0)
    ax.text(5, cursor - 1.0, "ACHIEVEMENTS / 已取得成果", fontsize=11, color=NAVY,
            fontweight="bold", va="top")
    _draw_lines(ax, 5, cursor - 3.0, achievement_lines, size=8.6, line_height=1.25)
    ax.text(53, cursor - 1.0, "CURRENT + NEXT GATE / 現階段與下一 Gate", fontsize=11,
            color=NAVY, fontweight="bold", va="top")
    _draw_lines(ax, 53, cursor - 3.0, right_lines, size=8.6, line_height=1.25)
    cursor -= summary_height

    for phase, completed_lines, open_lines, gate_lines, next_lines, row_height in phase_layout:
        y = cursor - row_height
        _rounded(ax, 3, y, 94, row_height, "white", edge=LINE, radius=1.0, linewidth=0.9)
        color = STATUS_COLORS[phase.status]
        _rounded(ax, 4.5, cursor - 4.1, 8.5, 2.8, color, radius=0.65, linewidth=0)
        ax.text(8.75, cursor - 2.7, phase.phase_id, fontsize=11, color="white",
                fontweight="bold", ha="center", va="center")
        ax.text(14.5, cursor - 1.4, phase.name, fontsize=12.2, color=NAVY,
                fontweight="bold", va="top")
        ax.text(
            95,
            cursor - 1.5,
            f"{STATUS_LABELS[phase.status]} · {phase.completed_count}/{len(phase.tasks)} completed",
            fontsize=8.7,
            color=color,
            fontweight="bold",
            va="top",
            ha="right",
        )
        ax.text(14.5, cursor - 3.6, _schedule_label(phase.tasks), fontsize=8.1,
                color=SUB, va="top")

        left_y = cursor - 5.3
        ax.text(5, left_y, "Completed evidence", fontsize=8.3, color="#2563A8",
                fontweight="bold", va="top")
        left_y = _draw_lines(ax, 18.0, left_y, completed_lines, size=8.1, line_height=1.18)
        ax.text(5, left_y - 0.25, "Outstanding", fontsize=8.3, color="#B4513C",
                fontweight="bold", va="top")
        _draw_lines(ax, 18.0, left_y - 0.25, open_lines, size=8.1, line_height=1.18)

        divider_x = 66.0
        ax.plot([divider_x, divider_x], [y + 1.2, cursor - 5.0], color=LINE, lw=0.8)
        right_y = cursor - 5.3
        ax.text(68, right_y, "Acceptance Gate", fontsize=8.3, color=NAVY,
                fontweight="bold", va="top")
        right_y = _draw_lines(ax, 79.0, right_y, gate_lines, size=8.0, line_height=1.18)
        ax.text(68, right_y - 0.25, "Next action", fontsize=8.3, color=NAVY,
                fontweight="bold", va="top")
        _draw_lines(ax, 79.0, right_y - 0.25, next_lines, size=8.0, line_height=1.18)
        cursor = y - gap

    ax.text(
        3,
        1.3,
        "Progress is derived only from explicit CSV task status. Dates are context; commits are not progress.",
        fontsize=8,
        color=SUB,
        va="bottom",
    )
    ax.text(97, 1.3, "CSV is the human-reviewed source of truth", fontsize=8, color=SUB,
            va="bottom", ha="right")

    base = Path(output_base)
    base.parent.mkdir(parents=True, exist_ok=True)
    svg_path = base.with_suffix(".svg")
    png_path = base.with_suffix(".png")
    metadata = {"Creator": "FilmSimulation generic roadmap renderer", "Date": None}
    fig.savefig(svg_path, format="svg", bbox_inches="tight", facecolor=BG, metadata=metadata)
    svg_text = svg_path.read_text(encoding="utf-8")
    svg_path.write_text(
        "\n".join(line.rstrip() for line in svg_text.splitlines()) + "\n",
        encoding="utf-8",
    )
    fig.savefig(png_path, format="png", dpi=dpi, bbox_inches="tight", facecolor=BG,
                metadata={"Software": "FilmSimulation generic roadmap renderer"})
    plt.close(fig)
    return svg_path, png_path


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv_path",
        nargs="?",
        type=Path,
        default=Path(__file__).with_name("roadmap") / "filmsimulation_roadmap.csv",
    )
    parser.add_argument("--project", help="override project name")
    parser.add_argument("--summary", help="override project summary")
    parser.add_argument("--output-base", type=Path, help="output path without extension")
    parser.add_argument("--dpi", type=int, default=170, help="PNG dots per inch")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    roadmap = load_roadmap(
        args.csv_path,
        project_name=args.project,
        project_summary=args.summary,
    )
    output_base = args.output_base or args.csv_path.with_suffix("")
    svg_path, png_path = render_roadmap(roadmap, output_base, dpi=args.dpi)
    summary = summarize(roadmap)
    print(
        f"rendered {len(roadmap.tasks)} tasks across {len(group_phases(roadmap))} phases; "
        f"completed={summary['completed']}/{summary['total']}"
    )
    print(f"saved {svg_path} ({file_sha256(svg_path)})")
    print(f"saved {png_path} ({file_sha256(png_path)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
