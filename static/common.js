// Helpers shared by every page.
const STATUS = { edible: "Edible", poisonous: "Poisonous", inedible: "Inedible" };
const VERDICT = { genus: "Same genus", family: "Same family", order: "Same order", class: "Different orders", phylum: "Different classes" };

const $ = (id) => document.getElementById(id);
const pct = (d) => `${Math.round(d * 100)}%`;
const verdict = (c) => VERDICT[c.shared_rank] || "Different phyla";
// Common names get capitals; a Latin name used as a fallback is left as it is.
const common = (s) => (s.common_name ? s.common_name.replace(/(^|\s)\w/g, (ch) => ch.toUpperCase()) : s.name);
// Text from outside databases is escaped before it goes into the page.
const esc = (t) => String(t).replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`);

// Status is drawn as shape + colour, so it never depends on colour alone.
function shape(status, x, y, r) {
  const cls = `class="mark ${status}"`;
  if (status === "edible") return `<rect ${cls} x="${x - r}" y="${y - r}" width="${2 * r}" height="${2 * r}"/>`;
  if (status === "poisonous") return `<polygon ${cls} points="${x},${y - r - 1} ${x + r + 1},${y + r} ${x - r - 1},${y + r}"/>`;
  if (status === "inedible") return `<polygon ${cls} points="${x},${y - r - 1} ${x + r + 1},${y} ${x},${y + r + 1} ${x - r - 1},${y}"/>`;
  return `<circle class="mark none" cx="${x}" cy="${y}" r="${r}"/>`; // no label in the curated list
}
const icon = (status) => `<svg width="12" height="12" viewBox="-7 -7 14 14" aria-hidden="true">${shape(status, 0, 0, 5)}</svg>`;
const statusTag = (s) => `<span class="status">${icon(s.status)}${STATUS[s.status] || "No label"}</span>`;

// Two maps side by side that move together. Returns show([a, b]), which puts one species on each.
function twinMaps() {
  const BASE = "https://tile.gbif.org/3857/omt/{z}/{x}/{y}@2x.png?style=gbif-light";
  const RECORDS = "https://api.gbif.org/v2/map/occurrence/density/{z}/{x}/{y}@2x.png?srs=EPSG:3857&bin=hex&hexPerTile=30&style=purpleYellow.poly&taxonKey=";
  const credit = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, © <a href="https://openmaptiles.org/">OpenMapTiles</a>, <a href="https://www.gbif.org/">GBIF</a>';
  const country = new Intl.DisplayNames(["en"], { type: "region" });

  const maps = ["map-a", "map-b"].map((id) => {
    const map = L.map(id, { minZoom: 1, maxZoom: 8, worldCopyJump: true }).setView([35, 10], 1);
    L.tileLayer(BASE, { attribution: credit }).addTo(map);
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
