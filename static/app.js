/* ArgM&ArgG Evaluation System - front-end logic */
"use strict";

const $ = (id) => document.getElementById(id);
let META = null;
const charts = {};

async function api(path, body, isForm) {
  const isGet = body === undefined;
  const opts = { method: isGet ? "GET" : "POST" };
  if (isForm) {
    opts.body = body;
  } else if (!isGet) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(path, opts);
  const j = await r.json().catch(() => ({ ok: false, error: "Failed to parse the response" }));
  if (!j.ok) throw new Error(j.error || "Request failed");
  return j.data;
}

function msg(el, text, type) {
  el.textContent = text;
  el.className = "msg show " + (type || "ok");
}
function fmt(x, n = 4) {
  if (x === null || x === undefined) return "—";
  const v = Number(x);
  if (Number.isNaN(v)) return String(x);        // non-numeric (province names etc.) shown as-is
  if (Number.isInteger(v)) return String(v);    // integers (years etc.) without decimals
  return v.toFixed(n);
}
function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function provCn(p) {
  return p;   // English province names are used throughout
}
function gradePill(g) {
  const cls = { I: "g1", II: "g2", III: "g3", IV: "g4" }[g] || "";
  return `<span class="pill ${cls}">Grade ${g}</span>`;
}
function chart(id, option) {
  let c = charts[id];
  const dom = $(id);
  if (!dom) return null;
  // Key fix: after innerHTML replaces the DOM, the old instance is bound to a detached node
  // and setOption would draw off-screen -> detect isConnected and rebuild if stale
  if (c && !c.getDom().isConnected) {
    try { c.dispose(); } catch (e) { /* ignore */ }
    delete charts[id];
    c = null;
  }
  if (!c) { c = echarts.init(dom); charts[id] = c; }
  c.setOption(option, true);
  return c;
}
function disposeAllCharts() {
  Object.values(charts).forEach((c) => { try { c.dispose(); } catch (e) { /* ignore */ } });
  for (const k of Object.keys(charts)) delete charts[k];
}
function clearResults() {
  disposeAllCharts();
  for (const id of ["weightsResult", "indicesResult", "forecastResult", "warningResult"]) {
    const el = $(id);
    if (el) el.innerHTML = "";
  }
  for (const id of ["dataMsg", "weightsMsg", "indicesMsg", "forecastMsg", "warningMsg"]) {
    const el = $(id);
    if (el) el.className = "msg";
  }
  directionOverride = {};
}
function resizeCharts() {
  Object.values(charts).forEach((c) => c && c.resize());
}
window.addEventListener("resize", resizeCharts);

/* ---------------- Tabs ---------------- */
document.querySelectorAll(".tab").forEach((t) => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    $("tab-" + t.dataset.tab).classList.add("active");
    resizeCharts();
  });
});

/* ---------------- Initialization ---------------- */
(async function init() {
  try {
    META = await api("/api/meta", undefined);
    renderAbout();
    refreshStatus();
  } catch (e) { console.error(e); }
})();

/* Auto demo mode: ?autodemo=weights|indices|forecast|warning  (also used for regression screenshots) */
const AUTO_DEMO = new URLSearchParams(location.search).get("autodemo");
(async function autodemo() {
  if (!AUTO_DEMO) return;
  while (!META) await new Promise((r) => setTimeout(r, 50));  // wait for metadata
  try {
    const level = (AUTO_DEMO === "weights") ? "indicator" : "index";
    const d = await api("/api/data/demo", { level });
    msg($("dataMsg"), d.message, "ok");
    if (AUTO_DEMO === "weights") {
      const w = await api("/api/weights", {});
      msg($("weightsMsg"), "Entropy weights computed.", "ok");
      renderWeights(w);
      $("tab-weights").scrollIntoView({ behavior: "instant" });
    } else {
      const i = await api("/api/indices", {});
      renderIndices(i);
      if (AUTO_DEMO === "forecast") {
        const f = await api("/api/forecast/batch", { B: 1000 });
        renderForecastBatch(f);
        const one = await api("/api/forecast/one", { province: "Guizhou", var: "M" });
        renderForecastOne(one);
        await loadSeriesSelect();
        $("seriesSelect").value = "Guizhou|M";
        msg($("forecastMsg"), "Auto demo: batch forecast + single series (Guizhou M, incl. nonlinear models).", "ok");
      } else if (AUTO_DEMO === "warning") {
        const f = await api("/api/forecast/batch", { B: 1000 });
        const w = await api("/api/earlywarning", {});
        renderWarning(w);
        msg($("warningMsg"), "Auto demo: early-warning dashboard.", "ok");
      }
    }
    await refreshStatus();
    document.querySelector(`.tab[data-tab="${AUTO_DEMO}"]`).click();
    window.__AUTODEMO_DONE = true;
  } catch (e) {
    console.error("autodemo failed:", e);
    msg($("dataMsg"), "Auto demo failed: " + e.message, "err");
    window.__AUTODEMO_DONE = true;
  }
})();

async function refreshStatus() {
  try {
    const s = await api("/api/status", undefined);
    $("statusChip").textContent = s.n_rows > 0 ? `${s.n_rows} rows · ${s.level === "index" ? "index level" : "indicator level"} · ${s.provinces.length} provinces` : "No data loaded";
    // dynamic batch button label (series count = provinces × 3 variables)
    if (s.provinces.length) {
      $("btnForecastAll").textContent = `⚡ Forecast All ${s.provinces.length * 3} Series in Batch (M/G/D)`;
    }
    if (s.level === "indicator" && s.indicator_cols.length) {
      $("skipStd").checked = !!s.skipped_std;
      $("addConstant").value = s.add_constant;
      renderDirectionEditor(s);
    }
    loadSeriesSelect();
  } catch (e) { /* ignore */ }
}

