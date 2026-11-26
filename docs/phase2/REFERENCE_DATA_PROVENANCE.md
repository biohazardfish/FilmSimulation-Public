# Phase II Reference Data Provenance

## 固定實作與 profiles

- spektrafilm commit：`3bb2c2d2801ff68b92019cf1dbcbb133d60832bc`；套件版本0.3.4；Python要求 `~=3.13`。
- 5219／500T profile key `kodak_vision3_500t`：`d7beca68bf16db88dbb7373fd13a6a1150a57a911a54bb0309a760a6f9883329`。
- 2383 profile key `kodak_2383`：`eb7fdfa3b75a909bf5c400802f7401160c8017ed1ac3e8e0d1c8448d56fbe184`。
- 程式碼依 upstream 聲明為 GPLv3／GPL-3.0-or-later。profiles及直接衍生編碼為 Andrea Volpato 的 CC BY-SA 4.0，需作者、專案連結、授權及修改註記。本輪不修改 profile。
- Profile metadata只概括表示資料來自 datasheets／公開科學資料，未逐個array提供原始量測檔、digitization控制點、擬合殘差或樣片批次。因此不能把 profile 視為某卷實體膠片的完整量測真值。

## Kodak來源

| product | source | SHA-256 | 資料性質 |
|---|---|---|---|
| 5219 | [cache/kodak_official/vision3_500t_5219_7219_H-1-5219.pdf](https://www.kodak.com/content/pdfs/motion/KODAK-VISION3-500T-5219-7219-technical-information.pdf) | `6d037d8090373ee50d10bedfff3df14777a575dd107c50edcafc7ec5862d0972` | Kodak官方技術資料；曲線是光柵圖 |
| 2383 | [cache/kodak_official/vision_2383_3383_H-1-2383.pdf](https://www.kodak.com/content/products-brochures/motion-picture/KODAK-VISION-Color-Print-Film-2383-3383-technical-information.pdf) | `a72fa4482ebd891a9ac4a823cafe740e3587c56470f27e4dfd4391f5c3e5a207` | Kodak官方技術資料；曲線是光柵圖 |

5219 PDF條件包括3200 K、ECN-2及圖中所述densitometry；2383包括ECP-2D／Status A等圖示條件。Datasheet明示曲線代表指定條件下的production coatings，而非特定一卷或規格保證。既有自動流程從PDF raster XObject、OCR刻度及ink trace取樣；沒有可靠追蹤時不以肉眼補點。

## 可比較性判定

| metric | status | reason |
|---|---|---|
| `B.kodak.kodak_2383.characteristic` | not_evaluable | trace incomplete or off the ink; missing=['R', 'G', 'B']; ink_hit_below_0.90=none |
| `B.kodak.kodak_2383.spectral_dye_density` | not_evaluable | trace incomplete or off the ink; missing=['cyan', 'magenta', 'yellow']; ink_hit_below_0.90=none |
| `B.kodak.kodak_2383.spectral_sensitivity` | not_evaluable | trace incomplete or off the ink; missing=['cyan', 'yellow']; ink_hit_below_0.90=none |
| `B.kodak.kodak_vision3_500t.characteristic` | not_evaluable | densitometer not established as the same quantity: profile=status_M, figure caption=ECN-2 |
| `B.kodak.kodak_vision3_500t.spectral_dye_density` | not_evaluable | trace incomplete or off the ink; missing=['magenta']; ink_hit_below_0.90=none |
| `B.kodak.kodak_vision3_500t.spectral_sensitivity` | not_evaluable | channel identity is not reliable: magenta trace does not pass its own label |
| `B.kodak.kodak_vision3_500t.granularity` | not_evaluable | the deterministic Phase II configuration disables grain/spatial effects and exposes no model quantity measured under the Kodak aperture/MTF conditions |
| `B.kodak.kodak_vision3_500t.modulation_transfer` | not_evaluable | the deterministic Phase II configuration disables grain/spatial effects and exposes no model quantity measured under the Kodak aperture/MTF conditions |
| `B.kodak.kodak_2383.granularity` | not_evaluable | the deterministic Phase II configuration disables grain/spatial effects and exposes no model quantity measured under the Kodak aperture/MTF conditions |
| `B.kodak.kodak_2383.modulation_transfer` | not_evaluable | the deterministic Phase II configuration disables grain/spatial effects and exposes no model quantity measured under the Kodak aperture/MTF conditions |

這些比較最多是V2 calibration-data agreement：profile本來就由公開datasheet資料處理而來，並非獨立驗證。Peak-normalized dye curve只能驗證形狀，不能驗證絕對光譜密度。現有可靠資料不足以計算真實膠片ΔE00、granularity或MTF模型誤差。

## Profile光譜資料範圍

- 5219：81個波長點；log sensitivity NaN=0；channel density NaN=15；base density NaN=4。
- 2383：81個波長點；log sensitivity NaN=0；channel density NaN=19；base density NaN=0。

RGB-to-spectrum重建並不唯一；Hanatos 2025與Mallett 2019的差只表示模型選擇敏感度。相機光譜敏感度與5219實際感光度並未由這張CR3的RGB值恢復，故不能把RGB重建當成實際入射光譜量測。
