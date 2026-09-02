# -*- coding: utf-8 -*-
"""M5 forecaster collection: paper benchmarks (ARIMA(1,1,0), Holt) + nonlinear models
(Verhulst grey, NARX-BP neural network, quadratic trend) + Algorithm 1 Step 9 cross-model checks.

- ARIMA(1,1,0) with drift, Holt linear trend: bit-identical to _robustness.py / Stata rerun
  (regression-test benchmark).
- Verhulst grey model (power form of GM(1,1), dx/dt + a·x = b·x²): nonlinear, suited to
  S-shaped/saturating growth.
- NARX-BP: recurrent neural network with exogenous inputs (pure numpy: tanh hidden layer +
  linear output, sliding window [x(t-1), x(t-2)] -> x(t), median over multiple starts,
  reproducible with a fixed seed).
- Quadratic polynomial trend: x ~ c0 + c1·t + c2·t² (the t² term is the nonlinear part).
"""
import numpy as np

MODEL_META = {
    "gm11":    {"name": "GM(1,1) Grey Model", "kind": "Paper core (linear, first-order)", "nonlinear": False},
    "verhulst": {"name": "Verhulst Grey Model", "kind": "Nonlinear (dx/dt + ax = bx²)", "nonlinear": True},
    "narx":    {"name": "NARX-BP Neural Network", "kind": "Nonlinear (recurrent neural network)", "nonlinear": True},
    "quad":    {"name": "Quadratic Polynomial Trend", "kind": "Nonlinear (t² term)", "nonlinear": True},
    "arima":   {"name": "ARIMA(1,1,0) with Drift", "kind": "Benchmark (linear)", "nonlinear": False},
    "holt":    {"name": "Holt Linear Trend", "kind": "Benchmark (linear)", "nonlinear": False},
}


def arima110(x, h=8):
    """ARIMA(1,1,0) with drift; returns the full h-step forecast sequence (length h)."""
    x = np.asarray(x, dtype=float)
    d = np.diff(x)
    X = np.column_stack([d[:-1], np.ones(len(d) - 1)])
    phi, c = np.linalg.lstsq(X, d[1:], rcond=None)[0]
    dh = d[-1]
    fc = []
    for _ in range(h):
        dh = c + phi * dh
        fc.append(dh)
    return x[-1] + np.cumsum(fc)


def holt(x, h=8):
    """Holt linear-trend exponential smoothing: α,β ∈ [0.05,0.95] in 0.05 steps,
    minimizing one-step-ahead forecast SSE."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    best = (None, None, None)
    for a in np.arange(0.05, 1.0, 0.05):
        for b in np.arange(0.05, 1.0, 0.05):
            l, bb = x[0], (x[1] - x[0]) if n > 1 else 0.0
            sse = 0.0
            for t in range(1, n):
                sse += (x[t] - (l + bb)) ** 2
                lnew = a * x[t] + (1 - a) * (l + bb)
                bb = b * (lnew - l) + (1 - b) * bb
                l = lnew
            if best[0] is None or sse < best[0]:
                best = (sse, a, b)
    _, a, b = best
    l, bb = x[0], (x[1] - x[0]) if n > 1 else 0.0
    for t in range(1, n):
        lnew = a * x[t] + (1 - a) * (l + bb)
        bb = b * (lnew - l) + (1 - b) * bb
        l = lnew
    return l + np.arange(1, h + 1) * bb


def verhulst(x, h=8):
    """Verhulst grey model (nonlinear). Discretized: x0(k) + a·z1(k) = b·(z1(k))².
    Time response: x1(k) = a·x1(0) / (b·x1(0) + (a - b·x1(0))·e^{a·k})
    Returns (forecast sequence, params dict); degenerates to GM(1,1) when b≈0.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    x1 = np.cumsum(x)
    z1 = (x1[:-1] + x1[1:]) / 2.0
    B = np.column_stack([-z1, z1 ** 2])
    Y = x[1:]
    a, b = np.linalg.lstsq(B, Y, rcond=None)[0]
    if abs(b) < 1e-12:
        from .gm11 import gm11
        m = gm11(x, h)
        return m["pred"], {"a": a, "b": b, "fallback": "GM(1,1)"}
    x10 = x1[0]
    K = n + h
    denom0 = b * x10 + (a - b * x10)
    x1p = np.empty(K)
    for k in range(1, K + 1):
        denom = b * x10 + (a - b * x10) * np.exp(a * k)
        if abs(denom) < 1e-14:
            return np.full(K, np.nan), {"a": a, "b": b, "blowup": True}
        x1p[k - 1] = a * x10 / denom
    x1p_full = np.concatenate([[x10], x1p])
    pred = np.empty(K)
    pred[0] = x1p_full[0]
    pred[1:] = np.diff(x1p_full[: n + h])
    return pred, {"a": a, "b": b, "fallback": None}


