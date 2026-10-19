const $ = (id) => document.getElementById(id);
const call = (path, method = "GET") => chrome.runtime.sendMessage({ type: "api", path, method, body: method === "POST" ? {} : undefined });
const store = {
  get: (k, d) => chrome.storage.local.get(k).then((s) => (s[k] === undefined ? d : s[k])),
  set: (k, v) => chrome.storage.local.set({ [k]: v }),
};

let ai = "claude", ready = false, currentAction = null, activeSite = null, activeTabId = null;
const onThisTab = () => !!activeSite && activeSite.id === ai;
const views = ["viewMain", "viewForm", "viewSetup"];
const show = (id) => views.forEach((v) => ($(v).hidden = v !== id));

// ---------- status ----------
function setStatus(text, cls) {
  $("topSub").textContent = text; $("dot").className = "dot " + (cls || "");
  $("st").textContent = text; $("dot2").className = "dot " + (cls || "");
}
async function refresh() {
  const r = await call("/status");
  ready = false;
  if (r.status === 0) { setStatus("The g-script app isn't running"); banner("Open the g-script app on your PC first."); }
  else if (r.status === 401) { setStatus("Connecting…", "warn"); banner("Connecting to the g-script app… if this stays, open ⚙ and press Reconnect."); }
  else if (r.ok && r.data.mcp_alive && r.data.tools.length) { ready = true; setStatus(`Studio connected (${r.data.tools.length} tools)`, "ok"); banner(""); }
  else if (r.ok) { setStatus("Waiting for Roblox Studio…", "warn"); banner("Open a place in Roblox Studio and turn on MCP."); }
  else { setStatus("Error " + r.status); banner(""); }
  $("go").disabled = !ready;
}
function banner(t) { $("banner").hidden = !t; $("banner").textContent = t; }

// ---------- AI chips ----------
function renderAis() {
  const box = $("ais"); box.innerHTML = "";
  GS_SITES.forEach((s) => {
    const el = document.createElement("div");
    el.className = "chip" + (s.id === ai ? " sel" : "");
    const dot = document.createElement("i"); dot.style.background = s.color;
    el.append(dot, document.createTextNode(s.name));
    el.onclick = () => { ai = s.id; store.set("gs_ai", ai); $("fresh").checked = !onThisTab(); renderAis(); };
    box.append(el);
  });
}
$("openAi").onclick = () => { chrome.runtime.sendMessage({ type: "open", ai }); window.close(); };

// ---------- actions ----------
function renderActions() {
  const box = $("actions"); box.innerHTML = "";
  GS_ACTIONS.forEach((a) => {
    const b = document.createElement("button"); b.className = "card";
    const ic = document.createElement("div"); ic.className = "ic"; ic.textContent = a.icon;
    const t = document.createElement("b"); t.textContent = a.title;
    const h = document.createElement("span"); h.textContent = a.hint;
    b.append(ic, t, h);
    b.onclick = () => openForm(a);
    box.append(b);
  });
}

function openForm(a) {
  currentAction = a;
  $("fIcon").textContent = a.icon; $("fTitle").textContent = a.title;
  $("note").textContent = ""; $("note").className = "note";
  const box = $("fFields"); box.innerHTML = "";
  a.fields.forEach((f) => {
    const lab = document.createElement("label"); lab.className = "f"; lab.textContent = f.label; lab.htmlFor = "f_" + f.id;
    let inp;
    if (f.type === "select") {
      inp = document.createElement("select");
      f.options.forEach((o) => { const op = document.createElement("option"); op.value = o; op.textContent = o; inp.append(op); });
    } else if (f.long) { inp = document.createElement("textarea"); inp.placeholder = f.placeholder || ""; }
    else { inp = document.createElement("input"); inp.type = "text"; inp.placeholder = f.placeholder || ""; }
    inp.id = "f_" + f.id;
    box.append(lab, inp);
  });
  $("fresh").checked = !onThisTab();
  $("where").textContent = onThisTab() ? "Runs in this tab." : `Opens ${GS_SITES.find((s) => s.id === ai).name}.`;
  show("viewForm");
  const first = box.querySelector("input,textarea"); if (first) first.focus();
}

$("back").onclick = () => show("viewMain");
$("back2").onclick = () => show("viewMain");
$("gear").onclick = () => { show("viewSetup"); loadPhone(); };

$("go").onclick = async () => {
  const a = currentAction; const v = {};
  for (const f of a.fields) {
    v[f.id] = $("f_" + f.id).value.trim();
    if (f.required && !v[f.id]) { $("note").textContent = "Please fill in: " + f.label; $("note").className = "note bad"; $("f_" + f.id).focus(); return; }
  }
  const site = GS_SITES.find((s) => s.id === ai);
  $("go").disabled = true; $("note").className = "note"; $("note").textContent = `Opening ${site.name}…`;
  const r = await chrome.runtime.sendMessage({ type: "run", ai, prompt: a.build(v), fresh: $("fresh").checked, tabId: onThisTab() ? activeTabId : undefined });
  if (r && r.ok) { $("note").textContent = `Sent to ${site.name}. Watch the g-script panel there.`; setTimeout(() => window.close(), 700); }
  else { $("note").textContent = (r && r.error) || "Couldn't reach the AI page."; $("note").className = "note bad"; $("go").disabled = !ready; }
};

// ---------- reconnect (pairing is automatic) ----------
$("reconnect").onclick = async () => {
  setStatus("Connecting…", "warn");
  await chrome.runtime.sendMessage({ type: "autopair", port: $("port").value.trim() });
  setTimeout(refresh, 400);
};

// ---------- phone ----------
let phone = null;
function renderPhone() {
  if (!phone) return;
  $("phoneSec").hidden = false;
  $("phoneBtn").textContent = phone.enabled ? "Turn off phone app" : "Enable phone app";
  $("phoneBox").hidden = !phone.enabled;
  if (phone.enabled) {
    $("phoneUrl").textContent = phone.url; $("phoneCode").textContent = phone.code;
    $("phoneSub").textContent = phone.devices ? `${phone.devices} phone${phone.devices === 1 ? "" : "s"} paired.` : "No phone paired yet.";
  } else $("phoneSub").textContent = "Build from your phone on the same Wi-Fi.";
}
async function loadPhone() { const r = await call("/remote/status"); if (r.ok) { phone = r.data; renderPhone(); } }
$("phoneBtn").onclick = async () => { const r = await call(phone && phone.enabled ? "/remote/disable" : "/remote/enable", "POST"); if (r.ok) { phone = r.data; renderPhone(); } };
$("copyUrl").onclick = () => navigator.clipboard.writeText(phone.url).then(() => { $("copyUrl").textContent = "Copied!"; setTimeout(() => ($("copyUrl").textContent = "Copy link"), 1200); });
$("unpair").onclick = async () => { const r = await call("/remote/reset", "POST"); if (r.ok) { phone = r.data; renderPhone(); } };

// ---------- start ----------
(async () => {
  ai = await store.get("gs_ai", "claude");
  if (!GS_SITES.some((s) => s.id === ai)) ai = "claude";
  try {                                            // default to the AI you are already looking at
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    activeSite = tab && tab.url ? GS_SITES.find((s) => tab.url.startsWith("https://" + s.host + "/")) || null : null;
    activeTabId = tab ? tab.id : null;
    if (activeSite) ai = activeSite.id;
  } catch (e) {}
  const p = await store.get("port", ""); if (p) $("port").value = p;
  renderAis(); renderActions(); show("viewMain");
  await refresh();
  setInterval(refresh, 3000);
})();
