# FS-P6-01 Public-data search, provenance classification and evidence register

Status: **executor submission, awaiting independent QC**. The roadmap status of FS-P6-01 stays `planned` (migration mode). Nothing here is a completion claim.

- Authorization: Research Director Decision 1 (2026-11-20); governance record decision 0004, [Decision 0004 public summary](../PUBLIC_GOVERNANCE_SUMMARY.md) (pending merge).
- Rules applied: `docs/phase6/PUBLIC_DATA_STUDY_DEFINITION.md` (§3 search budget, §4 classification, §5 register schema).
- Base: branch `cursor/p6-public-data-roadmap-7819` at `df828320bae3b21dc635b9f70126fa2bafdbfc3f`.
- Session: one executor session, 2026-11-20 18:43–19:05 UTC. No continuation session used.
- Not done here: no FS-P6-02 residuals, and no change to G4, FS-P4 verdicts, FS-P5, historical outputs or acceptance criteria.

## Outcome

No public independent physical measurement of 5219 or 2383 was found. Every curve dataset for either stock traces back to Kodak's own data sheets, and no entry has `lineage=none`. Independent physical validation therefore stays **`unavailable` / `not_evaluable`**, which §1 of the study definition accepts as a valid outcome.

Four entries are numerically usable by FS-P6-02, and none of them is independent of Kodak or spektrafilm:

| entry | what it is | permitted use (evidence level) |
|---|---|---|
| PD-001 | Academy S-2008-002 Annex C Status M→APD matrix for 5219, fitted to spectrophotometer measurements of ARRILASER-exposed patches | implementation cross-check (V1/V2) |
| PD-018 | Kodak 2383 LAD aim, Status A 1.09 / 1.06 / 1.03 (H-61B; also in H-1-2383t 2005) | manufacturer source-conformance / cross-check (V2) |
| PD-042 | film-scan-calibration raster traces of the 5219 sheet, with a full digitization audit | digitization uncertainty (V2) |
| PD-048 | moderates-film-simulator vector extraction of the 5219 sensitometric curves, with a documented re-extraction spread | digitization uncertainty (V2) |

## Reproduce

```bash
python3 scripts/validate_public_data_register.py      # schema + cross-field rules + search-log budget
python3 scripts/fingerprint_public_data.py            # §4.2 step d; clones pinned repos into cache/ (git-ignored)
python3 -m pytest tests/test_public_data_register.py -q
```

`scripts/fingerprint_public_data.py` reads spektrafilm at `77d448ad…` (tag `v0.2.0-legacy`) and `3bb2c2d…`, plus each candidate repository at the commit recorded in the register. It writes `validation/public_data/fingerprints.json`. It needs only `numpy` and `git`.

## Files

| path | content |
|---|---|
| `validation/public_data/evidence_register.csv` | 58 entries, UTF-8 without BOM, 26 columns (the §5 fields plus `archive_url`, `credibility_reason`, `found_by`) |
| `validation/public_data/evidence_register.schema.json` | JSON Schema for a register row |
| `validation/public_data/search_log.csv` | 39 queries + 1 citation hop, each with timestamp, engine, string, hit count and the basis of that count |
| `validation/public_data/fingerprints.json` | step-d metrics against the legacy CSVs and pinned profiles, plus digitizer-to-digitizer agreement |
| `scripts/validate_public_data_register.py`, `tests/test_public_data_register.py` | validator and tests |
| `scripts/fingerprint_public_data.py` | step-d fingerprint |

No third-party file is committed. Kodak, SMPTE and Academy PDFs carry no redistribution licence, so they are recorded by URL, retrieval time and SHA-256 only. Repository data is pinned by commit and blob hash.

## Search execution (§3)

| family | queries | budget | new entries outside NOT_COMPARABLE / shared lineage |
|---|---|---|---|
| 1 Academy / SMPTE / ACES | 8 | ≤10 | none: PD-001/002 have `lineage=unknown`, which counts as shared |
| 2 Kodak publications | 7 | ≤10 | none |
| 3 Academic databases (Crossref, OpenAlex, Zenodo, Figshare, web) | 10 + 1 citation hop | ≤10 | none |
| 4 Archives and institutions | 5 | ≤10 | none |
| 5 Implementations and datasets (GitHub code/repo search, web) | 9 | ≤10 | none |
| total | 39 + 1 hop | ≤50; entries 58 ≤60 | |

