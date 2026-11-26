# FS-P6-02 Public-data numerical comparison

Status: **executor submission, awaiting independent QC**. Roadmap status stays `planned` (migration mode). This is not a completion claim.

- Authorization: Research Director Decision 1 (2026-11-20); governance record decision 0004, [Decision 0004 public summary](../PUBLIC_GOVERNANCE_SUMMARY.md) (pending merge).
- Rules: `docs/phase6/PUBLIC_DATA_STUDY_DEFINITION.md` §6; register from FS-P6-01 (QC-approved at `7208ecc`).
- Base: branch stacked on FS-P6-01 (`cursor/fs-p6-01-public-data-register-cb45`).

## Outcome

**No independent physical validation** (`INDEPENDENT_PHYSICAL_MEASUREMENT` with `lineage=none`) exists in the register. Independent validation remains **`unavailable`**, per FS-P6-01 QC (0 `independent_validation` rows).

**Four register entries** were numerically compared (all non-independent, evidence V2):

| entry | label | evidence level | permitted use |
|---|---|---|---|
| PD-001 | implementation cross-check (Academy Status M→APD on profile samples) | V2 | implementation_crosscheck |
| PD-018 | manufacturer cross-check (Kodak 2383 LAD aim vs nearest profile density) | V2 | source_conformance |
| PD-042 | digitization uncertainty (film-scan-calibration vs pinned profile) | V2 | digitization_uncertainty |
| PD-048 | digitization uncertainty (moderates-film-simulator vs pinned profile) | V2 | digitization_uncertainty |

**54 entries** are recorded as excluded in `comparisons.json`: **51** `not_evaluable`, **3** `unavailable` (PD-004, PD-026, PD-055), each with the register `reason` and `entry_id`.

G4, FS-P4 historical `not_evaluable` rows, `docs/phase2/METRICS.json`, and FS-P5 criteria are **unchanged**.

## Reproduce

```bash
python3 scripts/compute_public_data_comparisons.py
python3 -m pytest tests/test_public_data_comparisons.py -q
```

The script clones pinned third-party repositories into `cache/public_data_repos/` (git-ignored) on first run, reads `validation/public_data/evidence_register.csv`, and writes `validation/public_data/comparisons.json`.

## Compared results (summary)

### PD-001 — Status M→APD implementation cross-check

Academy S-2008-002 Annex C matrix for Eastman Kodak 5219 (via [film-scan-calibration](https://github.com/OwlMightyCh/film-scan-calibration) `3716966`) applied to Status M RGB densities sampled from the **pinned 5219 profile**. The spektrafilm profile does not implement APD; this records the transform implied by the Academy fit. Academy fit residuals on unpublished patches (mean abs error ≤0.006 on grey) are metadata only, not a model pass/fail.

### PD-018 — 2383 LAD manufacturer cross-check

Published Kodak LAD Status A aim **1.09 / 1.06 / 1.03** (H-61B) compared to the nearest point on the pinned **2383 profile density curves** (model channel coefficients, **not** Status A). Residual RMSE **0.143 D** with explicit densitometry mismatch in `comparisons.json`. This is source-conformance proximity, not physical print measurement.

### PD-042 / PD-048 — digitization vs pinned profile

Aligned RMS (D) of independent Kodak-sheet digitizations against the pinned profile characteristic curves:

| channel | PD-042 (film-scan-calibration) | PD-048 (moderates-film-simulator) |
|---|---|---|
| R | 0.008 | 0.005 |
| G | **0.137** | **0.125** |
| B | 0.015 | 0.018 |

Red and blue agree at trace-noise scale (inter-digitizer yardstick ~0.0006–0.0007 D). **Green diverges by ~0.12–0.14 D RMS** from the pinned profile after alignment—the same source-conformance pattern noted in `docs/phase6/PUBLIC_DATA_SEARCH.md`. No Director-approved tolerance is applied; values are reported only.

## Excluded (not compared)

Every other register row (`PD-002`…`PD-058` except the four above) appears in `comparisons.json` with `outcome: not_evaluable` or `unavailable` and cites the register reason. Highlights:

- **Independent validation:** none (`lineage=none` count 0).
- **Raster-only Kodak sheets** (PD-011…017, PD-022): no audited digitization.
- **spektrafilm-lineage copies** (PD-052…058, PD-051, etc.): implementation_crosscheck only, never external.
- **Paywalled / commercial** (PD-004, PD-026, PD-055): `unavailable`, not acquired.

## Files

| path | role |
|---|---|
| `scripts/compute_public_data_comparisons.py` | single-command FS-P6-02 computation |
| `validation/public_data/comparisons.json` | machine-readable outcomes for all 58 entries |
| `tests/test_public_data_comparisons.py` | shape and reproducibility checks |

## Limitations

- Profile densities are model channel coefficients; Status M / Status A / APD conversions are documented where mismatched.
- No physical pass/fail without a Director-approved tolerance (study definition §1).
- Executor/QC identity separation is asserted, not proven (§7).