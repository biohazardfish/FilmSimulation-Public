from __future__ import annotations

from pathlib import Path
from typing import Any

from filmsim_experiment.experiment import FILM_KEY, PRINT_KEY, PROFILE_SHA256, UPSTREAM_COMMIT, write_text


def _status_counts(metrics: list[dict[str, Any]]) -> str:
    counts = {status: sum(row["status"] == status for row in metrics) for status in ("pass", "fail", "not_evaluable")}
    return f"pass {counts['pass']}、fail {counts['fail']}、not_evaluable {counts['not_evaluable']}"


def signal_flow_report(sens: dict[str, Any], spectral: dict[str, Any]) -> str:
    taps = sens["tap_summary"]["print"]
    negative_taps = sens["tap_summary"]["negative"]
    rows = []
    semantics = {
        "rgb_in": ("呼叫者提供的scene-linear ACEScg neutral ramp", "相對scene-linear RGB；0 EV定義為0.18，非絕對輻照度", "否；RGB本身不包含唯一光譜"),
        "rgb_pre": ("scene-linear ACEScg；由 `np.double` 預處理", "相對 scene-linear RGB；無絕對輻照度單位", "否；RGB 已丟失光譜同色異譜資訊"),
        "log_e_film": ("5219 三個感光層的相對 log10 exposure", "dimensionless relative log10 response，不是 lux-seconds", "否；RGB-to-spectrum 重建及三層積分不可逆"),
        "cmy_film": ("扣除每色曲線最小值、經 DIR coupler 後的三通道密度係數", "model channel coefficient；不自動等於 Status M 實測密度", "否；特性曲線飽和及耦合會丟失資訊"),
        "log_e_print": ("5219 光譜透射後對 2383 三感光層的相對 log10 exposure", "dimensionless relative log10 response，不是 lux-seconds", "否；光譜積分、printer light及正規化不可逆"),
        "cmy_print": ("2383 parametric characteristic curve 的三通道係數", "model channel coefficient；不自動等於 Status A 實測密度", "否；曲線飽和不可逆"),
        "rgb_out": ("2383掃描光源下的光譜透射→CIE XYZ→scene-linear ACEScg", "scene-linear ACEScg；無 CCTF；可超出0–1", "否；81波段積分成XYZ再成RGB"),
    }
    for tap in ("rgb_in", "rgb_pre", "log_e_film", "cmy_film", "log_e_print", "cmy_print", "rgb_out"):
        info = taps[tap]
        physical, unit, reversible = semantics[tap]
        rows.append(f"| `{tap}` | {physical} | {unit} | `{info['shape']}` / `{info['dtype']}` | {info['minimum']:.6g}…{info['maximum']:.6g} | {reversible} |")
    negative_info = negative_taps["rgb_out"]
    rows.append(
        f"| `rgb_out` (negative scan) | 5219光譜密度在D50下透射→CIE XYZ→scene-linear ACEScg | scene-linear ACEScg；無CCTF | `{negative_info['shape']}` / `{negative_info['dtype']}` | {negative_info['minimum']:.6g}…{negative_info['maximum']:.6g} | 否；81波段積分成XYZ再成RGB |"
    )
    return f"""# Phase II Signal Flow Audit

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
{chr(10).join(rows)}

所有影像 tap 為 `H×W×3`。合成 ramp 的 H=1、W=481；pipeline `_preprocess` 無條件轉為 float64。必要 metadata 是 RGB primaries、white point、CCTF狀態、profile key/hash、viewing/reference illuminant、曝光正規化及 scanner correction 狀態。

## 來源路徑與轉換

- `runtime/pipeline.py`：拓撲、`np.double`、auto-exposure及 crop/rescale。
- `runtime/stages/filming.py`：ACEScg RGB 經 Hanatos 2025 spectrum LUT與5219 sensitivity積分；乘曝光補償後取 `log10`。
- `model/develop.py`／`model/couplers.py`：特性曲線先扣 per-channel minimum；DIR coupler仍啟用，但 spatial diffusion為零；grain停用。
- `runtime/stages/printing.py`：`channel_density × cmy_film + base_density` 建立81波段光譜密度，`10^-D` 轉透射光，再由2383 sensitivity積分。
- `runtime/stages/scanning.py`：negative branch用5219與D50；print branch用2383與K75P；CIE 1931 2° XYZ後轉ACEScg。
- `utils/conversions.py::density_to_light` 把光譜密度轉成 `10^-D × light`，並把 NaN transmitted samples設為0。這不是插值，而是零光量假設；film/print `channel_density` 分別含 {spectral['film']['arrays']['channel_density']['nan_count']}／{spectral['print']['arrays']['channel_density']['nan_count']} 個 NaN，必須視為資訊缺口和模型選擇。

## 參數狀態

Auto-exposure、print exposure compensation、grain、halation、diffusion、glare、scanner blur/unsharp、black/white correction均關閉；output CCTF及output gamut compression關閉。input gamut compression的固定 xy LUT仍按 Phase I 參數啟用。隨機與空間效果停用，因此本輪主要測的是逐像素光譜／特性曲線模型。
"""


