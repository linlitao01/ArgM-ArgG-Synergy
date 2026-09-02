# -*- coding: utf-8 -*-
"""ArgM&ArgG evaluation system - Flask backend (paper M1-M6 module APIs).

Start: python app.py  ->  http://127.0.0.1:8000
The port can be overridden with the PORT environment variable.

API overview
------------
GET  /api/meta                    indicator presets / provinces / model metadata
GET  /api/status                  current session data status
POST /api/data/demo               {level: both|index|indicator} load demo data
POST /api/data/upload             upload Excel/CSV (multipart file)
POST /api/data/manual             {text} manually pasted data
POST /api/reset                   clear the session
POST /api/weights                 {directions?, add_constant?, skip_std?} entropy weights (M2+M3)
POST /api/indices                 {alpha?, beta?} indices and coupling coordination (M4)
GET  /api/series                  list of available forecast series
POST /api/forecast/batch          {vars?, methods?, B?, seed?, h?} batch forecast (M5)
POST /api/forecast/one            {province, var, ...} single-series multi-model forecast
POST /api/earlywarning            early-warning dashboard (M6)
"""
import io
import json
import os
import sys
import threading
import webbrowser

import numpy as np
import pandas as pd
from flask import Flask, jsonify, request, send_from_directory, Response, stream_with_context

from core import pipeline as pl
from core import indicators as ind
from core import forecasters as fc
from core import coupling as coup

FROZEN = getattr(sys, "frozen", False)


