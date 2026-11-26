# Licensing and attribution

## Original FilmSimulation integration

Original FilmSimulation software in this repository is licensed under **GPL-3.0-or-later**
(the full GNU GPLv3 text is at [../LICENSE](../LICENSE)). This is a project-level
license for original software only. It does not relicense third-party materials.

## Pinned upstream source and profiles

This experiment uses the exact external research dependency at:

- spektrafilm by Andrea Volpato
- https://github.com/andreavolpato/spektrafilm
- commit `3bb2c2d2801ff68b92019cf1dbcbb133d60832bc`

The upstream Python code declares GPLv3 / GPL-3.0-or-later in
`upstream/spektrafilm/pyproject.toml` and `upstream/spektrafilm/CITATION.cff`.
This experiment does not modify that upstream checkout.

The two pinned profiles `kodak_vision3_500t` and `kodak_2383` are by Andrea
Volpato and licensed CC BY-SA 4.0. Redistribution and derivatives must retain
the author, the canonical project link, the license, and a modification notice
where applicable. The complete profile license at the pinned upstream commit is
[SPEKTRAFILM_LICENSE.txt](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/SPEKTRAFILM_LICENSE.txt)
and is also present after bootstrap at
`upstream/spektrafilm/SPEKTRAFILM_LICENSE.txt`.

This repository does not redistribute the original profile JSON files, but it
does retain direct serialized encodings and profile-derived visual evidence,
including `intermediate/fixed_parameters.json`,
`output/phase2/fixed_parameters.json`, `output/phase2/spectral_profiles.png`,
`output/phase2/sensitometry_samples.csv`,
`output/phase2/sensitometry_taps.npz`,
`output/phase2/sensitometric_response.png`, and
`output/validation_curves.png`. Treat those profile-derived materials as
CC BY-SA 4.0 material by Andrea Volpato, sourced from the pinned spektrafilm
commit above. FilmSimulation did not modify the source profiles; it serialized
their runtime parameters and generated the listed plots.

Other generated experiment data and images identify the exact source profiles
by key and SHA-256 in `output/manifest.json`. The wrapper is maintained as an
integration layer around the pinned external dependency; this note does not
attempt to replace or narrow upstream terms. The repository-level GPL license
applies only to original FilmSimulation software and does not relicense these
separately identified CC BY-SA materials.
