// Talks to the local bridge on behalf of content scripts, and opens/switches AI tabs for the popup menu.
importScripts("sites.js");
const DEFAULT_PORT = 8765;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function cfg() {
  const s = await chrome.storage.local.get(["token", "port"]);
  return { token: s.token || "", port: s.port || DEFAULT_PORT };
}

// no codes: the g-script app trusts the first browser extension that asks, so we just ask
let pairing = null;
function autoPair() {
  if (pairing) return pairing;
  pairing = (async () => {
    try {
      const { port } = await cfg();
      const r = await fetch(`http://127.0.0.1:${port}/pair`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const d = await r.json().catch(() => ({}));
      if (r.ok && d.token) { await chrome.storage.local.set({ token: d.token }); return true; }
    } catch (e) { /* app not running yet */ }
    return false;
  })().finally(() => setTimeout(() => { pairing = null; }, 3000));
  return pairing;
}

async function call(path, method = "GET", body, retried = false) {
  const { token, port } = await cfg();
  try {
    const r = await fetch(`http://127.0.0.1:${port}${path}`, {
      method,
      headers: { "Content-Type": "application/json", "X-GScript-Token": token },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (r.status === 401 && !retried && (await autoPair())) return call(path, method, body, true);
    const data = await r.json().catch(() => ({}));
    return { ok: r.ok, status: r.status, data, hasToken: !!token };
  } catch (e) {
    return { ok: false, status: 0, data: { error: "bridge offline" }, hasToken: !!token };
  }
}

async function pair(code, port) {
  if (port) await chrome.storage.local.set({ port: Number(port) });
  const { port: p } = await cfg();
  try {
    const r = await fetch(`http://127.0.0.1:${p}/pair`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    const data = await r.json().catch(() => ({}));
    if (r.ok && data.token) {
      await chrome.storage.local.set({ token: data.token });
      return { ok: true };
    }
    return { ok: false, error: data.error || "pairing failed" };
  } catch (e) {
    return { ok: false, error: "the g-script app isn't running" };
  }
}

// ----- AI tabs -----
async function waitComplete(tabId, ms = 30000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    try { if ((await chrome.tabs.get(tabId)).status === "complete") return; } catch (e) { return; }
    await sleep(300);
  }
}

async function focusTab(tab) {
  await chrome.tabs.update(tab.id, { active: true });
  if (tab.windowId !== undefined) await chrome.windows.update(tab.windowId, { focused: true });
}

async function findOrOpen(site, preferId) {
  if (preferId) {                                   // stay on the tab the person is looking at
    try {
      const t = await chrome.tabs.get(preferId);
      if (t.url && t.url.startsWith(site.match.replace("/*", "/"))) { await focusTab(t); return { tab: t, created: false }; }
    } catch (e) { /* tab is gone */ }
  }
  const tabs = await chrome.tabs.query({ url: site.match });
  let tab = tabs.find((t) => t.active) || tabs[0];
  if (tab) { await focusTab(tab); return { tab, created: false }; }
  tab = await chrome.tabs.create({ url: site.newUrl, active: true });
  await waitComplete(tab.id);
  return { tab, created: true };
}

async function sendRun(tabId, payload) {
  for (let i = 0; i < 40; i++) {
    try {
      const r = await chrome.tabs.sendMessage(tabId, payload);
      if (r) return r;
    } catch (e) { /* the page's script isn't ready yet */ }
    await sleep(500);
  }
  return { ok: false, error: "The AI page didn't respond. Reload it and try again." };
}

async function openAi(aiId) {
  const site = (globalThis.GS_SITES || []).find((s) => s.id === aiId);
  if (!site) return { ok: false, error: "Unknown AI" };
  await findOrOpen(site);
  return { ok: true };
}

async function runOn(aiId, prompt, fresh, tabId) {
  const site = (globalThis.GS_SITES || []).find((s) => s.id === aiId);
  if (!site) return { ok: false, error: "Unknown AI" };
  const { tab } = await findOrOpen(site, tabId);
  return sendRun(tab.id, { type: "gs-run", prompt, fresh: !!fresh });
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "api") { call(msg.path, msg.method, msg.body).then(sendResponse); return true; }
  if (msg.type === "pair") { pair(msg.code, msg.port).then(sendResponse); return true; }
  if (msg.type === "run") { runOn(msg.ai, msg.prompt, msg.fresh, msg.tabId).then(sendResponse); return true; }
  if (msg.type === "autopair") { (msg.port ? chrome.storage.local.set({ port: Number(msg.port) }) : Promise.resolve()).then(autoPair).then((ok) => sendResponse({ ok })); return true; }
  if (msg.type === "open") { openAi(msg.ai).then(sendResponse); return true; }
});

chrome.runtime.onInstalled.addListener(() => autoPair());
chrome.runtime.onStartup.addListener(() => autoPair());
