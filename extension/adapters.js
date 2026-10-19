// Per-site DOM adapters. The selectors are best-effort and the part most likely to need a tweak when a
// site changes its layout. Everything else in g-script is site-agnostic.
(() => {
  const visible = (el) => !!el && (el.offsetParent !== null || el.getClientRects().length > 0);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const hashText = (s) => { let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0; return h; };

  // A visible button that stops generation (any site), and containers that hold the model's "thinking".
  const STOP_RE = /^(stop|cancel)( (generating|generation|response|streaming|reply))?$|stop (generating|generation|response|streaming)/i;
  const THINK_RE = /(^|[\s_-])(think|thinking|reasoning|thought)([\s_-]|$)|ds-think/i;

  const firstVisible = (sels) => {
    for (const s of sels) {
      const el = [...document.querySelectorAll(s)].find(visible);
      if (el) return el;
    }
    return null;
  };
  const allMatching = (sels) => {
    for (const s of sels) {
      const list = [...document.querySelectorAll(s)];
      if (list.length) return list;
    }
    return [];
  };
  // keep only the outermost match, so nested duplicates can't be counted as extra messages
  const topLevel = (list) => list.filter((el) => !list.some((o) => o !== el && o.contains(el)));

  const SITES = {
    "claude.ai": {
      input: ["div[contenteditable='true'].ProseMirror", "div[contenteditable='true'][role='textbox']", "fieldset div[contenteditable='true']"],
      send: ["button[aria-label='Send message']", "button[aria-label='Send Message']"],
      stop: ["button[aria-label='Stop response']", "button[aria-label='Stop Response']"],
      busy: ["[data-is-streaming='true']"],
      messages: [".font-claude-response", "div[data-is-streaming]", ".font-claude-message"],
      settleMs: 2000,
    },
    "chatgpt.com": {
      input: ["#prompt-textarea", "div[contenteditable='true'].ProseMirror", "textarea"],
      send: ["button[data-testid='send-button']", "button[aria-label='Send prompt']"],
      stop: ["button[data-testid='stop-button']", "button[aria-label='Stop streaming']"],
      busy: [".result-streaming"],
      messages: ["[data-message-author-role='assistant']"],
      settleMs: 2000,
    },
    "chat.deepseek.com": {
      input: ["textarea#chat-input", "textarea"],
      send: [],
      stop: [],
      busy: [],
      messages: [".ds-markdown"],
      enterToSend: true,
      settleMs: 3500, // no reliable stop button: wait longer for the text to stop changing
    },
    "gemini.google.com": {
      input: ["rich-textarea .ql-editor", "div.ql-editor[contenteditable='true']", "div[contenteditable='true']"],
      send: ["button.send-button", "button[aria-label='Send message']"],
      stop: ["button[aria-label='Stop response']"],
      busy: [],
      messages: ["message-content", ".model-response-text", ".markdown"],
      settleMs: 2500,
    },
  };

  function setText(el, text) {
    el.focus();
    if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
      const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value").set.call(el, text);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      return;
    }
    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(el);
    sel.removeAllRanges();
    sel.addRange(range);
    const ok = document.execCommand("insertText", false, text);
    if (!ok || !(el.innerText || "").trim()) {
      const dt = new DataTransfer();
      dt.setData("text/plain", text);
      el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    }
  }

  const inputEmpty = (el) => !el || ((el.tagName === "TEXTAREA" || el.tagName === "INPUT") ? !el.value.trim() : !(el.innerText || "").trim());

  function pressEnter(el) {
    el.focus();
    for (const type of ["keydown", "keypress", "keyup"]) {
      el.dispatchEvent(new KeyboardEvent(type, { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
    }
  }

  function stopButtonVisible() {
    for (const b of document.querySelectorAll("button,[role='button']")) {
      if (!visible(b)) continue;
      const label = (b.getAttribute("aria-label") || b.getAttribute("title") || b.textContent || "").trim();
      if (label && label.length < 40 && STOP_RE.test(label)) return true;
    }
    return false;
  }

  // ---- turn rendered chat DOM back into text, re-creating ```gscript fences ----
  const BLOCK = new Set(["P", "DIV", "LI", "UL", "OL", "H1", "H2", "H3", "H4", "H5", "H6", "TABLE", "TR", "BLOCKQUOTE", "SECTION"]);

  function isThinking(node) {
    const attr = (n) => (typeof node.getAttribute === "function" ? node.getAttribute(n) || "" : "");
    const cls = typeof node.getAttribute === "function" ? attr("class") + " " + attr("data-testid") : String(node.className || "");
    return THINK_RE.test(cls);
  }

  function fenceFor(pre) {
    const codeEl = pre.querySelector("code");
    const code = ((codeEl || pre).innerText || (codeEl || pre).textContent || "").replace(/\r/g, "").replace(/\n+$/, "");
    const m = ((codeEl && codeEl.className) || "").match(/language-([\w-]+)/);
    let lang = m ? m[1] : "";
    if (!lang || ["json", "plaintext", "text"].includes(lang)) {
      const t = code.trim();
      if (t.startsWith("{") && /"tool"\s*:/.test(t)) lang = "gscript"; // code block header may hide the language
    }
    return "```" + lang + "\n" + code + "\n```";
  }

  function domToText(node, out = [], root = true) {
    if (node.nodeType === 3) { out.push(node.nodeValue); return out; }
    if (node.nodeType !== 1) return out;
    if (!root && isThinking(node)) return out;   // never act on the model's hidden reasoning
    const tag = node.tagName;
    if (tag === "PRE") { out.push("\n" + fenceFor(node) + "\n"); return out; }
    if (tag === "BR") { out.push("\n"); return out; }
    const block = BLOCK.has(tag);
    if (block) out.push("\n");
    node.childNodes.forEach((c) => domToText(c, out, false));
    if (block) out.push("\n");
    return out;
  }

  window.__gsUtil = { domToText: (el) => domToText(el).join(""), topLevel, STOP_RE, THINK_RE };

  window.__gsAdapter = () => {
    const site = SITES[location.hostname];
    if (!site) return null;
    return {
      settleMs: site.settleMs,
      input() {
        const el = firstVisible(site.input);
        if (el) return el;
        const fields = [...document.querySelectorAll("textarea, div[contenteditable='true']")].filter(visible);
        const area = (e) => e.getBoundingClientRect().width * e.getBoundingClientRect().height;
        fields.sort((a, b) => area(b) - area(a));
        return fields[0] || null;
      },
      sendButton: () => (site.send.length ? firstVisible(site.send) : null),
      isGenerating() {
        return (site.stop.length && !!firstVisible(site.stop)) ||
               site.busy.some((s) => !!document.querySelector(s)) ||
               stopButtonVisible();
      },
      messages: () => topLevel(allMatching(site.messages)),
      lastMessage() { const l = this.messages(); return l.length ? l[l.length - 1] : null; },
      count() { return this.messages().length; },

      // wait until the AI has stopped writing AND its text has been still for a moment
      async waitIdle(timeout = 120000) {
        const t0 = Date.now();
        let lastH = null, lastT = Date.now();
        while (Date.now() - t0 < timeout) {
          const m = this.lastMessage();
          const h = m ? hashText(m.textContent || "") : 0;
          if (h !== lastH) { lastH = h; lastT = Date.now(); }
          if (!this.isGenerating() && Date.now() - lastT > 1200) return true;
          await sleep(300);
        }
        return false;
      },

      // put text in the chat box and send it; only returns true once the box has actually emptied
      async sendMessage(text) {
        for (let attempt = 0; attempt < 3; attempt++) {
          if (!(await this.waitIdle())) return false;
          const input = this.input();
          if (!input) return false;
          setText(input, text);
          await sleep(350);
          let clicked = false;
          if (!site.enterToSend) {
            for (let i = 0; i < 12 && !clicked; i++) {
              const b = this.sendButton();
              if (b && !b.disabled && b.getAttribute("aria-disabled") !== "true") { b.click(); clicked = true; }
              else await sleep(200);
            }
          }
          if (!clicked) pressEnter(input);
          for (let i = 0; i < 14; i++) {
            await sleep(250);
            if (inputEmpty(this.input())) return true;
          }
          // the site refused it (for example it was still generating): wait and try again
        }
        return false;
      },
    };
  };
})();