def provenance_report(pins: dict[str, Any], published: list[dict[str, Any]], spectral: dict[str, Any]) -> str:
    source_rows = "\n".join(
        f"| {key} | [{spec['path']}]({spec['url']}) | `{spec['actual_sha256']}` | Kodak官方技術資料；曲線是光柵圖 |"
        for key, spec in pins["official_pdfs"].items()
    )
    curve_rows = "\n".join(
        f"| `{row['metric_id']}` | {row['status']} | {row.get('reason') or '—'} |"
        for row in published
    )
    return f"""# Phase II Reference Data Provenance

## 固定實作與 profiles

- spektrafilm commit：`{UPSTREAM_COMMIT}`；套件版本0.3.4；Python要求 `~=3.13`。
- 5219／500T profile key `{FILM_KEY}`：`{PROFILE_SHA256[FILM_KEY]}`。
- 2383 profile key `{PRINT_KEY}`：`{PROFILE_SHA256[PRINT_KEY]}`。
- 程式碼依 upstream 聲明為 GPLv3／GPL-3.0-or-later。profiles及直接衍生編碼為 Andrea Volpato 的 CC BY-SA 4.0，需作者、專案連結、授權及修改註記。本輪不修改 profile。
- Profile metadata只概括表示資料來自 datasheets／公開科學資料，未逐個array提供原始量測檔、digitization控制點、擬合殘差或樣片批次。因此不能把 profile 視為某卷實體膠片的完整量測真值。

## Kodak來源

| product | source | SHA-256 | 資料性質 |
|---|---|---|---|
{source_rows}

5219 PDF條件包括3200 K、ECN-2及圖中所述densitometry；2383包括ECP-2D／Status A等圖示條件。Datasheet明示曲線代表指定條件下的production coatings，而非特定一卷或規格保證。既有自動流程從PDF raster XObject、OCR刻度及ink trace取樣；沒有可靠追蹤時不以肉眼補點。

## 可比較性判定

| metric | status | reason |
|---|---|---|
{curve_rows}

這些比較最多是V2 calibration-data agreement：profile本來就由公開datasheet資料處理而來，並非獨立驗證。Peak-normalized dye curve只能驗證形狀，不能驗證絕對光譜密度。現有可靠資料不足以計算真實膠片ΔE00、granularity或MTF模型誤差。

## Profile光譜資料範圍

- 5219：{spectral['film']['arrays']['wavelengths']['shape'][0]}個波長點；log sensitivity NaN={spectral['film']['arrays']['log_sensitivity']['nan_count']}；channel density NaN={spectral['film']['arrays']['channel_density']['nan_count']}；base density NaN={spectral['film']['arrays']['base_density']['nan_count']}。
- 2383：{spectral['print']['arrays']['wavelengths']['shape'][0]}個波長點；log sensitivity NaN={spectral['print']['arrays']['log_sensitivity']['nan_count']}；channel density NaN={spectral['print']['arrays']['channel_density']['nan_count']}；base density NaN={spectral['print']['arrays']['base_density']['nan_count']}。

RGB-to-spectrum重建並不唯一；Hanatos 2025與Mallett 2019的差只表示模型選擇敏感度。相機光譜敏感度與5219實際感光度並未由這張CR3的RGB值恢復，故不能把RGB重建當成實際入射光譜量測。
"""


