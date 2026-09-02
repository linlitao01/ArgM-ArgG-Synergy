/* Tab-5 warning step-dependency probe: click tab 5 first (guided) -> tab 4 batch (SSE) -> tab 5 again (should succeed) */
const { spawn } = require("child_process");
const http = require("http");

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const BASE = "http://127.0.0.1:8000";
const PORT = 9777;

const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", `--remote-debugging-port=${PORT}`, "--window-size=1500,1500", "about:blank"], { stdio: "ignore" });
function getJson(path) {
  return new Promise((resolve, reject) => {
    http.get({ host: "127.0.0.1", port: PORT, path }, (res) => {
      let d = "";
      res.on("data", (c) => (d += c));
      res.on("end", () => { try { resolve(JSON.parse(d)); } catch (e) { reject(e); } });
    }).on("error", reject);
  });
}
let msgId = 0;
function cdp(ws, method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++msgId;
    const onMsg = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id === id) { ws.removeEventListener("message", onMsg); m.error ? reject(new Error(m.error.message)) : resolve(m.result); }
    };
    ws.addEventListener("message", onMsg);
    ws.send(JSON.stringify({ id, method, params }));
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  let list = null;
  const t0 = Date.now();
  while (Date.now() - t0 < 20000) {
    try { list = await getJson("/json/list"); if (list.length) break; } catch (e) {}
    await sleep(300);
  }
  const page = list.find((p) => p.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  await cdp(ws, "Runtime.enable");
  await cdp(ws, "Page.enable");
  await cdp(ws, "Page.navigate", { url: BASE + "/" });
  await sleep(4000);
  async function evaljs(expr) {
    const r = await cdp(ws, "Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) console.log("[js-error]", JSON.stringify(r.exceptionDetails).slice(0, 300));
    return r.result ? r.result.value : undefined;
  }
  async function goto(tab) { await evaljs(`document.querySelector('.tab[data-tab="${tab}"]').click(); true`); }

  // 1. load index-level demo data
  await evaljs(`document.getElementById('btnDemo').click(); true`);
  await sleep(2500);
  // 2. click tab 5 directly (no indices/forecasts yet) -> guided to tab 3
  await goto("warning");
  await evaljs(`document.getElementById('btnWarning').click(); true`);
  await sleep(1200);
  console.log("step2:", await evaljs(`JSON.stringify({
    tab: document.querySelector('.tab.active')?.dataset.tab,
    msg: document.querySelector('#warningMsg')?.textContent
  })`));
  // 3. tab-3 indices -> click tab 5 -> guided to tab 4
  await evaljs(`document.getElementById('btnIndices').click(); true`);
  await sleep(2500);
  await goto("warning");
  await evaljs(`document.getElementById('btnWarning').click(); true`);
  await sleep(1200);
  console.log("step3:", await evaljs(`JSON.stringify({
    tab: document.querySelector('.tab.active')?.dataset.tab,
    msg: document.querySelector('#warningMsg')?.textContent
  })`));
  // 4. tab-4 batch forecast (SSE) -> wait -> tab 5
  await evaljs(`document.getElementById('btnForecastAll').click(); true`);
  await sleep(7000);
  await goto("warning");
  await evaljs(`document.getElementById('btnWarning').click(); true`);
  await sleep(2500);
  console.log("step4:", await evaljs(`JSON.stringify({
    tab: document.querySelector('.tab.active')?.dataset.tab,
    msg: document.querySelector('#warningMsg')?.textContent,
    hasMatrix: !!document.getElementById('chartRisk'),
    hasRows: (document.querySelectorAll('#warningResult tbody tr') || []).length
  })`));
  ws.close();
  chrome.kill();
  process.exit(0);
})().catch((e) => { console.error("ERR:", e.message); chrome.kill(); process.exit(1); });
