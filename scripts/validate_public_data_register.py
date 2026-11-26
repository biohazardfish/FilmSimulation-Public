#!/usr/bin/env python3
"""Validate the FS-P6-01 public-data evidence register and search log.

Checks the register against evidence_register.schema.json and enforces the
cross-field rules of docs/phase6/PUBLIC_DATA_STUDY_DEFINITION.md §§3-5,
including that no spektrafilm-lineage or unknown-lineage row is permitted as
independent validation. It does not compare any data with the model.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "validation" / "public_data"
DEFAULT_REGISTER = DATA / "evidence_register.csv"
DEFAULT_SCHEMA = DATA / "evidence_register.schema.json"
DEFAULT_SEARCH_LOG = DATA / "search_log.csv"

FAMILIES = (
    "1_academy_smpte_aces",
    "2_kodak_publications",
    "3_academic_databases",
    "4_archives_institutions",
    "5_implementations_datasets",
)
SEARCH_LOG_FIELDS = ("query_id", "family", "kind", "date_utc", "engine", "query", "hit_count", "hit_count_basis", "register_entries", "notes")
MAX_QUERIES_PER_FAMILY = 10
MAX_QUERIES = 50
MAX_ENTRIES = 60
SHARED_LINEAGES = {"same_primary_source", "derived_from_spektrafilm", "unknown"}
TIMESTAMP = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{path.name}: must be UTF-8 without BOM")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = []
        for number, values in enumerate(reader, start=2):
            if len(values) != len(header):
                raise ValueError(f"{path.name} line {number}: {len(values)} fields, header has {len(header)}")
            rows.append(dict(zip(header, values)))
    return header, rows


def check_schema(row: dict[str, str], schema: dict[str, Any], where: str) -> list[str]:
    errors = []
    props = schema["properties"]
    for name, rule in props.items():
        value = row.get(name)
        if value is None:
            errors.append(f"{where}: missing field {name}")
            continue
        if "enum" in rule and value not in rule["enum"]:
            errors.append(f"{where}: {name}={value!r} not in {rule['enum']}")
        if "pattern" in rule and not re.match(rule["pattern"], value):
            errors.append(f"{where}: {name}={value!r} does not match {rule['pattern']}")
        if len(value) < rule.get("minLength", 0):
            errors.append(f"{where}: {name} is empty")
    return errors


def check_rules(row: dict[str, str], where: str) -> list[str]:
    errors = []
    cls, lin, use = row["evidence_class"], row["lineage"], row["permitted_use"]
    usable = row["usable_for_residuals"] == "true"
    if use == "independent_validation" and (lin in SHARED_LINEAGES or lin != "none"):
        errors.append(f"{where}: lineage={lin} may not have permitted_use=independent_validation")
    if use == "independent_validation" and cls != "INDEPENDENT_PHYSICAL_MEASUREMENT":
        errors.append(f"{where}: independent_validation requires INDEPENDENT_PHYSICAL_MEASUREMENT")
    if lin == "derived_from_spektrafilm" and use not in {"implementation_crosscheck", "none"}:
        errors.append(f"{where}: derived_from_spektrafilm allows only implementation_crosscheck or none")
    if cls == "NOT_COMPARABLE":
        if use not in {"support", "none"}:
            errors.append(f"{where}: NOT_COMPARABLE allows only support or none")
        if usable:
            errors.append(f"{where}: NOT_COMPARABLE row cannot be usable_for_residuals")
    else:
        for step in ("a:", "b:", "c:", "d:"):
            if step not in row["lineage_evidence"]:
                errors.append(f"{where}: lineage_evidence lacks check {step[0]} (§4.2 steps a-d)")
    if cls == "DERIVED_OR_SIMULATED_DATA" and use in {"source_conformance", "digitization_uncertainty"}:
        errors.append(f"{where}: derived data allows only implementation_crosscheck, support or none")
    if lin == "none" and "c:" not in row["lineage_evidence"]:
        errors.append(f"{where}: lineage=none needs a named measurement chain (check c)")
    if usable != (row["status"] == "comparable"):
        errors.append(f"{where}: usable_for_residuals must be true exactly when status=comparable")
    if row["status"] != "comparable" and not row["reason"].strip():
        errors.append(f"{where}: status={row['status']} requires a reason")
    avail = row["availability"]
    if avail == "open_download" and row["sha256"] == "n/a":
        errors.append(f"{where}: open_download requires the sha256 of the retrieved file")
    if avail in {"paywalled_not_acquired", "removed", "unavailable"}:
        if row["sha256"] != "n/a":
            errors.append(f"{where}: {avail} rows must not carry a file hash")
        if usable:
            errors.append(f"{where}: {avail} row cannot be usable_for_residuals")
    if cls == "DIGITIZED_PUBLISHED_DATA":
        if row["values_via"] != "digitized":
            errors.append(f"{where}: DIGITIZED_PUBLISHED_DATA requires values_via=digitized")
        if row["digitization_record"] == "n/a" and (row["credibility"] != "low" or usable):
            errors.append(f"{where}: digitization without a record must be credibility=low and not usable (§4.1 rule 5)")
    return errors


def check_search_log(rows: list[dict[str, str]], header: list[str]) -> tuple[list[str], dict[str, Any]]:
    errors = []
    if tuple(header) != SEARCH_LOG_FIELDS:
        errors.append(f"search_log: header {header} != {list(SEARCH_LOG_FIELDS)}")
        return errors, {}
    ids = Counter(r["query_id"] for r in rows)
    errors += [f"search_log: duplicate query_id {q}" for q, n in ids.items() if n > 1]
    per_family: Counter[str] = Counter()
    hops = 0
    for r in rows:
        where = f"search_log {r['query_id']}"
        if r["family"] not in FAMILIES:
            errors.append(f"{where}: unknown family {r['family']}")
        if r["kind"] not in {"query", "citation_hop"}:
            errors.append(f"{where}: kind must be query or citation_hop")
        if not TIMESTAMP.match(r["date_utc"]):
            errors.append(f"{where}: date_utc must be an ISO UTC timestamp")
        if not r["hit_count"].isdigit():
            errors.append(f"{where}: hit_count must be a non-negative integer (zero included)")
        for field in ("engine", "query", "hit_count_basis", "register_entries"):
            if not r[field].strip():
                errors.append(f"{where}: {field} is empty")
        if r["kind"] == "query":
            per_family[r["family"]] += 1
        else:
            hops += 1
    for family in FAMILIES:
        if per_family[family] == 0:
            errors.append(f"search_log: family {family} was not searched")
        if per_family[family] > MAX_QUERIES_PER_FAMILY:
            errors.append(f"search_log: family {family} has {per_family[family]} queries (max {MAX_QUERIES_PER_FAMILY})")
    total = sum(per_family.values())
    if total > MAX_QUERIES:
        errors.append(f"search_log: {total} queries exceed the cap of {MAX_QUERIES}")
    return errors, {"queries": total, "citation_hops": hops, "per_family": dict(per_family)}


def validate(register: Path, schema_path: Path, search_log: Path) -> tuple[list[str], dict[str, Any]]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    header, rows = read_csv(register)
    if header != schema["required"]:
        errors.append(f"register: header must be exactly {schema['required']}")
        return errors, {}
    if len(rows) > MAX_ENTRIES:
        errors.append(f"register: {len(rows)} entries exceed the cap of {MAX_ENTRIES}")
    ids = Counter(r["entry_id"] for r in rows)
    errors += [f"register: duplicate entry_id {e}" for e, n in ids.items() if n > 1]
    for row in rows:
        where = f"register {row.get('entry_id', '?')}"
        schema_errors = check_schema(row, schema, where)
        errors += schema_errors
        if not schema_errors:
            errors += check_rules(row, where)
    log_header, log_rows = read_csv(search_log)
    log_errors, log_summary = check_search_log(log_rows, log_header)
    errors += log_errors
    known = {r["query_id"] for r in log_rows}
    for row in rows:
        for q in row["found_by"].split(";"):
            if q not in known:
                errors.append(f"register {row['entry_id']}: found_by {q} is not in the search log")
    summary = {
        "entries": len(rows),
        "by_class": dict(Counter(r["evidence_class"] for r in rows)),
        "by_lineage": dict(Counter(r["lineage"] for r in rows)),
        "by_status": dict(Counter(r["status"] for r in rows)),
        "by_permitted_use": dict(Counter(r["permitted_use"] for r in rows)),
        "independent_validation_rows": sum(r["permitted_use"] == "independent_validation" for r in rows),
        "search_log": log_summary,
    }
    return errors, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", type=Path, default=DEFAULT_REGISTER)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--search-log", type=Path, default=DEFAULT_SEARCH_LOG)
    args = parser.parse_args(argv)
    try:
        errors, summary = validate(args.register, args.schema, args.search_log)
    except ValueError as exc:
        errors, summary = [str(exc)], {}
    print(json.dumps({"valid": not errors, "errors": errors, "summary": summary}, indent=2, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