def performance_report(bench: dict[str, Any], tile: dict[str, Any]) -> str:
    rows = []
    for row in sorted(bench["results"], key=lambda item: (item["size"], item["branch"])):
        rows.append(
            f"| {row['size']}² | {row['branch']} | {row['median_total_seconds']:.3f} | {row['peak_rss_bytes']/1024**3:.3f} | {row['output_dtype']} | {row['output_bytes']/1024**2:.2f} | {row['deterministic']} | {row['finite']} |"
        )
    deferred = "\n".join(f"- {item}" for item in bench["deferred"]) or "- 無"
    tile_rows = "\n".join(
        f"| {branch} | {tile[branch]['bit_exact']} | {tile[branch]['rmse']:.9g} | {tile[branch]['max_abs']:.9g} |"
        for branch in ("negative", "print")
    )
    return f"""# Phase II Performance Report

## 方法

Apple M5 Pro、48 GiB RAM。每個尺寸／branch在獨立process執行；先64² warm-up，再做3次相同輸入。stage時間來自 `SimulationPipeline.get_timings()`；peak RSS來自macOS `resource.getrusage(RUSAGE_SELF).ru_maxrss`。RSS是process生命期峰值，不是單一stage的增量記憶體。

| size | route | median total s | peak RSS GiB | output dtype | output MiB | deterministic | finite |
|---:|---|---:|---:|---|---:|---|---|
{chr(10).join(rows)}

2048門檻：必須先有兩條1024 route，且最大1024 peak RSS的4倍推算低於48 GiB的50%。Deferred／失敗：
{deferred}

完整逐次與stage時間見 `output/phase2/performance_benchmarks.json`。

## Tile feasibility

1024²完整運算和四個512² tiles比較：

| route | bit exact | RMSE | max abs |
|---|---|---:|---:|
{tile_rows}

這個結果只適用於目前關閉global/spatial/stochastic effects的固定設定。一般tiler還必須處理auto-exposure、highlight global max、crop/rescale、DIR diffusion、halation、diffusion、blur、glare、unsharp和grain random field；因此本輪不提出bit-exact通用承諾，也不實作major optimization。

## 優化建議

優先做具halo的overlap tiles，為所有global statistics先做獨立低解析度／全圖pass，並用座標決定的counter-based RNG維持grain一致。逐tap的81波段暫存應以stage fusion或chunked wavelength reduction降低峰值；任何優化都須用本輪whole-vs-tile與ramp fixtures回歸，不能只比較顯示圖。
"""


def physical_report(metrics: list[dict[str, Any]], sens: dict[str, Any], bench: dict[str, Any], tile: dict[str, Any], color: dict[str, Any]) -> str:
    failures = [row for row in metrics if row["status"] == "fail"]
    return f"""# FilmSimulation Phase II：Physical Fidelity Benchmark

## 固定基準

- spektrafilm commit `{UPSTREAM_COMMIT}`，package 0.3.4；實際入口為 `init_params(...)`、`simulate(...)`、`params.taps.collect`，本輪性能量測另直接使用同一commit的 `SimulationPipeline` 及 `get_timings()`。
- Python 3.13.15；主要依賴：NumPy 2.5.5、SciPy 1.18.1、colour-science 0.4.7、rawpy 0.26.1、OpenImageIO 3.1.19.0、Matplotlib 3.11.2、Numba 0.68.1。
- Kodak VISION3 500T 35 mm 5219 profile `{FILM_KEY}`：`{PROFILE_SHA256[FILM_KEY]}`。
- Kodak VISION Color Print Film 2383 profile `{PRINT_KEY}`：`{PROFILE_SHA256[PRINT_KEY]}`。

## 結論

本輪結果為 {_status_counts(metrics)}。這些數目不是「膠片真實度分數」。V1只驗證固定程式與數值行為；V2是官方資料的有條件比較；本專案沒有V3獨立實體量測或V4 matched photographic validation。

## 已驗證

- 固定commit、指定5219／500T與2383 profiles及官方PDF hash均一致。
- 合成ACEScg neutral ramp涵蓋−6至+6 EV，共481點；所有已收集tap為有限float64，兩次pixel hash相同：`{all(sens['deterministic'].values())}`。
- 負片及印片branch確實分開；negative scan不經2383，print scan完整經 `log_e_print`／`cmy_print`。
- Profile內部characteristic運算、決定性和小尺寸資源趨勢可重現。既有Round 2的32 MP兩次pixel hashes亦作為V1先前證據重用，而非重跑。
- whole-vs-tile在固定逐像素設定下的結果已量化；negative bit-exact={tile['negative']['bit_exact']}，print bit-exact={tile['print']['bit_exact']}。

## 已反證或與直覺稱呼矛盾

- `log_e_film`／`log_e_print` 不是已校準的絕對lux-seconds，而是模型正規化後的相對log10 layer exposure。
- `cmy_film`／`cmy_print` 不能單憑名稱當成Status M／A實測密度；它們是模型通道係數，需經channel/base spectral density及明確densitometry才能比較。
- 光譜profile存在NaN，runtime將相應transmitted-light samples置零；這不是物理量測補全。
- 任何V1重現性通過都不能推出V2–V4。現有官方曲線追蹤不足時，不能把缺資料判成零誤差或pass。

本輪V1 failures：{len(failures)}。完整逐項見 `METRICS.json`；任何failure均保留，不以視覺結果掩蓋。

## 仍然未知／不可評估

- Profile擬合所用原始數字、digitization點、樣片批次和完整殘差沒有逐array公開。
- Kodak資料與profile不完全建立相同densitometer、process、軸及通道條件，現有六組自動curve traces均不足以作可靠三通道定量判決。
- 沒有實際5219／2383樣片的獨立spectral transmittance、Status density、ColorChecker或step-wedge量測；物理色準及ΔE00為 `{color['status']}`。
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
cd /path/to/FilmSimulation
PYTHONPATH=src .venv/bin/python scripts/run_phase2.py --all \
  --film-profile kodak_vision3_500t --print-profile kodak_2383 \
  --sizes 256,512,1024,2048
PYTHONPATH=src .venv/bin/python -m pytest tests -q

cd upstream/spektrafilm
../../.venv/bin/python -m pytest tests --ignore=tests/gui -q
```

最後一條預期重現四個已知upstream findings；它不是Phase II成功的零failure門檻，亦不得重生upstream baselines。
"""


