# Phase V Evidence-Level Closure (FS-P5-03)

## 判定

**狀態：complete_with_limitations。** 本文件凍結當前 FilmSimulation 研究輪次（Round 1／2 與 main 上既有 Phase I–V 證據）的分級結論。它不宣稱經實驗驗證的物理真實度，也不把缺失的獨立實測或公平 LUT 升格為通過條件。

本 closure **僅整合既有產物**；未重跑昂貴全流程、未修改 acceptance criteria、未合併 P6 分支。

## 證據分級定義

來源：`docs/phase2/METRICS.json` 之 `evidence_levels`。

| 級別 | 含義 | 本輪是否達成可宣稱結論 |
|---|---|---|
| **V1** | 計算一致性、內部模型、可重現性 | 是（有邊界） |
| **V2** | 已發表參考／來源一致性（非獨立） | 審計完成；可比較殘差多數 **not_evaluable** |
| **V3** | 獨立物理量測 | **不可得** — 記為限制，非 blocked |
| **V4** | 端到端攝影驗證 | **未評估** |

軟體正確性、內部模型一致性、已發表參考比較、實驗物理真實度 **必須分開表述**。

---

## 1. 軟體正確性（Software）

| 項目 | 狀態 | 證據 |
|---|---|---|
| 專案測試 | pass | 20 passed（`output/phase2/test_results.json`；命令 `PYTHONPATH=src .venv/bin/python -m pytest tests -q`） |
| Upstream core | 623 passed；4 known failures；1 skipped | 分類為既有 findings，未改 upstream／baselines（`docs/phase2/PHASE2_STATUS.md`） |
| 全解析度決定性（G3） | pass | 兩次解碼並跑完整流程；各 stage 像素 hash 一致（`output/ROUND2_REPORT.md`） |
| Round 1／2 輸入完整性 | 固定 | 輸入 hash、upstream commit `3bb2c2d…`、profile hashes（`docs/round1_baseline.json`、`output/ROUND2_REPORT.md`） |

**結論：** 在固定輸入與 pinned upstream 下，管線可重現且專案測試通過。這是 **軟體／工程證據**，不是膠片物理誤差。

---

## 2. 內部模型一致性（Internal model, V1）

來源：`docs/phase2/METRICS.json`（42 metrics）。

| 統計 | 數值 |
|---|---:|
| pass | 28 |
| fail | 0 |
| not_evaluable | 14 |
| V1 指標 | 31 |
| V2 指標 | 10 |
| V3 指標 | 1（`B.color.independent_delta_e00`，not_evaluable） |

重點保留項（不升格為 pass）：

- DIR-active 相關三項：`not_evaluable`（無外部容差；非 Status M 實測密度）。
- 階梯響應：481 階模擬 ramp 單調、finite；量為 **模型通道係數**（`docs/phase4/G4_PUBLISHED_REFERENCE_VALIDATION.md`）。
- 光譜方法敏感度：Hanatos 2025 vs Mallett 2019，scene-linear ACEScg RMSE **0.005952**，max abs **0.068574** — **模型選擇 spread**，非真實膠片誤差（`validation/uncertainty_metrics.json`）。
- Profile 光譜 NaN：5219 channel density 6.17% NaN、base 4.94%；2383 channel 7.82%；runtime 將 NaN transmitted-light **設為零** — 已量化假設（G4 文檔）。

敏感度矩陣與 printer-light 掃描在 160 px 長邊縮圖、空間效果關閉下取得（`validation/uncertainty_metrics.json`）；**不是**全解析度真實膠片誤差。

**結論：** 內部一致性與可運行分支行為已有機器可讀證據；**不得**解讀為 V3／V4 物理驗證。

---

## 3. 已發表參考比較（Published reference, V2）

來源：`docs/phase4/G4_PUBLISHED_REFERENCE_VALIDATION.md`、`docs/phase2/REFERENCE_DATA_PROVENANCE.md`、`output/ROUND2_REPORT.md`（G4a）。

Kodak 官方 PDF 已封存（SHA-256 見 provenance 文檔）。六組曲線自動 trace **均為 not_evaluable**（Round 2 報告表中記為 insufficient，語義與 G4 not_evaluable 一致）；**未**將缺失 residual 當零誤差或 pass。

| profile | curve | 狀態 | 摘要原因 |
|---|---|---|---|
| kodak_2383 | characteristic | not_evaluable | trace 不完整；缺 R/G/B |
| kodak_2383 | spectral_dye_density | not_evaluable | 缺 cyan/magenta/yellow |
| kodak_2383 | spectral_sensitivity | not_evaluable | 缺 cyan/yellow |
| kodak_vision3_500t | characteristic | not_evaluable | status_M vs ECN-2 圖注不一致 |
| kodak_vision3_500t | spectral_dye_density | not_evaluable | 缺 magenta |
| kodak_vision3_500t | spectral_sensitivity | not_evaluable | 通道標籤不可靠 |

