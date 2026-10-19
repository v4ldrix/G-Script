// g-script panel + agent loop. DOM access goes through adapters.js, timing decisions through loopcore.js.
// Design rules: the session NEVER stops on its own (only the user or the phone stops it), it survives
// page reloads, and it only sends when the AI has finished writing.
(() => {
  if (window.__gscriptLoaded) return;
  window.__gscriptLoaded = true;
  const A = window.__gsAdapter && window.__gsAdapter();
  if (!A) return;
  const { domToText } = window.__gsUtil;
  const L = window.GS_LOOP;
  const SITE = (window.GS_SITES || []).find((s) => s.host === location.hostname);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  const fp = (t) => L.fingerprint(t);
  const S = L.newState();

  async function api(path, method = "GET", body) {
    try {
      return (await chrome.runtime.sendMessage({ type: "api", path, method, body })) || { ok: false, status: 0, data: {} };
    } catch (e) {
      return { ok: false, status: -1, data: { error: "extension reloaded" } };
    }
  }

  // ---------- panel (shadow DOM so site CSS can't touch it) ----------
  const host = document.createElement("div");
  host.style.cssText = "position:fixed;right:18px;bottom:18px;z-index:2147483647;width:340px;";
  const root = host.attachShadow({ mode: "open" });
  root.innerHTML = `
    <style>
      *{box-sizing:border-box}
      [hidden]{display:none!important}
      .card,.pill{font:13px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;color:#e9edf1}
      .card{width:100%;background:linear-gradient(180deg,#1a1f26,#14181d);border:1px solid #ffffff1c;border-radius:14px;
            box-shadow:0 6px 24px #0006;padding:9px 11px;animation:in .18s ease-out}
      @keyframes in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
      .barrow{display:flex;align-items:center;gap:8px}
      .grow{flex:1}
      .dot{width:8px;height:8px;border-radius:50%;background:#6b7580;flex:none}
      .dot.warn{background:#f0b429}.dot.ok{background:#3ddc84;box-shadow:0 0 8px #3ddc8488}
      .dot.run{background:#4da3ff;animation:pulse 1.1s infinite}
      @keyframes pulse{50%{opacity:.35}}
      .statetxt{font-size:12.5px;color:#aeb8c2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .icon{background:none;border:0;color:#9aa6b2;font-size:17px;line-height:1;cursor:pointer;border-radius:8px;width:28px;height:28px;flex:none}
      .icon:hover{background:#ffffff12;color:#fff}
      .icon.hot{background:#7c5cff;color:#fff;animation:pulse 1.2s infinite}
      .bar{height:2px;border-radius:2px;background:#ffffff12;overflow:hidden;margin-top:8px}
      .bar i{display:block;height:100%;width:40%;border-radius:2px;background:linear-gradient(90deg,#7c5cff,#2f9bff);animation:slide 1.2s infinite ease-in-out}
      @keyframes slide{0%{margin-left:-40%}100%{margin-left:100%}}
      .msg{margin:0 0 7px;color:#cfd7df;word-break:break-word;font-size:12.5px}.msg:empty{display:none}
      .done{margin:0 0 7px;padding:7px 10px;border-radius:9px;background:#3ddc8420;border:1px solid #3ddc8455;color:#8ff0b8;font-weight:600}
      .log{list-style:none;margin:0 0 7px;padding:0;font-size:12px;color:#8c98a4}.log:empty{display:none}
      .log li{padding:1px 0;display:flex;gap:6px}.log li::before{content:"•";color:#4a5561}
      .ask{margin:0 0 8px;padding:10px;border-radius:11px;background:#222932;border:1px solid #ffffff14}
      .at{font-weight:600;margin-bottom:7px}
      .steps{list-style:none;margin:0 0 9px;padding:0;max-height:140px;overflow:auto}
      .steps li{display:flex;gap:8px;align-items:baseline;padding:3px 0;border-top:1px solid #ffffff0d}
      .steps li:first-child{border-top:0}
      .chip{background:#2f9bff26;color:#7cc0ff;border-radius:6px;padding:1px 7px;font:600 11px ui-monospace,monospace;flex:none}
      .args{color:#8c98a4;font:11px ui-monospace,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .row{display:flex;gap:8px}
      button.b{border:0;border-radius:9px;padding:7px 13px;font:600 13px system-ui,sans-serif;cursor:pointer;color:#fff;transition:filter .12s,transform .05s}
      .row button.b{flex:1}
      button.b:hover{filter:brightness(1.12)}button.b:active{transform:scale(.98)}
      .ok-b{background:#2fb872}.no-b{background:#3a434d}
      .go{background:linear-gradient(135deg,#7c5cff,#2f9bff);flex:none}.go.stop{background:#3a434d}
      .settings{margin-top:9px;padding-top:9px;border-top:1px solid #ffffff12;display:flex;flex-direction:column;gap:8px;align-items:flex-start}
      .sw{display:flex;align-items:center;gap:8px;font-size:12.5px;color:#aeb8c2;cursor:pointer;user-select:none}
      .sw input{display:none}
      .sw span{width:30px;height:17px;border-radius:9px;background:#3a434d;position:relative;transition:background .15s;flex:none}
      .sw span::after{content:"";position:absolute;top:2px;left:2px;width:13px;height:13px;border-radius:50%;background:#fff;transition:transform .15s}
      .sw input:checked+span{background:#2fb872}.sw input:checked+span::after{transform:translateX(13px)}
      .pill{display:inline-flex;align-items:center;gap:8px;padding:6px 12px;border-radius:999px;background:#171b21;border:1px solid #ffffff14;
            box-shadow:0 4px 14px #0007;cursor:pointer;font-weight:600}
    </style>
    <div class="pill" id="pill" hidden><span class="dot" id="dot2"></span>g-script</div>
    <div class="card" id="card">
      <div class="ask" id="phoneask" hidden>
        <div class="at" id="pname"></div>
        <div class="row"><button class="b ok-b" id="pyes">Allow</button><button class="b no-b" id="pno">Deny</button></div>
      </div>
      <div class="ask" id="ask" hidden>
        <div class="at" id="atitle"></div>
        <ul class="steps" id="asteps"></ul>
        <div class="row"><button class="b ok-b" id="yes">Approve</button><button class="b no-b" id="no">Decline</button></div>
      </div>
      <div class="done" id="done" hidden></div>
      <div class="msg" id="msg"></div>
      <ul class="log" id="log"></ul>
      <div class="barrow">
        <span class="dot" id="dot"></span><span class="statetxt" id="state">Starting…</span>
        <span class="grow"></span>
        <button class="b go" id="go">Start g-script</button>
        <button class="icon" id="gear" title="Settings">⚙</button>
      </div>
      <div class="bar" id="bar" hidden><i></i></div>
      <div class="settings" id="settings" hidden>
        <label class="sw"><input type="checkbox" id="auto"><span></span>Auto-approve actions</label>
        <button class="b no-b" id="rules" hidden>↻ Send the rules again</button>
        <button class="b no-b" id="min">Hide this bar</button>
      </div>
    </div>`;
  document.documentElement.appendChild(host);
  const $ = (id) => root.getElementById(id);

  const setMsg = (t) => { $("msg").textContent = t; };
  let curState = "";
  const setState = (label, cls) => {
    curState = label;
    $("state").textContent = label;
    $("dot").className = "dot " + (cls || "");
    $("dot2").className = "dot " + (cls || "");
    $("bar").hidden = cls !== "run";
  };
  const logLines = [];
  const log = (t) => {
    logLines.push(t);
    while (logLines.length > 2) logLines.shift();
    const ul = $("log");
    ul.innerHTML = "";
    logLines.forEach((l) => { const li = document.createElement("li"); li.textContent = l; ul.append(li); });
  };
  const showDone = (t) => { $("done").textContent = "✓ " + t; $("done").hidden = false; };
  const hideDone = () => { $("done").hidden = true; };
  const syncButtons = () => {
    $("go").textContent = S.active ? "Stop" : "Start g-script";
    $("go").classList.toggle("stop", S.active);
    $("rules").hidden = !S.active;
  };
  $("min").onclick = () => { $("card").hidden = true; $("pill").hidden = false; };
  $("pill").onclick = () => { $("pill").hidden = true; $("card").hidden = false; };


  // ---------- dock directly above the chat box (floats in the corner if the box can't be found) ----------
  function composerTarget() {
    const input = A.input();
    if (!input) return null;
    let el = input.closest("form") || input.closest("fieldset");
    if (el) return el;
    el = input;
    const iw = input.getBoundingClientRect().width;
    for (let i = 0; i < 5 && el.parentElement && el.parentElement !== document.body; i++) {
      const p = el.parentElement;
      if (i >= 2 && p.getBoundingClientRect().width > iw * 1.5) break;
      el = p;
    }
    return el;
  }
  function mount() {
    const t = composerTarget();
    if (!t || !t.parentNode) return false;
    if (host.parentNode !== t.parentNode || host.nextSibling !== t) t.parentNode.insertBefore(host, t);
    const w = Math.max(300, Math.round(t.getBoundingClientRect().width));
    host.style.cssText = `display:block;position:relative;z-index:5;box-sizing:border-box;width:${w}px;max-width:100%;margin:0 auto 8px;`;
    return true;
  }
  setInterval(mount, 1000);
  mount();
  $("gear").onclick = () => { $("settings").hidden = !$("settings").hidden; $("gear").classList.remove("hot"); };

  // a phone asks to connect: you compare two words and click Allow (no codes)
  let phoneAskId = null;
  function renderPhoneAsk(list) {
    const p = list && list[0];
    if (!p) { $("phoneask").hidden = true; phoneAskId = null; return; }
    if (phoneAskId !== p.id) { phoneAskId = p.id; $("pname").textContent = `📱 A phone wants to connect: ${p.words}. Allow only if your phone shows these same two words.`; }
    $("phoneask").hidden = false;
  }
  const decidePhone = async (ok) => { const id = phoneAskId; $("phoneask").hidden = true; await api("/remote/pair/decide", "POST", { id, approve: ok }); log(ok ? "Phone allowed" : "Phone denied"); };
  $("pyes").onclick = () => decidePhone(true);
  $("pno").onclick = () => decidePhone(false);

  // ---------- state ----------
  let ready = false, idle = false, ackPending = false, starting = false;
  let pendingId = null, resolver = null, lastSteps = 0, wasGenerating = false, bridgeState = "";
  let chatPath = location.pathname;
  const phoneQ = [];
  const keep = (on) => { try { on ? sessionStorage.setItem("gs_active", "1") : sessionStorage.removeItem("gs_active"); } catch (e) {} };

  // treat whatever is on screen as already handled (so history is never re-run)
  function rebaseline() {
    const m = A.lastMessage();
    S.lastText = m ? domToText(m) : "";
    S.doneHash = fp(S.lastText);
    S.lastChange = Date.now();
    S.awaitingNew = false;
    S.sawIncrease = 0;
  }

  function renderSteps(calls) {
    const ul = $("asteps");
    ul.innerHTML = "";
    ul.hidden = !calls.length;
    calls.slice(0, 8).forEach((c) => {
      const li = document.createElement("li");
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = c.tool;
      const args = document.createElement("span");
      args.className = "args";
      const s = JSON.stringify(c.args || {});
      args.textContent = s.length > 80 ? s.slice(0, 80) + "…" : s;
      li.append(chip, args);
      ul.append(li);
    });
    if (calls.length > 8) {
      const li = document.createElement("li");
      li.textContent = `+ ${calls.length - 8} more`;
      li.style.color = "#8c98a4";
      ul.append(li);
    }
  }

  function ask(title, calls, yes, no) {
    return new Promise((res) => {
      $("atitle").textContent = title;
      renderSteps(calls);
      $("yes").textContent = yes;
      $("no").textContent = no;
      $("ask").hidden = false;
      setState("Needs your OK", "warn");
      resolver = (v) => { $("ask").hidden = true; resolver = null; res(v); };
    });
  }
  $("yes").onclick = () => resolver && resolver(true);
  $("no").onclick = () => resolver && resolver(false);

  const postEvent = (type, text) => api("/ext/event", "POST", { type, text: String(text || "").slice(0, 3000) });
  const clean = (t) => t.replace(/\n{3,}/g, "\n\n").trim();

  // ---------- bridge status ----------
  function applyBridge(next) {
    ready = next === "ok";
    if (next === bridgeState) return;
    bridgeState = next;
    if (next === "reload") { setState("Refresh the page", ""); setMsg("The extension was updated. Reload this tab."); }
    else if (next === "offline") { setState("Offline", ""); setMsg(S.active ? "The g-script app isn't reachable. I'll carry on when it's back." : "Open the g-script app on your PC."); }
    else if (next === "unpaired") { setState("Connecting…", "warn"); setMsg("Connecting to the g-script app. If this stays, open the g-script icon > ⚙ > Reconnect."); }
    else if (next === "nostudio") { setState("Waiting for Studio", "warn"); setMsg("Open a place in Roblox Studio with MCP enabled."); }
    else if (!S.active) { setState("Ready", "ok"); setMsg("Click Start, then tell the AI what to build."); }
    else setState(idle ? "Ready" : "Working…", idle ? "ok" : "run");
  }
  async function refreshStatus() {
    const r = await api("/status");
    if (r.status === -1) return applyBridge("reload");
    if (r.status === 0) return applyBridge("offline");
    if (r.status === 401 || !r.hasToken) return applyBridge("unpaired");
    if (r.ok && (!r.data.mcp_alive || !r.data.tools.length)) return applyBridge("nostudio");
    if (r.ok) applyBridge("ok");
  }
  setInterval(refreshStatus, 3000);
  refreshStatus();

  // ---------- chat I/O ----------
  async function sendToChat(text) {
    const ok = await A.sendMessage(text);      // waits for the AI to be idle, verifies the box emptied
    if (!ok) {
      try { await navigator.clipboard.writeText(text); } catch (e) {}
      setMsg("Couldn't send to the chat. The text was copied, paste it and send it yourself.");
      return false;
    }
    const m = A.lastMessage();
    S.awaitingNew = true;
    S.hashAtSend = fp(m ? domToText(m) : "");
    S.countAtSend = A.count();
    S.sentAt = Date.now();
    S.sawIncrease = 0;
    return true;
  }

  async function handle(text) {
    const r = await api("/message", "POST", { text });
    if (!r.ok) { setMsg("Can't reach the g-script app. Trying again…"); return false; }
    const d = r.data;
    lastSteps = d.steps || lastSteps;
    if (d.status === "send") {
      hideDone();
      idle = false;
      setState("Working…", "run");
      if (d.count) log(`Ran ${plural(d.count, "step")} in Studio`);
      setMsg("Sent the results back to the AI.");
      if (!(await sendToChat(d.reply))) idle = true;
    } else if (d.status === "waiting") { await sleep(1500); return false; }
    else if (d.status === "finished") {
      idle = true;
      if (ackPending) ackPending = false;                 // the AI just acknowledged the rules
      else if (clean(text)) postEvent("ai", clean(text));
      setState("Ready", "ok");
      if (lastSteps > 0) { showDone(`Done. ${plural(lastSteps, "step")} ran in Studio.`); setMsg("Tell the AI what's next."); }
      else setMsg("Connected. Tell the AI what to build.");
    } else if (d.status === "approval") { await onApproval(d.pending); }
    else if (d.status === "limit") {
      const go = await ask("Step limit reached. Let the AI continue?", [], "Continue", "Stop");
      if (!S.active) return true;
      if (go) { await api("/reset", "POST", {}); S.doneHash = null; setState("Working…", "run"); }
      else await stop("Stopped at the step limit.");
    }
    return true;
  }

  async function onApproval(p) {
    const calls = p.calls && p.calls.length ? p.calls : [{ tool: p.tool, args: p.args }];
    const title = calls.length === 1 ? `Allow ${calls[0].tool}?` : `Review ${calls.length} steps`;
    pendingId = p.id;
    const ok = $("auto").checked ? true : await ask(title, calls, calls.length === 1 ? "Approve" : "Approve all", "Decline");
    pendingId = null;
    if (!S.active) return;
    setState("Working…", "run");
    const r = await api("/approve", "POST", { id: p.id, approve: ok });
    if (r.ok && r.data.reply) {
      hideDone();
      idle = false;
      log(ok ? `Ran ${plural(r.data.count || calls.length, "step")} in Studio` : "Declined");
      setMsg(ok ? "Sent the results back to the AI." : "Told the AI you declined.");
      if (!(await sendToChat(r.data.reply))) idle = true;
    }
  }

  // ---------- start / stop ----------
  async function start(fromPhone) {
    const fail = (m) => { setMsg(m); if (fromPhone) postEvent("error", "Couldn't start the chat: " + m); return false; };
    if (!ready) await refreshStatus();
    if (!ready) return fail("Not ready yet. Check the status above.");
    if (!A.input()) return fail("Can't find the chat box on this page.");
    const r = await api("/rules");
    if (!r.ok) return fail("Couldn't get the rules from the g-script app.");
    await api("/reset", "POST", {});
    rebaseline();
    S.active = true; S.retryAt = 0; S.busy = false;
    keep(true); syncButtons(); hideDone();
    lastSteps = 0;
    setState("Working…", "run");
    setMsg("Sending the rules to the AI…");
    idle = false;
    ackPending = true;                         // the AI's reply to the rules is not a build result
    if (!(await sendToChat(r.data.rules))) { idle = true; ackPending = false; return false; }
    setState("Ready", "ok");
    setMsg("Connected. Tell the AI what to build.");
    return true;
  }

  async function stop(msg) {
    S.active = false; S.awaitingNew = false;
    idle = false;
    phoneQ.length = 0;
    keep(false);
    if (resolver) resolver(false);
    await api("/reset", "POST", {});
    syncButtons(); hideDone();
    setMsg(msg || "Stopped.");
    bridgeState = "";
    refreshStatus();
  }

  async function resendRules() {
    if (!S.active) return;
    const r = await api("/rules");
    if (!r.ok) { setMsg("Couldn't get the rules from the g-script app."); return; }
    $("gear").classList.remove("hot");
    idle = false; ackPending = true;
    setMsg("Sending the rules again…");
    if (await sendToChat(r.data.rules)) setMsg("Rules sent. Tell the AI what to build.");
    else { idle = true; ackPending = false; }
  }

  // resume after the page reloads or the site re-mounts (never silently drop the session)
  function resume() {
    if (S.active) return;
    rebaseline();
    S.active = true; S.busy = false; S.retryAt = 0;
    S.settleUntil = Date.now() + 6000;
    idle = true;
    syncButtons();
    setState("Ready", "ok");
    setMsg("Resumed. g-script was kept running after the page reloaded.");
  }

  $("go").onclick = () => (S.active ? stop() : start(false));
  $("rules").onclick = resendRules;

  // ---------- main loop ----------
  let tickBusy = false;
  setInterval(async () => {
    if (!S.active || tickBusy) return;
    tickBusy = true;
    try {
      const m = A.lastMessage();
      const text = m ? domToText(m) : "";
      const generating = A.isGenerating();
      const now = Date.now();

      if (generating !== wasGenerating) {
        wasGenerating = generating;
        if (generating && !resolver) setState("AI is writing…", "run");
        else if (!generating && !resolver) setState(idle ? "Ready" : "Working…", idle ? "ok" : "run");
      }
      // the chat page changed (switched or started a new chat): never re-run what's on screen
      if (location.pathname !== chatPath) {
        chatPath = location.pathname;
        if (!S.awaitingNew && !S.busy) {
          rebaseline();
          $("gear").classList.add("hot"); $("rules").hidden = false;
          setMsg("Chat changed. If this is a new chat, press ↻ to send the rules here.");
          return;
        }
      }
      // right after a reload the history is still loading: keep treating it as handled
      if (S.settleUntil && now < S.settleUntil && !S.awaitingNew && !generating) { rebaseline(); return; }

      const act = L.decide(S, { text, h: fp(text), n: A.count(), generating, now, settleMs: A.settleMs });
      if (act === "process") {
        S.busy = true;
        let ok = false;
        try { ok = await handle(text); }
        catch (e) { setMsg("Error: " + e.message); console.error("[g-script]", e); }
        finally {
          S.busy = false;
          S.lastChange = Date.now();
          if (!ok) { S.doneHash = null; S.retryAt = Date.now() + 3000; }   // try this message again shortly
        }
      } else if (act === "await-timeout") {
        idle = true;
        setState("Ready", "ok");
        setMsg("The AI hasn't replied. Send it a message to continue.");
      }
    } catch (e) {
      console.error("[g-script]", e);
    } finally { tickBusy = false; }
  }, 600);

  // ---------- requests from the phone and from the popup menu ----------
  async function runPrompt(prompt, fresh) {
    for (let i = 0; i < 30 && !A.input(); i++) await sleep(500);
    for (let i = 0; i < 20 && !ready; i++) { await refreshStatus(); if (!ready) await sleep(500); }
    if (!ready) { setMsg("g-script isn't ready: open the g-script app and Roblox Studio."); return false; }
    if (S.active && fresh) await stop("Starting your request…");
    if (!S.active && !(await start(false))) return false;
    phoneQ.push(prompt);
    setMsg("Queued your request.");
    return true;
  }

  let polling = false;
  async function pollHub() {
    if (polling || document.visibilityState !== "visible") return;
    polling = true;
    try {
      const r = await api("/ext/poll", "POST", { active: S.active, busy: S.active && (!idle || S.busy || !!resolver), site: location.hostname, state: curState });
      if (!r.ok) return;
      const d = r.data;
      renderPhoneAsk(d.pairing);
      if (d.stop && S.active) { await stop("Stopped from your phone."); return; }
      if (resolver && pendingId && d.decisions && Object.prototype.hasOwnProperty.call(d.decisions, pendingId)) {
        log(d.decisions[pendingId] ? "Approved from phone" : "Declined from phone");
        resolver(!!d.decisions[pendingId]);
      }
      for (const p of d.prompts || []) phoneQ.push(p.text);
      if (d.autostart && !S.active && ready && !starting) {
        starting = true;
        try { await start(true); } finally { starting = false; }
      }
    } finally { polling = false; }
  }
  setInterval(pollHub, 1200);

  setInterval(async () => {
    if (!S.active || !idle || S.busy || resolver || !phoneQ.length || A.isGenerating()) return;
    const text = phoneQ.shift();
    idle = false;
    hideDone();
    setState("Working…", "run");
    log("Request: " + (text.length > 38 ? text.slice(0, 38) + "…" : text));
    setMsg("Sent your request to the AI.");
    if (!(await sendToChat(text))) idle = true;
    S.lastChange = Date.now();
  }, 800);

  try {
    chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
      if (!msg) return;
      if (msg.type === "gs-ping") { sendResponse({ ok: true, active: S.active }); return; }
      if (msg.type === "gs-run") {
        const fresh = !!msg.fresh;
        const onNewChat = SITE && location.pathname === SITE.newPath && A.count() === 0;
        if (fresh && SITE && !onNewChat) {          // go to a new chat first, then run once the page has loaded
          try { sessionStorage.setItem("gs_run", JSON.stringify({ prompt: msg.prompt })); } catch (e) {}
          sendResponse({ ok: true, navigating: true });
          location.href = SITE.newUrl;
          return;
        }
        sendResponse({ ok: true });
        runPrompt(msg.prompt, fresh).catch((e) => setMsg("Error: " + e.message));
      }
    });
  } catch (e) {}

  // ---------- remember panel settings ----------
  try {
    chrome.storage.local.get(["gs_auto", "gs_min"]).then((s) => {
      if (s.gs_auto) $("auto").checked = true;
      if (s.gs_min) { $("card").hidden = true; $("pill").hidden = false; }
    });
    $("auto").addEventListener("change", () => chrome.storage.local.set({ gs_auto: $("auto").checked }));
    $("min").addEventListener("click", () => chrome.storage.local.set({ gs_min: true }));
    $("pill").addEventListener("click", () => chrome.storage.local.set({ gs_min: false }));
  } catch (e) {}

  // ---------- on page load: run a queued request, or resume a running session ----------
  try {
    const queued = sessionStorage.getItem("gs_run");
    if (queued) {
      sessionStorage.removeItem("gs_run");
      keep(false);
      setTimeout(() => runPrompt(JSON.parse(queued).prompt, true).catch((e) => setMsg("Error: " + e.message)), 1500);
    } else if (sessionStorage.getItem("gs_active") === "1") {
      setTimeout(resume, 1200);
    }
  } catch (e) {}
})();