def _narx_fit(x, n_in, n_hid, epochs, lr, lam, seed):
    """Train one NARX-BP network. Returns (W1, b1, W2, b2, xmu, xsig) or None on failure."""
    rng = np.random.default_rng(seed)
    n = len(x)
    if n <= n_in + 1:
        return None
    # window samples: input [x(t-1),...,x(t-n_in)] -> output x(t)
    Xs = []
    ys = []
    for t in range(n_in, n):
        Xs.append(x[t - n_in: t])
        ys.append(x[t])
    X = np.array(Xs)          # (n-n_in, n_in)
    y = np.array(ys)          # (n-n_in,)
    xmu, xsig = X.mean(0), X.std(0) + 1e-9
    ymu, ysig = y.mean(), y.std() + 1e-9
    Xn = (X - xmu) / xsig
    yn = (y - ymu) / ysig
    W1 = rng.normal(0, 0.5, (n_in, n_hid))
    b1 = np.zeros(n_hid)
    W2 = rng.normal(0, 0.5, (n_hid, 1))
    b2 = 0.0
    vW1 = np.zeros_like(W1); vb1 = np.zeros_like(b1)
    vW2 = np.zeros_like(W2); vb2 = 0.0
    mom = 0.9
    for ep in range(epochs):
        H = np.tanh(Xn @ W1 + b1)
        out = H @ W2 + b2
        err = out.ravel() - yn
        gW2 = H.T @ err[:, None] + lam * W2
        gb2 = err.sum()
        gH = err[:, None] @ W2.T * (1 - H ** 2)
        gW1 = Xn.T @ gH + lam * W1
        gb1 = gH.sum(0)
        vW1 = mom * vW1 - lr * gW1; vb1 = mom * vb1 - lr * gb1
        vW2 = mom * vW2 - lr * gW2; vb2 = mom * vb2 - lr * gb2
        W1 += vW1; b1 += vb1; W2 += vW2; b2 += vb2
        if np.isnan(out).any() or np.abs(out).max() > 1e6:
            return None
    return (W1, b1, W2, b2, xmu, xsig, ymu, ysig)


def narx(x, h=8, n_in=2, n_hid=5, epochs=400, lr=0.05, lam=1e-3, restarts=5, seed=20260829):
    """NARX-BP recursive forecasting: median over multiple training starts
    (fixed seed family -> reproducible)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 4:
        raise ValueError("NARX requires at least 4 observations")
    preds = []
    params_ok = []
    for r in range(restarts):
        p = _narx_fit(x, n_in, n_hid, epochs, lr, lam, seed + r * 7919)
        if p is None:
            continue
        params_ok.append(p)
        W1, b1, W2, b2, xmu, xsig, ymu, ysig = p
        window = x[-n_in:].copy()
        fc = np.empty(h)
        for t in range(h):
            xn = (window - xmu) / xsig
            H = np.tanh(xn @ W1 + b1)
            out = float(H @ W2 + b2) * ysig + ymu
            fc[t] = out
            window = np.roll(window, -1)
            window[-1] = out
        preds.append(fc)
    if not preds:
        raise ValueError("NARX training failed (divergence); adjust parameters or use another model")
    return np.median(np.array(preds), axis=0), {"restarts": len(preds), "n_in": n_in, "n_hid": n_hid}


def quad_trend(x, h=8):
    """Quadratic polynomial trend x ~ c0 + c1·t + c2·t² (t=0,1,...)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    t = np.arange(n, dtype=float)
    X = np.column_stack([np.ones(n), t, t ** 2])
    coef = np.linalg.lstsq(X, x, rcond=None)[0]
    tf = np.arange(n, n + h, dtype=float)
    Xf = np.column_stack([np.ones(h), tf, tf ** 2])
    return Xf @ coef, {"c0": coef[0], "c1": coef[1], "c2": coef[2]}