/* ---------------- 1. Data management ---------------- */
$("btnDemo").addEventListener("click", async () => {
  try {
    const d = await api("/api/data/demo", { level: "index" });
    clearResults();
    msg($("dataMsg"), d.message, "ok");
    await refreshStatus();
    await previewData();
  } catch (e) { msg($("dataMsg"), e.message, "err"); }
});
$("btnDemoInd").addEventListener("click", async () => {
  try {
    const d = await api("/api/data/demo", { level: "indicator" });
    clearResults();
    msg($("dataMsg"), d.message + ". Go to tab 2 (Indicators & Weights) to compute entropy weights, then tab 3 (Index Computation) for coupling coordination.", "ok");
    await refreshStatus();
    await previewData();
  } catch (e) { msg($("dataMsg"), e.message, "err"); }
});
$("btnReset").addEventListener("click", async () => {
  await api("/api/reset", {});
  location.reload();
});
$("fileInput").addEventListener("change", async (ev) => {
  const f = ev.target.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  try {
    const d = await api("/api/data/upload", fd, true);
    clearResults();
    msg($("dataMsg"), `${d.message} (detected as ${d.level === "index" ? "index level" : "indicator level"}, ${d.rows} rows)`, "ok");
    await refreshStatus();
    await previewData();
  } catch (e) { msg($("dataMsg"), e.message, "err"); }
  ev.target.value = "";
});
$("btnManual").addEventListener("click", async () => {
  const text = $("manualText").value;
  if (!text.trim()) return msg($("dataMsg"), "Please paste some data first", "err");
  try {
    const d = await api("/api/data/manual", { text });
    clearResults();
    msg($("dataMsg"), `${d.message} (detected as ${d.level === "index" ? "index level" : "indicator level"}, ${d.rows} rows)`, "ok");
    await refreshStatus();
    await previewData();
  } catch (e) { msg($("dataMsg"), e.message, "err"); }
});

