# -*- coding: utf-8 -*-
"""Full-pipeline orchestration (M1-M6) + session state.

Data-level auto-detection:
- Index level: columns contain mech/green (or U1/U2) -> coupling coordination + forecasting directly
- Indicator level: otherwise -> preprocessing (M2) -> entropy weights (M3) -> composite indices ->
  coupling coordination (M4) -> forecasting (M5)

Data sources: demo data / uploaded files / manually pasted text (all auto-detected).
"""
import os
import sys
import numpy as np
import pandas as pd

from . import indicators as ind
from . import preprocessing as pre
from . import entropy as ent
from . import coupling as coup
from . import gm11
from . import forecasters as fc
from . import diagnostics as diag


def _resource_path(rel):
    """Under PyInstaller the resources live in _MEIPASS; in source mode locate them relative to this file."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, rel)


BASE_DIR = _resource_path("")
DEMO_DIR = _resource_path(os.path.join("data", "demo"))

INDEX_ALIASES = {"mech": ["mech", "u1", "m", "mechanization"],
                 "green": ["green", "u2", "g", "greening"],
                 "dcoord": ["dcoord", "d", "coordination"]}
OUTPUT_COLS = {"M_entropy", "M_equal", "G_entropy", "G_equal", "production", "carbon",
               "region", "province_id", "mech2", "lprod", "lcarb"}


def _norm_province(p):
    """Normalize province names: Chinese -> English, strip whitespace."""
    if p is None:
        return p
    s = str(p).strip()
    if s in ind.CN_PROVINCES:
        return ind.CN_PROVINCES[s]
    return s


def find_col(df, aliases):
    cols_lower = {c.lower().strip(): c for c in df.columns}
    for a in aliases:
        if a in cols_lower:
            return cols_lower[a]
    return None


def detect_level(df):
    """Returns 'index' | 'indicator' | None (unrecognized)."""
    c = {x.lower().strip(): x for x in df.columns}
    has_mech = any(a in c for a in INDEX_ALIASES["mech"])
    has_green = any(a in c for a in INDEX_ALIASES["green"])
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    if has_mech and has_green:
        return "index"
    if len(numeric_cols) >= 3:  # province + year + at least 1 indicator
        return "indicator"
    return None


class AppState:
    def __init__(self):
        self.reset()

    # ---------------- Data management M1 ----------------
    def reset(self):
        self.source = None            # demo | upload | manual
        self.level = None             # index | indicator
        self.panel = None             # long-panel DataFrame
        self.provinces = []
        self.years = []
        self.indicator_cols = []      # indicator level: indicator columns
        self.directions = {}          # {indicator name: ±1}
        self.preset_weights = {}      # paper weights (known indicators)
        self.add_constant = 0.01      # 0.01 constant safeguard
        self.skipped_std = False      # data already standardized, skip M2
        self.weights = None           # entropy weights {sys: {col: w}}
        self.entropy_vals = None
        self.std_df = None
        self.std_meta = None
        self.indices = None           # index panel DataFrame (U1/U2/C/T/D)
        self.alpha, self.beta = 0.5, 0.5
        self.forecasts = None         # batch forecast results list
        self.message = ""

    def set_message(self, m):
        self.message = m

    # Demo data: index-level panel + indicator-level standardized table
    def load_demo(self, level="both"):
        self.reset()
        panel_path = os.path.join(DEMO_DIR, "panel_data_final.xlsx")
        m_path = os.path.join(DEMO_DIR, "mech_standardized.csv")
        g_path = os.path.join(DEMO_DIR, "green_standardized.csv")
        if level in ("both", "index"):
            panel = pd.read_excel(panel_path)
            panel = self._clean_panel(panel)
            self.level = "index"
            self.source = "demo"
            self.panel = panel
            self._init_index_meta(panel)
            self.set_message(f"Demo data (index level) loaded: {len(panel)} rows, "
                             f"{len(self.provinces)} provinces x {len(self.years)} years (2013-2022)")
            return True
        if level in ("both", "indicator"):
            m = pd.read_csv(m_path)
            g = pd.read_csv(g_path)
            m["system"] = "M"
            g["system"] = "G"
            df = pd.concat([m, g], ignore_index=True)
            df = self._clean_panel(df)
            self.level = "indicator"
            self.source = "demo"
            self.panel = df
            self.skipped_std = True   # demo indicator table is already standardized (incl. +0.01)
            self._init_indicator_meta(df)
            self.set_message(f"Demo data (indicator level, already standardized) loaded: "
                             f"{len(self.panel)} indicator records x 2 systems")
            return True
        return False

    def load_upload(self, file_path):
        self.reset()
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".csv":
            raw = None
            for enc in ("utf-8-sig", "gbk", "utf-8"):
                try:
                    raw = pd.read_csv(file_path, encoding=enc)
                    break
                except Exception:
                    continue
            if raw is None:
                raise ValueError("CSV parsing failed (tried UTF-8 / GBK encodings)")
            df = raw
        elif ext in (".xlsx", ".xls"):
            df = self._read_excel_auto(file_path)
        else:
            raise ValueError(f"Unsupported file type: {ext} (supported: .csv/.xlsx/.xls)")
        return self._ingest(df, source="upload")

    def load_manual(self, text):
        self.reset()
        lines = [l.rstrip("\r") for l in text.split("\n") if l.strip()]
        if len(lines) < 2:
            raise ValueError("Manual input needs at least a header line plus one data row")
        header = lines[0]
        sep = "\t" if "\t" in header else (";" if ";" in header else ",")
        rows = [l.split(sep) for l in lines]
        ncol = len(rows[0])
        for r in rows[1:]:
            if len(r) != ncol:
                raise ValueError("Inconsistent column counts; check the separator (Tab / comma / semicolon)")
        df = pd.DataFrame(rows[1:], columns=rows[0])
        return self._ingest(df, source="manual")

    def _read_excel_auto(self, path):
        """Excel: if all sheet names are 4-digit years -> stack the year sheets;
        otherwise take the first sheet."""
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True)
        sheets = wb.sheetnames
        year_sheets = [s for s in sheets if str(s).isdigit() and 1900 <= int(s) <= 2100]
        if year_sheets:
            frames = []
            for s in year_sheets:
                d = pd.read_excel(path, sheet_name=s)
                d = d.rename(columns={c: str(c).strip() for c in d.columns})
                prov_col = None
                for c in d.columns:
                    if "省份" in str(c) or "province" in str(c).lower() or str(c).strip() == "省":
                        prov_col = c
                        break
                if prov_col is None:
                    raise ValueError(f"Sheet '{s}': no province column found (省份/省/province)")
                d = d.rename(columns={prov_col: "province"})
                d["year"] = int(s)
                frames.append(d)
            return pd.concat(frames, ignore_index=True)
        return pd.read_excel(path, sheet_name=0)

    def _clean_panel(self, df):
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        # province column
        prov_col = find_col(df, ["province", "省份", "省", "地区"])
        if prov_col is None:
            raise ValueError("No province column found (province/省份/省)")
        df = df.rename(columns={prov_col: "province"})
        df["province"] = df["province"].map(_norm_province)
        # year column
        year_col = find_col(df, ["year", "年份"])
        if year_col is None:
            raise ValueError("No year column found (year/年份)")
        df = df.rename(columns={year_col: "year"})
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
        df = df.dropna(subset=["province", "year"])
        df = df[df["province"].astype(str) != "nan"]
        df["province"] = df["province"].astype(str)
        df = df[df["province"] != ""]
        return df.reset_index(drop=True)

    def _init_index_meta(self, panel):
        self.provinces = sorted(panel["province"].unique().tolist())
        self.years = sorted(panel["year"].unique().tolist())
        self.indicator_cols = []

    def _init_indicator_meta(self, df):
        drop = {"province", "year", "system"} | OUTPUT_COLS
        cand = [c for c in df.columns if c not in drop and df[c].dtype.kind in "fi"]
        if "system" in df.columns:
            # demo data carries a system column (M/G each with 15 indicators, row-level split)
            m_cols = [c for c in cand if df.loc[df["system"] == "M", c].notna().any()]
            g_cols = [c for c in cand if df.loc[df["system"] == "G", c].notna().any()]
            if not m_cols and not g_cols:
                m_cols, g_cols = cand, []
            self._sys_cols = {"M": m_cols, "G": g_cols}
            self.indicator_cols = list(dict.fromkeys(m_cols + g_cols))
        else:
            self.indicator_cols = cand
            self._sys_cols = {"M": cand, "G": []}
        self.directions = {c: ind.default_direction(c) for c in self.indicator_cols}
        self.preset_weights = {}
        for _, name, _, w in ind.MECH_INDICATORS + ind.GREEN_INDICATORS:
            if name in self.indicator_cols:
                self.preset_weights[name] = w
        self.provinces = sorted(df["province"].unique().tolist())
        self.years = sorted(df["year"].unique().tolist())

    def _ingest(self, df, source):
        df = self._clean_panel(df)
        level = detect_level(df)
        if level is None:
            raise ValueError("Cannot detect the data level: neither an index panel (with mech/green "
                             "columns) nor a panel with enough numeric indicator columns")
        self.source = source
        self.level = level
        self.panel = df
        if level == "index":
            self._init_index_meta(df)
            self.set_message(f"Index-level data loaded: {len(df)} rows, "
                             f"{len(self.provinces)} provinces x {len(self.years)} years")
        else:
            self._init_indicator_meta(df)
            self.set_message(f"Indicator-level data loaded: {len(df)} records, "
                             f"{len(self.indicator_cols)} indicators")
        return {"level": level, "rows": len(df), "provinces": self.provinces,
                "years": self.years, "indicators": self.indicator_cols,
                "message": self.message}

    def _sys_frames(self, std_df=None):
        """Split standardized data by system (M rows/M columns, G rows/G columns);
        returns {sys: DataFrame}."""
        src = std_df if std_df is not None else self.panel
        sys_cols = getattr(self, "_sys_cols", {"M": self.indicator_cols, "G": []})
        frames = {}
        if "system" in self.panel.columns:
            for sys in ("M", "G"):
                mask = (self.panel["system"] == sys).values
                cols = [c for c in sys_cols.get(sys, []) if c in src.columns]
                if mask.any() and cols:
                    frames[sys] = src.loc[mask, cols].reset_index(drop=True)
                else:
                    frames[sys] = None
        else:
            cols = [c for c in self.indicator_cols if c in src.columns]
            frames["M"] = src[cols] if cols else None
            frames["G"] = None
        return frames

    # ---------------- Indicator system & weights M2-M3 ----------------
    def compute_weights(self, directions=None, add_constant=None, skip_std=None):
        if self.level != "indicator":
            raise ValueError("Current data is at the index level; entropy weights require "
                             "indicator-level data (M/G subsystem indicators)")
        if directions:
            for c, d in directions.items():
                if c in self.directions:
                    self.directions[c] = int(d)
        if add_constant is not None:
            self.add_constant = float(add_constant)
        if skip_std is not None:
            self.skipped_std = bool(skip_std)

        if self.skipped_std:
            std_df = self.panel[self.indicator_cols].astype(float)
            std_meta = None
        else:
            std_df, std_meta = pre.standardize(self.panel, self.indicator_cols,
                                               self.directions, self.add_constant)
        self.std_df = std_df
        self.std_meta = std_meta
        frames = self._sys_frames(std_df)
        weights, entropies = {}, {}
        for sys, fr in frames.items():
            if fr is None or fr.shape[1] == 0:
                continue
            w, e = ent.entropy_weights(fr, fr.columns.tolist())
            weights[sys] = w
            entropies[sys] = e
        self.weights = weights
        self.entropy_vals = entropies
        # Compare with the paper's exact entropy weights (possible for demo data)
        refs = {"M": os.path.join(DEMO_DIR, "entropy_weights_mech.csv"),
                "G": os.path.join(DEMO_DIR, "entropy_weights_green.csv")}
        checks = {}
        for sys, ref_path in refs.items():
            if sys in weights:
                chk = diag.check_entropy_weights(weights[sys], ref_path)
                if chk is not None:
                    checks[sys] = chk
        # VIF / correlation (ex-post independence check, paper §2.3)
        vifs, pairs = {}, {}
        for sys, fr in frames.items():
            if fr is None or fr.shape[1] < 2:
                continue
            p, v = diag.vif_corr(fr, fr.columns.tolist())
            vifs[sys] = {"max": max(v.values()), "mean": float(np.mean(list(v.values()))),
                         "vifs": {k: round(x, 2) for k, x in v.items()}}
            pairs[sys] = p
        return {"weights": weights, "entropy": entropies,
                "checks": checks, "vif": vifs, "pairs": pairs,
                "directions": self.directions, "skipped_std": self.skipped_std,
                "add_constant": self.add_constant}

    # ---------------- Index computation M4 ----------------
    def compute_indices(self, alpha=None, beta=None, weights=None):
        if weights is not None:
            self.weights = weights
        if alpha is not None:
            self.alpha = float(alpha)
        if beta is not None:
            self.beta = float(beta)

        if self.level == "index":
            panel = self.panel.copy()
            col_m = find_col(panel, INDEX_ALIASES["mech"])
            col_g = find_col(panel, INDEX_ALIASES["green"])
            # index-level panel values are already paper-convention (mech/green = U - 0.01)
            U1 = panel[col_m].astype(float).values
            U2 = panel[col_g].astype(float).values
            col_d = find_col(panel, INDEX_ALIASES["dcoord"])
            if col_d:
                D_panel = panel[col_d].astype(float).values
            else:
                D_panel = None
        else:
            if not self.weights:
                raise ValueError("Please compute the weights first (indicator-level data needs entropy weights)")
            std_df = self.std_df if self.std_df is not None else self.panel
            frames = self._sys_frames(std_df)
            # paper convention: composite index minus the constant -> U1/U2 (matches panel mech/green)
            Um = ent.composite_index(frames["M"], frames["M"].columns.tolist(),
                                     self.weights["M"]) if frames.get("M") is not None else np.zeros(len(self.panel))
            if frames.get("G") is not None:
                Ug = ent.composite_index(frames["G"], frames["G"].columns.tolist(),
                                         self.weights["G"])
            else:
                Ug = np.zeros(len(self.panel))
            U1 = Um - self.add_constant
            U2 = Ug - self.add_constant
            panel = self.panel.copy()
            D_panel = None
            if "system" in panel.columns:
                # demo indicator table: merge M rows and G rows back into a long panel
                pm = self.panel[self.panel["system"] == "M"].reset_index(drop=True)
                pg = self.panel[self.panel["system"] == "G"].reset_index(drop=True)
                pm["U1"] = U1
                pg["U2"] = U2
                panel = pm.merge(pg[["province", "year", "U2"]],
                                 on=["province", "year"], how="outer")
                U1 = panel["U1"].astype(float).values
                U2 = panel["U2"].astype(float).values
            else:
                panel["U1"] = U1
                panel["U2"] = U2
        C, T, D = coup.coupling_coordination(U1, U2, self.alpha, self.beta)
        # Compare with the panel's existing D (if provided)
        d_check = None
        if D_panel is not None:
            diff = np.abs(D - D_panel)
            d_check = {"max_diff": float(diff.max()),
                       "mean_diff": float(diff.mean())}
            D = D_panel  # panel D is authoritative (paper convention)
        out = panel.copy()
        out["U1"] = U1
        out["U2"] = U2
        out["C"] = C
        out["T"] = T
        out["D"] = D
        out["level"] = [coup.classify_d(d)["level"] for d in D]
        out["level_en"] = [coup.classify_d(d)["level_en"] for d in D]
        self.indices = out
        return {"indices": out, "d_check": d_check, "alpha": self.alpha, "beta": self.beta,
                "add_constant": self.add_constant, "levels": coup.LEVELS}

    # ---------------- Forecasting M5 ----------------
    def series_list(self):
        """Available forecast series: province x variable (M/G/D)."""
        if self.indices is None:
            raise ValueError("Please compute the indices first (indicator level needs weights and indices)")
        out = []
        for prov in self.provinces:
            sub = self.indices[self.indices["province"] == prov].sort_values("year")
            years = sub["year"].tolist()
            for var, col in (("M", "U1"), ("G", "U2"), ("D", "D")):
                vals = sub[col].astype(float).tolist()
                out.append({"province": prov, "var": var, "years": years, "values": vals})
        return out

    def _row_for(self, s, methods, B, seed, h):
        """Forecast row for a single series (shared by SSE progress and batch forecasting)."""
        x = np.array(s["values"], dtype=float)
        if len(x) < 4 or np.isnan(x).any():
            return {"province": s["province"], "var": s["var"],
                    "error": "Series missing/too short", "reliable": False}
        r = fc.forecast_series(x, h=h, methods=methods, B=B, seed=seed,
                               years=s["years"])
        r.update({"province": s["province"], "var": s["var"], "years": s["years"],
                  "values": s["values"]})
        return r

    def forecast_batch(self, vars=("M", "G", "D"), methods=("gm11", "arima", "holt"),
                       B=1000, seed=20260829, h=8, progress_cb=None):
        """Batch forecasting (all provinces x selected variables); GM runs on all
        (grading / intervals / cross-model checks included).
        progress_cb(done, total, current_name) optional: called after each series."""
        series = self.series_list()
        total = sum(1 for s in series if s["var"] in vars)
        rows = []
        done = 0
        for s in series:
            if s["var"] not in vars:
                continue
            row = self._row_for(s, methods, B, seed, h)
            rows.append(row)
            done += 1
            if progress_cb:
                progress_cb(done, total, f"{s['province']} {s['var']}")
        self.forecasts = rows
        stats = fc.coverage_stats(rows)
        return {"forecasts": rows, "coverage": stats,
                "params": {"B": B, "seed": seed, "h": h, "methods": list(methods)}}

    def forecast_single(self, province, var, methods=("gm11", "arima", "holt", "verhulst", "narx", "quad"),
                        B=1000, seed=20260829, h=8):
        for s in self.series_list():
            if s["province"] == province and s["var"] == var:
                x = np.array(s["values"], dtype=float)
                r = fc.forecast_series(x, h=h, methods=methods, B=B, seed=seed,
                                       years=s["years"])
                r.update({"province": province, "var": var, "years": s["years"],
                          "values": s["values"]})
                return r
        raise ValueError(f"Series not found: {province} x {var}")

    # ---------------- Data quality check M1 (paper: completeness checks) ----------------
    def data_quality(self):
        """Completeness checks: missing values / unbalanced panel / short series
        (forecasting needs >= 4 points)."""
        if self.panel is None:
            return {"checked": False}
        df = self.panel
        numeric = df.select_dtypes(include=[np.number]).columns.tolist()
        missing_cells = int(df[numeric].isna().sum().sum())
        # province x year panel balance
        counts = df.groupby("province")["year"].nunique().to_dict()
        max_years = max(counts.values()) if counts else 0
        unbalanced = [p for p, n in counts.items() if n < max_years]
        # series length (index level: mech/green/dcoord; indicator level: per province)
        short_series = []
        if self.level == "index":
            col_m = find_col(df, INDEX_ALIASES["mech"])
            if col_m:
                for p, g in df.groupby("province"):
                    if g[col_m].notna().sum() < 4:
                        short_series.append(p)
        return {
            "checked": True,
            "n_rows": len(df), "n_provinces": len(self.provinces),
            "n_years": len(self.years), "years": self.years,
            "missing_cells": missing_cells,
            "unbalanced": unbalanced,
            "short_series": short_series,
            "balanced": len(unbalanced) == 0,
        }

    # ---------------- Early warning M6 ----------------
    def early_warning(self):
        if self.forecasts is None:
            raise ValueError("Please run the batch forecast first")
        rows = []
        # combined rule: mechanization rising while greening stagnant (paper M6 example #2)
        by_prov = {}
        for r in self.forecasts:
            if "error" in r:
                continue
            by_prov.setdefault(r["province"], {})[r["var"]] = r
        for r in self.forecasts:
            if "error" in r:
                continue
            gm = r.get("gm11")
            if not gm:
                continue
            last = r["values"][-1]
            delta = gm["f2030"] - last
            flags = []
            if gm["reliable"] and delta < -0.005:
                flags.append(f"{r['var']} reliable grade {gm['grade']}, projected decline to 2030 "
                             f"{delta:.3f} (vs 2022) -> decline risk")
            if not gm["reliable"]:
                flags.append(f"{r['var']} grade {gm['grade']} (unreliable, excluded from quantitative interpretation)")
            df_ = r.get("direction_flags") or {}
            for m, v in df_.items():
                if v == "disagree":
                    flags.append(f"direction disagrees with {m} (cross-model divergence -> additional uncertainty)")
            # combined rule: this province's M is reliable and rising while G is stagnant
            # (paper M6: "mechanization rising while greening stagnant")
            if r["var"] == "M" and gm["reliable"] and delta > 0.005:
                g = by_prov.get(r["province"], {}).get("G")
                if g and g.get("gm11"):
                    gg = g["gm11"]
                    if gg["reliable"] and abs(gg["f2030"] - g["values"][-1]) < 0.02:
                        flags.append("mechanization reliably rising while greening stagnant (2030 change < 0.02) -> structural imbalance risk")
            rows.append({"province": r["province"], "var": r["var"],
                         "grade": gm["grade"], "reliable": gm["reliable"],
                         "last": round(last, 4), "f2030": round(gm["f2030"], 4),
                         "delta": round(delta, 4),
                         "ci30": [round(x, 4) for x in gm["ci30"]] if gm["ci30"] else None,
                         "flags": flags,
                         "risk": "High" if (gm["reliable"] and delta < -0.005) else
                                 ("Medium" if (not gm["reliable"]) or (df_ and any(v == "disagree" for v in df_.values())) or
                                  (flags and "structural imbalance" in flags[-1] if flags else False) else "Low")})
        # M6 trend data: per-province D observed series + GM forecast extension (front-end trend chart)
        trend = {}
        if self.indices is not None:
            idx = self.indices.sort_values(["province", "year"])
            for prov in self.provinces:
                sub = idx[idx["province"] == prov]
                trend[prov] = {"years": sub["year"].astype(int).tolist(),
                               "D": [round(float(x), 4) for x in sub["D"]]}
        for r in self.forecasts:
            if r.get("var") == "D" and r.get("gm11") and r["province"] in trend:
                n = len(r["values"])
                pred = r["gm11"]["pred"]
                trend[r["province"]]["pred"] = [round(float(x), 4) for x in pred[n:]]
        return {"rows": rows, "coverage": fc.coverage_stats(self.forecasts),
                "trend": trend}


STATE = AppState()
