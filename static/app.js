const STATUS = { edible: "Edible", poisonous: "Poisonous", inedible: "Inedible" };
const VERDICT = { family: "Same family", order: "Same order", class: "Different orders", phylum: "Different classes" };
const RANKS = ["phylum", "class", "order", "family", "genus"];

let species, byId, comparisons, cmp, alignments, nodes, leaves;
let pinned = null;
const edgeSets = new Map(); // tree edge element -> set of species below that edge

const $ = (id) => document.getElementById(id);
const key = (a, b) => [a, b].sort().join("|");
const pct = (d) => `${Math.round(d * 100)}%`;
const verdict = (c) => VERDICT[c.shared_rank] || "Different phyla";
const partner = (id) => species.find((s) => s.pair === byId[id].pair && s.id !== id).id;
const common = (s) => (s.common_name || s.name).replace(/(^|\s)\w/g, (ch) => ch.toUpperCase());
const lookalikes = () => comparisons.filter((c) => c.pair).sort((p, q) => p.distance - q.distance);

// Status is drawn as shape + colour, so it never depends on colour alone.
function shape(status, x, y, r) {
  const cls = `class="mark ${status}"`;
  if (status === "edible") return `<rect ${cls} x="${x - r}" y="${y - r}" width="${2 * r}" height="${2 * r}"/>`;
  if (status === "poisonous") return `<polygon ${cls} points="${x},${y - r - 1} ${x + r + 1},${y + r} ${x - r - 1},${y + r}"/>`;
  return `<polygon ${cls} points="${x},${y - r - 1} ${x + r + 1},${y} ${x},${y + r + 1} ${x - r - 1},${y}"/>`;
}
const icon = (status) => `<svg width="12" height="12" viewBox="-7 -7 14 14" aria-hidden="true">${shape(status, 0, 0, 5)}</svg>`;
const statusTag = (s) => `<span class="status">${icon(s.status)}${STATUS[s.status]}</span>`;

function describe(c) {
  const taxon = c.shared_taxon ? ` (${c.shared_taxon})` : "";
  const pair = c.pair ? ` · lookalike pair ${c.pair}` : "";
  return `${common(byId[c.a])} and ${common(byId[c.b])} · ${pct(c.distance)} of DNA positions differ · ${verdict(c)}${taxon}${pair}`;
}

// One function updates every graphic on the page.
function highlight(a, b) {
  const k = a && b ? key(a, b) : null;
  document.body.classList.toggle("has-active", !!k);
  const group = document.querySelector("#tree .edges");
  for (const [el, below] of edgeSets) {
    // An edge lies on the path between a and b when exactly one of them is below it.
    const on = !!k && below.has(a) !== below.has(b);
    el.classList.toggle("on", on);
    if (on) group.appendChild(el); // draw highlighted edges on top
  }
  document.querySelectorAll("[data-sp]").forEach((el) => el.classList.toggle("on", !!k && (el.dataset.sp === a || el.dataset.sp === b)));
  document.querySelectorAll("[data-pairkey]").forEach((el) => el.classList.toggle("on", el.dataset.pairkey === k));
  document.querySelectorAll("[data-readout]").forEach((el) => {
    el.textContent = k ? describe(cmp.get(k)) : "Nothing selected yet.";
    el.classList.toggle("idle", !k);
    if (k && "link" in el.dataset) el.insertAdjacentHTML("beforeend", ` · <a href="/tree#${k}">Show in tree</a>`);
  });
}

function bind(el, a, b) {
  const restore = () => highlight(...(pinned || []));
  const pin = () => {
    pinned = pinned && key(...pinned) === key(a, b) ? null : [a, b];
    history.replaceState(null, "", pinned ? "#" + key(a, b) : location.pathname); // shareable link
    restore();
  };
  el.addEventListener("mouseenter", () => highlight(a, b));
  el.addEventListener("mouseleave", restore);
  el.addEventListener("focus", () => highlight(a, b));
  el.addEventListener("blur", restore);
  el.addEventListener("click", pin);
  el.addEventListener("keydown", (e) => { if (e.key === "Enter") pin(); });
}

// Walk the tree once: depth = distance from root, row = vertical slot.
function layout(root) {
  nodes = []; leaves = [];
  (function walk(n, parent) {
    n.parent = parent;
    n.depth = (parent ? parent.depth : 0) + n.length;
    n.below = new Set();
    nodes.push(n);
    if (!n.children.length) {
      n.row = leaves.length;
      n.below.add(n.name);
      leaves.push(n);
    } else {
      for (const c of n.children) { walk(c, n); c.below.forEach((x) => n.below.add(x)); }
      n.row = (n.children[0].row + n.children.at(-1).row) / 2;
    }
  })(root, null);
}

