# Phase II Performance Report

## 方法

Apple M5 Pro、48 GiB RAM。每個尺寸／branch在獨立process執行；先64² warm-up，再做3次相同輸入。stage時間來自 `SimulationPipeline.get_timings()`；peak RSS來自macOS `resource.getrusage(RUSAGE_SELF).ru_maxrss`。RSS是process生命期峰值，不是單一stage的增量記憶體。

| size | route | median total s | peak RSS GiB | output dtype | output MiB | deterministic | finite |
|---:|---|---:|---:|---|---:|---|---|
| 256² | negative | 0.040 | 0.413 | float64 | 1.50 | True | True |
| 256² | print | 0.073 | 0.417 | float64 | 1.50 | True | True |
| 512² | negative | 0.147 | 0.840 | float64 | 6.00 | True | True |
| 512² | print | 0.285 | 0.852 | float64 | 6.00 | True | True |
| 1024² | negative | 0.617 | 2.520 | float64 | 24.00 | True | True |
| 1024² | print | 1.121 | 2.568 | float64 | 24.00 | True | True |
| 2048² | negative | 2.803 | 9.258 | float64 | 96.00 | True | True |
| 2048² | print | 4.497 | 9.445 | float64 | 96.00 | True | True |

2048門檻：必須先有兩條1024 route，且最大1024 peak RSS的4倍推算低於48 GiB的50%。Deferred／失敗：
- 無

完整逐次與stage時間見 `output/phase2/performance_benchmarks.json`。

## Tile feasibility

1024²完整運算和四個512² tiles比較：

| route | bit exact | RMSE | max abs |
|---|---|---:|---:|
| negative | True | 0 | 0 |
| print | True | 0 | 0 |

這個結果只適用於目前關閉global/spatial/stochastic effects的固定設定。一般tiler還必須處理auto-exposure、highlight global max、crop/rescale、DIR diffusion、halation、diffusion、blur、glare、unsharp和grain random field；因此本輪不提出bit-exact通用承諾，也不實作major optimization。

## 優化建議

優先做具halo的overlap tiles，為所有global statistics先做獨立低解析度／全圖pass，並用座標決定的counter-based RNG維持grain一致。逐tap的81波段暫存應以stage fusion或chunked wavelength reduction降低峰值；任何優化都須用本輪whole-vs-tile與ramp fixtures回歸，不能只比較顯示圖。
