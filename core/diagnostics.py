# -*- coding: utf-8 -*-
"""Diagnostics (paper §2.3 ex-post independence check conventions):
- pairwise correlation within each system (find near-duplicate indicator pairs with |r| > 0.9)
- VIF (each indicator regressed on the others, R² -> 1/(1-R²))
- entropy weights vs. the paper's exact weights
"""
import numpy as np
import pandas as pd


def vif_corr(df, indicator_cols):
    """Returns (pairs, vifs). pairs: indicator pairs with |r|>0.9; vifs: {column: VIF}."""
    Xall = df[indicator_cols].astype(float).values
    cols = list(indicator_cols)
    R = np.corrcoef(Xall, rowvar=False)
    pairs = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            if abs(R[i, j]) > 0.9:
                pairs.append({"i": cols[i], "j": cols[j], "r": round(float(R[i, j]), 3)})
    vifs = {}
    for j in range(len(cols)):
        y = Xall[:, j]
        X = np.delete(Xall, j, axis=1)
        Xc = np.column_stack([np.ones(len(y)), X])
        coef = np.linalg.lstsq(Xc, y, rcond=None)[0]
        r2 = 1.0 - np.sum((y - Xc @ coef) ** 2) / np.sum((y - y.mean()) ** 2)
        vifs[cols[j]] = float(1.0 / (1.0 - r2))
    return pairs, vifs


def check_entropy_weights(computed, reference_path):
    """computed: {column: weight}; reference_path: entropy_weights_*.csv (indicator, exact_weight).
    Returns (max_diff, full diff dict), or None when the reference file is missing."""
    import os
    if not os.path.exists(reference_path):
        return None
    ref = pd.read_csv(reference_path)
    diffs = {}
    for _, row in ref.iterrows():
        ind = row["indicator"]
        if ind in computed:
            diffs[ind] = float(computed[ind]) - float(row["exact_weight"])
    if not diffs:
        return None
    return {"max_diff": max(abs(v) for v in diffs.values()), "diffs": diffs}
