# Phase II Status

## Completed

- Source-grounded signal-flow audit and negative／print branch graph。
- −6…+6 EV ACEScg sensitometric ramp、all taps、numerical plots及V1 metrics。
- Kodak reference provenance及可比較性判定。
- Spectral profile／NaN audit與外部CIELAB validation interface。
- Small-scale performance、memory、determinism及1024 whole-vs-tile comparison。
- Required six documents、machine-readable metrics及artifact manifest。
- Phase I／Round 2 integrity：`True`。
- Project tests：20 passed in 1.89s；command `PYTHONPATH=src .venv/bin/python -m pytest tests -q`。
- Pinned upstream core tests：623 passed, 4 failed, 1 skipped, 10 warnings in 5.73s；四個failure分類為既有baseline／stale-test findings。

## Failed

- 無新增V1 failure。

## Blocked / NOT EVALUABLE

- `A.film.R.dir_active_deviation`
- `A.film.G.dir_active_deviation`
- `A.film.B.dir_active_deviation`
- `B.kodak.kodak_2383.characteristic`
- `B.kodak.kodak_2383.spectral_dye_density`
- `B.kodak.kodak_2383.spectral_sensitivity`
- `B.kodak.kodak_vision3_500t.characteristic`
- `B.kodak.kodak_vision3_500t.spectral_dye_density`
- `B.kodak.kodak_vision3_500t.spectral_sensitivity`
- `B.kodak.kodak_vision3_500t.granularity`
- `B.kodak.kodak_vision3_500t.modulation_transfer`
- `B.kodak.kodak_2383.granularity`
- `B.kodak.kodak_2383.modulation_transfer`
- `B.color.independent_delta_e00`

## Deferred

- 無；所有請求尺寸均完成。

四個Phase I已知upstream failures仍保留為既有finding；未修改upstream或regression baselines。直接從repo root無限制執行`pytest -q`會收集缺少qtpy的GUI tests，屬測試範圍／環境問題；正式命令固定為`pytest tests -q`。