Granularity／MTF 可比較性：決定性配置關閉 grain／spatial → **not_evaluable**（provenance 表）。

G4 gate：**complete_with_limitations**（`FS-P4-03` completed on main）。此完成 **不代表** 物理真實度。

---

## 4. 光譜不確定性與 LUT（P5 子任務）

| Roadmap ID | 狀態 | 結論 |
|---|---|---|
| FS-P5-01 | completed（main） | 模型 spread 已量化；見上 |
| FS-P5-02 | **blocked** | 公平 5219→2383 LUT：**unavailable** — 無 `.cube`/`.3dl`；spektrafilm 內建 LUT 非獨立於光譜管線的外部對照（`validation/uncertainty_metrics.json`） |
| FS-P5-03 | 本文件 | 證據分級 closure |

G5 顯示對照（同一 RAW 三聯圖、hard-clip 預覽）已完成；LUT 欄位維持 unavailable（`output/ROUND2_REPORT.md`）。

---

## 5. 未解決限制（Unresolved limitations）

以下為 **限制記錄**，非 closure 的阻斷條件（與 FS-P4／FS-P5 acceptance 一致）：

1. **獨立真實膠片量測（V3）不可得** — 無受控 5219／2383 樣片；**不計算**真實膠片 ΔE00（G4b insufficient；`B.color.independent_delta_e00` not_evaluable）。
2. **公平 5219→2383 LUT 不可得** — FS-P5-02 維持 blocked／unavailable。
3. **Kodak 官方光柵曲線** — 多數通道／軸／量測定義不足以可靠殘差；六組維持 not_evaluable。
4. **5219 characteristic** — profile status_M 與 PDF ECN-2 圖注未建立同一量。
5. **光譜交叉曲線與標籤重疊** — 自動分通道追蹤未成立。
6. **RGB→spectrum 非唯一** — 兩種可運行重建之差為模型敏感度。
7. **DPRAW auxiliary image 未使用** — 未評估對 scene-linear 輸入之影響（not_evaluable）。
8. **顯示路徑** — hard-clip 影響約 1.8% 像素；ACES Output Transform 於該環境不可用；平滑高光預覽非核心線性輸出（`output/ROUND2_REPORT.md`）。

**不得**將上述任一項改寫為「已通過物理驗證」。

---

## 6. P6 公開資料（未合併；僅背景）

下列工作 **不在 main**，不作為本 closure 的 merged 證據；獨立 QC 後若合併，可補充 V2 殘差，**不**自動滿足 V3：

| PR | Head SHA | 摘要 |
|---|---|---|
| #6 (private source record) FS-P6-01 | `7208ecc5bce3d77005d9158e239b0e8008e4b2f1` | 公開資料寄存器；**無** lineage=none 的獨立物理量測 |
| #7 (private source record) FS-P6-02 | `e3ac50635059121820e7e54dc9eb7aa6608fb680` | 四項可比較之 V2 殘差；**獨立物理驗證仍 unavailable** |

P5 closure **不依賴** P6 合併；G4 歷史 not_evaluable 與本表限制 **不因 P6 開 PR 而撤銷**。

---

## 7. 凍結結論摘要

| 證據類別 | 本輪判定 |
|---|---|
| Software correctness | 已證明可重現與測試通過（邊界：scoped pytest、upstream known failures） |
| Internal model (V1) | 28 pass / 0 fail / 14 not_evaluable；模型語義與假設已文件化 |
| Published reference (V2) | Provenance 完整；**定量殘差多數 not_evaluable** |
| Independent physical (V3) | **unavailable / not_evaluable** |
| End-to-end photographic (V4) | 未評估 |
| Fair LUT comparison | **blocked（FS-P5-02）** |

**FS-P5-03 交付物：** 本分級 closure。**下一階段：** 獨立 QC 於證據 commit 上審查；通過後方可將 roadmap 狀態自 `ready_for_review` 升格為 `completed`（執行代理不得自行完成）。

---

## 證據索引（main）

| 路徑 | 用途 |
|---|---|
| `docs/phase5/CLOSURE.md` | 本 closure（FS-P5-03） |
| `docs/phase4/G4_PUBLISHED_REFERENCE_VALIDATION.md` | G4 數值驗證與假設邊界 |
| `docs/phase2/METRICS.json` | 42 項 V1–V4 分級 metrics |
| `docs/phase2/REFERENCE_DATA_PROVENANCE.md` | Kodak PDF 與可比較性 |
| `validation/uncertainty_metrics.json` | 光譜 spread、LUT、敏感度 |
| `output/ROUND2_REPORT.md` | Round 2 閘門與 G3/G4a/G4b/G5 |
| `output/phase2/test_results.json` | 測試紀錄 |
| `roadmap/filmsimulation_roadmap.csv` | 任務狀態（FS-P5-02 blocked；FS-P5-03 → 本文件） |