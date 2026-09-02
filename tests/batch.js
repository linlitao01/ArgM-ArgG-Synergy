/* Runs only the batch forecast and screenshots (diagnoses chartFCI error bars) */
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const BASE = "http://127.0.0.1:8000";
const out = process.argv[2] || "_batch";
const PORT = 9555;

const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", `--remote-debugging-port=${PORT}`, "--window-size=1500,1700", "about:blank"], { stdio: "ignore" });
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
  await evaljs(`document.getElementById('btnDemo').click(); true`);
  await sleep(2500);
  await evaljs(`document.getElementById('btnIndices').click(); true`);
  await sleep(2500);
  await evaljs(`document.querySelector('.tab[data-tab="forecast"]').click(); true`);
  await sleep(800);
  await evaljs(`document.getElementById('btnForecastAll').click(); true`);
  await sleep(6000);
  const s = await cdp(ws, "Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(out, Buffer.from(s.data, "base64"));
  console.log("shot:", out);
  console.log("state:", await evaljs(`JSON.stringify({
    batchTable: !!document.querySelector('#forecastBatchResult table'),
    hasFCI: !!document.getElementById('chartFCI'),
    fciCanvas: !!document.querySelector('#chartFCI canvas'),
    btnText: document.getElementById('btnForecastAll')?.textContent,
    progressCleared: document.getElementById('batchProgress')?.children.length === 0,
    msg: document.querySelector('#forecastMsg')?.textContent
  })`));
  ws.close();
  chrome.kill();
  process.exit(0);
})().catch((e) => { console.error("ERR:", e.message); chrome.kill(); process.exit(1); });
