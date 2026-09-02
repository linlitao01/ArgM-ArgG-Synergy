/* Diagnostics: loads the page, prints console output and key state */
const { spawn } = require("child_process");
const http = require("http");

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const url = process.argv[2] || "http://127.0.0.1:8000/?autodemo=weights";
const PORT = 9333;

const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", `--remote-debugging-port=${PORT}`, "about:blank"], { stdio: "ignore" });

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
  let list = null;
  const t0 = Date.now();
  while (Date.now() - t0 < 20000) {
    try { list = await getJson("/json/list"); if (list.length) break; } catch (e) {}
    await new Promise((r) => setTimeout(r, 300));
  }
  const page = list.find((p) => p.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  ws.addEventListener("message", (ev) => {
    const m = JSON.parse(ev.data);
    if (m.method === "Runtime.consoleAPICalled") {
      const args = m.params.args.map((a) => a.value ?? a.description ?? "").join(" ");
      console.log("[console]", args);
    }
    if (m.method === "Runtime.exceptionThrown") {
      console.log("[exception]", JSON.stringify(m.params.exceptionDetails).slice(0, 800));
    }
  });
  await cdp(ws, "Runtime.enable");
  await cdp(ws, "Page.enable");
  await cdp(ws, "Page.navigate", { url });
  await new Promise((r) => setTimeout(r, 15000));
  const res = await cdp(ws, "Runtime.evaluate", {
    expression: `JSON.stringify({
      ready: document.readyState,
      done: window.__AUTODEMO_DONE,
      meta: !!window.__META_DEBUG,
      chip: document.getElementById('statusChip')?.textContent,
      tabActive: document.querySelector('.tab.active')?.dataset.tab,
      hasWeights: !!document.getElementById('weightsResult')?.children.length,
      hasIndices: !!document.getElementById('indicesResult')?.children.length
    })`,
    returnByValue: true,
  });
  console.log("STATE:", res.result.value);
  ws.close();
  chrome.kill();
  process.exit(0);
})().catch((e) => { console.error("ERR:", e.message); chrome.kill(); process.exit(1); });
