# 已封存：可選的未來 5219／2383 step-wedge 研究筆記

> **狀態：目前不在計畫中（not currently planned），2026-11-20。** 本筆記保留為封存研究文件。
> 依 Research Director 2026-11-20 決定，實體膠片量測不屬於目前授權的研究計畫，
> 目前沒有指定執行者，亦不授權購買膠片、器材、商業 LUT 或付費資料集。目前授權
> 的外部比較路徑是 P6 Public-Data External Comparison（由另一個 roadmap PR 定義）。
> 治理紀錄：decision 0004 (Decision 0004 public summary, pending merge)。本標註以下
> 的內容未修改。

本筆記在目前 Roadmap 之外。它不是 G4，也不服務目前的 `FS-P4-03`。G4 是
Published-Reference Numerical Validation，以已發表參考資料做數值驗證；完成
G4 不需要本筆記描述的實體資料集。缺獨立實測只記為限制。

本筆記保留量測鏈、sample ID、canonical dataset 與 validator 的科學要求，供
日後若另行研究時使用。它不是 matched photographic V4。取得一份資料集也不能
單獨宣稱模型已經物理準確。物理準確度的 pass／fail tolerance 不在本筆記內；
未另行審定 tolerance 時，只可報告測量值、殘差與不確定度。

## 證據邊界

不得用掃描圖、目視比較、generic LUT、模型內部 `log_e_*` 或 `cmy_*` 代替獨立
實測。`log_e_*` 是相對模型曝光；`cmy_*` 是模型通道係數，不是 Status M／A
實測密度。

## 若日後進行量測時的固定量測鏈

1. 使用同一批次的 35 mm KODAK VISION3 500T 5219；記錄產品、批次、卷／短片、
   保存與處理條件。
2. 使用有有效校準紀錄的 3200 K sensitometer 及可追溯 step wedge。保存每階
   nominal 與 measured exposure、單位、儀器型號／序號、calibration ID／日期及
   exposure run ID。
3. 以標準 ECN-2 處理 5219。保存 process run ID、實際時間、溫度、化學品批次、
   偏差及操作紀錄。
4. 對 5219 每個可追溯 step sample 量測 Status M RGB density 及原生光譜透射。
5. 使用同一批次的 KODAK VISION Color Print Film 2383。每個 print sample 必須可
   反查 source negative sample；完整記錄 printer-light R／G／B、print exposure、
   單位、設備與 run ID。
6. 以 ECP-2D 處理 2383，保存與 ECN-2 同等層級的 process log。
7. 對 2383 每個可追溯 step sample 量測 Status A RGB density 及原生光譜透射。
8. 光譜資料必須以儀器原生 sampling 保存並覆蓋 380–780 nm；記錄 sampling
   interval、spectral bandwidth、儀器與 calibration。任何 resampling 只能在保留
   原生資料後另行產生。

本筆記不規定 step 數、strip 數、repeat 數或期限，也不把這些項目設成目前任務。

## Sample ID 與追溯

- `run_id`：一次完整曝光／處理／量測鏈的唯一 ID。
- `sample_id`：實體可回收樣片的唯一 ID，不可在 5219 與 2383 間重用。
- `strip_id`：母 strip ID；`step_id`：step wedge 階位；`repeat_id`：獨立量測重複。
- 5219 與 2383 分別使用固定 `batch_id`；所有資料列必須與 manifest 一致。
- `print_map.csv` 必須把每個 2383 `print_sample_id` 對回一個 5219
  `negative_sample_id`，並附 printer lights 與 print exposure。
- 若資料集記錄樣片交接，須能以 sample ID 追溯儲存條件、異常與缺失；照片只作
  追溯證據，不作密度量測。

## 必須交付的 machine-readable 資料

每個 run 使用 `validation/phase4/templates/` 定義的 canonical dataset：

- `manifest.json`：材料批次、設備、校準、ECN-2／ECP-2D process、printer 與檔案
  SHA-256。
- `density.csv`：long-form Status M／A RGB density。
- `print_map.csv`：negative-to-print mapping 與 printer-light provenance。
- `spectral_transmittance.csv`：儀器原生 wavelength／transmittance rows。

原始輸出須原封保存；轉換至 canonical dataset 時要記錄來源檔 hash、轉換程式
版本與任何單位轉換，不可覆蓋原始檔。

檢查指令：

```bash
.venv/bin/python scripts/validate_phase4_dataset.py path/to/dataset
```

## 日後資料集的接收條件

一份資料集只有在以下各項全部成立時才可進入數值分析。拒絕該資料集不會使 G4
未通過：

- 5219 與 2383 批次、所有 sample IDs、step IDs 和 print mapping 可閉合追溯。
- 3200 K exposure、ECN-2、printer lights、ECP-2D 均有實際 run log。
- 5219 使用 Status M，2383 使用 Status A；儀器校準 ID／日期與不確定度齊全。
- 光譜原生資料覆蓋 380–780 nm，且沒有只交圖像、平滑圖或已丟失原始 sampling 的
  匯出。
- canonical files 通過 `scripts/validate_phase4_dataset.py`，CSV hashes 與 manifest
  一致。

任何缺項均不得以零值、插值、模型輸出或肉眼抄點補上。應保留原資料並記錄拒收
理由。

## 不適用於目前 Roadmap 的情況

- 沒有實體資料集：G4 仍依已發表參考完成，缺獨立實測只記為限制。
- 材料批次、校準或 process provenance 不可追溯：該 run 不能稱為獨立實測。
- negative-to-print mapping 或 printer lights 遺失：該資料集不能做 2383 closure 分析。
- Status M／A 或 380–780 nm 原生光譜不可取得：不得用掃描或 LUT 代替。
- 未經人審定 tolerance：只可報告測量值、殘差與不確定度，不可判定物理準確度
  pass／fail。