Notes on the log:

- Web-search hit counts are the number of links the engine returned; it returns at most 5. Crossref, OpenAlex, Zenodo and GitHub counts are the totals each API reports, with the screened depth stated in `hit_count_basis`. Zero-hit queries are logged (Q23 Figshare, Q37 GitHub `filename:density_curve_r.csv`).
- Q27 was issued during the family 3 pass but targets emulator datasets. It is logged under family 5, and the note in the log says so.
- **Saturation.** Treating `unknown` as shared (§4.2), the saturation condition, two consecutive families with nothing new outside the shared classes, was already met after family 2. The executor still ran families 3–5, because FS-P6-01 acceptance criterion 1 requires every family to be searched. See the Director items below.

## Register summary

| evidence_class | same_primary_source | derived_from_spektrafilm | unknown | none | total |
|---|---|---|---|---|---|
| INDEPENDENT_PHYSICAL_MEASUREMENT | 0 | 0 | 0 | 0 | **0** |
| MANUFACTURER_PUBLISHED_MEASUREMENT | 9 | 0 | 0 | 0 | 9 |
| DIGITIZED_PUBLISHED_DATA | 10 | 1 | 0 | 0 | 11 |
| DERIVED_OR_SIMULATED_DATA | 1 | 4 | 3 | 0 | 8 |
| NOT_COMPARABLE | 0 | 0 | 30 | 0 | 30 |
| total | 20 | 5 | 33 | **0** | 58 |

Status: 4 `comparable`, 51 `not_evaluable`, 3 `unavailable` (paywalled: SMPTE ST 2065-2/-3, a 2010 SMPTE paper, and a commercial chart-scan product; none acquired). No row has `permitted_use=independent_validation`, and the validator enforces this.

`NOT_COMPARABLE` rows carry `lineage=unknown` because §4.2 checks a–c are not required for them. That value does not assert anything about their provenance.

## Lineage fingerprint (§4.2 step d)

Spektrafilm's sources were re-verified as follows. The legacy `info.txt` files cite "2015 h15219t" and "March 2005 H-1-2383t". The pinned profile hashes match `docs/phase2/REFERENCE_DATA_PROVENANCE.md` (`d7beca68…`, `eb7fdfa3…`). The FS-P4 Kodak cache hashes match the March 2026 5219 and August 2026 2383 editions (PD-013, PD-016).

RMS differences against the legacy CSVs, in density units (D) for curves and log units for sensitivity:

| dataset | 5219 characteristic (aligned) | 5219 dyes (raw) | 2383 characteristic | shared sample positions |
|---|---|---|---|---|
| film-scan-calibration (PD-042) | 0.013–0.016 | 0.002–0.009 | — | ≤1.3% |
| luce-develop (PD-043/044) | 0.014–0.016 | 0.001–0.003 | 0.031–0.037 raw | ≤1% |
| moderates-film-simulator (PD-048) | 0.007–0.009 | — | — | — |
| spectral_film_lut (PD-040/041) | 0.006–0.007 | 0.002–0.005 | 0.004–0.005 aligned | 0% |
| Fixer (PD-045/046) | 0.0006–0.0019 **raw** | 0.002–0.003 | 0.007–0.011 raw | 0.3% |

How to read this table:

- **Independent tracers of the same Kodak figure agree tightly.** film-scan-calibration (raster) and luce-develop (vector, November 2007 edition) agree with each other at 0.0006–0.0007 D. So a close match is expected between careful traces and is not, by itself, evidence of copying.
- **The legacy CSVs use a camera-stops x-axis** (x = stops × log10 2). Kodak's printed log-exposure axis differs from it by about 4%. Most of the 0.013–0.016 aligned residual for tracers that used the log-exposure axis comes from that scale difference.
- **Fixer is borderline.** Its 5219 characteristic curves match the legacy CSV within 0.0006–0.0019 D raw, below the 0.01 threshold. Its sample positions and range do not match, and it also uses the camera-stops axis. The §4.2 rule for `derived_from_spektrafilm` therefore does not fire, and Fixer is classified `same_primary_source` and flagged for QC.
- **spectral_film_lut's 2383 data** has R and B characteristic curves offset by −0.305 / +0.295 logH relative to both the legacy CSV and luce-develop. This is an undocumented processing choice on the same Kodak figure.
- **Vendored copies.** Of 507 code-search hits for `kodak_2383 density`, the 10 sampled copies are byte-identical or array-identical to spektrafilm profile versions. They are recorded together as PD-052 (`derived_from_spektrafilm`).

