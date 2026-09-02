# -*- coding: utf-8 -*-
"""Regression tests: software output vs. paper benchmarks (Stata rerun / data-package results).

Run: python tests/test_regression.py   (no pytest needed)
Benchmark files (inside data/demo/):
- 04_appendix_reliable.csv    21 reliable series (source of Appendix A.9, computed in Stata)
- 01_results_33series.csv     all 33 series (incl. III/IV)
- gm_params_recomputed.csv    33 GM parameter sets (full-precision hard-check benchmark)
- entropy_weights_mech/green.csv  exact entropy weights
- panel_data_final.xlsx       index panel (mech/green/dcoord)
"""
import os
import sys
import json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import pipeline as pl
from core import coupling as coup

DEMO = pl.DEMO_DIR
PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


def t1_entropy_weights():
    print("== T1 entropy-weight reproduction (M3) ==")
    pl.STATE.load_demo("indicator")
    r = pl.STATE.compute_weights()
    for sys, ref_file in (("M", "entropy_weights_mech.csv"), ("G", "entropy_weights_green.csv")):
        ref = pd.read_csv(os.path.join(DEMO, ref_file))
        w = r["weights"][sys]
        worst = 0.0
        for _, row in ref.iterrows():
            worst = max(worst, abs(w[row["indicator"]] - row["exact_weight"]))
        check(f"entropy {sys} vs paper exact weights, max diff", worst < 1e-9, f"worst={worst:.2e}")
    check("M system has 15 indicators", len(r["weights"]["M"]) == 15)
    check("G system has 15 indicators", len(r["weights"]["G"]) == 15)
    check("weights sum to 1", abs(sum(r["weights"]["M"].values()) - 1) < 1e-9)
    check("paper-weight check exists", "M" in r["checks"] and r["checks"]["M"]["max_diff"] < 1e-9)


def t2_indices_reproduce_panel():
    print("== T2 indices reproduce the panel (M4) ==")
    panel = pd.read_excel(os.path.join(DEMO, "panel_data_final.xlsx"))
    pnl = panel.sort_values(["province", "year"]).reset_index(drop=True)
    U1, U2 = pnl["mech"].values, pnl["green"].values
    C = 2 * np.sqrt(U1 * U2) / (U1 + U2)
    T = 0.5 * U1 + 0.5 * U2
    D = np.sqrt(C * T)
    # ---- path A: indicator-level full pipeline -> U1/U2 reproduce the panel, D = formula D ----
    pl.STATE.load_demo("indicator")
    pl.STATE.compute_weights()
    r = pl.STATE.compute_indices()
    idx = r["indices"].sort_values(["province", "year"]).reset_index(drop=True)
    dU1 = np.abs(idx["U1"].values - pnl["mech"].values).max()
    dU2 = np.abs(idx["U2"].values - pnl["green"].values).max()
    check("indicator-level U1 reproduces panel mech", dU1 < 1e-9, f"maxdiff={dU1:.2e}")
    check("indicator-level U2 reproduces panel green", dU2 < 1e-9, f"maxdiff={dU2:.2e}")
    check("indicator-level C=2√(U1U2)/(U1+U2)", np.abs(C - idx["C"].values).max() < 1e-12)
    check("indicator-level T=0.5U1+0.5U2", np.abs(T - idx["T"].values).max() < 1e-12)
    check("indicator-level D=√(CT)", np.abs(D - idx["D"].values).max() < 1e-12)
    # the panel dcoord follows the author data package's historical convention
    # (diff vs formula recomputation <= 0.01, consistent with the left-column formula)
    dD_formula = np.abs(D - pnl["dcoord"].values).max()
    check("formula D vs panel dcoord diff < 0.01 (historical convention, not a formula issue)",
          dD_formula < 0.01, f"maxdiff={dD_formula:.4f}")
    # ---- path B: index level -> panel D is authoritative (paper forecast figures),
    #      d_check reports the difference ----
    pl.STATE.load_demo("index")
    r2 = pl.STATE.compute_indices()
    idx2 = r2["indices"].sort_values(["province", "year"]).reset_index(drop=True)
    check("index-level D adopts panel dcoord (bit-identical)",
          np.abs(idx2["D"].values - pnl["dcoord"].values).max() < 1e-12)
    check("d_check reports formula difference", r2["d_check"] is not None and r2["d_check"]["max_diff"] < 0.01,
          str(r2["d_check"]))
    # classification: Jiangsu mean 0.813 -> Good coordination; 0.606 -> Primary coordination
    js = pnl[pnl["province"] == "Jiangsu"]["dcoord"].mean()
    check("Jiangsu mean D≈0.813 -> Good coordination",
          abs(js - 0.813) < 0.002 and coup.classify_d(js)["level"] == "Good coordination", f"D={js:.3f}")
    check("D=0.606 -> Primary coordination", coup.classify_d(0.606)["level"] == "Primary coordination")
    check("D=0.500 -> Barely coordinated", coup.classify_d(0.500)["level"] == "Barely coordinated")


