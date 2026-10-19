// Small QR code generator (byte mode, error correction M, versions 1-10). No dependencies.
(function (root) {
  "use strict";
  const ECC_PER_BLOCK = [10, 16, 26, 18, 24, 16, 18, 22, 22, 26];   // level M, versions 1..10
  const NUM_BLOCKS    = [1, 1, 1, 2, 2, 4, 4, 4, 5, 5];

  function gfMul(x, y) {
    let z = 0;
    for (let i = 7; i >= 0; i--) { z = (z << 1) ^ ((z >>> 7) * 0x11D); z ^= ((y >>> i) & 1) * x; }
    return z;
  }
  function rsDivisor(degree) {
    const r = new Array(degree).fill(0); r[degree - 1] = 1;
    let root = 1;
    for (let i = 0; i < degree; i++) {
      for (let j = 0; j < degree; j++) { r[j] = gfMul(r[j], root); if (j + 1 < degree) r[j] ^= r[j + 1]; }
      root = gfMul(root, 0x02);
    }
    return r;
  }
  function rsRemainder(data, divisor) {
    const r = new Array(divisor.length).fill(0);
    for (const b of data) {
      const factor = b ^ r.shift(); r.push(0);
      divisor.forEach((c, i) => { r[i] ^= gfMul(c, factor); });
    }
    return r;
  }
  function rawModules(ver) {
    let r = (16 * ver + 128) * ver + 64;
    if (ver >= 2) { const n = Math.floor(ver / 7) + 2; r -= (25 * n - 10) * n - 55; if (ver >= 7) r -= 36; }
    return r;
  }
  const dataCodewords = (ver) => Math.floor(rawModules(ver) / 8) - ECC_PER_BLOCK[ver - 1] * NUM_BLOCKS[ver - 1];

  function addEcc(data, ver) {
    const nb = NUM_BLOCKS[ver - 1], eccLen = ECC_PER_BLOCK[ver - 1];
    const raw = Math.floor(rawModules(ver) / 8);
    const nShort = nb - (raw % nb), shortLen = Math.floor(raw / nb);
    const div = rsDivisor(eccLen), blocks = [];
    for (let i = 0, k = 0; i < nb; i++) {
      const dat = data.slice(k, k + shortLen - eccLen + (i < nShort ? 0 : 1)); k += dat.length;
      const ecc = rsRemainder(dat, div);
      if (i < nShort) dat.push(0);
      blocks.push(dat.concat(ecc));
    }
    const out = [];
    for (let i = 0; i < blocks[0].length; i++)
      blocks.forEach((b, j) => { if (i !== shortLen - eccLen || j >= nShort) out.push(b[i]); });
    return out;
  }
  function alignPositions(ver) {
    if (ver === 1) return [];
    const n = Math.floor(ver / 7) + 2, size = ver * 4 + 17;
    const step = ver === 32 ? 26 : Math.ceil((ver * 4 + 4) / (n * 2 - 2)) * 2;
    const r = [6];
    for (let pos = size - 7; r.length < n; pos -= step) r.splice(1, 0, pos);
    return r;
  }

  function make(text, opts) {
    const bytes = Array.from(new TextEncoder().encode(text));
    let ver = 1;
    for (;; ver++) {
      if (ver > 10) throw new Error("text is too long for a QR code");
      if (4 + (ver <= 9 ? 8 : 16) + bytes.length * 8 <= dataCodewords(ver) * 8) break;
    }
    const bits = [];
    const push = (v, n) => { for (let i = n - 1; i >= 0; i--) bits.push((v >>> i) & 1); };
    push(4, 4); push(bytes.length, ver <= 9 ? 8 : 16); bytes.forEach((b) => push(b, 8));
    const cap = dataCodewords(ver) * 8;
    push(0, Math.min(4, cap - bits.length));
    while (bits.length % 8) bits.push(0);
    for (let pad = 0xEC; bits.length < cap; pad ^= 0xEC ^ 0x11) push(pad, 8);
    const data = [];
    for (let i = 0; i < bits.length; i += 8) { let v = 0; for (let j = 0; j < 8; j++) v = (v << 1) | bits[i + j]; data.push(v); }
    const all = addEcc(data, ver);

    const size = ver * 4 + 17;
    const mod = Array.from({ length: size }, () => new Array(size).fill(false));
    const fn = Array.from({ length: size }, () => new Array(size).fill(false));
    const setF = (x, y, dark) => { mod[y][x] = dark; fn[y][x] = true; };

    for (let i = 0; i < size; i++) { setF(6, i, i % 2 === 0); setF(i, 6, i % 2 === 0); }
    const finder = (cx, cy) => {
      for (let dy = -4; dy <= 4; dy++) for (let dx = -4; dx <= 4; dx++) {
        const d = Math.max(Math.abs(dx), Math.abs(dy)), x = cx + dx, y = cy + dy;
        if (x >= 0 && x < size && y >= 0 && y < size) setF(x, y, d !== 2 && d !== 4);
      }
    };
    finder(3, 3); finder(size - 4, 3); finder(3, size - 4);
    const pos = alignPositions(ver), n = pos.length;
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      if ((i === 0 && j === 0) || (i === 0 && j === n - 1) || (i === n - 1 && j === 0)) continue;
      for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++)
        setF(pos[i] + dx, pos[j] + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
    }
    const drawFormat = (mask) => {   // error correction level M has format bits 00
      const d = mask; let rem = d;
      for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
      const b = ((d << 10) | rem) ^ 0x5412, bit = (i) => ((b >>> i) & 1) !== 0;
      for (let i = 0; i <= 5; i++) setF(8, i, bit(i));
      setF(8, 7, bit(6)); setF(8, 8, bit(7)); setF(7, 8, bit(8));
      for (let i = 9; i < 15; i++) setF(14 - i, 8, bit(i));
      for (let i = 0; i < 8; i++) setF(size - 1 - i, 8, bit(i));
      for (let i = 8; i < 15; i++) setF(8, size - 15 + i, bit(i));
      setF(8, size - 8, true);
    };
    const drawVersion = () => {
      if (ver < 7) return;
      let rem = ver;
      for (let i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1F25);
      const b = (ver << 12) | rem;
      for (let i = 0; i < 18; i++) {
        const dark = ((b >>> i) & 1) !== 0, a = size - 11 + (i % 3), c = Math.floor(i / 3);
        setF(a, c, dark); setF(c, a, dark);
      }
    };
    drawFormat(0); drawVersion();

    let i = 0;
    for (let right = size - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5;
      for (let vert = 0; vert < size; vert++) for (let j = 0; j < 2; j++) {
        const x = right - j, up = ((right + 1) & 2) === 0, y = up ? size - 1 - vert : vert;
        if (!fn[y][x] && i < all.length * 8) { mod[y][x] = ((all[i >>> 3] >>> (7 - (i & 7))) & 1) !== 0; i++; }
      }
    }

    const applyMask = (m) => {
      for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
        let inv;
        switch (m) {
          case 0: inv = (x + y) % 2 === 0; break;
          case 1: inv = y % 2 === 0; break;
          case 2: inv = x % 3 === 0; break;
          case 3: inv = (x + y) % 3 === 0; break;
          case 4: inv = (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0; break;
          case 5: inv = ((x * y) % 2) + ((x * y) % 3) === 0; break;
          case 6: inv = (((x * y) % 2) + ((x * y) % 3)) % 2 === 0; break;
          default: inv = (((x + y) % 2) + ((x * y) % 3)) % 2 === 0;
        }
        if (!fn[y][x] && inv) mod[y][x] = !mod[y][x];
      }
    };
    const runs = (get) => {
      let r = 0, run = 1;
      for (let k = 1; k < size; k++) { if (get(k) === get(k - 1)) run++; else { if (run >= 5) r += run - 2; run = 1; } }
      if (run >= 5) r += run - 2;
      return r;
    };
    const FIND = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0], FIND_R = FIND.slice().reverse();
    const finds = (get) => {
      let r = 0;
      for (let k = 0; k + 11 <= size; k++) {
        const w = []; for (let t = 0; t < 11; t++) w.push(get(k + t) ? 1 : 0);
        if (w.every((v, t) => v === FIND[t])) r += 40;
        if (w.every((v, t) => v === FIND_R[t])) r += 40;
      }
      return r;
    };
    const penalty = () => {
      let r = 0, dark = 0;
      for (let y = 0; y < size; y++) {
        r += runs((k) => mod[y][k]) + runs((k) => mod[k][y]) + finds((k) => mod[y][k]) + finds((k) => mod[k][y]);
        for (let x = 0; x < size; x++) {
          if (mod[y][x]) dark++;
          if (x + 1 < size && y + 1 < size && mod[y][x] === mod[y][x + 1] && mod[y][x] === mod[y + 1][x] && mod[y][x] === mod[y + 1][x + 1]) r += 3;
        }
      }
      const total = size * size;
      return r + (Math.ceil(Math.abs(dark * 20 - total * 10) / total) - 1) * 10;
    };
    let best = 0, bestP = Infinity;
    for (let m = 0; m < 8; m++) {
      if (opts && opts.mask !== undefined && m !== opts.mask) continue;   // (testing aid)
      applyMask(m); drawFormat(m);
      const p = penalty();
      if (p < bestP) { best = m; bestP = p; }
      applyMask(m);
    }
    applyMask(best); drawFormat(best);
    return { size, modules: mod, version: ver };
  }

  // draw onto a <canvas>: dark modules on a white background with a 4-module quiet zone (scans on dark pages too)
  function draw(canvas, text, px) {
    const q = make(text), scale = px || 6, quiet = 4, dim = (q.size + quiet * 2) * scale;
    canvas.width = canvas.height = dim;
    const c = canvas.getContext("2d");
    c.fillStyle = "#fff"; c.fillRect(0, 0, dim, dim);
    c.fillStyle = "#000";
    for (let y = 0; y < q.size; y++) for (let x = 0; x < q.size; x++)
      if (q.modules[y][x]) c.fillRect((x + quiet) * scale, (y + quiet) * scale, scale, scale);
  }

  const api = { make, draw };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.GS_QR = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
