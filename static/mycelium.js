// Page transition: mycelium. Loaded in <head> so an arriving page is covered before it is ever drawn.
// Click a link: glowing fungal threads race across the page from the cursor while a light veil in the page's own
// colour gathers behind them. The next page appears under the very same web (rebuilt from a stored random seed, not
// passed as a picture) and the web dissolves from the middle outwards.
// Kept cheap: each thread is drawn once, onto a canvas that is never cleared, and the dissolve only erases a growing
// circle per frame. Plain navigation for modified clicks, other sites, downloads and reduced motion.
(() => {
  const GROW_MS = 300, CLEAR_MS = 380, VEIL = 0.72;
  const root = document.documentElement;
  const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

  // A small seeded random generator, so both pages grow exactly the same web from the same seed.
  const random = (seed) => () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const reachFrom = (x, y, w, h) => Math.hypot(Math.max(x, w - x), Math.max(y, h - y)) * 1.08;

  // Threads: random walks that wander and branch, as segments sorted by distance from the start.
  // At most 90 tips grow at once, so the web is dense yet still reaches every edge.
  function hyphae(x, y, reach, rnd) {
    const segs = [], tips = [];
    for (let i = 0; i < 20; i++) tips.push({ x, y, a: (i / 20) * Math.PI * 2 + rnd() * 0.3, d: 0, w: 2.4 });
    while (tips.length && segs.length < 4200) {
      const t = tips.shift(), step = 20 + rnd() * 14, a = t.a + (rnd() - 0.5) * 0.75;
      const nx = t.x + Math.cos(a) * step, ny = t.y + Math.sin(a) * step, d = t.d + step;
      segs.push({ x1: t.x, y1: t.y, x2: nx, y2: ny, d, w: t.w });
      if (d > reach) continue;
      tips.push({ x: nx, y: ny, a, d, w: Math.max(0.7, t.w * 0.95) });
      if (tips.length < 90 && rnd() < 0.24) tips.push({ x: nx, y: ny, a: a + (rnd() < 0.5 ? -1 : 1) * (0.5 + rnd() * 0.6), d, w: t.w * 0.7 });
    }
    return segs.sort((p, q) => p.d - q.d);
  }
  // Segments [from, to) in three batched paths: a wide faint glow, then the thread in two thicknesses.
  function stroke(g, segs, from, to, colour) {
    g.strokeStyle = colour; g.lineCap = "round";
    const pass = (width, alpha, keep) => {
      g.globalAlpha = alpha; g.lineWidth = width; g.beginPath();
      for (let i = from; i < to; i++) { const s = segs[i]; if (keep(s)) { g.moveTo(s.x1, s.y1); g.lineTo(s.x2, s.y2); } }
      g.stroke();
    };
    pass(6, 0.12, () => true);
    pass(2.2, 1, (s) => s.w >= 1.5);
    pass(1, 0.9, (s) => s.w < 1.5);
    g.globalAlpha = 1;
  }
  function colours() {  // the colour variables hold light-dark() pairs, which a canvas cannot read; a probe resolves them
    const probe = document.createElement("i");
    root.append(probe);
    const read = (v) => { probe.style.color = `var(${v})`; return getComputedStyle(probe).color; };
    const out = { paper: read("--paper"), thread: read("--accent") };
    probe.remove();
    return out;
  }
  function canvas(w, h) {
    const c = document.createElement("canvas");
    c.className = "mycelium";
    c.width = w; c.height = h;  // normal resolution; the glow hides the softness
    root.append(c);  // on <html>, so it works before <body> exists
    return [c, c.getContext("2d")];
  }

  // Leaving: grow the web from the click, with the veil gathering underneath, then go.
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[href]");
    if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || calm()) return;
    if (a.origin !== location.origin || a.target || a.hasAttribute("download") || a.pathname.startsWith("/static/")) return;
    if (a.pathname === location.pathname && a.search === location.search) return;  // same page (or an #anchor on it)
    e.preventDefault();
    const W = innerWidth, H = innerHeight, x = e.clientX || W / 2, y = e.clientY || H / 2, seed = (Math.random() * 2 ** 31) | 0;
    const reach = reachFrom(x, y, W, H), segs = hyphae(x, y, reach, random(seed)), { paper, thread } = colours();
    const veil = document.createElement("div");
    veil.className = "veil"; veil.style.background = paper;
    root.append(veil);
    veil.animate([{ opacity: 0 }, { opacity: VEIL }], { duration: GROW_MS, easing: "ease-in", fill: "forwards" });
    const [, g] = canvas(W, H);
    try { sessionStorage.setItem("web", JSON.stringify({ seed, x, y, W, H })); } catch (err) { /* the next page just appears */ }
    let drawn = 0;
    const begin = performance.now();
    const frame = (now) => {
      const t = Math.min(1, (now - begin) / GROW_MS), front = (t < 1 ? 1 - Math.pow(1 - t, 1.6) : 1) * reach;
      let next = drawn;
      while (next < segs.length && segs[next].d <= front) next++;
      if (next > drawn) { stroke(g, segs, drawn, next, thread); drawn = next; }  // only the new tips
      if (t < 1) requestAnimationFrame(frame); else location.href = a.href;
    };
    requestAnimationFrame(frame);
  });

  // Arriving: put up the same veil and web before the page is first drawn, then dissolve them from the middle.
  let web = null;
  try { web = JSON.parse(sessionStorage.getItem("web")); sessionStorage.removeItem("web"); } catch (err) { /* no transition */ }
  if (web && !calm() && web.W === innerWidth && web.H === innerHeight) {
    const { paper, thread } = colours(), reach = reachFrom(web.x, web.y, web.W, web.H);
    const [c, g] = canvas(web.W, web.H);
    g.globalAlpha = VEIL; g.fillStyle = paper; g.fillRect(0, 0, web.W, web.H); g.globalAlpha = 1;
    const segs = hyphae(web.x, web.y, reach, random(web.seed));
    stroke(g, segs, 0, segs.length, thread);
    const cx = web.W / 2, cy = web.H / 2, far = Math.hypot(cx, cy) + 160;
    const begin = performance.now() + 30;  // let the page draw its first frame under the web
    const clear = (now) => {
      const t = Math.max(0, Math.min(1, (now - begin) / CLEAR_MS)), r = (1 - Math.pow(1 - t, 2.2)) * far;
      if (r > 0) {  // erase a growing circle with a soft rim, so the web frays away rather than being cut
        const hole = g.createRadialGradient(cx, cy, Math.max(0, r - 140), cx, cy, r);
        hole.addColorStop(0, "rgba(0,0,0,1)"); hole.addColorStop(1, "rgba(0,0,0,0)");
        g.globalCompositeOperation = "destination-out"; g.fillStyle = hole;
        g.fillRect(cx - r, cy - r, 2 * r, 2 * r);
        g.globalCompositeOperation = "source-over";
      }
      if (t < 1) requestAnimationFrame(clear); else c.remove();
    };
    requestAnimationFrame(clear);
  }

  // Fetch a page as soon as the pointer is on its link, so the wait after the growth stays short on a real network.
  const fetched = new Set();
  const prefetch = (e) => {
    const a = e.target.closest?.("a[href]");
    if (!a || a.origin !== location.origin || a.pathname.startsWith("/static/") || fetched.has(a.href)) return;
    fetched.add(a.href);
    const link = document.createElement("link");
    link.rel = "prefetch"; link.href = a.href;
    document.head.append(link);
  };
  document.addEventListener("pointerover", prefetch, { passive: true });
  document.addEventListener("focusin", prefetch);
  // Coming back with the browser's back button can restore a page that was mid-transition; clear it.
  addEventListener("pageshow", (e) => { if (e.persisted) document.querySelectorAll(".mycelium, .veil").forEach((el) => el.remove()); });
})();