def t3_gm_hard_validation():
    print("== T3 GM(1,1) hard check on 33 series (M5, vs Stata rerun) ==")
    pl.STATE.load_demo("index")
    pl.STATE.compute_indices()
    r = pl.STATE.forecast_batch(B=1000)
    ref = pd.read_csv(os.path.join(DEMO, "01_results_33series.csv"))
    vmap = {"mech": "M", "green": "G", "dcoord": "D"}
    got = {f"{x['province']}|{x['var']}": x for x in r["forecasts"] if "gm11" in x}
    worst = {"alpha": 0, "mu": 0, "C": 0, "P": 0, "f2025": 0, "f2030": 0, "arima": 0, "holt": 0}
    grade_mismatch = []
    for _, row in ref.iterrows():
        key = f"{row['province']}|{vmap[row['var']]}"
        g = got[key]["gm11"]
        worst["alpha"] = max(worst["alpha"], abs(g["alpha"] - row["alpha"]))
        worst["mu"] = max(worst["mu"], abs(g["mu"] - row["mu"]))
        worst["C"] = max(worst["C"], abs(g["C"] - row["C"]))
        worst["P"] = max(worst["P"], abs(g["P"] - row["P"]))
        worst["f2025"] = max(worst["f2025"], abs(g["f2025"] - row["f2025"]))
        worst["f2030"] = max(worst["f2030"], abs(g["f2030"] - row["f2030"]))
        worst["arima"] = max(worst["arima"], abs(got[key]["arima"]["f2030"] - row["arima30"]))
        worst["holt"] = max(worst["holt"], abs(got[key]["holt"]["f2030"] - row["holt30"]))
        if g["grade"] != row["grade"]:
            grade_mismatch.append((row["province"], row["var"], g["grade"], row["grade"]))
    for k, v in worst.items():
        check(f"33-series {k} max diff", v < 1e-6, f"worst={v:.2e}")
    check("33-series grades all identical", len(grade_mismatch) == 0, str(grade_mismatch))
    # 21 reliable series (Appendix A.9)
    apx = pd.read_csv(os.path.join(DEMO, "04_appendix_reliable.csv"))
    m21 = {"f2025": 0, "f2030": 0, "alpha": 0, "mu": 0, "C": 0}
    for _, row in apx.iterrows():
        g = got[f"{row['province']}|{row['var']}"]["gm11"]
        m21["f2025"] = max(m21["f2025"], abs(g["f2025"] - row["f2025"]))
        m21["f2030"] = max(m21["f2030"], abs(g["f2030"] - row["f2030"]))
        m21["alpha"] = max(m21["alpha"], abs(g["alpha"] - row["alpha"]))
        m21["mu"] = max(m21["mu"], abs(g["mu"] - row["mu"]))
        m21["C"] = max(m21["C"], abs(g["C"] - row["C"]))
    for k, v in m21.items():
        check(f"21 reliable series {k} max diff", v < 1e-6, f"worst={v:.2e}")
    # coverage statistics
    cov = r["coverage"]
    check("M reliable 9/11", cov["M"]["reliable"] == 9 and cov["M"]["total"] == 11)
    check("G reliable 5/11", cov["G"]["reliable"] == 5 and cov["G"]["total"] == 11)
    check("D reliable 7/11", cov["D"]["reliable"] == 7 and cov["D"]["total"] == 11)
    check("M unreliable: Jiangsu/Hubei",
          sorted(cov["M"]["unreliable_provs"]) == ["Hubei", "Jiangsu"], str(cov["M"]["unreliable_provs"]))
    check("D unreliable: Shanghai/Jiangsu/Anhui+Hubei (7/11 reliable)",
          sorted(cov["D"]["unreliable_provs"]) == ["Anhui", "Hubei", "Jiangsu", "Shanghai"],
          str(cov["D"]["unreliable_provs"]))


