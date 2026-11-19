// Helpers shared by every page.
const STATUS = { edible: "Edible", inedible: "Inedible", caution: "Caution", poisonous: "Poisonous", deadly: "Deadly" };
const VERDICT = { genus: "Same genus", family: "Same family", order: "Same order", class: "Different orders", phylum: "Different classes" };

const $ = (id) => document.getElementById(id);
const pct = (d) => `${Math.round(d * 100)}%`;
const verdict = (c) => VERDICT[c.shared_rank] || "Different phyla";
// Common names get capitals; a Latin name used as a fallback is left as it is.
const common = (s) => (s.common_name ? s.common_name.replace(/(^|\s)\w/g, (ch) => ch.toUpperCase()) : s.name);
// Text from outside databases is escaped before it goes into the page.
const esc = (t) => String(t).replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`);

// Theme: follows the device until the visitor picks one, and the choice is remembered in this browser.
const root = document.documentElement;
const isDark = () => (root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches);
function themeButton() {
  $("theme").dataset.dark = isDark();
  $("theme").setAttribute("aria-label", isDark() ? "Switch to light mode" : "Switch to dark mode");
}
themeButton();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { themeButton(); dispatchEvent(new Event("themechange")); });
$("theme").addEventListener("click", () => {
  root.classList.add("switching");
  root.dataset.theme = isDark() ? "light" : "dark";
  try { localStorage.setItem("theme", root.dataset.theme); } catch (e) { /* private window: the choice lasts until the page closes */ }
  themeButton();
  getComputedStyle(root).color; // apply the new colours now, before transitions are allowed again
  requestAnimationFrame(() => root.classList.remove("switching"));
  dispatchEvent(new Event("themechange"));
});

// Sideways scrollers stretch a little past either end, with growing resistance, then spring back.
document.addEventListener("wheel", (e) => {
  const box = e.target.closest(".scroll"), inner = box && box.firstElementChild;
  const dx = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : 0;
  if (!inner || !dx || box.scrollWidth <= box.clientWidth || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const atStart = box.scrollLeft <= 0, atEnd = box.scrollLeft + box.clientWidth >= box.scrollWidth - 1;
  if ((dx < 0 && !atStart) || (dx > 0 && !atEnd)) return;
  box.pull = (box.pull || 0) - dx;
  const MAX = 60; // the stretch can never pass this many pixels
  const offset = Math.sign(box.pull) * MAX * (1 - 1 / (Math.abs(box.pull) * 0.55 / MAX + 1));
  inner.style.transition = "none";
  inner.style.transform = `translateX(${offset}px)`;
  clearTimeout(box.release);
  box.release = setTimeout(() => {
    inner.style.transition = "transform .5s cubic-bezier(.3, 1.4, .5, 1)"; // a slight overshoot reads as a spring
    inner.style.transform = "";
    box.pull = 0;
  }, 120);
}, { passive: true });

const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

// Remember where a link was clicked, so the next page's ink blot spreads from there (see base.html).
addEventListener("click", (e) => {
  const a = e.target.closest("a[href]");
  if (!a || a.origin !== location.origin || !e.clientX) return;
  try { sessionStorage.setItem("ink", JSON.stringify([e.clientX, e.clientY])); } catch (err) { /* the blot starts in the middle */ }
}, true);

// A puff of spores from a point: dots that burst out, drift down and vanish.
function spores(x, y, n = 14) {
  if (calm()) return;
  for (let i = 0; i < n; i++) {
    const s = document.createElement("i");
    s.className = "spore";
    s.style.left = `${x}px`;
    s.style.top = `${y}px`;
    document.body.append(s);
    const a = Math.random() * Math.PI * 2, d = 18 + Math.random() * (n > 20 ? 110 : 46);
    s.animate([
      { transform: "translate(-50%, -50%) scale(1)", opacity: 1 },
      { transform: `translate(calc(-50% + ${Math.cos(a) * d}px), calc(-50% + ${Math.sin(a) * d + 34}px)) scale(.97)`, opacity: 0 },
    ], { duration: 700 + Math.random() * 600, easing: "cubic-bezier(.15, .7, .4, 1)" }).finished.then(() => s.remove());
  }
}
addEventListener("click", (e) => {
  const b = e.target.closest(".button, .theme, .picker button");
  if (!b) return;
  const r = b.getBoundingClientRect();
  spores(e.clientX || r.left + r.width / 2, e.clientY || r.top + r.height / 2); // keyboard clicks have no pointer position
});

// Page headings are split into words so they can arrive one after another.
document.querySelectorAll("main h1:not([id])").forEach((h) => {
  h.innerHTML = h.textContent.trim().split(/\s+/).map((w, i) => `<span class="word" style="--i:${i}">${esc(w)}</span>`).join(" ");
});

// Dopple says something in his speech bubble. Pages call this to make him react; it does nothing while he is hidden.
let say = () => {};

// Dopple, the walking mushroom. He crosses the screen as you scroll, but never faster than half a pixel
// per pixel scrolled, so on a short page he strolls part of the way instead of sprinting across.
{
  const w = $("walker"), MAX_SPEED = 0.5;
  let last = scrollY, still, clicks = 0, hush;
  const place = () => {
    const room = innerWidth - 56, scrollable = document.documentElement.scrollHeight - innerHeight;
    const x = scrollable > 0 ? (scrollY / scrollable) * Math.min(room, scrollable * MAX_SPEED) : 0;
    w.style.translate = `${12 + x}px 0`;
    w.classList.toggle("right", x > innerWidth / 2);
  };
  place();
  addEventListener("resize", place);
  addEventListener("scroll", () => {
    if (calm()) return;
    place();
    w.classList.add("walking");
    w.classList.toggle("back", scrollY < last);
    last = scrollY;
    clearTimeout(still);
    still = setTimeout(() => w.classList.remove("walking"), 160);
  }, { passive: true });

  const QUIPS = [
    "hi! i'm dopple :)",
    "i walk when you scroll. it's my whole job",
    "don't eat me. i'm a looker, not a snack",
    "most of me is underground tbh",
    "fungi are closer cousins to you than plants are!",
    "a honey fungus in oregon is bigger than a town. goals",
    "spore-ry, were you reading?",
    "lookalikes?? don't get me started",
  ];
  say = (text) => {
    if (root.dataset.walker === "off") return;
    $("quip").textContent = text;
    $("bubble").hidden = false;
    $("bubble").style.animation = "none"; $("bubble").offsetHeight; $("bubble").style.animation = ""; // replay the pop-in
    clearTimeout(hush);
    hush = setTimeout(() => { $("bubble").hidden = true; }, 3800);
  };
  // A hello for each page, once per visit, a moment after it opens.
  const GREET = {
    "/": "hi! scroll and i'll walk with you", "/lens": "ooh, show me a mushroom", "/compare": "pick two. i love a rivalry",
    "/quiz": "quiz time! no pressure", "/glossary": "big words. i know some", "/method": "dna stuff. i'm made of that",
    "/sources": "all the receipts are here", "/privacy": "no cookies here. only spores", "/about": "that's my human!", "/analysis": "numbers! i love numbers",
  };
  const hello = document.querySelector("[data-greet]")?.dataset.greet || GREET[location.pathname];
  let greeted = false;
  try { greeted = sessionStorage.getItem(`greeted:${location.pathname}`); sessionStorage.setItem(`greeted:${location.pathname}`, "1"); } catch (e) { /* greet anyway */ }
  if (hello && !greeted) setTimeout(() => say(hello), 1200);

  $("dopple").addEventListener("click", () => {
    clicks += 1;
    say(clicks > 8 ? "hehe stop, i'm ticklish" : QUIPS[(clicks - 1) % QUIPS.length]);
    const r = $("dopple").getBoundingClientRect();
    spores(r.left + r.width / 2, r.top + 6, 12);
    if (!calm()) $("dopple").animate([{ translate: "0 0", rotate: "0deg" }, { translate: "0 -22px", rotate: "-10deg" }, { translate: "0 0", rotate: "0deg" }],
      { duration: 520, easing: "cubic-bezier(.3, .7, .3, 1)" });
  });

  // He can be switched off from his speech bubble or the footer; the choice is remembered.
  const setWalker = (on) => {
    if (on) delete root.dataset.walker; else root.dataset.walker = "off";
    try { localStorage.setItem("walker", on ? "on" : "off"); } catch (e) { /* lasts until the page closes */ }
    $("walker-toggle").textContent = on ? "Hide the walking mushroom" : "Bring back the walking mushroom";
    $("bubble").hidden = true;
  };
  $("walker-toggle").textContent = root.dataset.walker === "off" ? "Bring back the walking mushroom" : "Hide the walking mushroom";
  $("walker-hide").addEventListener("click", () => setWalker(false));
  $("walker-toggle").addEventListener("click", () => setWalker(root.dataset.walker === "off"));
}

// Status is drawn as shape + colour, so it never depends on colour alone.
function shape(status, x, y, r) {
  const cls = `class="mark ${status}"`;
  if (status === "edible") return `<rect ${cls} x="${x - r}" y="${y - r}" width="${2 * r}" height="${2 * r}"/>`;
  if (status === "poisonous" || status === "deadly") return `<polygon ${cls} points="${x},${y - r - 1} ${x + r + 1},${y + r} ${x - r - 1},${y + r}"/>`;
  if (status === "inedible" || status === "caution") return `<polygon ${cls} points="${x},${y - r - 1} ${x + r + 1},${y} ${x},${y + r + 1} ${x - r - 1},${y}"/>`;
  return `<circle class="mark none" cx="${x}" cy="${y}" r="${r}"/>`; // no label in the curated list
}
const icon = (status) => `<svg width="12" height="12" viewBox="-7 -7 14 14" aria-hidden="true">${shape(status, 0, 0, 5)}</svg>`;
const fromWiki = (s) => (s.label && s.label.from === "wikipedia" ? " (Wikipedia)" : "");
const statusTag = (s) => `<span class="status">${icon(s.status)}${STATUS[s.status] || "No label"}${fromWiki(s)}</span>`;

// Two maps side by side that move together. Returns show([a, b]), which puts one species on each.
function twinMaps() {
  const base = () => `https://tile.gbif.org/3857/omt/{z}/{x}/{y}@2x.png?style=gbif-${isDark() ? "dark" : "light"}`;
  const RECORDS = "https://api.gbif.org/v2/map/occurrence/density/{z}/{x}/{y}@2x.png?srs=EPSG:3857&bin=hex&hexPerTile=30&style=purpleYellow.poly&taxonKey=";
  const credit = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, © <a href="https://openmaptiles.org/">OpenMapTiles</a>, <a href="https://www.gbif.org/">GBIF</a>';
  const country = new Intl.DisplayNames(["en"], { type: "region" });

  const maps = ["map-a", "map-b"].map((id) => {
    const map = L.map(id, { minZoom: 1, maxZoom: 8, worldCopyJump: true }).setView([35, 10], 1);
    const tiles = L.tileLayer(base(), { attribution: credit }).addTo(map);
    addEventListener("themechange", () => tiles.setUrl(base()));
    return map;
  });
  // Moving one map moves the other. The flag stops them from updating each other forever.
  let syncing = false;
  maps.forEach((map, i) => map.on("move zoomend", () => {
    if (syncing) return;
    syncing = true;
    maps[1 - i].setView(map.getCenter(), map.getZoom(), { animate: false });
    syncing = false;
  }));

  const layers = [];
  return function show(pair) {
    document.querySelector(".maps").classList.toggle("single", pair.length < 2);
    pair.forEach((s, i) => {
      if (layers[i]) layers[i].remove();
      layers[i] = s.gbif && L.tileLayer(RECORDS + s.gbif.gbif_key, { opacity: 0.85 }).addTo(maps[i]);
      const records = s.gbif ? `${s.gbif.records.toLocaleString("en")} records` : "not found in GBIF";
      $(`cap-${"ab"[i]}`).innerHTML = `<b>${esc(common(s))}</b><i>${esc(s.name)}</i><small>${statusTag(s)} · ${records}</small>`;
    });
    if (pair.length < 2) { $("overlap-title").textContent = ""; $("overlap").innerHTML = ""; return; }

    // Sort every country by its combined record count, then split into three groups.
    const [x, y] = pair.map((s) => (s.gbif ? s.gbif.countries : {}));
    const codes = [...new Set([...Object.keys(x), ...Object.keys(y)])]
      .sort((p, q) => (x[q] || 0) + (y[q] || 0) - (x[p] || 0) - (y[p] || 0));
    const groups = [
      ["Both", codes.filter((k) => k in x && k in y)],
      [`Only ${common(pair[0])}`, codes.filter((k) => !(k in y))],
      [`Only ${common(pair[1])}`, codes.filter((k) => !(k in x))],
    ];
    $("overlap-title").textContent = `Both are recorded in ${groups[0][1].length} countries`;
    $("overlap").innerHTML = groups.map(([label, list]) =>
      `<div><h3>${esc(label)} · ${list.length}</h3><p>${list.map((k) => country.of(k)).join(", ") || "None"}</p></div>`).join("");
  };
}