function renderTree() {
  const svg = $("tree");
  const ROW = 48, TOP = 28, PAD = 12, LABEL = 252, COL = 24, TEXT = 60;
  const row = Object.fromEntries(leaves.map((l) => [l.name, l.row]));
  const pairs = comparisons.filter((c) => c.pair)
    .sort((p, q) => Math.abs(row[p.a] - row[p.b]) - Math.abs(row[q.a] - row[q.b])); // short brackets innermost
  const W = Math.max(svg.parentElement.clientWidth, 720);
  const H = TOP + leaves.length * ROW + 40;
  const plotW = W - PAD - 16 - LABEL - pairs.length * COL - 4;
  const maxDepth = Math.max(...leaves.map((l) => l.depth));
  const X = (d) => PAD + (d / maxDepth) * plotW;
  const Y = (r) => TOP + r * ROW + ROW / 2;
  const labelX = PAD + plotW + 16;

  let edges = `<path class="edge" d="M${X(0) - 8},${Y(nodes[0].row)}H${X(0)}"/>`;
  nodes.forEach((n, i) => {
    if (n.parent) edges += `<path class="edge" data-i="${i}" d="M${X(n.parent.depth)},${Y(n.parent.row)}V${Y(n.row)}H${X(n.depth)}"/>`;
  });

  const tips = leaves.map((n) => {
    const y = Y(n.row), s = byId[n.name];
    const photo = s.photo ? `<image href="${s.photo.square}" x="${labelX}" y="${y - 17}" width="34" height="34" preserveAspectRatio="xMidYMid slice"/>` : "";
    return `<g class="leaf" data-sp="${n.name}" tabindex="0">
      <line class="leader" x1="${X(n.depth) + 6}" x2="${labelX - 6}" y1="${y}" y2="${y}"/>
      ${photo}${shape(s.status, labelX + 46, y, 5)}
      <text class="cn" x="${labelX + TEXT}" y="${y - 8}" dominant-baseline="central">${common(s)}</text>
      <text class="latin" x="${labelX + TEXT}" y="${y + 10}" dominant-baseline="central">${s.name}</text>
      <rect x="${labelX - 4}" y="${y - ROW / 2}" width="${LABEL}" height="${ROW}" fill="transparent"/>
    </g>`;
  }).join("");

  const brackets = pairs.map((c, i) => {
    const x = labelX + LABEL + i * COL + COL / 2;
    const [y1, y2] = [Y(row[c.a]), Y(row[c.b])].sort((p, q) => p - q);
    const d = `M${x - 6},${y1}H${x}V${y2}H${x - 6}`;
    const mid = (y1 + y2) / 2;
    return `<g class="bracket" data-pairkey="${key(c.a, c.b)}" data-x="${x - 6}" tabindex="0">
      <path d="${d}"/><path d="${d}" style="stroke:transparent;stroke-width:16"/>
      <rect x="${x - 9}" y="${mid - 9}" width="18" height="18"/>
      <text x="${x}" y="${mid}" text-anchor="middle" dominant-baseline="central">${c.pair}</text>
    </g>`;
  }).join("");

  const unit = 0.05, sy = H - 14, sx = PAD + (unit / maxDepth) * plotW;
  svg.setAttribute("width", W);
  svg.setAttribute("height", H);
  svg.innerHTML = `<g class="edges">${edges}</g>${tips}${brackets}
    <text class="small" x="${labelX + LABEL + 4}" y="14">Lookalike pairs</text>
    <path class="scale" d="M${PAD},${sy - 5}V${sy}H${sx}V${sy - 5}"/>
    <text class="small" x="${sx + 8}" y="${sy}">${pct(unit)} DNA difference</text>`;

  edgeSets.clear();
  svg.querySelectorAll(".edge[data-i]").forEach((el) => edgeSets.set(el, nodes[el.dataset.i].below));
  svg.querySelectorAll(".leaf").forEach((el) => bind(el, el.dataset.sp, partner(el.dataset.sp)));
  svg.querySelectorAll(".bracket").forEach((el) => {
    const ids = el.dataset.pairkey.split("|");
    bind(el, ...ids);
    for (const id of ids) { // dotted line from the end of each name to its bracket
      const widths = [...svg.querySelectorAll(`.leaf[data-sp="${id}"] text`)].map((t) => t.getComputedTextLength());
      const x1 = labelX + TEXT + 8 + Math.max(...widths);
      el.insertAdjacentHTML("afterbegin", `<line class="leader" x1="${x1}" x2="${el.dataset.x}" y1="${Y(row[id])}" y2="${Y(row[id])}"/>`);
    }
  });
}

