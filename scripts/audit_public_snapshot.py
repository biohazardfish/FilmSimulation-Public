#!/usr/bin/env python3
"""Audit a curated snapshot for privacy, provenance, and manifest integrity."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote


FORBIDDEN_PATHS = {
    "AGENTS.md",
    "docs/PUBLIC_RELEASE.md",
    "docs/round1_baseline.json",
    "output/display_clipping_map.png",
    "output/round2_comparison.png",
    "output/round2_uncertainty.png",
    "roadmap/filmsimulation_roadmap.png",
    "roadmap/filmsimulation_roadmap.svg",
}
FORBIDDEN_PARTS = {".git", "input", "cache", "upstream", ".venv", "__pycache__"}
TEXT_SUFFIXES = {"", ".csv", ".gitignore", ".json", ".md", ".py", ".sh", ".svg", ".txt", ".yml", ".yaml"}
PRIVATE_IDENTIFIERS_PATTERN = r"(?:tai" r"chengwong|bio" r"hazardfish)"
PRIVATE_GOVERNANCE_PATTERN = r"research" r"-governance"
FORBIDDEN_TEXT = {
    "absolute-user-path": re.compile(r"/(?:Users|home)/[^/\s]+/"),
    "historical-username": re.compile(PRIVATE_IDENTIFIERS_PATTERN, re.IGNORECASE),
    "private-governance": re.compile(PRIVATE_GOVERNANCE_PATTERN, re.IGNORECASE),
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github-token": re.compile(r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    "aws-key": re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}"),
    "slack-token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "inaccessible-link-placeholder": re.compile(r"\]\(private source record(?:/[^)]*)?\)"),
}
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_snapshot(root: Path) -> dict:
    root = root.resolve()
    failures: list[str] = []
    manifest_path = root / "PUBLIC_SNAPSHOT_MANIFEST.json"
    if not manifest_path.is_file():
        return {"status": "fail", "failures": ["missing PUBLIC_SNAPSHOT_MANIFEST.json"]}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("git_history_included") is not False:
        failures.append("manifest does not declare git_history_included=false")
    if manifest.get("source_tree_dirty") is not False:
        failures.append("snapshot was not built from a clean exact candidate commit")
    if manifest.get("stale_rendered_roadmap_included") is not False:
        failures.append("snapshot does not exclude the stale pre-Decision-0006 roadmap render")
    statuses = manifest.get("decision_0006_statuses")
    if statuses != {
        "FS-P5-02": "blocked",
        "FS-P5-03": "completed",
        "FS-P6-01": "completed",
        "FS-P6-02": "completed",
    }:
        failures.append(f"Decision 0006 status mismatch: {statuses}")

    actual_files = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and not any(part in FORBIDDEN_PARTS for part in path.relative_to(root).parts)
    }
    for relative in sorted(FORBIDDEN_PATHS & set(actual_files)):
        failures.append(f"forbidden path present: {relative}")
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in FORBIDDEN_PARTS for part in relative.parts):
            failures.append(f"forbidden directory component present: {relative.as_posix()}")

    manifest_records = {row["path"]: row for row in manifest.get("included_files", [])}
    expected_files = set(manifest_records) | {"PUBLIC_SNAPSHOT_MANIFEST.json"}
    if set(actual_files) != expected_files:
        failures.append(
            f"manifest file set mismatch: extra={sorted(set(actual_files)-expected_files)}, "
            f"missing={sorted(expected_files-set(actual_files))}"
        )
    for relative, record in manifest_records.items():
        path = actual_files.get(relative)
        if path and sha256_file(path) != record["sha256"]:
            failures.append(f"manifest hash mismatch: {relative}")

    for relative, path in actual_files.items():
        if relative == "PUBLIC_SNAPSHOT_MANIFEST.json":
            continue
        raw = path.read_bytes()
        lowered = raw.lower()
        byte_markers = (
            b"tai" + b"chengwong",
            b"bio" + b"hazardfish",
            b"research" + b"-governance",
            b"/" + b"users" + b"/",
        )
        for marker in byte_markers:
            if marker in lowered:
                failures.append(f"private byte sequence in {relative}: {marker.decode('ascii')}")
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"LICENSE", ".gitignore"}:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in FORBIDDEN_TEXT.items():
            if pattern.search(text):
                failures.append(f"{label} in {relative}")
        if path.suffix.lower() == ".md":
            for match in MARKDOWN_LINK.finditer(text):
                target = match.group(1).strip()
                if target.startswith("<") and target.endswith(">"):
                    target = target[1:-1]
                target = target.split(maxsplit=1)[0]
                if target.startswith(("#", "http://", "https://", "mailto:")):
                    continue
                local = unquote(target.split("#", 1)[0])
                if local and not (path.parent / local).exists():
                    failures.append(f"missing local Markdown target in {relative}: {target}")

    governance = root / "docs" / "PUBLIC_GOVERNANCE_SUMMARY.md"
    if not governance.is_file():
        failures.append("missing sanitized public governance summary")
    readme = (root / "README.md").read_text(encoding="utf-8") if (root / "README.md").is_file() else ""
    if "scripts/bootstrap_research.sh" not in readme or "pytest tests -q" not in readme:
        failures.append("README lacks reproducibility commands")
    return {"status": "pass" if not failures else "fail", "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    result = audit_snapshot(args.snapshot)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
