/* CDP screenshot tool: waits for render completion then screenshots (used with ?autodemo=)
   Usage: node shot.js <url> <outfile> [width] [height] [timeoutMs]
   Depends on Node 22+ built-in WebSocket; no third-party packages. */
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const url = process.argv[2];
const out = process.argv[3];
const W = parseInt(process.argv[4] || "1500");
const H = parseInt(process.argv[5] || "1250");
const TIMEOUT = parseInt(process.argv[6] || "90000");
const PORT = 9222 + Math.floor(Math.random() * 400);

const chrome = spawn(CHROME, [
  "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
  `--remote-debugging-port=${PORT}`, `--window-size=${W},${H}`,
  "about:blank",
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

(async () => {
  // wait for the debug port
  let list = null;
  const t0 = Date.now();
  while (Date.now() - t0 < 30000) {
    try { list = await getJson("/json/list"); if (list.length) break; } catch (e) {}
    await new Promise((r) => setTimeout(r, 300));
  }
  if (!list || !list.length) throw new Error("chrome devtools port not ready");
  const page = list.find((p) => p.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  await cdp(ws, "Page.enable");
  await cdp(ws, "Runtime.enable");
  await cdp(ws, "Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await cdp(ws, "Page.navigate", { url });
  // poll for the render-complete signal
  const t1 = Date.now();
  let done = false;
  while (Date.now() - t1 < TIMEOUT) {
    await new Promise((r) => setTimeout(r, 400));
    const res = await cdp(ws, "Runtime.evaluate", {
      expression: `document.readyState === 'complete' && (window.__AUTODEMO_DONE === true || !location.search.includes('autodemo'))`,
      returnByValue: true,
    });
    if (res.result && res.result.value) { done = true; break; }
  }
  if (!done) console.error("⚠ timeout: page did not finish rendering");
  await new Promise((r) => setTimeout(r, 600));  // leave room for chart animation
  const shot = await cdp(ws, "Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(out, Buffer.from(shot.data, "base64"));
  console.log(`saved ${out} (${fs.statSync(out).size} bytes)`);
  ws.close();
  chrome.kill();
  process.exit(0);
})().catch((e) => { console.error("ERR:", e.message); chrome.kill(); process.exit(1); });
