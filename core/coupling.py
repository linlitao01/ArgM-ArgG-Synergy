# -*- coding: utf-8 -*-
"""M4 coupling-coordination engine (paper §2.3 conventions, Wang et al. 2021):

    Coupling index:  C = 2*sqrt(U1*U2) / (U1 + U2)
    Coordination index: T = α*U1 + β*U2,   α = β = 0.5 (equal weight, adjustable)
    Coordination degree: D = sqrt(C * T)

Ten-level classification of the coordination degree (the standard scheme behind the
paper's §3.2 statement "barely coordinated to good coordination, primary coordination dominant"):
    [0.0,0.1) Extreme imbalance          [0.1,0.2) Severe imbalance
    [0.2,0.3) Moderate imbalance         [0.3,0.4) Mild imbalance
    [0.4,0.5) On the verge of imbalance  [0.5,0.6) Barely coordinated
    [0.6,0.7) Primary coordination       [0.7,0.8) Intermediate coordination
    [0.8,0.9) Good coordination          [0.9,1.0] High-quality coordination
"""
import numpy as np
import pandas as pd

LEVELS = [
    (0.0, 0.1, "Extreme imbalance"),
    (0.1, 0.2, "Severe imbalance"),
    (0.2, 0.3, "Moderate imbalance"),
    (0.3, 0.4, "Mild imbalance"),
    (0.4, 0.5, "On the verge of imbalance"),
    (0.5, 0.6, "Barely coordinated"),
    (0.6, 0.7, "Primary coordination"),
    (0.7, 0.8, "Intermediate coordination"),
    (0.8, 0.9, "Good coordination"),
    (0.9, 1.0001, "High-quality coordination"),
]


def classify_d(D):
    """Map a coordination degree to its level name. D must lie in [0,1]
    (out-of-range values snap to the nearest level)."""
    d = float(D)
    if d < 0:
        d = 0.0
    if d > 1.0:
        d = 1.0
    for lo, hi, en in LEVELS:
        if lo <= d < hi:
            return {"level": en, "level_en": en, "value": round(d, 4)}
    return {"level": "High-quality coordination", "level_en": "High-quality coordination", "value": round(d, 4)}


def coupling_coordination(U1, U2, alpha=0.5, beta=0.5):
    """Input U1/U2 (paper-convention indices, i.e., after removing the constant)
    -> C, T, D.

    Returns arrays: C, T, D.
    """
    U1 = np.asarray(U1, dtype=float)
    U2 = np.asarray(U2, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        denom = U1 + U2
        C = np.where(denom > 0, 2.0 * np.sqrt(U1 * U2) / denom, 0.0)
        C = np.clip(C, 0.0, 1.0)
    T = alpha * U1 + beta * U2
    D = np.sqrt(np.clip(C * T, 0.0, None))
    return C, T, D


def coupling_frame(panel, alpha=0.5, beta=0.5):
    """Compute C/T/D for a long panel (province, year, U1, U2) with level labels;
    returns a DataFrame."""
    C, T, D = coupling_coordination(panel["U1"].values, panel["U2"].values, alpha, beta)
    out = panel.copy()
    out["C"] = C
    out["T"] = T
    out["D"] = D
    out["level"] = [classify_d(d)["level"] for d in D]
    out["level_en"] = [classify_d(d)["level_en"] for d in D]
    return out
