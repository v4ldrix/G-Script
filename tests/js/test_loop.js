const assert = require("assert");
const L = require("../../extension/loopcore.js");

const F = "```";
const call = (n = "x") => `${F}gscript\n{"tool":"${n}"}\n${F}`;
const mk = (over = {}) => Object.assign(L.newState(), { active: true }, over);
const obs = (text, o = {}) => Object.assign({ text, h: L.fingerprint(text), n: 1, generating: false, now: 0, settleMs: 2000 }, o);
let passed = 0;
const test = (name, fn) => { fn(); passed++; console.log("ok -", name); };

test("waits for streaming to finish, then processes exactly once", () => {
  const s = mk(); let t = 0;
  const full = "Doing it\n" + call();
  for (const part of ["Doing", "Doing it", full]) assert.equal(L.decide(s, obs(part, { now: (t += 500) })), "observe");
  assert.equal(L.decide(s, obs(full, { now: (t += 500) })), "none");                    // not settled yet
  assert.equal(L.decide(s, obs(full, { now: (t += 2000), generating: true })), "none"); // site says still generating
  assert.equal(L.decide(s, obs(full, { now: (t += 100) })), "process");
  assert.equal(L.decide(s, obs(full, { now: (t += 3000) })), "none");
});

test("message count flicker never re-runs a handled message", () => {
  const s = mk(); let t = 0; const full = "A\n" + call();
  L.decide(s, obs(full, { now: 0 })); assert.equal(L.decide(s, obs(full, { now: 2500 })), "process");
  t = 3000;
  for (const [text, n] of [["", 0], [full, 1], ["", 0], [full, 2], [full, 1]]) {
    for (let i = 0; i < 4; i++) assert.notEqual(L.decide(s, obs(text, { n, now: (t += 200) })), "process");
  }
  for (let i = 0; i < 20; i++) assert.notEqual(L.decide(s, obs(full, { n: 1, now: (t += 1000) })), "process"); // and later too
  for (let i = 0; i < 20; i++) assert.notEqual(L.decide(s, obs("", { n: 0, now: (t += 1000) })), "process");   // even a lasting empty page
});

test("a re-render with different prose but the same call is not a new message", () => {
  const s = mk(); const a = "Plan one\n" + call("a"), b = "  Plan   one!!\n" + call("a");
  L.decide(s, obs(a, { now: 0 })); assert.equal(L.decide(s, obs(a, { now: 2500 })), "process");
  L.decide(s, obs(b, { now: 3000 }));
  assert.equal(L.decide(s, obs(b, { now: 9000 })), "none");
});

test("after sending, the old message is ignored until a new one appears", () => {
  const s = mk(); const old = "A\n" + call();
  L.decide(s, obs(old, { now: 0 })); L.decide(s, obs(old, { now: 2500 }));
  Object.assign(s, { awaitingNew: true, hashAtSend: L.fingerprint(old), countAtSend: 1, sentAt: 3000 });
  for (let t = 3000; t < 20000; t += 1000) assert.equal(L.decide(s, obs(old, { now: t })), "none");
  assert.equal(L.decide(s, obs("Done.", { now: 21000 })), "observe");
  assert.equal(L.decide(s, obs("Done.", { now: 24000 })), "process");
});

test("an identical repeated call is still run, once the extra message lasts", () => {
  const s = mk(); const c = "Retry\n" + call("same");
  L.decide(s, obs(c, { now: 0 })); L.decide(s, obs(c, { now: 2500 }));
  Object.assign(s, { awaitingNew: true, hashAtSend: L.fingerprint(c), countAtSend: 1, sentAt: 3000 });
  assert.equal(L.decide(s, obs(c, { n: 2, now: 4000 })), "none");
  assert.equal(L.decide(s, obs(c, { n: 2, now: 5000 })), "none");
  assert.equal(L.decide(s, obs(c, { n: 2, now: 6100 })), "observe");
  assert.equal(L.decide(s, obs(c, { n: 2, now: 6200 })), "observe");
  assert.equal(L.decide(s, obs(c, { n: 2, now: 9000 })), "process");
});

test("a brief count blip after sending does not count as a new message", () => {
  const s = mk(); const c = "A\n" + call();
  L.decide(s, obs(c, { now: 0 })); L.decide(s, obs(c, { now: 2500 }));
  Object.assign(s, { awaitingNew: true, hashAtSend: L.fingerprint(c), countAtSend: 1, sentAt: 3000 });
  L.decide(s, obs(c, { n: 2, now: 4000 })); L.decide(s, obs(c, { n: 1, now: 4500 }));
  assert.equal(L.decide(s, obs(c, { n: 2, now: 7000 })), "none");
});

test("gives up waiting after a long silence", () => {
  const s = mk(); const c = "A\n" + call();
  Object.assign(s, { awaitingNew: true, hashAtSend: L.fingerprint(c), countAtSend: 1, sentAt: 0 });
  assert.equal(L.decide(s, obs(c, { now: 50000 })), "none");
  assert.equal(L.decide(s, obs(c, { now: 91000 })), "await-timeout");
  assert.equal(s.awaitingNew, false);
});

test("retry delay, busy and inactive states do nothing", () => {
  const c = "A\n" + call();
  assert.equal(L.decide(mk({ retryAt: 5000 }), obs(c, { now: 1000 })), "none");
  assert.equal(L.decide(mk({ busy: true }), obs(c, { now: 1000 })), "none");
  assert.equal(L.decide(mk({ active: false }), obs(c, { now: 1000 })), "none");
});

console.log(`${passed} loop tests passed`);
