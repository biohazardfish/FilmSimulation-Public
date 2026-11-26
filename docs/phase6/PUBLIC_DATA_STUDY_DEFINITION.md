# P6 Public-Data External Comparison — study definition

狀態：**planned**（定義文件，不是證據）。本文件記錄 Research Director Decision 1（2026-11-20）核准的研究設計，供 `FS-P6-01` 與 `FS-P6-02` 執行與獨立 QC 使用。Governance record: decision 0004 (Decision 0004 public summary, pending merge), file `decisions/0004-film-p6-public-data-comparison.md` in `non-public governance archive`.

The authoritative acceptance criteria are the `acceptance` cells of `FS-P6-01` and `FS-P6-02` in `roadmap/filmsimulation_roadmap.csv`. This document holds the approved rules those cells reference. The approved text is kept in English to avoid translation drift. Changing any rule here is a roadmap definition change and needs a recorded Director decision.

This document creates no evidence. The evidence register, search log and reports listed below are produced by the executor on a task branch.

## 1. Objective and non-goals

**Objective.** Run a bounded, auditable search of public data for numerical comparison with Kodak VISION3 500T 5219 and VISION Color Print Film 2383. Classify every candidate by evidence class and by provenance relative to spektrafilm. Record the results in a machine-readable evidence register. Where a candidate is genuinely comparable, compute residuals against the pinned FilmSimulation model. Everything else is recorded as `unavailable` or `not_evaluable`.

**Non-goals.**

- No physical film measurement by anyone in the project, including the Director. No equipment, film, processing, standard or data purchase. No commercial LUTs. No paid dataset acquisition.
- No change to the G4 conclusions (`docs/phase4/G4_PUBLISHED_REFERENCE_VALIDATION.md`), the FS-P4-01/02/03 verdicts, the six historical `not_evaluable` published comparisons, `docs/phase2/METRICS.json`, historical outputs, or any existing acceptance criterion.
- No effect on FS-P5-03 Closure. P6 is independent of P5: Closure neither waits for P6 nor absorbs its results, and FS-P5-03 is not blocked, reopened or redefined because of P6. P6 results go into P6's own reports.
- No physical-accuracy pass/fail. Without a Director-approved tolerance, the study reports only values, residuals and uncertainty.
- No re-labelling of spektrafilm-lineage data as independent validation.
- Not a fix for FS-P5-02 (the fair LUT comparison). LUTs are out of scope.

An outcome of `unavailable` or `not_evaluable` is scientifically acceptable when supported by documented evidence. It is a valid completion, not a failure or `blocked`.

## 2. Tasks and dependencies

| id | goal | depends_on | deliverable | gate |
|---|---|---|---|---|
| FS-P6-01 | Search for public 5219/2383 data, classify it, and build the evidence register | *(none)* | `validation/public_data/evidence_register.csv` with schema and validator, `validation/public_data/search_log.csv`, `docs/phase6/PUBLIC_DATA_SEARCH.md` | — |
| FS-P6-02 | Compute residuals for register entries judged comparable, and keep `not_evaluable` everywhere else | FS-P6-01 | `validation/public_data/comparisons.json`, `docs/phase6/PUBLIC_DATA_COMPARISON.md` | G6 |

No existing task depends on P6. FS-P6-02 may use the FS-P4 comparison code and the pinned profiles, but declares no dependency on FS-P4 or P5 tasks, so P6 promotion does not wait on the historical QC backlog for those claims.

## 3. Search scope, sources, and stopping rule

**In scope:**

- Products: 5219/7219 and 2383/3383. A sibling stock (5207, 5213, 2393, and so on) is only recorded, as `NOT_COMPARABLE` with the reason "different product".
- Quantities: characteristic curves (density against log exposure, with the densitometry status stated), spectral sensitivity, spectral dye density, Dmin or base spectra, spectral transmittance of processed samples, printing density (APD, RP 180, Cineon), LAD aims, and Status M↔printing-density conversions.

**Source families, searched in this order:**