def t4_bootstrap_and_agreement():
    print("== T4 bootstrap intervals and cross-model direction agreement ==")
    pl.STATE.load_demo("index")
    pl.STATE.compute_indices()
    r = pl.STATE.forecast_batch(B=1000)
    # mean half-widths (Stata benchmark: M 0.0454 / G 0.0153 / D 0.0160; randomness allows ±0.008)
    for var, ref_hw in (("M", 0.0454), ("G", 0.0153), ("D", 0.0160)):
        hws = []
        for x in r["forecasts"]:
            if x["var"] == var and x["gm11"]["ci30"]:
                lo, hi = x["gm11"]["ci30"]
                hws.append((hi - lo) / 2)
        mean_hw = float(np.mean(hws)) if hws else None
        check(f"{var} 2030 mean half-width≈{ref_hw}", mean_hw is not None and abs(mean_hw - ref_hw) < 0.008,
              f"mean={mean_hw}")
    # interval sanity: point forecast inside the interval
    ok = all(x["gm11"]["ci30"][0] < x["gm11"]["f2030"] < x["gm11"]["ci30"][1]
             for x in r["forecasts"] if x["gm11"]["ci30"])
    check("all reliable point forecasts ∈ 90% interval", ok)
    # direction agreement 16/21, 5 disagreements (paper convention)
    rel = [x for x in r["forecasts"] if x["gm11"]["reliable"]]
    agree = sum(1 for x in rel if x.get("direction_agree_all"))
    dis = sorted(f"{x['province']} {x['var']}" for x in rel if not x.get("direction_agree_all"))
    check("direction agreement 16/21", agree == 16 and len(rel) == 21, f"agree={agree}/21")
    expect_dis = ["Chongqing D", "Hunan G", "Shanghai M", "Yunnan M", "Zhejiang D"]
    check("5 disagreement names match", dis == expect_dis, str(dis))
    # reproducibility: two batch runs are identical
    r2 = pl.STATE.forecast_batch(B=1000)
    same = all(
        x["gm11"]["ci30"] == y["gm11"]["ci30"] and x["gm11"]["f2030"] == y["gm11"]["f2030"]
        for x, y in zip(r["forecasts"], r2["forecasts"]) if x["gm11"]["ci30"] and y["gm11"]["ci30"])
    check("fixed seed reproducible (two runs, identical CIs)", same)


def t5_nonlinear_models():
    print("== T5 nonlinear models (Verhulst / NARX / quadratic trend) ==")
    pl.STATE.load_demo("index")
    pl.STATE.compute_indices()
    r = pl.STATE.forecast_single("Guizhou", "M",
                                 methods=("gm11", "arima", "holt", "verhulst", "narx", "quad"))
    check("GM grade I (Guizhou M, paper Table 4)", r["gm11"]["grade"] == "I", r["gm11"]["grade"])
    for m in ("verhulst", "narx", "quad", "arima", "holt"):
        v = r.get(m, {}).get("f2030")
        check(f"{m} 2030 forecast finite", v is not None and np.isfinite(v), str(v))
    check("Verhulst params exist", "params" in r.get("verhulst", {}))
    check("NARX median over starts", r["narx"]["params"]["restarts"] >= 1)
    # direction flags exist (cross-model check, Algorithm 1 Step 9)
    check("direction flags exist", "direction_flags" in r and len(r["direction_flags"]) >= 3,
          str(r.get("direction_flags")))
    # vs paper benchmark: Guizhou M f2030 = 0.665? Appendix A.9: Guizhou M 2030 CI [0.536, 0.790]
    ci = r["gm11"]["ci30"]
    check("Guizhou M 2030 CI contains [0.536, 0.790] (randomness tolerance)",
          abs(ci[0] - 0.536) < 0.01 and abs(ci[1] - 0.790) < 0.01, str(ci))