function renderPairs() {
  const pairs = lookalikes();
  const max = Math.ceil(Math.max(...comparisons.map((c) => c.distance)) * 10) / 10;
  const block = (s) => `<span class="sp">
    ${s.photo ? `<img src="${s.photo.medium}" alt="${common(s)}" title="${s.photo.attribution}" loading="lazy">` : "<span></span>"}
    <span><b>${common(s)}</b><i>${s.name}</i><small>${statusTag(s)} · ${s.taxonomy.family}</small></span>
  </span>`;
  $("pairs").innerHTML = pairs.map((c) => {
    const [e, o] = byId[c.a].status === "edible" ? [byId[c.a], byId[c.b]] : [byId[c.b], byId[c.a]];
    return `<a class="pair" href="/tree#${key(c.a, c.b)}">
      <span class="no">${c.pair}</span>
      ${block(e)}
      <span class="dist"><span class="track"><i style="width:${(c.distance / max) * 100}%"></i></span><b>${pct(c.distance)}</b></span>
      ${block(o)}
      <span class="verdict"><b>${verdict(c)}</b><small>${c.shared_taxon || ""}</small></span>
    </a>`;
  }).join("");

  const count = (rank) => pairs.filter((c) => c.shared_rank === rank).length;
  const far = pairs.length - count("family") - count("order");
  $("summary").textContent = `Of ${pairs.length} pairs: ${count("family")} in the same family, ${count("order")} in the same order, ${far} not closely related.`;
  $("stats").innerHTML = [
    [species.length, "species"],
    [pairs.length, "edible and lookalike pairs"],
    [`${pairs.length - far}/${pairs.length}`, "pairs that are real relatives"],
  ].map(([n, label]) => `<div><dt>${n}</dt><dd>${label}</dd></div>`).join("");
}

function renderHeat() {
  const order = leaves.map((l) => l.name);
  const N = order.length, CELL = 44, STEP = 46, LEFT = 232, TOP = 22;
  const all = comparisons.map((c) => c.distance);
  const lo = Math.floor(Math.min(...all) * 20) / 20, hi = Math.ceil(Math.max(...all) * 20) / 20;
  const DARK = [28, 40, 54], LIGHT = [228, 225, 216];
  const colour = (t) => `rgb(${DARK.map((v, i) => Math.round(v + (LIGHT[i] - v) * t)).join(",")})`;

  let out = "";
  order.forEach((id, i) => {
    const y = TOP + i * STEP + CELL / 2, s = byId[id];
    out += `<text class="idx" x="${LEFT + i * STEP + CELL / 2}" y="12" text-anchor="middle">${i + 1}</text>
      <g class="row" data-sp="${id}">
        <text class="idx" x="16" y="${y}" text-anchor="end" dominant-baseline="central">${i + 1}</text>
        ${shape(s.status, 30, y, 4.5)}
        <text class="name" x="42" y="${y}" dominant-baseline="central">${common(s)}</text>
      </g>`;
    order.forEach((other, j) => {
      const x = LEFT + j * STEP, top = TOP + i * STEP;
      if (i === j) { out += shape(s.status, x + CELL / 2, y, 4.5); return; }
      const c = cmp.get(key(id, other));
      const t = (c.distance - lo) / (hi - lo);
      out += `<g class="cell" data-pairkey="${key(id, other)}">
        <rect x="${x}" y="${top}" width="${CELL}" height="${CELL}" fill="${colour(t)}"/>
        <text x="${x + CELL / 2}" y="${y}" text-anchor="middle" dominant-baseline="central" fill="${t < 0.42 ? "#f5f3ee" : "#1b1b19"}">${Math.round(c.distance * 100)}</text>
        ${c.pair ? `<rect class="ring" x="${x - 1}" y="${top - 1}" width="${CELL + 2}" height="${CELL + 2}"/>` : ""}
        <rect class="focus" x="${x - 0.5}" y="${top - 0.5}" width="${CELL + 1}" height="${CELL + 1}"/>
      </g>`;
    });
  });
  const svg = $("heat");
  svg.setAttribute("viewBox", `0 0 ${LEFT + N * STEP} ${TOP + N * STEP}`);
  svg.innerHTML = out;
  svg.querySelectorAll(".cell").forEach((el) => bind(el, ...el.dataset.pairkey.split("|")));

  $("ramp").innerHTML = [0, 0.2, 0.4, 0.6, 0.8, 1]
    .map((t) => `<span><i style="background:${colour(t)}"></i>${pct(lo + t * (hi - lo))}</span>`).join("");
}