def forecast_series(x, h=8, methods=("gm11", "arima", "holt"), seed=20260829, B=1000,
                    years=None):
    """Run multiple models on a single series; returns a result dict
    (including the Algorithm 1 Step 9 direction-consistency flags)."""
    from .gm11 import forecast_one
    x = np.asarray(x, dtype=float)
    n = len(x)
    out = {"n": n}
    for mname in methods:
        try:
            if mname == "gm11":
                r = forecast_one(x, h=h, B=B, seed=seed, years=years)
                out["gm11"] = r
            elif mname == "arima":
                fc = arima110(x, h)
                out["arima"] = {"pred": fc.tolist(), "f2030": float(fc[-1]),
                                "f_horizon_end": float(fc[-1])}
            elif mname == "holt":
                fc = holt(x, h)
                out["holt"] = {"pred": fc.tolist(), "f2030": float(fc[-1]),
                               "f_horizon_end": float(fc[-1])}
            elif mname == "verhulst":
                fc, params = verhulst(x, h)
                out["verhulst"] = {"pred": fc.tolist(), "params": params,
                                   "f2030": float(fc[-1]) if not np.isnan(fc[-1]) else None}
            elif mname == "narx":
                fc, params = narx(x, h=h, seed=seed)
                out["narx"] = {"pred": fc.tolist(), "params": params,
                               "f2030": float(fc[-1])}
            elif mname == "quad":
                fc, params = quad_trend(x, h)
                out["quad"] = {"pred": fc.tolist(), "params": params,
                               "f2030": float(fc[-1])}
            else:
                raise ValueError(f"Unknown model {mname}")
        except Exception as e:  # a single model failure must not break the whole run
            out["methods"][mname] = {"error": str(e)}
            continue
    # Algorithm 1 Step 9: direction consistency of GM vs ARIMA/Holt
    # (paper convention: sign(f2030 - f2025))
    if "gm11" in out and out["gm11"].get("reliable"):
        s = np.sign(out["gm11"]["f2030"] - out["gm11"]["f2025"])
        flags = {}
        for mname in ("arima", "holt", "verhulst", "narx", "quad"):
            r = out.get(mname)
            if r and "f2030" in r and r["f2030"] is not None and s != 0:
                sm = np.sign(r["f2030"] - out["gm11"]["f2025"])
                r["direction_agree"] = bool(sm == s)
                flags[mname] = "agree" if sm == s else "disagree"
        out["direction_flags"] = flags
        out["direction_agree_all"] = all(v == "agree" for v in flags.values()) if flags else None
    return out


def coverage_stats(forecast_results):
    """Coverage statistics (paper convention): reliable-series counts per variable."""
    stats = {"M": {"reliable": 0, "total": 0, "unreliable_provs": []},
             "G": {"reliable": 0, "total": 0, "unreliable_provs": []},
             "D": {"reliable": 0, "total": 0, "unreliable_provs": []}}
    for r in forecast_results:
        if "error" in r:
            continue
        gm = r.get("gm11") or {}
        v = r["var"]
        stats[v]["total"] += 1
        if gm.get("reliable"):
            stats[v]["reliable"] += 1
        else:
            stats[v]["unreliable_provs"].append(r["province"])
    return stats
