# -*- coding: utf-8 -*-
"""M5 GM(1,1) reference implementation (paper Algorithm 1 / §2.4 conventions,
consistent with _robustness.py and the Stata rerun):

1. 1-AGO accumulation to obtain X(1)
2. Design matrix B, data vector Y
3. Least squares [α, μ]^T = (B^T B)^{-1} B^T Y
4. Time-response function + IAGO restoration of forecasts
5. Fitting residuals (including the k=1 zero residual); S1 = std(X(0)) (ddof=1), S2 = std(residuals) (ddof=1)
6. Grading: posterior error ratio C = S2/S1, small error probability P = mean(|res - res̄| < 0.6745*S1)
   I: C<=0.35 and P>=0.95; II: C<=0.50 and P>=0.80; III: C<=0.65 and P>=0.70; otherwise IV
7. Grade I/II -> 1000 residual-resample bootstrap 90% interval (5%/95% percentiles)
8. Grade III/IV -> "unreliable" flag, excluded from quantitative interpretation
"""
import numpy as np

GRADE_RULES = [
    (0.35, 0.95, "I", "Good"),
    (0.50, 0.80, "II", "Qualified"),
    (0.65, 0.70, "III", "Barely qualified"),
    (np.inf, -np.inf, "IV", "Unqualified"),
]


def gm11(x, h=8):
    """GM(1,1); returns dict: alpha, mu, C, P, pred (length n+h), res (length n)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    x1 = np.cumsum(x)
    B = np.column_stack([-(x1[:-1] + x1[1:]) / 2.0, np.ones(n - 1)])
    Y = x[1:]
    a, mu = np.linalg.lstsq(B, Y, rcond=None)[0]
    K = n + h
    x1p = np.empty(K)
    x1p[0] = x[0]
    for k in range(1, K):
        x1p[k] = (x[0] - mu / a) * np.exp(-a * k) + mu / a
    pred = np.empty(K)
    pred[0] = x1p[0]
    pred[1:] = np.diff(x1p)
    fit = pred[:n]
    res = x - fit                      # includes the k=1 zero residual
    S2 = res.std(ddof=1)
    S1 = x.std(ddof=1)
    C = S2 / S1
    ebar = res.mean()
    P = float(np.mean(np.abs(res - ebar) < 0.6745 * S1))
    return {"alpha": float(a), "mu": float(mu), "C": float(C), "P": float(P),
            "pred": pred, "res": res}


def grade_of(C, P):
    """Joint C&P grading rule."""
    for c_th, p_th, g, gname in GRADE_RULES:
        if C <= c_th and P >= p_th:
            return {"grade": g, "grade_name": gname}
    return {"grade": "IV", "grade_name": "Unqualified"}


def bootstrap_ci(x, B=1000, h=8, seed=20260829):
    """Residual bootstrap 90% interval (5%/95% percentiles);
    returns (lo25, hi25, lo30, hi30)."""
    base = gm11(x, h)
    n = len(x)
    res = base["res"]
    rng = np.random.default_rng(seed)
    f25, f30 = [], []
    for _ in range(B):
        eb = rng.choice(res, size=n, replace=True)
        y = base["pred"][:n] + eb
        m = gm11(y, h)
        f25.append(m["pred"][n + 2])   # 2025 = n=10 -> index 12
        f30.append(m["pred"][n + 7])   # 2030 = index 17
    return (float(np.percentile(f25, 5)), float(np.percentile(f25, 95)),
            float(np.percentile(f30, 5)), float(np.percentile(f30, 95)))


def forecast_one(x, h=8, B=1000, seed=20260829, years=None):
    """Full Algorithm 1 (without Step 9 cross-model checks; see forecasters.compare_models).

    Returns dict: alpha/mu/C/P/grade/fit/pred/ci/flag/reliable.
    years: observed year list (length n), used to locate the 2025/2030 forecast points;
           if omitted, the paper convention n=10 and 2013-2022 -> 2025=index n+2, 2030=index n+7.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    m = gm11(x, h)
    g = grade_of(m["C"], m["P"])
    pred = m["pred"]
    # 2025/2030 indices: paper fixes n=10 (2013-2022), horizon 2023-2030 (H=8) -> n+2/n+7;
    # user data is located by observed first year: idx = target - first_year (valid within [0, n+h))
    idx2025, idx2030 = n + 2, n + 7
    if years is not None and len(years) == n:
        first = int(min(years))
        for target in (2025, 2030):
            i = target - first
            if 0 <= i < n + h:
                if target == 2025:
                    idx2025 = i
                else:
                    idx2030 = i
    out = {
        "alpha": m["alpha"], "mu": m["mu"], "C": m["C"], "P": m["P"],
        "grade": g["grade"], "grade_name": g["grade_name"],
        "reliable": g["grade"] in ("I", "II"),
        "pred": pred.tolist(), "res": m["res"].tolist(),
        "f2025": float(pred[idx2025]), "f2030": float(pred[idx2030]),
        "unreliable_flag": g["grade"] in ("III", "IV"),
    }
    if out["reliable"]:
        lo25, hi25, lo30, hi30 = bootstrap_ci(x, B=B, h=h, seed=seed)
        out["ci25"] = [round(lo25, 6), round(hi25, 6)]
        out["ci30"] = [round(lo30, 6), round(hi30, 6)]
        out["bootstrap"] = {"B": B, "seed": seed, "method": "Residual bootstrap 90% percentile interval"}
    else:
        out["ci25"] = None
        out["ci30"] = None
        out["bootstrap"] = None
    return out