function renderMethod() {
  const pairs = lookalikes();
  const picks = [pairs[0], pairs.at(-1)]; // closest and most distant lookalike pair
  const alnFor = (c) => alignments.find((a) => key(a.a, a.b) === key(c.a, c.b));

  const first = alnFor(picks[0]), s = byId[first.a];
  const letters = [...first.top].filter((ch) => ch !== "-");
  $("strip").innerHTML = letters.map((ch) => `<span>${ch}</span>`).join("");
  $("strip-caption").innerHTML = `${letters.length} letters from the barcode of ${common(s)} (<i>${s.name}</i>). The full barcode used here is GenBank record ${s.accession}.`;

  $("alignments").innerHTML = picks.map((c) => {
    const aln = alnFor(c), top = [...aln.top], bottom = [...aln.bottom];
    const differ = top.filter((ch, i) => ch !== bottom[i]).length;
    const show = (ch) => (ch === "-" ? "–" : ch);
    return `<figure class="aln">
      <figcaption><b>${common(byId[aln.a])}</b> and <b>${common(byId[aln.b])}</b> · ${differ} of ${top.length} positions differ in this excerpt · ${pct(c.distance)} across all ${aln.length} positions</figcaption>
      <div class="alnrow">
        <div class="alnlabels"><span>${common(byId[aln.a])}</span><span>${common(byId[aln.b])}</span></div>
        <div class="scroll"><div class="alncols">${top.map((ch, i) =>
          `<span class="${ch !== bottom[i] ? "x" : ""}"><b>${show(ch)}</b><b>${show(bottom[i])}</b></span>`).join("")}</div></div>
      </div>
    </figure>`;
  }).join("");

  $("lineages").innerHTML = picks.map((c) => {
    const [a, b] = [byId[c.a], byId[c.b]];
    const rows = RANKS.map((r) => {
      const [x, y] = [a.taxonomy[r], b.taxonomy[r]];
      return `<span class="rank">${r}</span>` + (x === y ? `<span class="same">${x}</span>` : `<span>${x}</span><span>${y}</span>`);
    }).join("");
    return `<div class="lineage"><span class="rank"></span><b>${common(a)}</b><b>${common(b)}</b>${rows}
      <span class="rank"></span><em>${verdict(c)}</em></div>`;
  }).join("");
}

function renderSources() {
  $("sources").tBodies[0].innerHTML = species.map((s) => `<tr>
    <td><i>${s.name}</i><small>${common(s)}</small></td>
    <td>${statusTag(s)}</td>
    <td><a href="${s.source}">${new URL(s.source).hostname}</a></td>
    <td><a href="https://www.ncbi.nlm.nih.gov/nuccore/${s.accession}">${s.accession}</a></td>
    <td><a href="https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=${s.taxonomy.taxid}">${s.taxonomy.family}, ${s.taxonomy.order}</a></td>
    <td class="credit">${s.photo ? `${s.photo.attribution} · <a href="https://www.inaturalist.org/taxa/${s.inat_id}">iNaturalist</a>` : ""}</td>
  </tr>`).join("");
}

async function main() {
  let tree;
  [species, comparisons, tree, alignments] = await Promise.all(
    ["species", "comparisons", "tree", "alignments"].map((p) => fetch(`/api/${p}`).then((r) => r.json())));
  byId = Object.fromEntries(species.map((s) => [s.id, s]));
  cmp = new Map(comparisons.map((c) => [key(c.a, c.b), c]));
  layout(tree);

  // Each page only contains some of these containers.
  if ($("pairs")) renderPairs();
  if ($("tree")) renderTree();
  if ($("heat")) renderHeat();
  if ($("strip")) renderMethod();
  if ($("sources")) renderSources();
  if ($("legend")) $("legend").innerHTML = Object.keys(STATUS).map((s) => `<span>${icon(s)}${STATUS[s]}</span>`).join("");

  const linked = decodeURIComponent(location.hash.slice(1));
  if (cmp.has(linked)) pinned = linked.split("|");
  highlight(...(pinned || []));

  if ($("tree")) {
    const redraw = () => { renderTree(); highlight(...(pinned || [])); };
    document.fonts.ready.then(redraw); // label widths change once fonts load
    let timer;
    window.addEventListener("resize", () => { clearTimeout(timer); timer = setTimeout(redraw, 150); });
  }
}

main();
