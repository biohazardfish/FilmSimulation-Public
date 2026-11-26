# FilmSimulation 第一輪實驗報告

## 結論

本輪固定使用 Kodak VISION3 500T Color Negative Film 5219（35 mm 產品編號 5219；profile key `kodak_vision3_500t`）與 Kodak VISION 2383（profile key `kodak_2383`）。spektrafilm 核心輸入與輸出均為 scene-linear ACEScg（AP1、D60）；RAW 解碼、核心模擬與顯示轉換分開保存。完整 CR3 流程狀態：**完成**。

## 固定上游與 API

- 倉庫：https://github.com/andreavolpato/spektrafilm
- commit：`3bb2c2d2801ff68b92019cf1dbcbb133d60832bc`
- 套件版本：`0.3.4`
- Python 要求：`~=3.13`
- 實際參數入口：`init_params(film_profile=..., print_profile=...)`
- 實際運算入口：`simulate(image, params, digest_params_first=True, print_timings=False)`
- 中間 tap：`params.taps.collect`，值為 `log_e_film`、`cmy_film`、`log_e_print`、`cmy_print`
- 文件差異：根 README 使用 `create_params`，但本 commit 並未匯出該名稱；原始碼與範例實際使用 `init_params`。

| 材料 | profile key | metadata 版本 | SHA-256 |
|---|---|---:|---|
| Kodak Vision3 500T | kodak_vision3_500t | 0.3.2 | `d7beca68bf16db88dbb7373fd13a6a1150a57a911a54bb0309a760a6f9883329` |
| Kodak Vision 2383 | kodak_2383 | 0.3.2 | `eb7fdfa3b75a909bf5c400802f7401160c8017ed1ac3e8e0d1c8448d56fbe184` |

## RAW 與色彩邊界

RAW 由 rawpy/LibRaw 以 AHD、相機 as-shot 白平衡、16-bit linear ACES2065-1、`no_auto_bright=True`、`gamma=(1,1)` 解碼；不做去噪、鏡頭修正、Film Look、S-curve、顆粒、halation、創意調色或顯示 gamma。其後由 colour-science 將 linear ACES2065-1（AP0、D60）轉為 linear ACEScg（AP1、D60），不套 CCTF、不裁切 scene-linear 值。相機為 Canon EOS R7，ISO 800、1/200 s、f/5.6；as-shot 色溫 5213 K、RGGB `1808 1024 1024 1584`。raw sensor 為 7128×4732，LibRaw 有效輸出為 6984×4660，相機建議 crop 為 6960×4640；黑位 `[2047, 2047, 2047, 2047]`、相機每通道白位 `[13660, 13660, 13660, 13660]`、容器白位 `16383`。解碼陣列 `[4660, 6984, 3]`，像素 hash `6162702b301f4b620a5828a1aeb4f5edf15509d74086a4ef03105a7a65039ccc`。

顯示檔另行將 linear ACEScg 轉 linear sRGB，僅為顯示範圍硬裁切至 [0,1]，最後套 sRGB CCTF；**沒有 tone mapper**。這一階段不屬於 spektrafilm 核心。

## 固定模擬設定

負片自動曝光關閉、曝光補償 0 EV；印片曝光補償關閉、印片曝光 1.0；使用上游資料庫的 500T→2383 中性濾片。Grain、halation、glare、diffusion、鏡頭 blur、scanner correction/unsharp 均關閉；所有隨機與空間效果停用。非空間 DIR coupler 化學交互仍保留，但空間 diffusion 為 0。上游輸入 spectral-locus gamut compression 保留並記錄；輸出 gamut/lightness compression 關閉，使核心輸出維持未套顯示映射的 linear RGB。

完整參數見 `intermediate/fixed_parameters.json`。

## 環境

- Python：3.13.15 (main, Aug  5 2026, 12:25:43) [Clang 21.0.0 (clang-2100.1.1.101)]
- LibRaw：0.22.0
- 安裝範圍：spektrafilm runtime dependencies only; GUI/LUT-creator dependencies intentionally not installed
- OpenImageIO: 3.1.19.0
- Pillow: 12.3.0
- colour-science: 0.4.7
- exiv2: 0.18.1
- lensfunpy: 1.18.0
- matplotlib: 3.11.2
- numba: 0.68.1
- numpy: 2.5.5
- pyfftw: 0.15.1
- pytest: 9.2.0
- rawpy: 0.26.1
- scikit-image: 0.26.0
- scipy: 1.18.1
- spektrafilm: 0.3.4

## 測試與驗收

- 上游 runtime/core 測試：189 passed、4 failed。失敗包含一個測試仍期待不存在的 `GrainParams.mult_usm_amount`，以及三個 committed regression baseline 與目前程式碼不一致。未修改上游、未重生 baseline。
- 本實驗 synthetic smoke：**pass**。指定 profiles 可載入、完整負片與印片流程可執行、所有 tap 尺寸/通道正確、無 NaN/Inf、重跑 bit-exact。
- G1 scene-linear 編碼及 primaries 明確：**通過**
- G2 指定 500T/5219 與 2383 從指定上游載入：**通過**
- G3 同一輸入與設定可重現：**通過（合成完整流程 bit-exact；CR3 解碼曾重跑且像素 hash 相同）**。全解析度 spektrafilm end-to-end 沒有再做第二次完整重跑，這個較窄的證據缺口保留在限制中。
- G4 灰階 ramp 與曝光階梯可解釋：**通過**（見 `output/validation_curves.png` 與 `intermediate/smoke_test.json`）
- G5 負片、印片、顯示轉換分階段：**通過**

