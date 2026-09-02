# -*- coding: utf-8 -*-
"""M3 entropy-weighting engine (paper §2.4 conventions): information-entropy weights + composite index.

Formulas (paper Eq.):
    y_ij = x'_ij / Σ_i x'_ij        (x' is the standardized value including the +0.01 constant)
    e_j  = -K * Σ_i y_ij * ln(y_ij),  K = 1/ln(m),  m = number of samples (all province-year rows)
    w_j  = (1 - e_j) / Σ_j (1 - e_j)
    U    = Σ_j w_j * x'_ij           (composite index, including the constant safeguard)
Paper-convention index (identical to panel mech/green) = U - 0.01  (since Σw_j = 1, a 0.01 shift)
"""
import numpy as np
import pandas as pd


def entropy_weights(std_df, indicator_cols):
    """Input: standardized indicator panel (including the +0.01 constant);
    output {column: weight}."""
    m = len(std_df)
    if m < 2:
        raise ValueError("Insufficient sample size to compute entropy weights")
    K = 1.0 / np.log(m)
    w = {}
    e = {}
    for c in indicator_cols:
        y = pd.to_numeric(std_df[c], errors="coerce").astype(float).values
        if y.min() <= 0:
            raise ValueError(f"Indicator '{c}' contains non-positive values; the entropy formula "
                             f"requires y>0 (please confirm the +0.01 constant safeguard was applied)")
        p = y / y.sum()
        with np.errstate(divide="ignore", invalid="ignore"):
            ent = -K * np.sum(p * np.log(p))
        e[c] = float(ent)
        w[c] = float(1.0 - ent)
    s = sum(w.values())
    w = {c: v / s for c, v in w.items()}
    return w, e


def composite_index(std_df, indicator_cols, weights):
    """U = Σ w_j x'_ij (composite index including the +0.01 constant safeguard)."""
    U = np.zeros(len(std_df))
    for c in indicator_cols:
        U = U + weights[c] * pd.to_numeric(std_df[c], errors="coerce").astype(float).values
    return U


def paper_index(U, add_constant=0.01):
    """Paper-convention index = U - 0.01 (removes the constant shift;
    identical to the panel mech/green/dcoord values)."""
    return U - add_constant


def diagnose_entropy(e_list):
    """Entropy diagnostics: returns the per-column information entropy and utility values
    (used by the front end)."""
    return e_list
