/* Interactive-flow reproduction/verification script: simulates real user clicks and screenshots
   Usage: node flow.js <outPrefix> [mode]
   Mode: reproduce | verify
   Flow: index-level demo -> indices -> indicator-level demo -> weights -> indices -> forecast A -> forecast B
   (waits and screenshots after each key step) */
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const BASE = "http://127.0.0.1:8000";
const outPrefix = process.argv[2] || "_flow";
const PORT = 9444 + Math.floor(Math.random() * 200);

const chrome = spawn(CHROME, [
  "--headless=new", "--disable-gpu", `--remote-debugging-port=${PORT}`, "--window-size=1500,1400", "about:blank",
], { stdio: "ignore" });

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

  async function shot(name) {
    await sleep(900);  // wait for chart animation
    const s = await cdp(ws, "Page.captureScreenshot", { format: "png" });
    const p = `${outPrefix}_${name}.png`;
    fs.writeFileSync(p, Buffer.from(s.data, "base64"));
    console.log("shot:", p);
  }
  async function evaljs(expr) {
    const r = await cdp(ws, "Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) console.log("[js-error]", JSON.stringify(r.exceptionDetails).slice(0, 400));
    return r.result ? r.result.value : undefined;
  }
  async function click(id) { await evaljs(`document.getElementById('${id}').click(); true`); }
  async function goto(tab) { await evaljs(`document.querySelector('.tab[data-tab="${tab}"]').click(); true`); }

  // 1. index-level demo -> compute indices -> tab 3
  await click("btnDemo"); await sleep(2500);
  await shot("0_preview");   // tab 1: preview should show data rows
  await click("btnIndices"); await sleep(2500);
  await goto("indices"); await sleep(1200);
  await shot("1_index_layer");

  // 2. indicator-level demo -> weights -> indices -> tab 3
  await goto("data"); await sleep(600);
  await click("btnDemoInd"); await sleep(2500);
  await click("btnWeights"); await sleep(2500);
  await click("btnIndices"); await sleep(3000);
  await goto("indices"); await sleep(1200);
  await shot("2_indicator_layer");
  console.log("state2:", await evaljs(`JSON.stringify({chip:document.getElementById('statusChip').textContent, hasWeights:!!document.getElementById('weightsResult').children.length, hasIndices:!!document.getElementById('indicesResult').children.length, err:document.querySelector('#indicesMsg')?.textContent})`));

  // 3. forecast: batch -> Guizhou M -> Zhejiang G
  await goto("forecast"); await sleep(800);
  await click("btnForecastAll"); await sleep(4000);
  await evaljs(`document.getElementById('seriesSelect').value='Guizhou|M'; true`);
  await click("btnForecastOne"); await sleep(4000);
  await shot("3_forecast_guizhouM");
  await evaljs(`document.getElementById('seriesSelect').value='Zhejiang|G'; true`);
  await click("btnForecastOne"); await sleep(4000);
  await shot("4_forecast_zhejiangG");
  console.log("state4:", await evaljs(`JSON.stringify({title:document.querySelector('#forecastOneResult h2')?.textContent, chartCanvas:!!document.querySelector('#chartF1 canvas'), err:document.querySelector('#forecastMsg')?.textContent})`));

  ws.close();
  chrome.kill();
  process.exit(0);
})().catch((e) => { console.error("ERR:", e.message); chrome.kill(); process.exit(1); });