## 產物

所有產物的共同 provenance 在 `output/manifest.json`；EXR 另含上游 commit、輸入/profile hash、tap/domain 與色彩空間標記。

- `intermediate/cmy_film.exr` — 367864773 bytes — `fd4ef8351886fd3c62be1139a416b217ed36fd8652fcd12cbfb7970ad43f4a8f`
- `intermediate/cmy_print.exr` — 367047054 bytes — `71a1d9dc89f7ec61b0853f7b8ed80f1479e9ede1f7e0f603b247c5898cfcc420`
- `intermediate/diagnostics/README.md` — 604 bytes — `0b93fdfb87cd35aded7a8dafa32d94cb028fcb531f9e43b40d9f3c1433f2f2a7`
- `intermediate/environment.json` — 761 bytes — `05d5547041ff8c314351cc6500856638accd7f1747313cb1bb801f6fe635e0e0`
- `intermediate/final_display_transform.json` — 426 bytes — `4fdb96ee21570df8d008dea9d812f243e9225084d858b713dacf3d17765de325`
- `intermediate/fixed_parameters.json` — 9357 bytes — `08b1cf63781ceb490d54a77b674b782092c022e601ae7c284b17ad62a0ec47c2`
- `intermediate/log_e_film.exr` — 372523296 bytes — `5df041c1c7b7a6fe0bb8533227108b304cceecdf0365b89b52e9865d163fd45b`
- `intermediate/log_e_print.exr` — 371936421 bytes — `1ceccaa69efc808301bbf0c7c1eb6e244752e2d0769752517b8486821c6962d6`
- `intermediate/negative_display_transform.json` — 422 bytes — `1690f20654946f05d919ad58256d6d988525430f2df4e33533c61cd88c3dfb93`
- `intermediate/raw_metadata.json` — 3822 bytes — `aab75d9c640351562959ebe0acda4c6919ecd46d0f71fd0d53e35432b7d2a70b`
- `intermediate/scene_linear_acescg.exr` — 368878442 bytes — `20fc320566362449e100c0ed826ebdd159640cee2405987f050d58d45660b1f7`
- `intermediate/smoke_test.json` — 5741 bytes — `147a65e8cea5da534059effebede7d2598f07ce1cef21984e2b3e54da4968267`
- `intermediate/upstream_inspection.json` — 5999 bytes — `e88fefbe591996589160efdf26ddcef30e190eca0056a05df60edb9b8fbd9100`
- `output/5219_to_2383_display_srgb.jpg` — 12577560 bytes — `4a85e8460ef1742beddf9cb7ee9139ced6b7d3e246f08cdc36670e6eb41930cb`
- `output/5219_to_2383_display_srgb.tif` — 172749519 bytes — `66f44544742061c5cf54b46df51065d13fe2f0bd4a47ed8de3f2c8b8a6c09db2`
- `output/5219_to_2383_linear_acescg.exr` — 372568869 bytes — `ddf2af6303fe3c84a8128bd4927f1039b31aa3aade6aae8bb9022841b42f8532`
- `output/validation_curves.png` — 258563 bytes — `047df954defa5a28d48594aa2fcdff50fd1f46823b4edc08a3be4e91c838965c`
- `output/virtual_negative_preview_srgb.jpg` — 6468270 bytes — `1187a9a7e5e54fbed0b80b640b3d33e56beb3f7f78c1875b4eb1444a050ba59b`
- `output/virtual_negative_scan_linear_acescg.exr` — 365139872 bytes — `98f551d0d5bfe6c69d78eb597b479f5429535c3fd47cedcd890e71e2da1e5483`

## 完整重跑

```bash
cd <repo-root>
PYTHONPATH=src .venv/bin/python scripts/run_experiment.py --all
```

只跑基準：

```bash
PYTHONPATH=src .venv/bin/python scripts/run_experiment.py --smoke-only
```

## 授權、限制與資料缺口

spektrafilm 程式碼依上游聲明為 GPLv3 / GPL-3.0-or-later；profiles 為 Andrea Volpato 建立、依 CC BY-SA 4.0 授權，需保留作者、專案連結、授權與修改說明。詳見 `docs/LICENSES.md` 與未修改的 `upstream/spektrafilm/SPEKTRAFILM_LICENSE.txt`。本實驗將 spektrafilm 作為固定版本的外部研究依賴，沒有修改 profiles。

公開 profiles 是由 datasheet 與公開科學資料處理而得，不是任何一卷實體膠片的完整測量真值。沒有同場景、受控條件的真實 5219/2383 對照，因此本輪不宣稱相對真實膠片的 ΔE00，也不宣稱物理準確度。RAW 色彩取決於 LibRaw 的 Canon EOS R7 相機矩陣與 as-shot metadata；沒有獨立 DNG/光譜相機校正或拍攝現場光源測量。顯示檔的 hard clip 只為 SDR 預覽，不能代表完整 scene-linear 動態範圍。完整全解析度 spektrafilm end-to-end 只成功執行一次；G3 的 bit-exact 證據來自合成完整流程，CR3 重跑證據只到 RAW 解碼像素 hash。
