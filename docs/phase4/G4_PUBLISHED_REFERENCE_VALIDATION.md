# G4 Published-Reference Numerical Validation

## 判定

狀態：**complete_with_limitations**。`FS-P4-03` 的離線數值驗證已完成；不需要實體膠片資料集。這個完成狀態只代表可重現性、參數 provenance、模型內部一致性與已發表參考比較均已明示，**不代表經實驗驗證的物理真實度**。

## 模擬 step-wedge

固定 neutral ramp 共 481 階，範圍 -6 至 +6 EV，0 EV 定義為 scene-linear 0.18。下列數字是模型通道係數，不是 Status M／A 實測密度。

| material | channel | min | max | straight-line gradient | monotonic violations |
|---|---|---:|---:|---:|---:|
| film | R | 0.048300 | 1.538316 | 0.465827 | 0 |
| print | R | 0.004143 | 3.437973 | 4.034067 | 0 |
| film | G | 0.052533 | 1.413235 | 0.407442 | 0 |
| print | G | 0.001913 | 2.877261 | 2.962557 | 0 |
| film | B | 0.040820 | 1.664412 | 0.515037 | 0 |
| print | B | 0.003247 | 2.636810 | 3.108530 | 0 |

## Kodak published-reference comparison

| profile | curve | status | reason |
|---|---|---|---|
| `kodak_2383` | characteristic | not_evaluable | trace incomplete or off the ink; missing=['R', 'G', 'B']; ink_hit_below_0.90=none |
| `kodak_2383` | spectral_dye_density | not_evaluable | trace incomplete or off the ink; missing=['cyan', 'magenta', 'yellow']; ink_hit_below_0.90=none |
| `kodak_2383` | spectral_sensitivity | not_evaluable | trace incomplete or off the ink; missing=['cyan', 'yellow']; ink_hit_below_0.90=none |
| `kodak_vision3_500t` | characteristic | not_evaluable | densitometer not established as the same quantity: profile=status_M, figure caption=ECN-2 |
| `kodak_vision3_500t` | spectral_dye_density | not_evaluable | trace incomplete or off the ink; missing=['magenta']; ink_hit_below_0.90=none |
| `kodak_vision3_500t` | spectral_sensitivity | not_evaluable | channel identity is not reliable: magenta trace does not pass its own label |

六組曲線均維持 `not_evaluable`；沒有把缺失 residual 當成零誤差或 pass。

## 光譜 sensitivity 與 dye-density arrays

兩個 profiles 均覆蓋 380–780 nm、81 個波長點。NaN 統計如下：

| profile | densitometer | sensitivity NaN | channel-density NaN | base-density NaN |
|---|---|---:|---:|---:|
| kodak_vision3_500t | status_M | 0/243 | 15/243 (6.17%) | 4/81 (4.94%) |
| kodak_2383 | status_A | 0/243 | 19/243 (7.82%) | 0/81 (0.00%) |

Runtime 將相應 transmitted-light NaN samples 設為零光量；這是已量化的模型假設，不是實測補值。

## 可重現性與模型敏感度

- 合成 taps 全部 deterministic：`True`。
- 全解析度重跑：`pass`。
- 固定參數 SHA-256：`f2dd314b27d87d5bedd2728c943c29932545a7057f265c7a05d95108a33e4d28`。
- Hanatos 2025 對 Mallett 2019：RMSE `0.005952126`、max abs `0.068574250`；這只是 spectral reconstruction model spread。
- 輸入是 DPRAW、包含 `2` 個 RAW images；FilmSimulation 只使用預設 image，未使用 auxiliary dual-pixel data。

## 未支持假設與限制

- `published_curve_digitization` — **not_evaluable**：Published raster traces lack sufficient channel, axis, or measurement-definition comparability.
- `spectral_nan_to_zero_light` — **quantified_model_assumption**：Runtime maps NaN transmitted-light samples to zero; this is not measured interpolation.
- `rgb_to_spectrum_non_uniqueness` — **quantified_model_sensitivity**：Difference between runnable reconstruction methods is not error relative to real film.
- `dpraw_auxiliary_image_unused` — **not_evaluable**：The effect of unused phase/depth information on the scene-linear input was not evaluated and is not spectral evidence.
- `independent_real_film_measurement` — **unavailable_limitation**：No independent controlled measurement of a physical 5219 or 2383 sample is in this project. Source-conformance is not real-film error, and no real-film Delta E00 is computed.

## Evidence boundary

本 gate 沒有獨立真實 5219／2383 樣片、matched capture 或真實膠片 Delta E00。模型 consistency 與 published-reference source conformance 不得改稱 physical fidelity。
