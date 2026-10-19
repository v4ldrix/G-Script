// Pure decision logic for the agent loop (no DOM), so it can be tested.
// The loop must (1) never stop on its own, (2) never run the same message twice,
// (3) never act on a message that is still being written, (4) not misread a re-render as a new reply.
(function (root) {
  const norm = (s) => String(s || "").replace(/\s+/g, " ").trim();
  function hash(s) { let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0; return h; }

  // What identifies a message: its gscript blocks if it has any (prose may re-render), else its text.
  function fingerprint(text) {
    const blocks = String(text || "").match(/```[ \t]*gscript[ \t]*\r?\n[\s\S]*?```/gi);
    return hash(blocks ? norm(blocks.join("\n")) : norm(text));
  }

  function newState() {
    return {
      active: false, busy: false,
      awaitingNew: false, hashAtSend: 0, countAtSend: 0, sentAt: 0, sawIncrease: 0, awaitTimeout: 90000,
      lastText: "", lastChange: 0, doneHash: null, retryAt: 0,
    };
  }

  // s = state (mutated), o = observation {text, h, n, generating, now, settleMs}
  // returns: "none" | "observe" | "process" | "await-timeout"
  function decide(s, o) {
    if (!s.active || s.busy) return "none";
    if (o.now < s.retryAt) return "none";

    if (s.awaitingNew) {                       // we just sent something; wait for the AI's NEW message
      if (o.h !== s.hashAtSend) {
        s.awaitingNew = false; s.sawIncrease = 0; s.lastText = o.text; s.lastChange = o.now;
        return "observe";
      }
      if (o.n > s.countAtSend) {               // a new message that looks identical: only trust a lasting increase
        if (!s.sawIncrease) s.sawIncrease = o.now;
        else if (o.now - s.sawIncrease >= 2000) {
          s.awaitingNew = false; s.sawIncrease = 0; s.doneHash = null; s.lastText = null;
          return "observe";
        }
      } else s.sawIncrease = 0;
      if (o.now - s.sentAt > s.awaitTimeout && !o.generating) {
        s.awaitingNew = false; s.sawIncrease = 0;
        return "await-timeout";
      }
      return "none";
    }

    if (o.text !== s.lastText) { s.lastText = o.text; s.lastChange = o.now; return "observe"; }
    if (!String(o.text).trim()) return "none";  // nothing there (a re-render blip): nothing to handle
    if (o.h === s.doneHash) return "none";     // already handled (also covers re-renders and count flicker)
    if (o.generating || o.now - s.lastChange < o.settleMs) return "none";
    s.doneHash = o.h;
    return "process";
  }

  const api = { norm, hash, fingerprint, newState, decide };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.GS_LOOP = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
