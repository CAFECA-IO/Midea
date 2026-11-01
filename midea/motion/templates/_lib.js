// Shared helpers for Midea motion templates (deterministic: everything is a function of t).
const P = __PARAMS__;
const C = __PALETTE__;
const W = __W__, H = __H__;
const FONT = "__FONT__";
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, k) => a + (b - a) * k;
const prog = (t, start, dur) => clamp((t - start) / dur);
const ease = {
  linear: k => k,
  outCubic: k => 1 - Math.pow(1 - k, 3),
  inOutCubic: k => (k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2),
  outBack: k => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); },
  outElastic: k => k === 0 ? 0 : k === 1 ? 1 : Math.pow(2, -10 * k) * Math.sin((k * 10 - .75) * (2 * Math.PI) / 3) + 1,
  inOutSine: k => -(Math.cos(Math.PI * k) - 1) / 2,
};
// exit animation helper: 1 → 0 over the last `d` seconds
const outro = (t, total, d = .5) => 1 - ease.inOutCubic(prog(t, total - d, d));
const SVGNS = "http://www.w3.org/2000/svg";
function el(tag, attrs = {}, parent) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
function stage() {
  document.body.style.cssText = `margin:0;width:${W}px;height:${H}px;overflow:hidden;background:${C.bg};font-family:'${FONT}',sans-serif;`;
  const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` });
  document.body.appendChild(svg);
  const defs = el("defs", {}, svg);
  const g = el("radialGradient", { id: "bgGrad", cx: "50%", cy: "40%", r: "75%" }, defs);
  el("stop", { offset: "0%", "stop-color": C.bg2 }, g);
  el("stop", { offset: "100%", "stop-color": C.bg }, g);
  const f = el("filter", { id: "glow", x: "-50%", y: "-50%", width: "200%", height: "200%" }, defs);
  el("feGaussianBlur", { stdDeviation: 6, result: "b" }, f);
  const m = el("feMerge", {}, f); el("feMergeNode", { in: "b" }, m); el("feMergeNode", { in: "SourceGraphic" }, m);
  el("rect", { width: W, height: H, fill: "url(#bgGrad)" }, svg);
  // ambient particle field (style: faint lavender/amber dust) — keeps "holds" alive without distracting
  if (!P.no_ambient) {
    const g = el("g", { opacity: .55 }, svg), dots = [];
    for (let i = 0; i < 42; i++) dots.push({ e: el("circle", { r: (1.2 + (i * 7) % 3) * Math.min(W, H) / 1080, fill: i % 5 ? C.accent2 : C.accent, opacity: .35 }, g),
      x: (i * 997) % W, y: (i * 613) % H, vx: ((i * 37) % 11 - 5) * 2, vy: -6 - (i * 13) % 14 });
    window.__bg = t => dots.forEach(d => { d.e.setAttribute("cx", ((d.x + d.vx * t) % W + W) % W); d.e.setAttribute("cy", ((d.y + d.vy * t * 3) % H + H) % H); });
  }
  return svg;
}
const U = Math.min(W, H) / 1080;   // unit scale so templates work at 16:9, 9:16 and 1:1
function text(parent, s, x, y, size, attrs = {}) {
  const t = el("text", { x, y, "font-size": size * U, fill: C.fg, "text-anchor": "middle", "dominant-baseline": "middle",
                        "font-weight": 700, ...attrs }, parent);
  t.textContent = s; return t;
}
function ready() { window.__ready = true; }