def status_report(metrics: list[dict[str, Any]], integrity: dict[str, Any], bench: dict[str, Any]) -> str:
    failures = [row["metric_id"] for row in metrics if row["status"] == "fail"]
    not_eval = [row["metric_id"] for row in metrics if row["status"] == "not_evaluable"]
    tests = integrity.get("test_results") or {}
    project_tests = tests.get("project", {})
    upstream_tests = tests.get("upstream_core", {})
    return f"""# Phase II Status

## Completed

- Source-grounded signal-flow audit and negative／print branch graph。
- −6…+6 EV ACEScg sensitometric ramp、all taps、numerical plots及V1 metrics。
- Kodak reference provenance及可比較性判定。
- Spectral profile／NaN audit與外部CIELAB validation interface。
- Small-scale performance、memory、determinism及1024 whole-vs-tile comparison。
- Required six documents、machine-readable metrics及artifact manifest。
- Phase I／Round 2 integrity：`{integrity['all_match']}`。
- Project tests：{project_tests.get('summary', 'not recorded')}；command `{project_tests.get('command', 'not recorded')}`。
- Pinned upstream core tests：{upstream_tests.get('summary', 'not recorded')}；四個failure分類為既有baseline／stale-test findings。

## Failed

{chr(10).join(f'- `{item}`' for item in failures) if failures else '- 無新增V1 failure。'}

## Blocked / NOT EVALUABLE

{chr(10).join(f'- `{item}`' for item in not_eval)}

## Deferred

{chr(10).join(f'- {item}' for item in bench['deferred']) if bench['deferred'] else '- 無；所有請求尺寸均完成。'}

四個Phase I已知upstream failures仍保留為既有finding；未修改upstream或regression baselines。直接從repo root無限制執行`pytest -q`會收集缺少qtpy的GUI tests，屬測試範圍／環境問題；正式命令固定為`pytest tests -q`。
"""


def write_reports(root: Path, docs: Path, *, metrics: list[dict[str, Any]], sens: dict[str, Any], spectral: dict[str, Any], pins: dict[str, Any], published: list[dict[str, Any]], bench: dict[str, Any], tile: dict[str, Any], color: dict[str, Any], integrity: dict[str, Any]) -> list[Path]:
    docs.mkdir(parents=True, exist_ok=True)
    payloads = {
        "SIGNAL_FLOW_AUDIT.md": signal_flow_report(sens, spectral),
        "REFERENCE_DATA_PROVENANCE.md": provenance_report(pins, published, spectral),
        "PERFORMANCE_REPORT.md": performance_report(bench, tile),
        "PHYSICAL_VALIDATION_REPORT.md": physical_report(metrics, sens, bench, tile, color),
        "PHASE2_STATUS.md": status_report(metrics, integrity, bench),
    }
    paths = []
    for name, text in payloads.items():
        path = docs / name
        write_text(path, text)
        paths.append(path)
    return paths
