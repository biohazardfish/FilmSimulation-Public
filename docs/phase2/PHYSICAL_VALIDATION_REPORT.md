# FilmSimulation Phase II：Physical Fidelity Benchmark

## 固定基準

- spektrafilm commit `3bb2c2d2801ff68b92019cf1dbcbb133d60832bc`，package 0.3.4；實際入口為 `init_params(...)`、`simulate(...)`、`params.taps.collect`，本輪性能量測另直接使用同一commit的 `SimulationPipeline` 及 `get_timings()`。
- Python 3.13.15；主要依賴：NumPy 2.5.5、SciPy 1.18.1、colour-science 0.4.7、rawpy 0.26.1、OpenImageIO 3.1.19.0、Matplotlib 3.11.2、Numba 0.68.1。
- Kodak VISION3 500T 35 mm 5219 profile `kodak_vision3_500t`：`d7beca68bf16db88dbb7373fd13a6a1150a57a911a54bb0309a760a6f9883329`。
- Kodak VISION Color Print Film 2383 profile `kodak_2383`：`eb7fdfa3b75a909bf5c400802f7401160c8017ed1ac3e8e0d1c8448d56fbe184`。

## 結論

本輪結果為 pass 28、fail 0、not_evaluable 14。這些數目不是「膠片真實度分數」。V1只驗證固定程式與數值行為；V2是官方資料的有條件比較；本專案沒有V3獨立實體量測或V4 matched photographic validation。

## 已驗證

- 固定commit、指定5219／500T與2383 profiles及官方PDF hash均一致。
- 合成ACEScg neutral ramp涵蓋−6至+6 EV，共481點；所有已收集tap為有限float64，兩次pixel hash相同：`True`。
- 負片及印片branch確實分開；negative scan不經2383，print scan完整經 `log_e_print`／`cmy_print`。
- Profile內部characteristic運算、決定性和小尺寸資源趨勢可重現。既有Round 2的32 MP兩次pixel hashes亦作為V1先前證據重用，而非重跑。
- whole-vs-tile在固定逐像素設定下的結果已量化；negative bit-exact=True，print bit-exact=True。

## 已反證或與直覺稱呼矛盾

- `log_e_film`／`log_e_print` 不是已校準的絕對lux-seconds，而是模型正規化後的相對log10 layer exposure。
- `cmy_film`／`cmy_print` 不能單憑名稱當成Status M／A實測密度；它們是模型通道係數，需經channel/base spectral density及明確densitometry才能比較。
- 光譜profile存在NaN，runtime將相應transmitted-light samples置零；這不是物理量測補全。
- 任何V1重現性通過都不能推出V2–V4。現有官方曲線追蹤不足時，不能把缺資料判成零誤差或pass。

本輪V1 failures：0。完整逐項見 `METRICS.json`；任何failure均保留，不以視覺結果掩蓋。

## 仍然未知／不可評估

- Profile擬合所用原始數字、digitization點、樣片批次和完整殘差沒有逐array公開。
- Kodak資料與profile不完全建立相同densitometer、process、軸及通道條件，現有六組自動curve traces均不足以作可靠三通道定量判決。
- 沒有實際5219／2383樣片的獨立spectral transmittance、Status density、ColorChecker或step-wedge量測；物理色準及ΔE00為 `not_evaluable`。
- Grain、halation、MTF和granularity在本輪固定關閉，不可由本輪輸出評分。
- 這張CR3經LibRaw相機矩陣成為ACEScg後，原場景光譜與相機spectral sensitivity mismatch不可恢復。

## Evidence levels

- **V1**：本輪ramp、determinism、profile內部運算、branch、precision及performance；以及既有full-resolution repeat。
- **V2**：Kodak官方PDF來源與條件已確認，但目前數值curve agreement多數 `not_evaluable`；即使成立也只是calibration-data agreement。
- **V3**：無獨立物理量測，未得分。
- **V4**：無matched film/digital capture、lab、print/scan chain，未得分。

## 最能提高信心的下一個實驗

用同批35 mm 5219在校準3200 K sensitometer下曝光step wedge，依標準ECN-2顯影；以完整記錄printer lights印到同批2383並作ECP-2D。對負片和印片每階同時量測Status M／A及光譜透射密度。這會直接提供未參與profile建構的V3資料，並把film exposure、negative density、print exposure和print density逐段隔離。

> **2026-11-20 註記：** 上段建議保留為歷史紀錄。依Research Director 2026-11-20決定，實體膠片量測（sensitometer曝光、ECN-2／ECP-2D沖印、Status M／A及光譜量測）不屬於目前授權的研究計畫，亦不授權購買膠片、器材、商業LUT或付費資料集。目前授權的外部比較路徑是P6 Public-Data External Comparison（FS-P6-01、FS-P6-02；由另一個roadmap PR定義）。治理紀錄：decision 0004 (Decision 0004 public summary, pending merge)。本報告的結果、evidence levels及 `not_evaluable` 判定不因本註記改變；V3／V4仍未得分。

## 完整重跑命令

```bash
cd <repo-root>
PYTHONPATH=src .venv/bin/python scripts/run_phase2.py --all   --film-profile kodak_vision3_500t --print-profile kodak_2383   --sizes 256,512,1024,2048
PYTHONPATH=src .venv/bin/python -m pytest tests -q

cd upstream/spektrafilm
../../.venv/bin/python -m pytest tests --ignore=tests/gui -q
```

最後一條預期重現四個已知upstream findings；它不是Phase II成功的零failure門檻，亦不得重生upstream baselines。