async function previewData() {
  try {
    const s = await api("/api/status", undefined);
    const el = $("dataPreview");
    if (!(s.n_rows > 0)) { el.innerHTML = '<p class="hint">No data loaded.</p>'; return; }
    const d = await api("/api/data/preview", undefined);
    const heads = d.columns;
    const rows = d.rows;
    const q = d.quality || {};
    let qualityHtml = "";
    if (q.checked) {
      const badges = [];
      badges.push(`<span class="tag ${q.balanced ? "lo" : "hi"}">Panel ${q.balanced ? "balanced" : "unbalanced"}</span>`);
      badges.push(`<span class="tag ${q.missing_cells === 0 ? "lo" : "mid"}">Missing cells ${q.missing_cells}</span>`);
      badges.push(`<span class="tag lo">${q.n_provinces} provinces × ${q.n_years} years</span>`);
      qualityHtml = `<p class="hint">📋 Data completeness checks (paper M1 completeness checks): ${badges.join(" ")}
        ${q.unbalanced.length ? `<br>⚠ Unbalanced-panel provinces (fewer years): ${q.unbalanced.map(provCn).join(", ")}` : ""}
        ${q.short_series.length ? `<br>⚠ Series too short (&lt;4 points, cannot forecast): ${q.short_series.map(provCn).join(", ")}` : ""}</p>`;
    }
    el.innerHTML = qualityHtml + `<p class="hint">${d.total} records in total; previewing the first ${rows.length}:</p>
      <table><thead><tr>${heads.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((r) => `<tr>${heads.map((h) => `<td>${esc(fmt(r[h]))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  } catch (e) {
    $("dataPreview").innerHTML = `<p class="hint">Preview failed: ${esc(e.message)}</p>`;
  }
}

/* ---------------- 2. Indicators & weights ---------------- */
let directionOverride = {};

function renderDirectionEditor(s) {
  const host = $("directionsHost");
  if (!host) return;
  const rows = s.indicator_cols.map((c) => {
    const d = directionOverride[c] !== undefined ? directionOverride[c] : s.directions[c];
    return `<tr><td>${esc(c)}</td><td>
      <button class="btn" data-dir-col="${esc(c)}" data-dir="${d > 0 ? 1 : -1}" style="padding:2px 10px">
        ${d > 0 ? "Positive ↑" : "Negative ↓"}</button></td></tr>`;
  }).join("");
  host.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Indicator</th><th>Direction (click to toggle)</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}
document.addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-dir-col]");
  if (!b) return;
  const c = b.dataset.dirCol;
  const cur = Number(b.dataset.dir);
  const nxt = cur > 0 ? -1 : 1;
  directionOverride[c] = nxt;
  b.dataset.dir = nxt;
  b.textContent = nxt > 0 ? "Positive ↑" : "Negative ↓";
});

$("btnWeights").addEventListener("click", async () => {
  try {
    const s = await api("/api/status", undefined);
    if (!(s.n_rows > 0)) return msg($("weightsMsg"), "Please load or upload indicator-level data in tab 1 first", "err");
    if (s.level === "index") {
      return msg($("weightsMsg"), "The current data is at the index level: no weights are needed (index-level mech/green are already composite indices). To run the full indicator pipeline, load the indicator-level demo or upload indicator-level data.", "err");
    }
    const body = { directions: directionOverride };
    if ($("skipStd").checked) body.skip_std = true;
    body.add_constant = parseFloat($("addConstant").value || 0.01);
    const r = await api("/api/weights", body);
    msg($("weightsMsg"), "Entropy weights computed.", "ok");
    renderWeights(r);
  } catch (e) { msg($("weightsMsg"), e.message, "err"); }
});

function renderWeights(r) {
  const el = $("weightsResult");
  const sysNames = { M: "Mechanization subsystem (M)", G: "Greening subsystem (G)" };
  let html = "";
  for (const sys of ["M", "G"]) {
    const w = r.weights[sys];
    if (!w) continue;
    const entries = Object.entries(w).sort((a, b) => b[1] - a[1]);
    html += `<div class="card"><h2>${sysNames[sys]} · Entropy Weights (M3)</h2>`;
    if (r.checks && r.checks[sys]) {
      html += `<p class="hint">✅ Checked against the paper's exact entropy weights: max difference ${fmt(r.checks[sys].max_diff, 6)} (demo data ≈ 0)</p>`;
    }
    html += `<div class="grid2">
      <div><div class="table-wrap" style="max-height:380px"><table><thead>
        <tr><th>Indicator</th><th>Direction</th><th>Information entropy e</th><th>Entropy weight w</th><th>Paper weight</th></tr></thead><tbody>`;
    for (const [name, wgt] of entries) {
      const eVal = r.entropy[sys][name];
      const paperW = META.indicators.find((i) => i.name === name)?.paper_weight;
      html += `<tr><td>${esc(name)}</td><td>${r.directions[name] > 0 ? "+" : "−"}</td>
        <td>${fmt(eVal, 6)}</td><td><b>${fmt(wgt, 6)}</b></td><td>${paperW != null ? fmt(paperW, 3) : "—"}</td></tr>`;
    }
    html += `</tbody></table></div></div>
      <div><div id="chartW${sys}" class="chart"></div></div></div>`;
    if (r.vif && r.vif[sys]) {
      const v = r.vif[sys];
      html += `<p class="hint">Ex-post independence check (paper §2.3): max VIF <b>${fmt(v.max, 2)}</b> (mean ${fmt(v.mean, 2)});
        indicator pairs with |r|&gt;0.9: ${r.pairs[sys].length ? r.pairs[sys].map((p) => esc(p.i) + "↔" + esc(p.j) + " (" + fmt(p.r, 3) + ")").join("; ") : "none"}</p>`;
    }
    html += `</div>`;
  }
  // overall (coupling-coordination) system weights
  html += `<div class="card"><h2>Coupling-Coordination System Weights (M4)</h2>
    <p class="hint">Coordination index T = α·U₁ + β·U₂, default α = β = 0.5 (paper convention: the two subsystems are equally weighted).
    Subsystem weights come from the entropy weights above; if a dcoord panel was uploaded, D follows the panel values (historical convention), and the formula-recomputed D is shown for checking.</p></div>`;
  el.innerHTML = html;
  setTimeout(() => {
    for (const sys of ["M", "G"]) {
      const w = r.weights[sys];
      if (!w) continue;
      const entries = Object.entries(w).sort((a, b) => b[1] - a[1]);
      chart("chartW" + sys, {
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
        grid: { left: 8, right: 16, top: 10, bottom: 8, containLabel: true },
        xAxis: { type: "value", max: 0.22 },
        yAxis: { type: "category", data: entries.map(([n]) => n.length > 16 ? n.slice(0, 15) + "…" : n),
                 axisLabel: { fontSize: 10 } },
        series: [{
          type: "bar", data: entries.map(([, v]) => +v.toFixed(6)),
          itemStyle: { color: sys === "M" ? "#166534" : "#0e7490" }, barWidth: 12,
          label: { show: true, position: "right", fontSize: 9 }
        }]
      });
    }
  }, 50);
}

/* ---------------- 3. Index computation ---------------- */
$("btnIndices").addEventListener("click", async () => {
  try {
    const r = await api("/api/indices", { alpha: parseFloat($("alpha").value), beta: parseFloat($("beta").value) });
    msg($("indicesMsg"), "Indices and coupling coordination computed." + (r.d_check ? ` (Panel dcoord vs formula-recomputed D: max difference ${fmt(r.d_check.max_diff, 4)}; panel values adopted per paper convention)` : ""), "ok");
    renderIndices(r);
    await loadSeriesSelect();   // refresh the forecast-series dropdown once indices are ready
  } catch (e) { msg($("indicesMsg"), e.message, "err"); }
});

function renderIndices(r) {
  const el = $("indicesResult");
  const rows = r.table;
  const provs = [...new Set(rows.map((x) => x.province))];
  const years = [...new Set(rows.map((x) => x.year))].sort();
  // KPI
  const avgD = rows.reduce((a, x) => a + x.D, 0) / rows.length;
  const last = rows.filter((x) => x.year === years[years.length - 1]);
  const regionAvg = {};
  for (const [k, v] of Object.entries(META.regions)) {
    const sub = rows.filter((x) => v.provinces.includes(x.province));
    regionAvg[k] = sub.length ? sub.reduce((a, x) => a + x.D, 0) / sub.length : null;
  }
  el.innerHTML = `
    <div class="card"><div class="kpi">
      <div class="kpi-item"><div class="v">${fmt(avgD, 3)}</div><div class="l">Full-sample mean coordination degree D</div></div>
      <div class="kpi-item"><div class="v">${fmt(regionAvg.Downstream ?? 0, 3)}</div><div class="l">Downstream mean D (${META.regions.Downstream.provinces.length} provinces)</div></div>
      <div class="kpi-item"><div class="v">${fmt(regionAvg.Midstream ?? 0, 3)}</div><div class="l">Midstream mean D (3 provinces)</div></div>
      <div class="kpi-item"><div class="v">${fmt(regionAvg.Upstream ?? 0, 3)}</div><div class="l">Upstream mean D (4 provinces)</div></div>
      <div class="kpi-item"><div class="v">${fmt(Math.max(...rows.map((x) => x.D)), 3)}</div><div class="l">Max D (${provCn(rows[rows.findIndex((x) => x.D === Math.max(...rows.map((y) => y.D)))].province)})</div></div>
    </div></div>
    <div class="card"><div class="grid3">
      <div><div id="chartTrend" class="chart tall"></div></div>
      <div><div id="chartD" class="chart tall"></div></div>
      <div><div id="chartRegion" class="chart tall"></div></div>
    </div></div>
    <div class="card"><h2>Index Panel (U1/U2/C/T/D)</h2>
      <div class="table-wrap" style="max-height:420px"><table><thead><tr>
        <th>Province</th><th>Year</th><th>U1 Mechanization</th><th>U2 Greening</th><th>Coupling index C</th>
        <th>Coordination index T</th><th>Coordination degree D</th><th>Level</th></tr></thead><tbody>
      ${rows.map((x) => `<tr><td>${esc(provCn(x.province))}</td><td>${x.year}</td>
        <td>${fmt(x.U1, 4)}</td><td>${fmt(x.U2, 4)}</td><td>${fmt(x.C, 4)}</td>
        <td>${fmt(x.T, 4)}</td><td><b>${fmt(x.D, 4)}</b></td>
        <td>${esc(x.level)}</td></tr>`).join("")}
      </tbody></table></div></div>`;
  setTimeout(() => {
    // trend chart: multi-province U1/U2/D
    const selProvs = provs.slice(0, 6);
    chart("chartTrend", {
      tooltip: { trigger: "axis" }, legend: { type: "scroll" },
      grid: { left: 50, right: 20, top: 40, bottom: 30 },
      xAxis: { type: "category", data: years },
      yAxis: { type: "value", min: 0, max: 1 },
      series: selProvs.flatMap((p) => [
        { name: provCn(p) + " U1", type: "line", data: rows.filter((x) => x.province === p).map((x) => +x.U1.toFixed(4)), showSymbol: false },
        { name: provCn(p) + " U2", type: "line", data: rows.filter((x) => x.province === p).map((x) => +x.U2.toFixed(4)), showSymbol: false },
      ])
    });
    // D heatmap by province × year (color bar on the right, room for year labels)
    chart("chartD", {
      tooltip: { position: "top" },
      grid: { left: 90, right: 70, top: 10, bottom: 30 },
      xAxis: { type: "category", data: years, splitArea: { show: true },
               axisLabel: { fontSize: 11, margin: 10 } },
      yAxis: { type: "category", data: provs.map(provCn), splitArea: { show: true } },
      visualMap: { min: 0.45, max: 0.85, calculable: true, orient: "vertical",
                   right: 0, top: "center", itemHeight: 160,
                   text: ["High", "Low"], textStyle: { fontSize: 10 },
                   inRange: { color: ["#fee2e2", "#fef3c7", "#bbf7d0", "#166534"] } },
      series: [{
        type: "heatmap", data: rows.map((x) => [years.indexOf(x.year), provs.indexOf(x.province), +x.D.toFixed(4)]),
        label: { show: true, fontSize: 8, formatter: (p) => p.data[2].toFixed(3), color: "#1f2937" }
      }]
    });
    // regional mean comparison (M/G/D)
    const regs = Object.keys(META.regions);
    const regData = regs.map((k) => {
      const sub = rows.filter((x) => META.regions[k].provinces.includes(x.province));
      return { D: sub.reduce((a, x) => a + x.D, 0) / sub.length,
               U1: sub.reduce((a, x) => a + x.U1, 0) / sub.length,
               U2: sub.reduce((a, x) => a + x.U2, 0) / sub.length };
    });
    chart("chartRegion", {
      tooltip: { trigger: "axis" }, legend: { data: ["U1 Mechanization", "U2 Greening", "D Coordination"] },
      grid: { left: 50, right: 20, top: 40, bottom: 30 },
      xAxis: { type: "category", data: regs.map((k) => META.regions[k].name) },
      yAxis: { type: "value", min: 0, max: 1 },
      series: [
        { name: "U1 Mechanization", type: "bar", data: regData.map((x) => +x.U1.toFixed(3)), itemStyle: { color: "#166534" } },
        { name: "U2 Greening", type: "bar", data: regData.map((x) => +x.U2.toFixed(3)), itemStyle: { color: "#0e7490" } },
        { name: "D Coordination", type: "line", data: regData.map((x) => +x.D.toFixed(3)), itemStyle: { color: "#b45309" } },
      ]
    });
  }, 50);
}

/* ---------------- 4. Forecasting ---------------- */
async function loadSeriesSelect() {
  try {
    const d = await api("/api/series", undefined);
    const sel = $("seriesSelect");
    if (!d.series.length) { sel.innerHTML = "<option>(complete the index computation first)</option>"; return; }
    const cur = sel.value;
    sel.innerHTML = d.series.map((s) =>
      `<option value="${s.province}|${s.var}">${provCn(s.province)} · ${s.var === "M" ? "Mechanization" : s.var === "G" ? "Greening" : "Coordination D"} (${s.years[0]}–${s.years[s.years.length - 1]})</option>`).join("");
    if (cur && [...sel.options].some((o) => o.value === cur)) sel.value = cur;
  } catch (e) { /* indices not computed yet */ }
}

$("btnForecastAll").addEventListener("click", async () => {
  const B = parseInt($("B").value || 1000);
  const seed = parseInt($("seed").value || 20260829);
  const qs = new URLSearchParams({ B, seed, h: 8, vars: "M,G,D", methods: "gm11,arima,holt" }).toString();
  // progress-bar UI
  $("batchProgress").innerHTML =
    `<div class="progress-bar"><div class="progress-fill" id="pf" style="width:0%"></div></div>
     <div class="progress-text" id="pt">Preparing…</div>`;
  $("btnForecastAll").disabled = true;
  $("forecastMsg").className = "msg";
  let finished = false;
  const es = new EventSource(`/api/forecast/batch/stream?${qs}`);
  es.addEventListener("progress", (e) => {
    const p = JSON.parse(e.data);
    $("pf").style.width = `${(p.done / p.total * 100).toFixed(0)}%`;
    $("pt").textContent = `Forecasting: ${p.current} (${p.done}/${p.total})`;
  });
  es.addEventListener("done", (e) => {
    es.close(); finished = true;
    $("btnForecastAll").disabled = false;
    const r = JSON.parse(e.data);
    msg($("forecastMsg"), `Batch forecast complete: ${r.forecasts.length} series, GM(1,1) grading + bootstrap intervals + ARIMA/Holt cross-model checks.`, "ok");
    renderForecastBatch(r);
    setTimeout(() => { $("batchProgress").innerHTML = ""; }, 600);
  });
  es.addEventListener("error", (e) => {
    if (finished) return;
    // EventSource reconnects on drop; after reconnect the stream restarts (idempotent).
    // Only report an error once the stream is truly closed.
    if (e.target && e.target.readyState === EventSource.CLOSED) {
      es.close();
      $("btnForecastAll").disabled = false;
      $("batchProgress").innerHTML = "";
      msg($("forecastMsg"), "Batch forecast connection lost; please retry.", "err");
    }
  });
});

function renderForecastBatch(r) {
  const el = $("forecastBatchResult");
  const cov = r.coverage;
  const vn = { M: "Mechanization", G: "Greening", D: "Coordination" };
  el.innerHTML = `
    <div class="card"><div class="kpi">
      ${["M", "G", "D"].map((v) => `<div class="kpi-item"><div class="v">${cov[v].reliable}/${cov[v].total}</div>
        <div class="l">${vn[v]} reliable series (Grade I/II)</div></div>`).join("")}
      <div class="kpi-item"><div class="v">${r.params.seed}</div><div class="l">Bootstrap random seed (reproducible)</div></div>
      <div class="kpi-item"><div class="v">${r.params.B}</div><div class="l">Bootstrap resamples B</div></div>
    </div></div>
    <div class="card"><h2>Forecast results for all ${r.forecasts.length} series (2030)</h2>
      <div class="table-wrap" style="max-height:480px"><table><thead><tr>
        <th>Province</th><th>Variable</th><th>Grade</th><th>f2025</th><th>f2030</th><th>90% interval (2030)</th>
        <th>ARIMA</th><th>Holt</th><th>Direction agreement</th></tr></thead><tbody>
      ${r.forecasts.map((x) => {
        const g = x.gm11 || {};
        if (!g.grade) return `<tr><td>${esc(provCn(x.province))}</td><td>${vn[x.var]}</td><td colspan="7">${esc(x.error || "No result")}</td></tr>`;
        const flags = x.direction_flags || {};
        const bad = Object.values(flags).filter((v) => v === "disagree").length;
        return `<tr><td>${esc(provCn(x.province))}</td><td>${vn[x.var]}</td>
          <td>${gradePill(g.grade)}</td><td>${fmt(g.f2025, 3)}</td><td><b>${fmt(g.f2030, 3)}</b></td>
          <td>${g.ci30 ? `[${fmt(g.ci30[0], 3)}, ${fmt(g.ci30[1], 3)}]` : '<span class="tag mid">Unreliable</span>'}</td>
          <td>${x.arima ? fmt(x.arima.f2030, 3) : "—"}</td><td>${x.holt ? fmt(x.holt.f2030, 3) : "—"}</td>
          <td>${g.reliable ? (bad ? `<span class="tag mid">Divergence ${bad}</span>` : '<span class="tag lo">Agree</span>') : "—"}</td></tr>`;
      }).join("")}
      </tbody></table></div></div>
    <div class="card"><div id="chartFCI" class="chart tall"></div></div>`;
  setTimeout(() => {
    // all series as bars: reliable = green (with 90% interval error bars), unreliable = grey (no interval)
    const all = r.forecasts.filter((x) => x.gm11 && x.gm11.grade);
    const cats = all.map((x) => `${provCn(x.province)}·${vn[x.var]}`);
    const barData = all.map((x) => ({
      value: +x.gm11.f2030.toFixed(3),
      itemStyle: { color: x.gm11.reliable ? "#166534" : "#cbd5e1" }
    }));
    const relIdx = all.map((x, i) => (x.gm11.ci30 ? i : -1)).filter((i) => i >= 0);
    chart("chartFCI", {
      tooltip: { trigger: "axis",
        formatter: (ps) => {
          const i = ps[0].dataIndex;
          const x = all[i];
          const g = x.gm11;
          return `${cats[i]}<br>f2030: <b>${g.f2030.toFixed(3)}</b>` +
            (g.ci30 ? `<br>90% interval: [${g.ci30[0].toFixed(3)}, ${g.ci30[1].toFixed(3)}]` : `<br><span style="color:#b45309">Grade ${g.grade}, unreliable (no interval)</span>`);
        } },
      legend: { bottom: 0, data: [
        { name: "2030 point forecast (reliable)", icon: "rect", itemStyle: { color: "#166534" } },
        { name: "2030 point forecast (unreliable)", icon: "rect", itemStyle: { color: "#cbd5e1" } },
        { name: "90% interval", icon: "rect", itemStyle: { color: "#1d4ed8" } },
      ] },
      grid: { left: 60, right: 30, top: 40, bottom: 130 },
      xAxis: { type: "category", data: cats,
               axisLabel: { rotate: 45, fontSize: 10, interval: 0, margin: 14 } },
      yAxis: { type: "value", min: 0.3, max: 0.9, scale: true },
      series: [
        { name: "2030 point forecast (reliable)", type: "bar",
          data: barData.map((d, i) => (all[i].gm11.reliable ? d : null)),
          barWidth: 14 },
        { name: "2030 point forecast (unreliable)", type: "bar",
          data: barData.map((d, i) => (all[i].gm11.reliable ? null : d)),
          barWidth: 14 },
        { name: "90% interval", type: "custom",
          itemStyle: { color: "#1d4ed8" },   // legend swatch matches the error-bar color
          renderItem: (params, api) => {
            const i = params.dataIndex;
            if (relIdx.indexOf(i) < 0) return null;
            const lo = api.coord([i, all[i].gm11.ci30[0]]);
            const hi = api.coord([i, all[i].gm11.ci30[1]]);
            return { type: "group", children: [
              { type: "line", shape: { x1: lo[0], y1: lo[1], x2: lo[0], y2: hi[1] }, style: { stroke: "#1d4ed8", lineWidth: 2.5 } },
              { type: "line", shape: { x1: lo[0] - 7, y1: lo[1], x2: lo[0] + 7, y2: lo[1] }, style: { stroke: "#1d4ed8", lineWidth: 2.5 } },
              { type: "line", shape: { x1: hi[0] - 7, y1: hi[1], x2: hi[0] + 7, y2: hi[1] }, style: { stroke: "#1d4ed8", lineWidth: 2.5 } },
            ]};
          },
          data: all.map(() => 0) }
      ]
    });
  }, 50);
}

$("btnForecastOne").addEventListener("click", async () => {
  const val = $("seriesSelect").value;
  if (!val || !val.includes("|")) return msg($("forecastMsg"), "Complete the index computation in tab 3 first (the series list refreshes automatically), or select a series above", "err");
  const [prov, var_] = val.split("|");
  try {
    const body = { province: prov, var: var_, B: parseInt($("B").value || 1000), seed: parseInt($("seed").value || 20260829) };
    const r = await api("/api/forecast/one", body);
    msg($("forecastMsg"), "Single-series multi-model forecast complete.", "ok");
    renderForecastOne(r);
  } catch (e) { msg($("forecastMsg"), e.message, "err"); }
});

function renderForecastOne(r) {
  const el = $("forecastOneResult");
  const g = r.gm11;
  const vn = { M: "Mechanization", G: "Greening", D: "Coordination" };
  const n = r.values.length;
  const obsYears = r.years;
  const hF = (r.gm11?.pred?.length ?? 0) - n;   // forecast horizon h (= 8)
  const fYears = Array.from({ length: hF }, (_, i) => obsYears[obsYears.length - 1] + i + 1);
  el.innerHTML = `
    <div class="card"><h2>${provCn(r.province)} · ${vn[r.var]} (${obsYears[0]}–${obsYears[obsYears.length - 1]})</h2>
      <div class="kpi">
        <div class="kpi-item"><div class="v">${gradePill(g.grade)}</div><div class="l">GM(1,1) accuracy grade</div></div>
        <div class="kpi-item"><div class="v">${fmt(g.C, 4)}</div><div class="l">Posterior error ratio C (lower is better)</div></div>
        <div class="kpi-item"><div class="v">${fmt(g.P, 4)}</div><div class="l">Small error probability P</div></div>
        <div class="kpi-item"><div class="v">${fmt(g.alpha, 5)}</div><div class="l">Development coefficient α</div></div>
        <div class="kpi-item"><div class="v">${fmt(g.mu, 5)}</div><div class="l">Grey action quantity μ</div></div>
      </div>
      ${g.reliable
        ? `<p class="hint">${g.bootstrap.method} (B=${g.bootstrap.B}, seed ${g.bootstrap.seed}): 2025 forecast ${fmt(g.f2025, 4)} [${fmt(g.ci25[0], 4)}, ${fmt(g.ci25[1], 4)}]; 2030 forecast <b>${fmt(g.f2030, 4)}</b> [${fmt(g.ci30[0], 4)}, ${fmt(g.ci30[1], 4)}]</p>`
        : `<p class="hint"><span class="tag hi">Unreliable (Grade ${g.grade})</span> excluded from quantitative interpretation per paper convention; shown for reference only.</p>`}
    </div>
    <div class="card"><div id="chartF1" class="chart tall"></div></div>
    <div class="card"><h2>Cross-Model Comparison (2030)</h2>
      <div class="table-wrap"><table><thead><tr>
        <th>Model</th><th>Type</th><th>2030 forecast</th><th>Direction agreement</th><th>Notes</th></tr></thead><tbody>
      ${["gm11", "arima", "holt", "verhulst", "narx", "quad"].map((m) => {
        const meta = META.models[m];
        const v = r[m];
        if (!v) return "";
        const dirFlag = (r.direction_flags || {})[m];
        return `<tr><td>${meta.name}</td><td>${meta.kind}</td>
          <td><b>${v.f2030 != null ? fmt(v.f2030, 4) : "—"}</b></td>
          <td>${dirFlag ? (dirFlag === "agree" ? '<span class="tag lo">Agree</span>' : '<span class="tag mid">Disagree</span>') : "—"}</td>
          <td style="text-align:left;font-size:12px">${m === "gm11" ? `Grade ${g.grade}` : ""}</td></tr>`;
      }).join("")}
      </tbody></table></div></div>`;
  setTimeout(() => {
    const series = [
      { name: "Observed", type: "line", data: r.values.map((x) => +x.toFixed(4)), symbolSize: 6, lineStyle: { width: 2.5, color: "#111827" }, itemStyle: { color: "#111827" } },
    ];
    const colors = { gm11: "#166534", arima: "#0e7490", holt: "#7c3aed", verhulst: "#b45309", narx: "#be123c", quad: "#64748b" };
    const names = { gm11: "GM(1,1)", arima: "ARIMA(1,1,0)", holt: "Holt", verhulst: "Verhulst", narx: "NARX-BP", quad: "Quadratic trend" };
    for (const m of Object.keys(colors)) {
      if (m === "gm11") continue;   // GM gets its own dedicated series below (fit + forecast)
      if (!r[m] || !r[m].pred) continue;
      const pred = r[m].pred;
      if (pred.some((x) => x == null || !isFinite(x))) continue;
      series.push({ name: names[m], type: "line", data: [...Array(n).fill(null), ...pred.map((x) => +x.toFixed(4))], showSymbol: false, lineStyle: { width: 2, color: colors[m] }, itemStyle: { color: colors[m] } });
    }
    const xAxisData = [...obsYears, ...fYears];
    // GM forecast includes fitted values (first n entries of pred are the fit)
    series.push({ name: "GM fit+forecast", type: "line", data: r.gm11.pred.map((x) => +x.toFixed(4)), showSymbol: false, lineStyle: { width: 2.5, color: "#166534" }, itemStyle: { color: "#166534" } });
    chart("chartF1", {
      tooltip: { trigger: "axis" }, legend: { type: "scroll" },
      grid: { left: 55, right: 25, top: 40, bottom: 40 },
      xAxis: { type: "category", data: xAxisData },
      yAxis: { type: "value", min: (v) => Math.max(0, Math.floor(v.min * 10) / 10), max: (v) => Math.min(1, Math.ceil(v.max * 10) / 10), scale: true },
      series: series.filter((s) => s.data.length === xAxisData.length || s.name === "Observed")
    });
  }, 50);
}

/* ---------------- 5. Early-warning dashboard ---------------- */
$("btnWarning").addEventListener("click", async () => {
  try {
    const s = await api("/api/status", undefined);
    if (!(s.n_rows > 0)) return msg($("warningMsg"), "Please load or upload data in tab 1 first", "err");
    if (!s.has_indices) {
      msg($("warningMsg"), "The early-warning dashboard requires the index computation: click 'Compute Indices & Coupling Coordination' in tab 3 first.", "err");
      return document.querySelector('.tab[data-tab="indices"]').click();
    }
    if (!s.has_forecasts) {
      msg($("warningMsg"), "The early-warning dashboard requires the batch forecast: click 'Forecast All Series in Batch' in tab 4 first.", "err");
      return document.querySelector('.tab[data-tab="forecast"]').click();
    }
    const r = await api("/api/earlywarning", {});
    msg($("warningMsg"), "Early-warning dashboard generated.", "ok");
    renderWarning(r);
  } catch (e) { msg($("warningMsg"), e.message, "err"); }
});

function renderWarning(r) {
  const el = $("warningResult");
  const rows = r.rows;
  const vn = { M: "Mechanization", G: "Greening", D: "Coordination" };
  const riskMap = { High: 3, Medium: 2, Low: 1 };
  const provs = [...new Set(rows.map((x) => x.province))];
  el.innerHTML = `
    <div class="card"><h2>Coordination degree D trend (observed → GM(1,1) forecast extension)</h2>
      <div id="chartTrendD" class="chart tall"></div>
      <p class="hint">2013–2022 observed trajectories of the coupling coordination degree D for the 11 provinces (solid lines) with 2023–2030 GM(1,1) forecast extensions (dashed);
      only Grade I/II forecasts enter quantitative interpretation (dashed extensions are shown for reference only).</p></div>
    <div class="card"><h2>Risk Matrix (province × variable)</h2>
      <div id="chartRisk" class="chart"></div></div>
    <div class="card"><h2>Warning Details</h2>
      <div class="table-wrap" style="max-height:460px"><table><thead><tr>
        <th>Province</th><th>Variable</th><th>Grade</th><th>2022 value</th><th>2030 forecast</th><th>Δ</th><th>90% interval</th><th>Risk</th><th>Warning rules</th></tr></thead><tbody>
      ${rows.map((x) => `<tr><td>${esc(provCn(x.province))}</td><td>${vn[x.var]}</td>
        <td>${gradePill(x.grade)}</td><td>${fmt(x.last, 3)}</td><td>${fmt(x.f2030, 3)}</td>
        <td>${x.delta >= 0 ? "+" : ""}${fmt(x.delta, 3)}</td>
        <td>${x.ci30 ? `[${fmt(x.ci30[0], 3)}, ${fmt(x.ci30[1], 3)}]` : "—"}</td>
        <td><span class="tag ${x.risk === "High" ? "hi" : x.risk === "Medium" ? "mid" : "lo"}">${x.risk}</span></td>
        <td style="text-align:left;font-size:12px">${x.flags.length ? x.flags.map((f) => `<span class="tag ${x.risk === "High" ? "hi" : "mid"}">${esc(f)}</span>`).join("") : '<span class="tag lo">Normal</span>'}</td></tr>`).join("")}
      </tbody></table></div></div>`;
  setTimeout(() => {
    // M6 trend chart: per-province D observed (solid) + GM(1,1) forecast extension (dashed),
    // forecast period in a light background
    const trend = r.trend || {};
    const provList = Object.keys(trend);
    const t0 = provList.length ? trend[provList[0]] : { years: [], D: [], pred: [] };
    const obsYears = t0.years || [];
    const obsLen = obsYears.length;
    const predLen = (t0.pred || []).length;
    const lastYear = obsLen ? obsYears[obsLen - 1] : 2022;
    const predYears = Array.from({ length: predLen }, (_, i) => lastYear + i + 1);
    const xYears = [...obsYears, ...predYears];
    const obsSeries = provList.map((p) => {
      const t = trend[p];
      return {
        name: provCn(p), type: "line",
        data: [...(t.D || []), ...Array(predLen).fill(null)],
        showSymbol: false, lineStyle: { width: 2 },
      };
    });
    const predSeries = provList.map((p) => {
      const t = trend[p];
      return {
        name: provCn(p), type: "line",
        data: [...Array(obsLen).fill(null), ...(t.pred || [])],
        showSymbol: false, lineStyle: { width: 1.8, type: "dashed", opacity: 0.75 },
      };
    });
    chart("chartTrendD", {
      tooltip: { trigger: "axis" },
      legend: { type: "scroll", data: provList.map(provCn), bottom: 0, pageIconSize: 10 },
      grid: { left: 55, right: 25, top: 45, bottom: 90 },
      xAxis: { type: "category", data: xYears },
      yAxis: { type: "value", min: 0.4, max: 0.9, scale: true },
      series: [...obsSeries, ...predSeries]
    });
    chart("chartRisk", {
      tooltip: { position: "top", formatter: (p) => {
        const x = rows.find((r2) => r2.province === provs[p.value[1]] && r2.var === p.value[0]);
        return `${provCn(x.province)} · ${vn[x.var]}<br>Risk: ${x.risk}<br>${x.flags.join("<br>") || "Normal"}`;
      } },
      grid: { left: 90, right: 70, top: 20, bottom: 30 },
      xAxis: { type: "category", data: ["M", "G", "D"].map((v) => vn[v]), splitArea: { show: true },
               axisLabel: { fontSize: 12, margin: 12 } },
      yAxis: { type: "category", data: provs.map(provCn), splitArea: { show: true } },
      visualMap: { min: 1, max: 3, calculable: false, orient: "vertical",
                   right: 0, top: "center", itemHeight: 150,
                   inRange: { color: ["#dcfce7", "#fef3c7", "#fee2e2"] },
                   text: ["High risk", "Low risk"], textStyle: { fontSize: 10 } },
      series: [{
        type: "heatmap",
        data: rows.map((x) => ["M", "G", "D"].indexOf(x.var) + "|" + provs.indexOf(x.province)).map((k) => {
          const [xi, yi] = k.split("|").map(Number);
          return [xi, yi, riskMap[rows.find((x) => x.var === ["M", "G", "D"][xi] && x.province === provs[yi]).risk]];
        }),
        label: { show: true, formatter: (p) => riskMap[rows.find((x) => x.var === ["M", "G", "D"][p.value[0]] && x.province === provs[p.value[1]]).risk] === 3 ? "⚠" : "" }
      }]
    });
  }, 50);
}

/* ---------------- 6. Methodology notes ---------------- */
function renderAbout() {
  const rules = META.grade_rules.map((g) =>
    `<tr><td>${g.grade}</td><td>${esc(g.cn)}</td><td>${esc(g.rule)}</td></tr>`).join("");
  const models = Object.entries(META.models).map(([k, m]) =>
    `<tr><td>${k}</td><td>${esc(m.name)}</td><td>${esc(m.kind)}</td><td>${m.nonlinear ? "✔" : "—"}</td></tr>`).join("");
  $("aboutContent").innerHTML = `
  <div class="grid2">
  <div>
    <h3>M2 Preprocessing</h3>
    <p class="hint">Positive indicator x′ = (x−x<sub>min</sub>)/(x<sub>max</sub>−x<sub>min</sub>); negative indicator x′ = (x<sub>max</sub>−x)/(x<sub>max</sub>−x<sub>min</sub>);
    standardization is pooled over the full sample (all province-year rows); a constant of 0.01 is then added to eliminate zero/negative values (range [0.01, 1.01]).</p>
    <h3>M3 Entropy Weights</h3>
    <p class="hint">y<sub>ij</sub> = x′<sub>ij</sub>/Σx′<sub>ij</sub>; e<sub>j</sub> = −K·Σ y·ln y (K = 1/ln m, m = number of samples);
    w<sub>j</sub> = (1−e<sub>j</sub>)/Σ(1−e<sub>j</sub>); U = Σ w<sub>j</sub>·x′<sub>j</sub>.
    Paper-convention index = U − 0.01 (bit-identical to the panel mech/green). Weights are normalized within each subsystem.</p>
    <h3>M4 Coupling Coordination</h3>
    <p class="hint">C = 2√(U₁U₂)/(U₁+U₂); T = αU₁+βU₂ (α=β=0.5); D = √(C·T).
    Ten-level D classification: 0.4–0.5 on the verge of imbalance, 0.5–0.6 barely coordinated, 0.6–0.7 primary coordination, 0.7–0.8 intermediate coordination, 0.8–0.9 good coordination, 0.9+ high-quality coordination.</p>
    <h3>M5 Forecasting (Algorithm 1)</h3>
    <p class="hint">GM(1,1): 1-AGO accumulation → least squares [α,μ]ᵀ=(BᵀB)⁻¹BᵀY → time response + IAGO → residuals (incl. the k=1 zero residual; S1/S2 use ddof=1)
    → C=S2/S1, P → Grade I–IV; only I/II enter quantitative interpretation; I/II additionally get 1000-resample residual bootstrap 90% intervals; Step 9 benchmarks ARIMA(1,1,0)/Holt and flags direction disagreement.</p>
  </div>
  <div>
    <h3>Grade Rules (paper Table 4 conventions)</h3>
    <div class="table-wrap"><table><thead><tr><th>Grade</th><th>Meaning</th><th>Rule (joint C and P)</th></tr></thead>
    <tbody>${rules}</tbody></table></div>
    <h3>Forecast Models</h3>
    <div class="table-wrap"><table><thead><tr><th>Key</th><th>Model</th><th>Type</th><th>Nonlinear</th></tr></thead>
    <tbody>${models}</tbody></table></div>
    <h3>Regression Verification (tests/test_regression.py, 67/67 passed)</h3>
    <p class="hint">Entropy weights vs. the paper's exact weights: max difference &lt;1e-9; U1/U2 reproduce the panel mech/green bit-identically;
    GM(1,1) α/μ/C/P and point forecasts for 33 series: max difference vs. the Stata rerun (01_results_33series.csv) &lt;1e-6;
    grades 33/33 identical; coverage M 9/11, G 5/11, D 7/11; direction agreement 16/21 (the 5 disagreements match the paper);
    2030 mean half-widths M 0.045 / G 0.015 / D 0.016.</p>
    <p class="hint">Note: the panel dcoord follows the historical convention of the author's data package (max difference vs. formula recomputation ≤0.007);
    the software uses the panel D at the index level (matching the paper's forecast figures) and the formula D at the indicator level.</p>
  </div></div>`;
}
