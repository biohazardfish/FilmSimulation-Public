# 已封存：可選的未來真實膠片研究

> **狀態：目前不在計畫中（not currently planned），2026-11-20。** 本文件保留為封存研究文件。
> 依 Research Director 2026-11-20 決定，實體膠片量測不屬於目前授權的研究計畫，
> 目前沒有指定執行者，亦不授權購買膠片、器材、商業 LUT 或付費資料集。目前授權
> 的外部比較路徑是 P6 Public-Data External Comparison（由另一個 roadmap PR 定義）。
> 治理紀錄：decision 0004 (Decision 0004 public summary, pending merge)。本標註以下
> 的內容未修改。

本文件在目前 Roadmap 之外，只保存日後若另行研究真實膠片時可參考的科學要求。
它不是 G4，也不是目前任何 gate 或下一步。

G4 是 Published-Reference Numerical Validation：以已發表參考資料評估模擬
step-wedge、光譜敏感度與染料密度、數值可重現性、參數 provenance，以及可行時
的未支持假設，並把模型一致性與未經實驗驗證的物理真實度分開。完成 G4 不需要
實體量測資料集。缺獨立實測只記為限制。

下表與 `scripts/validate_phase4_dataset.py`、`validation/phase4/templates/`
描述同一套資料結構。Validator 只檢查結構、provenance、Status M／A、光譜覆蓋、
sample mapping 與檔案 hash，不計算物理準確度分數，也不判定 G4。

## 科學要求

| 項目 | 科學要求 | 要求證據／交付 |
|---|---|---|
| 5219／2383 | 同批次 35 mm 5219 及同批次 2383，並保留 batch ID | stock／batch／sample 清單 |
| Sensitometer | 校準 3200 K sensitometer 與可追溯 step wedge | 型號、序號、calibration ID／日期、每階 nominal／measured exposure、單位、不確定度 |
| ECN-2 | 標準 ECN-2 並提供實際 run log | time、temperature、chemistry lot、run ID、偏差 |
| Printing | 每個 5219 step 可追溯到 2383 sample | printer 型號／run ID、RGB printer lights、print exposure／unit、negative-to-print mapping |
| ECP-2D | ECP-2D 並提供實際 run log | time、temperature、chemistry lot、run ID、偏差 |
| Status M | 5219 的 RGB Status M density | 儀器型號／序號、calibration ID／日期、不確定度、原始表格 |
| Status A | 2383 的 RGB Status A density | 儀器型號／序號、calibration ID／日期、不確定度、原始表格 |
| Spectral | 5219／2383 原生 spectral transmittance 覆蓋 380–780 nm | 儀器、calibration、native sampling interval、bandwidth、不確定度、原始 wavelength／transmittance rows |
| Data | machine-readable 原始資料，不只 PDF／圖像 | CSV／JSON／儀器原始檔、欄位與單位說明 |
| Provenance | 可保存量測 provenance 與檔案 hash | 設備／calibration／process 紀錄 |
| Custody | sample ID 全程可追溯 | custody log、異常及缺失清單 |

## 資料邊界

掃描圖、目視比較、其他 LUT 或模型內部 `log_e_*`／`cmy_*` 都不能代替獨立實測。
`log_e_*` 是相對模型曝光；`cmy_*` 是模型通道係數，不是 Status M／A 實測密度。
本表不設定目前任務，也不把缺項記成 G4 未通過。
