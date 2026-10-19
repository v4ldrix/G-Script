const assert = require("assert");
global.window = {}; global.location = { hostname: "claude.ai" }; global.document = { querySelectorAll: () => [] };
require("../../extension/adapters.js");
const U = window.__gsUtil;
const F = "```";

const txt = (s) => ({ nodeType: 3, nodeValue: s });
function el(tag, kids = [], attrs = {}) {
  const n = { nodeType: 1, tagName: tag, childNodes: kids, className: attrs.class || "", innerText: attrs.innerText,
    getAttribute: (k) => (attrs[k] === undefined ? null : attrs[k]),
    querySelector: (sel) => (sel === "code" ? kids.find((k) => k.tagName === "CODE") || null : null),
    contains(o) { return o === n || kids.some((k) => k.contains && k.contains(o)); } };
  return n;
}
const code = (s, cls = "") => el("CODE", [txt(s)], { class: cls, innerText: s });
let passed = 0;
const test = (name, fn) => { fn(); passed++; console.log("ok -", name); };

test("unlabeled JSON code block becomes a gscript fence", () => {
  const out = U.domToText(el("DIV", [el("P", [txt("Plan.")]), el("PRE", [code('{"tool": "get_tree", "args": {}}\n')])]));
  assert.ok(out.includes(F + 'gscript\n{"tool": "get_tree", "args": {}}\n' + F));
});

test("other code blocks keep their language", () => {
  const out = U.domToText(el("DIV", [el("PRE", [code('print("hi")', "language-lua")])]));
  assert.ok(out.includes(F + 'lua\nprint("hi")\n' + F));
});

test("the model's thinking is never read as an instruction", () => {
  const thinking = el("DIV", [el("PRE", [code('{"tool": "run_luau", "args": {"code": "bad"}}')])], { class: "thinking-block" });
  const ds = el("DIV", [txt("secret")], { class: "ds-think-content" });
  const out = U.domToText(el("DIV", [thinking, ds, el("P", [txt("Final answer")])]));
  assert.ok(!out.includes("run_luau") && !out.includes("secret"));
  assert.ok(out.includes("Final answer"));
});

test("an element merely containing 'think' inside a word is kept", () => {
  assert.ok(!U.THINK_RE.test("thinker-card"));
  assert.ok(U.THINK_RE.test("font-thinking text-sm"));
  assert.ok(!U.THINK_RE.test("rethinkable"));
});

test("only the outermost match counts as a message", () => {
  const inner = el("DIV"), outer = el("DIV", [inner]), other = el("DIV");
  assert.deepStrictEqual(U.topLevel([outer, inner, other]), [outer, other]);
});

test("stop-button labels", () => {
  for (const s of ["Stop", "Stop response", "Stop generating", "Stop streaming", "Cancel"]) assert.ok(U.STOP_RE.test(s), s);
  for (const s of ["Send message", "Stopwatch settings", "Share"]) assert.ok(!U.STOP_RE.test(s), s);
});

console.log(`${passed} adapter tests passed`);