An observation for FS-P6-02, not a result: after an x-shift plus offset alignment, every independent digitization differs from the **pinned profile's green 5219 characteristic curve** by about 0.14–0.16 D RMS, against 0.006–0.035 D for red and blue. moderates-film-simulator independently reports the profile's green gamma as about 23% lower than its own vector extraction. The profile's density curve comes from a fitted model, so this is a source-conformance question for FS-P6-02 at evidence level V2. It does not change any G4 or FS-P4 verdict.

## What remains not_evaluable or unavailable

- Independent physical validation of 5219 or 2383 is `unavailable`. No public numeric measurement by a non-Kodak party with a named instrument was found.
- PD-007, the Forsythe CIC 2009 paper, contains the only third-party 2383 measurement found, a Status A check of print matches. Only aggregate statistics are published, so it is not comparable.
- Real-film ΔE00, the full 5219→2383 chain, granularity and MTF, and absolute spectral dye density all remain `not_evaluable`, as the study definition expected (§6).
- Kodak data-sheet curves (PD-011..017, PD-022) exist only as raster figures. Using them numerically still depends on the digitizations.

## Corrections to the study definition's preliminary notes

These correct facts in the definition; they are not changes to any rule.

- The CIC 2009 APD paper (DOI 10.2352/cic.2009.17.1.art00054) is by **Alexander Forsythe** (AMPAS), not "Maltz et al.". Its negative stocks are not named.
- `v0.2.0-legacy` is an annotated tag object `03664a79…` that points to commit **`77d448ad…`**. The register and fingerprint pin the commit.
- S-2008-002 Annex C states that the 31 stocks' patches were exposed with an ARRILASER recorder and measured with a spectrophotometer at 10 nm intervals. The instrument model and operator are not named, and the patch spectra are not published. The matrix is therefore `DERIVED_OR_SIMULATED_DATA` with `lineage=unknown`, not `none`.

## Limitations

- Web-search hit counts are capped at 5 links, so they show plausibility, not completeness. QC re-runs will see different link sets as the web changes.
- Query timestamps are recorded to the minute from the session clock.
- Of 507 vendored-profile code hits, 10 were sampled. The rest are classified by path and file name only.
- Edition identity of Kodak curves across 2007, 2015, 2022 and 2026 was not verified pixel by pixel. Treating `unknown` as shared makes this conservative.
- Identity separation between executor and QC is asserted, not proven (shared account; study definition §7).

## Items needing a Research Director decision

1. **Saturation vs AC1.** The saturation stop was met after family 2, but AC1 requires every family to be searched. The executor ran all five. Please confirm that AC1 takes precedence, or record which rule governs.
2. **Lineage for Kodak data that spektrafilm did not use.** The lineage vocabulary has no value for this case (PD-018 LAD aims, PD-022 EDR scanning plot). The executor used `same_primary_source`, which is conservative. If the Director prefers a distinct label, that is a schema change.
3. **Annex C lineage (PD-001).** It is `unknown` because the instrument and operator are not named. A Director-approved inquiry to the Academy (councilinfo@oscars.org, as the document suggests) could settle it, but that is outreach and is not authorized here.
4. **Fixer (PD-045).** Its classification is borderline (see the fingerprint section). QC may dispute it, and the Director adjudicates disputes.
5. **Data-sheet rows classed MANUFACTURER with raster-only values** (PD-011..017, PD-022). Rule 4 asks for numbers. The executor kept the class to record the manufacturer source and set `usable_for_residuals=false`. QC may dispute this.
