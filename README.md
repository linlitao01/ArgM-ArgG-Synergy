# ArgM&ArgG Evaluation System

**Agricultural Mechanization–Greening Coupling Coordination Assessment and Forecasting Platform** (case study: 11 provinces of the Yangtze River Economic Belt)
Companion software of the paper *ArgM&ArgG*. Implemented according to the **M1–M6 modular architecture** of paper §2.5; the core algorithms are regression-verified against all paper figures (Stata rerun, Appendix A.9).

**Three main functions**
| Function | Paper module | Description |
|---|---|---|
| 1. Indicators & Weights | M2–M3 | Direction-aware min–max standardization (+0.01 constant safeguard) → within-subsystem entropy weights (15 mechanization, 15 greening) → overall coupling-system weights α=β=0.5 (adjustable); includes checks against the paper's exact entropy weights and VIF/independence verification |
| 2. Index Computation | M4 | U1/U2 composite indices → coupling index C, coordination index T, coordination degree D → ten-level classification |
| 3. Forecasting | M5 (Algorithm 1) | GM(1,1) (grading + 1000-resample residual bootstrap 90% intervals + ARIMA/Holt cross-model checks); nonlinear models: Verhulst grey model, NARX-BP neural network, quadratic trend; batch forecasting with a live progress bar |

Plus: M1 data management (upload / manual input / demo data) and the M6 early-warning dashboard (province × variable risk matrix + rule-based warnings).

---

## Quick Start

### Option A: Windows standalone build (no installation required)
1. Unzip `ArgM_ArgG_Eval_Windows_Standalone.zip` to any folder;
2. Double-click **`ArgMArgG_Eval.exe`**;
3. The browser opens http://127.0.0.1:8000 automatically (if the port is occupied it steps to the next one; check the window message);
4. Close the black window to stop the service.
> First launch takes 5–15 seconds; if antivirus prompts, choose "Allow" (this software runs purely locally and does not connect to the network).

### Option B: Source version (Python 3.9+)
```bat
pip install -r requirements.txt
run.bat        (or: python app.py)
```
Open http://127.0.0.1:8000 in the browser (the port can be overridden with the `PORT` environment variable).

---

## Workflow (six tabs)

| Tab | Function | Description |
|---|---|---|
| 1. Data Management | Data input & preview | **Load demo data** (index level: the paper's 11-province 2013–2022 panel; indicator level: full 30-indicator pipeline); or upload Excel/CSV; or paste manually (Tab/comma/semicolon separated, first row is the header). Index level = province, year, mech, green (dcoord optional); indicator level = province, year, indicator columns (Chinese province names are mapped automatically; Excel workbooks with one sheet per year are stacked automatically). After loading, the **M1 completeness checks** run automatically (missing values / panel balance / series length) |
| 2. Indicators & Weights | Indicator system & entropy weights | Directions can be adjusted on the page; weights are only needed for indicator-level data (the page guides you for index-level data) |
| 3. Index Computation | Composite indices & coupling coordination | U1/U2/C/T/D panel, regional comparison, D heatmap, ten-level classification |
| 4. Forecasting | Forecasting & reliability | Batch forecast of all series (live progress bar); single-series multi-model comparison (GM/ARIMA/Holt/Verhulst/NARX/quadratic + direction-agreement flags) |
| 5. Early-Warning Dashboard | Early warning | Per-province coordination degree D **trend charts** (2013–2022 observed + 2023–2030 GM forecast extensions), risk matrix + rule-based warnings (reliable greening decline / mechanization rising while greening stagnant → structural imbalance / unreliable / cross-model divergence); if a step is skipped, you are prompted and guided to the prerequisite step |
| 6. Methodology Notes | All formulas & verification results | Computation conventions, grade rules, regression verification |

**Recommended order**: 1. Load demo data → 2. Compute weights (indicator level) → 3. Compute indices → 4. Batch forecast → 5. Early-warning dashboard.

---

## Consistency with the Paper (built-in verification)

- **Entropy weights**: max difference vs. the paper's exact weights < 1e-9 (the demo-data page shows "max difference 0.000000");
- **Indices**: U1/U2 reproduce the paper's panel mech/green bit-identically;
- **GM(1,1)**: α/μ/C/P and point forecasts for all 33 series match the paper's Stata rerun within 1e-6; grades 33/33 identical;
- **Coverage**: M reliable 9/11, G 5/11, D 7/11; cross-model direction agreement 16/21 (same as the paper);
- **Uncertainty**: mean 2030 90%-interval half-widths M 0.045 / G 0.015 / D 0.016 (paper §3.3 and Appendix A.9).
- Note: the panel dcoord follows the historical convention of the paper's data package; the software uses the panel D at the index level (matching the paper's figures) and the formula D at the indicator level, with an on-page check note.

---

## FAQ

| Symptom | Handling |
|---|---|
| Port occupied | Standalone build steps to the next port automatically; source version: `PORT=8001 python app.py` |
| Antivirus/firewall prompt | The software runs purely locally, does not connect to the network and makes no external calls; choose "Allow" |
| Garbled characters when uploading a Chinese-named CSV | Use UTF-8 or GBK encoding (both are auto-detected) |
| Want to use your own data | Prepare an index-level or indicator-level table as described in tab 1 |

---

## Developer Information

**Directory layout**
```
├── app.py                 Flask backend (M1–M6 APIs)
├── core/                  algorithm core (pure numpy, no third-party scientific-computation dependency)
│   ├── indicators.py      indicator dictionary (C1–C15/Z1–Z15, directions, paper weights)
│   ├── preprocessing.py   M2 standardization     ├── entropy.py   M3 entropy weights
│   ├── coupling.py        M4 coupling coordination    ├── gm11.py      M5 GM(1,1)+grading+bootstrap intervals
│   ├── forecasters.py     ARIMA/Holt/Verhulst/NARX/quadratic trend
│   ├── diagnostics.py     VIF/correlation    └── pipeline.py  full-pipeline orchestration + session state
├── static/                front end (vanilla JS + localized ECharts, offline-capable)
├── data/demo/             demo data (paper panel / standardized indicators / Stata benchmark CSVs)
├── tests/                 regression tests test_regression.py (67/67) + CDP screenshot/flow scripts
└── run.bat / requirements.txt / README.md
```

**API overview**: `GET /api/meta|status|series|data/preview`; `POST /api/data/demo|upload|manual|reset`, `/api/weights`, `/api/indices`, `/api/forecast/batch|one`, `/api/earlywarning`; `GET /api/forecast/batch/stream` (SSE progress).

**Regression tests**: `python tests/test_regression.py` (no third-party dependency; 67/67 passed).

**Tech stack**: Python 3.9 + Flask + numpy/pandas + ECharts; runs locally as a single machine, data lives in memory only and is never persisted.

*Version v1.1.0 · English UI · 2026-08-30*
