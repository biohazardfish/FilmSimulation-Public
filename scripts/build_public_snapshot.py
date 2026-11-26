#!/usr/bin/env python3
"""Build a deterministic, history-free, privacy-curated public snapshot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_EXACT = {
    "AGENTS.md",
    "PUBLIC_SNAPSHOT_MANIFEST.json",
    "docs/PUBLIC_RELEASE.md",
    "docs/round1_baseline.json",
    "intermediate/environment.json",
    "intermediate/raw_metadata.json",
    "output/display_clipping_map.png",
    "output/manifest.json",
    "output/phase2/phase1_integrity_before_after.json",
    "output/round2_comparison.png",
    "output/round2_manifest.json",
    "output/round2_uncertainty.png",
    "roadmap/filmsimulation_roadmap.png",
    "roadmap/filmsimulation_roadmap.svg",
    "validation/display_diagnostics.json",
}
EXCLUDED_PREFIXES = ("intermediate/diagnostics/",)
TEXT_SUFFIXES = {
    "", ".csv", ".gitignore", ".json", ".md", ".py", ".sh", ".svg", ".txt", ".yml", ".yaml",
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return sorted(item.decode("utf-8") for item in result.stdout.split(b"\0") if item)


def source_commit(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def source_dirty(root: Path) -> bool:
    return bool(
        subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )


def excluded(relative: str) -> bool:
    return relative in EXCLUDED_EXACT or relative.startswith(EXCLUDED_PREFIXES)


def sanitize_text(relative: str, text: str) -> tuple[str, list[str]]:
    changes: list[str] = []

    def replace(pattern: str, replacement: str, label: str, *, flags: int = 0) -> None:
        nonlocal text
        updated, count = re.subn(pattern, replacement, text, flags=flags)
        if count:
            changes.append(label)
            text = updated

    replace(
        r"https://github\.com/non-public governance archive(?:/pull/10)?",
        "../PUBLIC_GOVERNANCE_SUMMARY.md" if relative.startswith("docs/") else "docs/PUBLIC_GOVERNANCE_SUMMARY.md",
        "private-governance-url",
    )
    replace(r"non-public governance archive", "non-public governance archive", "private-governance-name")
    replace(r"Decision 0004 public summary", "Decision 0004 public summary", "private-governance-pr")
    replace(r"non-public governance archive", "non-public governance archive", "private-governance-name")
    replace(
        r"https://github\.com/REDACTED/FilmSimulation(?:/pull/\d+)?",
        "private source record",
        "private-source-url",
    )
    replace(
        r"\[([^\]]+)\]\(private source record(?:/[^)]*)?\)",
        r"\1 (private source record)",
        "private-source-link",
    )
    replace(
        r"/(?:Users|home)/[^/\s]+/Projects/FilmSimulation",
        "<repo-root>",
        "absolute-user-path",
    )
    replace(
        r"(?:REDACTED|REDACTED)",
        "REDACTED",
        "historical-username",
        flags=re.IGNORECASE,
    )
    if relative == "README.md":
        replace(
            r", and \[publication checklist\]\(docs/PUBLIC_RELEASE\.md\)",
            "",
            "private-release-checklist-link",
        )
    return text, sorted(set(changes))


def roadmap_statuses(root: Path) -> dict[str, str]:
    with (root / "roadmap" / "filmsimulation_roadmap.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    wanted = {"FS-P5-02", "FS-P5-03", "FS-P6-01", "FS-P6-02"}
    return {row["id"]: row["status"] for row in rows if row["id"] in wanted}


def build_snapshot(root: Path, destination: Path) -> dict:
    root = root.resolve()
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError(f"Snapshot destination must be absent or empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    if (destination / ".git").exists():
        raise RuntimeError("Snapshot destination unexpectedly contains .git")

    included: list[dict] = []
    excluded_paths: list[str] = []
    for relative in tracked_files(root):
        source = root / relative
        if excluded(relative):
            excluded_paths.append(relative)
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        source_bytes = source.read_bytes()
        transformations: list[str] = []
        output_bytes = source_bytes
        if source.suffix.lower() in TEXT_SUFFIXES or source.name in {"LICENSE", ".gitignore"}:
            try:
                text = source_bytes.decode("utf-8")
            except UnicodeDecodeError:
                pass
            else:
                sanitized, transformations = sanitize_text(relative, text)
                output_bytes = sanitized.encode("utf-8")
        target.write_bytes(output_bytes)
        os.chmod(target, source.stat().st_mode & 0o777)
        included.append({
            "path": relative,
            "bytes": len(output_bytes),
            "sha256": sha256_bytes(output_bytes),
            "source_sha256": sha256_bytes(source_bytes),
            "transformations": transformations,
        })

    statuses = roadmap_statuses(root)
    if statuses != {
        "FS-P5-02": "blocked",
        "FS-P5-03": "completed",
        "FS-P6-01": "completed",
        "FS-P6-02": "completed",
    }:
        raise RuntimeError(f"Decision 0006 status drift: {statuses}")
    manifest = {
        "schema_version": 1,
        "snapshot_type": "history-free curated public research snapshot",
        "source_commit": source_commit(root),
        "source_tree_dirty": source_dirty(root),
        "git_history_included": False,
        "raw_input_included": False,
        "kodak_pdfs_included": False,
        "private_governance_included": False,
        "identifiable_scene_assets_included": False,
        "stale_rendered_roadmap_included": False,
        "license_scope": {
            "original_software": "GPL-3.0-or-later",
            "third_party_materials": "retain separately identified licenses",
        },
        "decision_0006_statuses": statuses,
        "excluded_paths": sorted(excluded_paths),
        "included_files": sorted(included, key=lambda row: row["path"]),
    }
    (destination / "PUBLIC_SNAPSHOT_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    manifest = build_snapshot(args.root, args.destination)
    print(args.destination.resolve())
    print(f"source_commit={manifest['source_commit']}")
    print(f"files={len(manifest['included_files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