1. **Academy / SMPTE / ACES.** S-2008-002 (ADX/APD) with Annex C, TB-2014-005, Maltz et al. CIC 2009, ACESCentral attachments, and SMPTE RP 180 (free archived copy only).
2. **Kodak publications.** All public editions of H-1-5219 and H-1-2383, the TI/Ti2397 data sheets, H-387 (Digital LAD), H-61 (LAD), H-24 (ECN-2/ECP-2D manual) and Kodak conference papers.
3. **Academic databases.** IS&T CIC / JIST / Electronic Imaging, the SMPTE Motion Imaging Journal (abstracts only if paywalled), Google Scholar, Zenodo, Figshare, institutional repositories, and theses. Search terms: "5219", "Vision3 500T", "2383", "print film" combined with spectral, densitometry, sensitometry or printing density.
4. **Archives and research institutions.** Film-archive and restoration labs, conservation-science groups, and NIST/NBS reports. Material on discontinued stocks is recorded as `NOT_COMPARABLE`.
5. **Independent implementations and datasets on GitHub/GitLab.** film-scan-calibration, spectral_film_lut, colour-science datasets, vkdt/darktable filmsim, and code-search hits for "5219" or "2383" CSV/JSON files.

**Budget and stopping rule.** The study is bounded by work units, not calendar time. Stop at whichever comes first:

- Every source family has had its fixed query list run (at most 10 queries per family, listed in the search log), plus at most 2 hops of citation chasing from each non-`NOT_COMPARABLE` hit.
- Hard caps are reached: at most 50 queries, at most 60 register entries, and 1 executor session plus at most 1 continuation session.
- Saturation: two consecutive families add no new entry outside `NOT_COMPARABLE`, `same_primary_source` or `derived_from_spektrafilm`.

Every query is logged with its date, engine, string and hit count, including queries that return nothing, so "nothing found" is auditable. Paywalled items are recorded from metadata only (`availability=paywalled_not_acquired`) and are never bought.

## 4. Classification scheme

Each entry has two independent labels: an **evidence class** (exactly one) and a **spektrafilm lineage** flag. The class describes what the data *is*. The lineage flag decides what the data may be *used for*.

### 4.1 Evidence class: apply the rules in order and take the first match

1. **NOT_COMPARABLE.** The entry is the wrong product, or a metric definition only (for example RP 180 responsivities, or a standard without film data). It may also be a discontinued or different stock, a reflection paper, or a quantity the model does not expose under matching conditions (for example granularity or MTF while grain is disabled). It also applies when conditions cannot be established at all: no process, no densitometry status, no illuminant. *Exception:* a metric definition needed to compute another comparison is kept as a supporting entry with `role=support`.
2. **DERIVED_OR_SIMULATED_DATA.** The numbers come from a model, fit, matrix, LUT or simulation, and are not a direct reading of a measured or published curve. Examples are another emulator's outputs, a computed APD from digitized dye curves, and fitted conversion matrices whose underlying patches are not published.
3. **INDEPENDENT_PHYSICAL_MEASUREMENT.** A party other than Kodak measured physical, processed 5219 or 2383 samples with a stated instrument and stated conditions, and the values are published as numbers (a table or data file). A figure counts only with an audited digitization, and then the entry is tagged `values_via=digitized`.
4. **MANUFACTURER_PUBLISHED_MEASUREMENT.** Kodak (or the Academy reporting Kodak-supplied measurements) published values for 5219 or 2383 as **numbers** (tables, LAD aims, conversion tables) with stated conditions.
5. **DIGITIZED_PUBLISHED_DATA.** Values extracted from a published raster or vector figure, usually a Kodak curve. To be usable, the entry must have axis calibration points, the extraction method and tool, per-curve control points, and an error record (re-trace spread, or residual against the printed grid). A digitization that lacks these keeps its class but gets `credibility=low` and `usable_for_residuals=false`.

### 4.2 Spektrafilm lineage flag: `lineage`

| value | meaning | permitted use |
|---|---|---|
| `none` | Primary source and processing chain are disjoint from spektrafilm's (shown positively, see below) | Eligible as independent validation for its quantity |
| `same_primary_source` | Traces or reproduces the same Kodak documents spektrafilm used (any edition of H-1-5219 / H-1-2383 whose curves are unchanged) | Source-conformance or digitization-uncertainty only (V2); **never** independent validation |
| `derived_from_spektrafilm` | Uses agx-emulsion/spektrafilm CSVs, profiles or code outputs, or is numerically indistinguishable from them | Software/implementation cross-check only |
| `unknown` | Provenance not established | Treated as `same_primary_source` |

**Fingerprint of spektrafilm's sources (to be re-verified by the executor):**