def resource_path(rel):
    """Under PyInstaller the resources live in _MEIPASS; in source mode locate them relative to this file."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


BASE_DIR = resource_path("")
if FROZEN:
    # standalone build: uploads go next to the exe (the temp extraction dir is not writable)
    EXE_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
    UPLOAD_DIR = os.path.join(EXE_DIR, "uploads")
else:
    UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.json.allow_nan = False  # safeguard: any NaN reaching serialization raises (instead of invalid JSON)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # dev: do not cache static files (avoid stale JS after edits)
_lock = threading.Lock()


# ---------------- JSON serialization ----------------
def _clean_float(v):
    """NaN / ±Infinity -> None (browsers reject NaN literals in JSON.parse)."""
    v = float(v)
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return v


def jsonable(obj):
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        return jsonable(obj.to_dict(orient="records"))
    if isinstance(obj, pd.Series):
        return jsonable(obj.tolist())
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return _clean_float(obj)
    if isinstance(obj, np.ndarray):
        return jsonable(obj.tolist())
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if obj is None or isinstance(obj, (str, int, float, bool)):
        if isinstance(obj, float):
            return _clean_float(obj)
        return obj
    return str(obj)


def ok(data=None, **kw):
    out = {"ok": True, **kw}
    if data is not None:
        out["data"] = jsonable(data)
    return jsonify(out)


def err(msg, code=400):
    return jsonify({"ok": False, "error": str(msg)}), code


# ---------------- Pages ----------------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------------- Metadata / status ----------------
@app.route("/api/meta")
def api_meta():
    return ok({
        "indicators": ind.indicator_config(),
        "systems": ind.SYSTEMS,
        "provinces_cn": ind.PROV_CN,
        "regions": {k: {"name": ind.REGION_CN[k], "provinces": v} for k, v in ind.REGIONS.items()},
        "levels": coup.LEVELS,
        "models": fc.MODEL_META,
        "grade_rules": [
            {"grade": "I", "cn": "Good", "rule": "C <= 0.35 and P >= 0.95"},
            {"grade": "II", "cn": "Qualified", "rule": "C <= 0.50 and P >= 0.80"},
            {"grade": "III", "cn": "Barely qualified", "rule": "C <= 0.65 and P >= 0.70"},
            {"grade": "IV", "cn": "Unqualified", "rule": "otherwise"},
        ],
        "demo_files": sorted(os.listdir(os.path.join(BASE_DIR, "data", "demo"))),
        "version": "1.1.0",
    })


@app.route("/api/status")
def api_status():
    with _lock:
        s = pl.STATE
        return ok({
            "source": s.source, "level": s.level,
            "message": s.message,
            "n_rows": len(s.panel) if s.panel is not None else 0,
            "provinces": s.provinces, "years": s.years,
            "indicator_cols": s.indicator_cols,
            "has_weights": bool(s.weights),
            "has_indices": s.indices is not None,
            "has_forecasts": s.forecasts is not None,
            "alpha": s.alpha, "beta": s.beta, "add_constant": s.add_constant,
            "skipped_std": s.skipped_std,
            "directions": s.directions,
        })


@app.route("/api/data/preview")
def api_data_preview():
    """Raw data preview (first 50 rows, no computation) + M1 completeness checks."""
    with _lock:
        s = pl.STATE
        if s.panel is None:
            return ok({"rows": [], "columns": [], "total": 0, "quality": None})
        df = s.panel.head(50)
        return ok({"rows": jsonable(df), "columns": [str(c) for c in df.columns],
                   "total": len(s.panel), "quality": jsonable(s.data_quality())})


# ---------------- Data management M1 ----------------
@app.route("/api/data/demo", methods=["POST"])
def api_data_demo():
    level = (request.get_json(silent=True) or {}).get("level", "both")
    with _lock:
        try:
            pl.STATE.load_demo(level)
            return ok({"level": pl.STATE.level, "rows": len(pl.STATE.panel),
                       "message": pl.STATE.message})
        except Exception as e:
            return err(e)


@app.route("/api/data/upload", methods=["POST"])
def api_data_upload():
    f = request.files.get("file")
    if f is None:
        return err("Missing file field 'file'")
    name = f.filename or "upload"
    path = os.path.join(UPLOAD_DIR, name)
    f.save(path)
    with _lock:
        try:
            info = pl.STATE.load_upload(path)
            return ok(info)
        except Exception as e:
            return err(e)


@app.route("/api/data/manual", methods=["POST"])
def api_data_manual():
    body = request.get_json(silent=True) or {}
    text = body.get("text", "")
    if not text.strip():
        return err("No data text provided")
    with _lock:
        try:
            info = pl.STATE.load_manual(text)
            return ok(info)
        except Exception as e:
            return err(e)


@app.route("/api/reset", methods=["POST"])
def api_reset():
    with _lock:
        pl.STATE.reset()
        return ok({"message": "Session reset"})


# ---------------- Indicator system & weights M2-M3 ----------------
@app.route("/api/weights", methods=["POST"])
def api_weights():
    body = request.get_json(silent=True) or {}
    with _lock:
        try:
            r = pl.STATE.compute_weights(
                directions=body.get("directions"),
                add_constant=body.get("add_constant"),
                skip_std=body.get("skip_std"))
            return ok(r)
        except Exception as e:
            return err(e)


# ---------------- Index computation M4 ----------------
@app.route("/api/indices", methods=["POST"])
def api_indices():
    body = request.get_json(silent=True) or {}
    with _lock:
        try:
            r = pl.STATE.compute_indices(alpha=body.get("alpha"), beta=body.get("beta"))
            # table for the front end: sorted by province x year, key columns only
            # (avoid leaking internal columns into the response)
            df = r["indices"].sort_values(["province", "year"])
            key_cols = [c for c in ["province", "year", "U1", "U2", "C", "T", "D",
                                    "level", "level_en"] if c in df.columns]
            out = {k: v for k, v in r.items() if k != "indices"}
            out["table"] = df[key_cols]
            out["levels"] = coup.LEVELS
            return ok(out)
        except Exception as e:
            return err(e)


# ---------------- Forecasting M5 ----------------
@app.route("/api/series")
def api_series():
    with _lock:
        try:
            lst = pl.STATE.series_list()
            # slim: omit full value series (the front end fetches them on demand)
            slim = [{k: v for k, v in s.items() if k != "values"} for s in lst]
            return ok({"series": slim})
        except Exception as e:
            return err(e)


@app.route("/api/forecast/batch", methods=["POST"])
def api_forecast_batch():
    body = request.get_json(silent=True) or {}
    B = int(body.get("B", 1000))
    h = int(body.get("h", 8))
    if B < 10:
        return err("Bootstrap sample size B must be at least 10")
    if not 1 <= h <= 30:
        return err("Forecast horizon h must be between 1 and 30")
    with _lock:
        try:
            r = pl.STATE.forecast_batch(
                vars=tuple(body.get("vars", ["M", "G", "D"])),
                methods=tuple(body.get("methods", ["gm11", "arima", "holt"])),
                B=B,
                seed=body.get("seed", 20260829),
                h=h)
            return ok(r)
        except Exception as e:
            return err(e)


@app.route("/api/forecast/batch/stream")
def api_forecast_batch_stream():
    """SSE streaming batch forecast: pushes one progress event per series, then a final done event."""
    B = int(request.args.get("B", 1000))
    h = int(request.args.get("h", 8))
    seed = request.args.get("seed", "20260829")
    if seed in ("", "null", "None"):
        seed = None
    else:
        seed = int(seed)
    vars_ = tuple(request.args.get("vars", "M,G,D").split(","))
    methods = tuple(request.args.get("methods", "gm11,arima,holt").split(","))
    if B < 10:
        return err("Bootstrap sample size B must be at least 10")

    def gen():
        try:
            with _lock:
                series = pl.STATE.series_list()
                total = sum(1 for s in series if s["var"] in vars_)
                rows = []
                done = 0
                for s in series:
                    if s["var"] not in vars_:
                        continue
                    row = pl.STATE._row_for(s, methods, B, seed, h)
                    rows.append(row)
                    done += 1
                    ev = {"done": done, "total": total,
                          "current": f"{s['province']} {s['var']}"}
                    yield f"event: progress\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
                result = {"forecasts": jsonable(rows),
                          "coverage": jsonable(fc.coverage_stats(rows)),
                          "params": {"B": B, "seed": seed, "h": h,
                                     "methods": list(methods)}}
                pl.STATE.forecasts = rows  # key: write back to session state (tab 5 depends on it)
                yield f"event: done\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(gen()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/forecast/one", methods=["POST"])
def api_forecast_one():
    body = request.get_json(silent=True) or {}
    prov, var = body.get("province"), body.get("var")
    if not prov or not var:
        return err("Missing province/var")
    B = int(body.get("B", 1000))
    h = int(body.get("h", 8))
    if B < 10:
        return err("Bootstrap sample size B must be at least 10")
    if not 1 <= h <= 30:
        return err("Forecast horizon h must be between 1 and 30")
    with _lock:
        try:
            r = pl.STATE.forecast_single(
                prov, var,
                methods=tuple(body.get("methods",
                                       ["gm11", "arima", "holt", "verhulst", "narx", "quad"])),
                B=B,
                seed=body.get("seed", 20260829),
                h=h)
            return ok(r)
        except Exception as e:
            return err(e)


# ---------------- Early warning M6 ----------------
@app.route("/api/earlywarning", methods=["POST"])
def api_earlywarning():
    with _lock:
        try:
            r = pl.STATE.early_warning()
            return ok(r)
        except Exception as e:
            return err(e)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    if FROZEN:
        # standalone build: automatically step to a free port and open the browser
        for p in range(port, port + 10):
            try:
                import socket
                s = socket.socket()
                s.bind(("127.0.0.1", p))
                s.close()
                port = p
                break
            except OSError:
                continue
        print(f"\n  ArgM&ArgG Evaluation System started: http://127.0.0.1:{port}")
        print(f"  (Close this window to stop the service; uploaded files are saved in: {UPLOAD_DIR})\n")
        webbrowser.open(f"http://127.0.0.1:{port}")
    else:
        print(f"\n  ArgM&ArgG Evaluation System started: http://127.0.0.1:{port}\n")
    app.run(host="127.0.0.1", port=port, threaded=True)
