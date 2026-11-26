# FilmSimulation Round 2

## 這是什麼

Round 2 在不改 `input/_C5A0880.CR3`、不改 `upstream/spektrafilm` tracked 內容的前提下，補上 Round 1 的三個缺口：全解析度重跑、Kodak 官方曲線的 source-conformance，以及同一條 RAW 的顯示對照與模型不確定性。

這不是獨立的真實膠片驗證。spektrafilm profile 本身來自公開 datasheet。官方曲線對得上，只表示 profile 與 Kodak 技術資料在所述對齊下的 source-conformance。專案裡沒有受控實測的 5219/2383 樣片，所以 **不計算、也不宣稱真實膠片 Delta E00**。G4b 維持 insufficient。

## 基準

Round 1 的輸入、profile、上游 commit 與關鍵輸出 hash 在 `docs/round1_baseline.json`。上游 commit 仍是 `3bb2c2d2801ff68b92019cf1dbcbb133d60832bc`。輸入 hash `f3e47c2d9df3bbb07a16c49b6e283dfd787e066a5dc141fa9d42441a644c3780`。

## G3 全解析度重跑

兩次各自解碼並跑完 scene、四個 tap、negative scan、final print。比較的是未壓縮像素 SHA-256。第二次的大圖沒有寫成 EXR。

狀態：**pass**

| stage | match | seconds pass 1 | seconds pass 2 |
|---|---|---:|---:|
| `scene` | True | 1.7 | 2.2 |
| `log_e_film` | True | 2.4 | 2.6 |
| `cmy_film` | True | 3.1 | 3.1 |
| `log_e_print` | True | 242.7 | 246.4 |
| `cmy_print` | True | 258.2 | 240.3 |
| `negative_scan` | True | 253.9 | 254.0 |
| `final_print` | True | 482.7 | 454.2 |

## G4a 官方資料 source-conformance

只使用 Kodak 官方 PDF：

- KODAK VISION3 500T Color Negative Film 5219 / 7219，H-1-5219，March 2026; Revised 3-26，https://www.kodak.com/content/pdfs/motion/KODAK-VISION3-500T-5219-7219-technical-information.pdf，SHA-256 `6d037d8090373ee50d10bedfff3df14777a575dd107c50edcafc7ec5862d0972`
- KODAK VISION Color Print Film 2383 / 3383，H-1-2383，August 2026; Revised 8-26，https://www.kodak.com/content/products-brochures/motion-picture/KODAK-VISION-Color-Print-Film-2383-3383-technical-information.pdf，SHA-256 `a72fa4482ebd891a9ac4a823cafe740e3587c56470f27e4dfd4391f5c3e5a207`

曲線在 PDF 裡是光柵圖，不是矢量路徑。座標來自 OCR 與刻度線，追蹤失敗或通道對不上就標 insufficient，不靠目視填座標。容差在看殘差之前已寫死。

| profile | curve | status | page | reason |
|---|---|---|---:|---|
| `kodak_2383` | characteristic | insufficient | 4 | trace incomplete or off the ink; missing=['R', 'G', 'B']; ink_hit_below_0.90=none |
| `kodak_2383` | spectral_dye_density | insufficient | 5 | trace incomplete or off the ink; missing=['cyan', 'magenta', 'yellow']; ink_hit_below_0.90=none |
| `kodak_2383` | spectral_sensitivity | insufficient | 5 | trace incomplete or off the ink; missing=['cyan', 'yellow']; ink_hit_below_0.90=none |
| `kodak_vision3_500t` | characteristic | insufficient | 3 | densitometer not established as the same quantity: profile=status_M, figure caption=ECN-2 |
| `kodak_vision3_500t` | spectral_dye_density | insufficient | 4 | trace incomplete or off the ink; missing=['magenta']; ink_hit_below_0.90=none |
| `kodak_vision3_500t` | spectral_sensitivity | insufficient | 4 | channel identity is not reliable: magenta trace does not pass its own label |

## G4b

**insufficient**。No independent controlled measurement of a physical 5219 or 2383 sample is in this project. Source-conformance is not real-film error, and no real-film Delta E00 is computed.

## G5 對照與不確定性

三联圖是同一條全解析度 RAW，套與 Round 1 相同的 hard-clip 顯示轉換後縮小的預覽：中性 RAW、virtual negative、5219→2383。LUT：**unavailable**。沒有拿別的 LUT 代替。

光譜重建只跑這個 commit 的 `filming.py` 真正分支：hanatos2025, mallett2019。`rgb_to_raw_aces_idt` 不是可選 pipeline 方法，沒有拿來充數。

模型 spread（scene-linear ACEScg RMSE，hanatos2025 對 mallett2019）：**0.005952**。這是兩種重建之間的差，不是相對真實膠片的誤差。

敏感度矩陣在空間效果關閉後的 160 px 長邊面積縮圖上跑白平衡、負片曝光和 print exposure，另有 yellow printer-light CC。數字在 `validation/uncertainty_metrics.json`。

顯示 hard clip 的全解析度計數在 `validation/display_diagnostics.json`。受影響像素比例 0.018083，被裁切的 component 比例 0.006028。線性 EXR 沒有改寫。平滑高光版本是 `output/5219_to_2383_display_smooth_highlight_shoulder_srgb.jpg`，公式為 `max(x,0)/(1+max(x,0))` 後接 sRGB CCTF，不是 ACES，也不是核心輸出。ACES Output Transform 在這個環境不可用。

## 閘門

- G3：pass
- G4a：逐項，見上表
- G4b：insufficient
- G5：pass

## 重跑

```bash
cd <repo-root>
PYTHONPATH=src .venv/bin/python scripts/run_experiment.py --round2
PYTHONPATH=src .venv/bin/python -m pytest tests -q
```

## 仍然不足

- G4b 沒有獨立受控實測。
- 官方曲線多數無法在通道、密度計或軸校準都成立時完成數值比較；insufficient 的項目沒有被改判成 pass。
- 5219 sensitometric 圖的密度計文字是 ECN-2，profile 是 status_M，同一份 PDF 沒有把兩者寫成同一件事。
- 光譜曲線會交叉，標籤又壓在線上，可靠分通道的追蹤沒有成立。
- 敏感度矩陣是縮圖上的模型響應，不是全解析度，也不是真實膠片誤差。
- 沒有公平的 5219→2383 LUT。
- 平滑顯示仍會把負的 linear sRGB 夾到 0；它不取代 Round 1 的 hard-clip TIFF/JPEG。