- The profile metadata states "Kodak and Fujifilm data-sheets, scientific publications, and technical material". The FilmSimulation copy is in `intermediate/fixed_parameters.json`.
- The legacy raw digitizations at spektrafilm tag `v0.2.0-legacy` are `agx_emulsion/data/film/negative/kodak_vision3_500t/*.csv` and `agx_emulsion/data/paper/kodak_2383/*.csv`. Their `info.txt` files cite "2015 h15219t" for 5219, and "March 2005, H-1-2383t, Tungsten + KODAK heat-absorbing glass N 2043 (+ series 1700), 1.0 D over min, Status A" for 2383.
- The pinned profiles are `kodak_vision3_500t.json` and `kodak_2383.json` at spektrafilm `3bb2c2d2801ff68b92019cf1dbcbb133d60832bc`, with hashes in `docs/phase2/REFERENCE_DATA_PROVENANCE.md`.
- Kodak's own datasheets (also cached by FS-P4-01) are therefore `same_primary_source` by default.

**Detection procedure.** Steps a–c are required for every entry outside `NOT_COMPARABLE`. Step d is required wherever numbers can be resampled.

- a. **Citation check.** Does the source cite Kodak H-1-5219/H-1-2383 or a Kodak data sheet, or spektrafilm/agx-emulsion, Volpato, or CC BY-SA spektrafilm attribution?
- b. **Code/data check.** Look for imports, vendored files, or identical file layouts (`density_curve_r.csv`, `dye_density_mid.csv`, and so on).
- c. **Measurement-chain check.** Is a physical sample, instrument and operator named that are not Kodak's?
- d. **Numerical fingerprint.** Resample to the spektrafilm grid and compute RMS difference and maximum absolute difference against the legacy CSV and the profile arrays. If the RMS is below the larger of the stated digitization error and 0.01 D (or 0.01 log-sensitivity), with matching sample positions or matching NaN or extrapolation patterns, flag it as `derived_from_spektrafilm` unless provenance proves otherwise. Agreement with Kodak curves within trace noise implies `same_primary_source`, not independence.

`lineage=none` requires positive evidence from step c. Absence of a citation is not enough.

## 5. Evidence register schema and location

Written by the FS-P6-01 executor on the task branch, not by this definition:

- `validation/public_data/evidence_register.csv`: one row per candidate, UTF-8, no BOM.
- `validation/public_data/evidence_register.schema.json`: JSON Schema, checked by a small validator such as `scripts/validate_public_data_register.py` with a unit test.
- `validation/public_data/search_log.csv`: every query.
- `validation/public_data/sources/<entry_id>/`: retrieved numeric files, only where the licence permits redistribution. Otherwise only the URL, the retrieval date and the SHA-256 are stored.
- `docs/phase6/PUBLIC_DATA_SEARCH.md` and `docs/phase6/PUBLIC_DATA_COMPARISON.md`: human reports.

The existing physical-dataset validator `scripts/validate_phase4_dataset.py` does not apply to public data and is not modified or loosened.

**Register fields:**

| field | type / allowed values | notes |
|---|---|---|
| `entry_id` | `PD-###` | stable |
| `product` | `5219` \| `2383` \| `both` \| `other:<code>` | |
| `quantity` | `characteristic_curve` \| `spectral_sensitivity` \| `spectral_dye_density` \| `dmin_spectrum` \| `spectral_transmittance` \| `printing_density` \| `lad_aim` \| `density_conversion` \| `other` | |
| `evidence_class` | the five classes | §4.1 |
| `lineage` | `none` \| `same_primary_source` \| `derived_from_spektrafilm` \| `unknown` | §4.2 |
| `lineage_evidence` | text | results of checks a–d |
| `source_url` | URL | plus `archive_url` if one exists |
| `citation` | full reference, with DOI or publication code and edition/date | |
| `publisher_role` | `manufacturer` \| `standards_body` \| `academic` \| `archive` \| `independent_dev` \| `other` | |
| `measurement_conditions` | structured text: illuminant/CCT, exposure time, process (ECN-2/ECP-2D), densitometry status (M/A/APD/RP180), geometry, sampling interval, bandwidth, instrument, sample batch | `not_stated` where absent |
| `data_format` | `table` \| `csv` \| `json` \| `raster_figure` \| `vector_figure` \| `text` \| `none` | |
| `values_via` | `native_numeric` \| `digitized` \| `computed` | |
| `digitization_record` | path or `n/a` | axis calibration points, tool and version, control points, error estimate |
| `availability` | `open_download` \| `open_view_only` \| `paywalled_not_acquired` \| `removed` \| `unavailable` | |
| `license` | SPDX or text | governs whether files can be cached in the repo |
| `retrieved_at`, `sha256` | UTC timestamp, 64-hex | for each retrieved file |
| `credibility` | `high` \| `medium` \| `low` | plus `credibility_reason` |
| `usable_for_residuals` | bool | |
| `permitted_use` | `independent_validation` \| `source_conformance` \| `digitization_uncertainty` \| `implementation_crosscheck` \| `support` \| `none` | derived from the class and lineage |
| `status` | `comparable` \| `not_evaluable` \| `unavailable` | |
| `reason` | text | required for `not_evaluable` and `unavailable` |
| `verified_by` | `executor` \| `qc` | QC fills this in during review |