def t6_manual_input_and_upload_paths():
    print("== T6 manual input / index-panel path ==")
    pl.STATE.load_demo("index")
    panel = pl.STATE.panel
    # manual paste: header + first 12 rows
    head = "\t".join(panel.columns)
    lines = [head] + ["\t".join(str(v) for v in row) for row in panel.head(12).values]
    pl.STATE.load_manual("\n".join(lines))
    check("manual input detected as index level", pl.STATE.level == "index")
    check("manual input has 12 rows", len(pl.STATE.panel) == 12)
    r = pl.STATE.compute_indices()
    check("manual input computes C/T/D", r["indices"]["D"].notna().all())
    # index level without dcoord: D computed automatically
    panel2 = panel.drop(columns=["dcoord"])
    pl.STATE.panel = panel2
    pl.STATE._init_index_meta(panel2)
    r2 = pl.STATE.compute_indices()
    d = pd.read_excel(os.path.join(DEMO, "panel_data_final.xlsx"))
    dd = r2["indices"].merge(d[["province", "year", "dcoord"]], on=["province", "year"])
    check("D auto-computed without dcoord (formula convention, diff from panel < 0.01)",
          np.abs(dd["D"] - dd["dcoord"]).max() < 0.01,
          f"maxdiff={np.abs(dd['D'] - dd['dcoord']).max():.4f}")


def t7_early_warning():
    print("== T7 early-warning dashboard (M6) ==")
    pl.STATE.load_demo("index")
    pl.STATE.compute_indices()
    pl.STATE.forecast_batch(B=1000)
    r = pl.STATE.early_warning()
    rows = r["rows"]
    check("warning rows = 33", len(rows) == 33)
    check("unreliable flags exist", any(x["grade"] in ("III", "IV") for x in rows))
    check("high-risk flags exist", any(x["risk"] == "High" for x in rows))
    # paper rule: greening decline with a reliable grade (e.g., Zhejiang G declines by 2030)
    zg = next(x for x in rows if x["province"] == "Zhejiang" and x["var"] == "G")
    check("Zhejiang G reliable and declining -> high risk", zg["reliable"] and zg["risk"] == "High",
          f"delta={zg['delta']} grade={zg['grade']}")


def t8_gm_params_recomputed_cross():
    print("== T8 cross-check vs gm_params_recomputed.csv ==")
    pl.STATE.load_demo("index")
    pl.STATE.compute_indices()
    r = pl.STATE.forecast_batch(B=1000)
    ref = pd.read_csv(os.path.join(DEMO, "gm_params_recomputed.csv"))
    vmap = {"mech": "M", "green": "G", "dcoord": "D"}
    worst = 0.0
    for _, row in ref.iterrows():
        g = next(x["gm11"] for x in r["forecasts"]
                 if x["province"] == row["province"] and x["var"] == vmap[row["var"]])
        worst = max(worst, abs(g["alpha"] - row["alpha"]), abs(g["mu"] - row["mu"]),
                    abs(g["C"] - row["C"]))
    check("33-series α/μ/C match codex full precision", worst < 1e-9, f"worst={worst:.2e}")


def t9_python_json_reference():
    print("== T9 vs _robustness_results.json (entropy weights / half-widths) ==")
    jpath = os.path.join(DEMO, "_robustness_results.json")
    if not os.path.exists(jpath):
        print("  [SKIP] _robustness_results.json not found")
        return
    with open(jpath, encoding="utf-8") as f:
        ref = json.load(f)
    pl.STATE.load_demo("indicator")
    r = pl.STATE.compute_weights()
    for sys, key in (("M", "entropy_mech"), ("G", "entropy_green")):
        worst = max(abs(r["weights"][sys][k] - v) for k, v in ref[key].items())
        check(f"entropy {sys} vs Python reference (6dp)", worst < 1e-6, f"worst={worst:.2e}")
    pl.STATE.load_demo("index")
    pl.STATE.compute_indices()
    rb = pl.STATE.forecast_batch(B=1000)
    for var in ("M", "G", "D"):
        key = f"halfwidth30_{var}"
        if key in ref:
            hws = [(x["gm11"]["ci30"][1] - x["gm11"]["ci30"][0]) / 2
                   for x in rb["forecasts"] if x["var"] == var and x["gm11"]["ci30"]]
            mean = float(np.mean(hws))
            check(f"{var} half-width mean vs Python reference", abs(mean - ref[key]["mean"]) < 0.01,
                  f"{mean:.4f} vs {ref[key]['mean']:.4f}")


def main():
    print("=" * 70)
    print("ArgM&ArgG Evaluation System - regression tests (vs paper/Stata benchmarks)")
    print("=" * 70)
    for fn in (t1_entropy_weights, t2_indices_reproduce_panel, t3_gm_hard_validation,
               t4_bootstrap_and_agreement, t5_nonlinear_models, t6_manual_input_and_upload_paths,
               t7_early_warning, t8_gm_params_recomputed_cross, t9_python_json_reference):
        fn()
    print("=" * 70)
    print(f"Result: PASS={PASS}  FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
