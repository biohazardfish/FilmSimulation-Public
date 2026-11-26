# FilmSimulation

**Experimental spectral film-simulation research, not a finished film-look product.**

FilmSimulation investigates a reproducible, physically informed path from Canon camera RAW through scene-linear ACEScg, a spectral Kodak VISION3 500T (5219) negative model, and a Kodak 2383 print-film model, using a pinned [spektrafilm](https://github.com/andreavolpato/spektrafilm) dependency.

The research records numerical evidence and limitations separately from claims about physical film. Software/reproducibility checks and internal-model comparisons are not evidence that a physical 5219/2383 print has been replicated. Independent real-film validation remains unavailable; end-to-end photographic validation has not been performed. The fair comparable LUT comparison (FS-P5-02) remains blocked.

**Project status:** research prototype. See [Phase V closure](docs/phase5/CLOSURE.md), [public-data comparison](docs/phase6/PUBLIC_DATA_COMPARISON.md), [public governance summary](docs/PUBLIC_GOVERNANCE_SUMMARY.md). Scientific acceptance criteria and `not_evaluable` findings are deliberately preserved.

## Reproduce the research environment

For macOS with Python 3.13 and Git:

```bash
bash scripts/bootstrap_research.sh
PYTHONPATH=src .venv/bin/python scripts/run_experiment.py --smoke-only
PYTHONPATH=src .venv/bin/python -m pytest tests -q
```

The bootstrap checks out pinned spektrafilm commit `3bb2c2d`, downloads the two
official Kodak technical PDFs into ignored local cache from their recorded
official URLs, verifies their pinned SHA-256 values, and installs the research
runtime without unrelated GUI/LUT-creator dependencies. The PDFs are not
redistributed. The smoke gate uses synthetic input. The full-resolution frozen
experiment requires the exact `input/_C5A0880.CR3` file with its recorded
checksum; it is **not included**. Numerical identity across platforms is not
claimed solely by installing dependencies.

**License:** original FilmSimulation software is licensed under GNU GPL v3 or
later; see [LICENSE](LICENSE) and [upstream attribution](docs/LICENSES.md).
Original spektrafilm profiles and profile-derived materials are CC BY-SA 4.0.
Third-party materials retain their own terms.

In the private evidence checkout only, frozen evidence is verified without
being rewritten:

```bash
PYTHONPATH=src .venv/bin/python scripts/verify_frozen_evidence.py --require-private-artifacts
```

The curated public snapshot intentionally excludes the private manifests and
masters required by that command; its reproducibility contract is the bootstrap,
smoke, and pytest sequence above.

Replacing the Round 1 descriptor is not a test operation. It requires the
separate `scripts/regenerate_round1_baseline.py` command and its explicit
frozen-evidence acknowledgement flag.

---

## Frozen first-round experiment

The only input is `input/_C5A0880.CR3`. The experiment pins the external
spektrafilm reference checkout under `upstream/spektrafilm` and uses only
`kodak_vision3_500t` (Kodak VISION3 500T / 5219) and `kodak_2383`.

## Research roadmap

The roadmap is human-directed and machine-rendered from the reviewed
[CSV source](roadmap/filmsimulation_roadmap.csv). Explicit task status—not
dates or commit counts—drives the visual progress. Software correctness,
internal model consistency, and published-reference numerical validation
are separate evidence levels. G4 is Published-Reference Numerical
Validation against available published reference data. It can pass without
a physical laboratory dataset. Missing independent real-film measurements
remain a recorded limitation.

The curated public snapshot excludes the historical PNG/SVG render because it
predates Decision 0006. The reviewed CSV above remains the source of truth.

Render locally without running the film simulation:

```bash
.venv/bin/python render_roadmap.py roadmap/filmsimulation_roadmap.csv
```

## RAW input provenance

The pinned EOS R7 input is Dual Pixel RAW and contains two RAW images. The
FilmSimulation decode uses only LibRaw/rawpy's default Bayer image; auxiliary
dual-pixel data is not used for depth, viewpoint, ghosting, or spectral
estimation. The additive audit is in
[`validation/raw_input_provenance.json`](validation/raw_input_provenance.json)
and does not rewrite the frozen Round 1 outputs.

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_raw_input.py
```

## Published-reference numerical validation

G4 is reproducibly assembled from the existing Phase II step-wedge, spectral,
source-conformance, uncertainty, and provenance artifacts. Non-comparable
published curves remain `not_evaluable`; completing G4 does not claim
experimentally verified physical fidelity.

```bash
PYTHONPATH=src .venv/bin/python scripts/run_published_reference_validation.py
```

## Public-data external comparison (P6)

P6 — Public-Data External Comparison is the authorized research path for
comparing the simulation with external data. It was authorized under Research
Director decision 0004 (2026-11-20), summarized in the
[public governance record](docs/PUBLIC_GOVERNANCE_SUMMARY.md).
Its roadmap definition and public-data evidence are now present on `main`. It searches public data, classifies its
provenance, and makes reproducible numerical comparisons only where the data
is scientifically comparable. `unavailable` and `not_evaluable` are acceptable
outcomes when documented. P6 is independent of P5 closure. Physical film
measurement, equipment purchases, commercial LUT purchases, and paid datasets
are not part of the authorized plan.

## Optional future real-film dataset validator (not currently planned)

`scripts/validate_phase4_dataset.py` checks structure, provenance, Status M/A
usage, spectral coverage, sample mapping, and file hashes for a canonical
measurement dataset. This validator is optional future real-film research
outside the current roadmap. It is not a G4 requirement and does not
calculate a physical-accuracy score. Archived scientific notes for that
dataset live in `docs/phase4/`.

As of 2026-11-20 this real-film route is not currently planned: no physical
measurement is authorized. The validator and its tests are kept unchanged. It
requires an independent physical measurement dataset and does not apply to
P6 public data.

```bash
.venv/bin/python scripts/validate_phase4_dataset.py path/to/dataset
```

Run unit tests:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests -q
```

Run the required synthetic gate:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_experiment.py --smoke-only
```

Run through controlled RAW decoding only:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_experiment.py --decode-only
```

Run the complete full-resolution experiment:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_experiment.py --all
```

Run Round 2 (full-resolution repeat, Kodak source-conformance, comparison and uncertainty):

```bash
PYTHONPATH=src .venv/bin/python scripts/run_experiment.py --round2
```

Round 1 writes `output/manifest.json` and `output/EXPERIMENT_REPORT.md`.
Round 2 writes `output/round2_manifest.json` and `output/ROUND2_REPORT.md`
and does not replace the Round 1 linear EXR. The Round 2 curve check is
source-conformance against Kodak technical-data PDFs, not a measurement of
a physical roll.
