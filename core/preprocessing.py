# -*- coding: utf-8 -*-
"""M2 preprocessing: direction-aware min-max standardization + 0.01 constant safeguard
(paper §2.4 conventions).

Positive indicator: x' = (x - xmin)/(xmax - xmin)
Negative indicator: x' = (xmax - x)/(xmax - xmin)
A constant of 0.01 is then added to eliminate zero/negative values -> [0.01, 1.01].
Standardization is pooled over the full sample (all province-year rows), consistent
with the paper's original computation tables.
"""
import numpy as np
import pandas as pd


def standardize(df, indicator_cols, directions, add_constant=0.01):
    """Direction-aware min-max standardization of a long panel df
    (must contain the numeric columns in indicator_cols).

    Parameters
    ----------
    df : DataFrame with the indicator_cols columns
    indicator_cols : list[str]
    directions : dict[str, +1/-1], direction of each indicator
    add_constant : float, 0 to disable the constant safeguard

    Returns
    -------
    out : DataFrame with only the indicator_cols standardized values (constant included)
    meta : dict, per-column min/max (for front-end display and verification)
    """
    out = pd.DataFrame(index=df.index)
    meta = {}
    for c in indicator_cols:
        v = pd.to_numeric(df[c], errors="coerce").astype(float)
        if v.isna().any():
            raise ValueError(f"Indicator '{c}' contains missing or non-numeric values; cannot standardize")
        vmin, vmax = float(v.min()), float(v.max())
        d = int(directions.get(c, +1))
        if vmax > vmin:
            s = (v - vmin) / (vmax - vmin)
            if d < 0:
                s = 1.0 - s
        else:
            s = pd.Series(0.0, index=v.index)  # constant column
        out[c] = s + add_constant
        meta[c] = {"min": round(vmin, 6), "max": round(vmax, 6),
                   "direction": d, "add_constant": add_constant}
    return out, meta


def already_standardized(df, indicator_cols, tol=1e-6):
    """Heuristic check of whether data is already in [0.01, 1.01] standardized form
    (used to skip M2)."""
    if len(indicator_cols) == 0:
        return False
    v = pd.to_numeric(df[indicator_cols[0]], errors="coerce")
    if v.isna().any():
        return False
    lo, hi = float(v.min()), float(v.max())
    return lo >= -tol and hi <= 1.01 + tol and lo >= 0.01 - 0.1 and hi > 0.5