## 6. Comparisons enabled per class, and what stays not_evaluable

| class (and lineage) | possible comparison | evidence level | label in the report |
|---|---|---|---|
| INDEPENDENT_PHYSICAL_MEASUREMENT, `none` | Residuals for the matching quantity under matching conditions (for example 5219 APD or Status M from measured patches, 2383 Status A, spectral transmittance) | V3, partial | "independent measurement residual"; no pass/fail without a tolerance |
| MANUFACTURER_PUBLISHED_MEASUREMENT, numeric, `same_primary_source` | Source-conformance against numbers rather than raster traces | V2 | "manufacturer source-conformance", not physical fidelity |
| MANUFACTURER_PUBLISHED_MEASUREMENT, from a Kodak dataset spektrafilm did not use (for example LAD aims, Status M↔printing-density tables) | Manufacturer cross-check of model behaviour on a quantity spektrafilm was not fitted to | V2+ | "manufacturer cross-check"; still not independent of Kodak |
| DIGITIZED_PUBLISHED_DATA, `same_primary_source` | Agreement between independent digitizers of the same Kodak figure, measured against spektrafilm's legacy CSVs, to estimate digitization uncertainty | V2 | "digitization uncertainty" |
| DERIVED_OR_SIMULATED_DATA | Implementation cross-checks of assumptions: Status M vs printing density, NaN-to-zero handling, masking, print-matrix conventions, and numerical consistency | V1/V2 | "implementation cross-check" |
| any class with `derived_from_spektrafilm` | Software regression only | V1 | never external |
| NOT_COMPARABLE | none | — | recorded with a reason |

A newly computed residual never overwrites or "upgrades" the six historical FS-P4 `not_evaluable` rows. It is reported as a new FS-P6-02 result, and FS-P4 is left as it stands.

**Expected to remain `not_evaluable` unless independent data turns up:** real-film ΔE00 (`B.color.independent_delta_e00`); the full 5219→2383 chain, which needs matched negative and print with printer lights (V4); granularity and MTF, since grain and spatial effects are disabled; 2383 physical fidelity without independent print measurements; absolute spectral dye density, because Kodak's dye curves are peak-normalized and support shape comparison only.

## 7. Roles and independent QC

| role | who | constraint |
|---|---|---|
| Authorizer | Research Director (`REDACTED`) | Decision 1 (2026-11-20); decision 0004 (Decision 0004 public summary, pending merge) |
| Executor | One execution agent on a FilmSimulation-scoped worker, on branch and PR only | Records the candidate SHA, the search log, the register and known limitations in the PR. Migration mode: review is requested in the PR and the CSV status is not changed to `ready_for_review` |
| Independent QC | A separate session, with a separate identity where one is available, in a fresh clone at the exact candidate SHA | Re-runs the register validator and the FS-P6-02 computation, recording actual output. Re-checks the class and lineage of **every** entry that is not `NOT_COMPARABLE`, plus a random sample of at least 20% of the `NOT_COMPARABLE` entries. Re-runs at least 5 logged queries to confirm the hit counts are plausible. Writes `qc/film/FS-P6-0x/<id>.json` in non-public governance archive with `not_evaluable` preserved |
| Disputes | Research Director | Disputes over class or lineage go to the Director. QC must not resolve them by re-labelling |

The QC session must not reuse executor outputs except the submitted commit itself. Given the shared GitHub account, independence is only an asserted property of the session and cannot be proven. Completion is claimed only after approved independent QC of the exact candidate SHA.
