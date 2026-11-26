# Phase II Signal Flow Audit

## 實際執行圖

```text
CR3 --rawpy/LibRaw AHD, as-shot WB, linear ACES2065-1-->
scene-linear ACEScg (AP1/D60)
  -> rgb_in -> rgb_pre -> log_e_film -> cmy_film
                                  |-> negative scan: film channel/base spectral density -> D50 -> XYZ -> ACEScg rgb_out
                                  `-> print exposure: TH-KG3 printer light -> log_e_print -> cmy_print
                                      -> print scan: print channel/base spectral density -> K75P -> XYZ -> ACEScg rgb_out
```

RAW decode、相機矩陣、白平衡及 AP0→AP1 轉換位於 spektrafilm 核心之外；顯示用 sRGB clip/CCTF 也在核心之外。本輪合成資料直接從明確的 scene-linear ACEScg `rgb_in` 開始。

## Tap 語義與本輪數值範圍

| tap | 物理解釋 | 數值尺度／單位 | shape / dtype | −6…+6 EV 實測範圍 | 可逆性／損失 |
|---|---|---|---|---:|---|
| `rgb_in` | 呼叫者提供的scene-linear ACEScg neutral ramp | 相對scene-linear RGB；0 EV定義為0.18，非絕對輻照度 | `[1, 481, 3]` / `float64` | 0.0028125…11.52 | 否；RGB本身不包含唯一光譜 |
| `rgb_pre` | scene-linear ACEScg；由 `np.double` 預處理 | 相對 scene-linear RGB；無絕對輻照度單位 | `[1, 481, 3]` / `float64` | 0.0028125…11.52 | 否；RGB 已丟失光譜同色異譜資訊 |
| `log_e_film` | 5219 三個感光層的相對 log10 exposure | dimensionless relative log10 response，不是 lux-seconds | `[1, 481, 3]` / `float64` | -1.84799…1.80296 | 否；RGB-to-spectrum 重建及三層積分不可逆 |
| `cmy_film` | 扣除每色曲線最小值、經 DIR coupler 後的三通道密度係數 | model channel coefficient；不自動等於 Status M 實測密度 | `[1, 481, 3]` / `float64` | 0.0408198…1.66441 | 否；特性曲線飽和及耦合會丟失資訊 |
| `log_e_print` | 5219 光譜透射後對 2383 三感光層的相對 log10 exposure | dimensionless relative log10 response，不是 lux-seconds | `[1, 481, 3]` / `float64` | -0.932144…0.863431 | 否；光譜積分、printer light及正規化不可逆 |
| `cmy_print` | 2383 parametric characteristic curve 的三通道係數 | model channel coefficient；不自動等於 Status A 實測密度 | `[1, 481, 3]` / `float64` | 0.00191347…3.43797 | 否；曲線飽和不可逆 |
| `rgb_out` | 2383掃描光源下的光譜透射→CIE XYZ→scene-linear ACEScg | scene-linear ACEScg；無 CCTF；可超出0–1 | `[1, 481, 3]` / `float64` | 0.000293976…0.876814 | 否；81波段積分成XYZ再成RGB |
| `rgb_out` (negative scan) | 5219光譜密度在D50下透射→CIE XYZ→scene-linear ACEScg | scene-linear ACEScg；無CCTF | `[1, 481, 3]` / `float64` | 0.00302466…0.441567 | 否；81波段積分成XYZ再成RGB |

所有影像 tap 為 `H×W×3`。合成 ramp 的 H=1、W=481；pipeline `_preprocess` 無條件轉為 float64。必要 metadata 是 RGB primaries、white point、CCTF狀態、profile key/hash、viewing/reference illuminant、曝光正規化及 scanner correction 狀態。

## 來源路徑與轉換

- `runtime/pipeline.py`：拓撲、`np.double`、auto-exposure及 crop/rescale。
- `runtime/stages/filming.py`：ACEScg RGB 經 Hanatos 2025 spectrum LUT與5219 sensitivity積分；乘曝光補償後取 `log10`。
- `model/develop.py`／`model/couplers.py`：特性曲線先扣 per-channel minimum；DIR coupler仍啟用，但 spatial diffusion為零；grain停用。
- `runtime/stages/printing.py`：`channel_density × cmy_film + base_density` 建立81波段光譜密度，`10^-D` 轉透射光，再由2383 sensitivity積分。
- `runtime/stages/scanning.py`：negative branch用5219與D50；print branch用2383與K75P；CIE 1931 2° XYZ後轉ACEScg。
- `utils/conversions.py::density_to_light` 把光譜密度轉成 `10^-D × light`，並把 NaN transmitted samples設為0。這不是插值，而是零光量假設；film/print `channel_density` 分別含 15／19 個 NaN，必須視為資訊缺口和模型選擇。

## 參數狀態

Auto-exposure、print exposure compensation、grain、halation、diffusion、glare、scanner blur/unsharp、black/white correction均關閉；output CCTF及output gamut compression關閉。input gamut compression的固定 xy LUT仍按 Phase I 參數啟用。隨機與空間效果停用，因此本輪主要測的是逐像素光譜／特性曲線模型。
