// Search, species and lens pages. Everything here is looked up live through /api.
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

async function api(path, options) {
  const r = await fetch(path, options);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Something went wrong.");
  return body;
}

// Searches are kept in the address bar, so the back button returns to the same results.
const params = new URLSearchParams(location.search);
const remember = () => history.replaceState(null, "", "?" + params);

// Wait until typing pauses before asking, so there is not one request per keystroke.
function debounce(fn, ms = 300) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

const photo = (s, size) => (s.photo
  ? `<img src="${esc(s.photo[size])}" alt="" title="${esc(s.photo.attribution)}" loading="lazy">`
  : `<span class="nophoto"></span>`);
const names = (s) => `<b>${esc(common(s))}</b><i>${esc(s.name)}</i>`;
const card = (s) => `<a class="card" href="/species/${s.id}">${photo(s, "square")}
  <span>${names(s)}<small>${s.status ? statusTag(s) : ""}${s.count ? `${s.count.toLocaleString("en")} record${s.count > 1 ? "s" : ""}` : ""}${s.note ? esc(s.note) : ""}</small></span></a>`;
const cards = (el, list, empty) => { el.innerHTML = list.length ? list.map(card).join("") : `<p class="caption">${empty}</p>`; };
const note = (el, text) => { el.innerHTML = `<p class="caption">${esc(text)}</p>`; };

function initSearch() {

  const byName = async (q) => {
    params.set("q", q); remember();
    if (q.length < 2) { $("name-results").innerHTML = ""; return; }
    try {
      const list = await api(`/api/find?q=${encodeURIComponent(q)}`);
      if (q === $("name").value.trim()) cards($("name-results"), list, "No mushroom species found with that name."); // ignore answers to older typing
    } catch (e) { note($("name-results"), e.message); }
  };
  $("name").addEventListener("input", debounce(() => byName($("name").value.trim())));

  let place = null;
  const showPlace = async () => {
    const month = $("month").value;
    params.set("place", place.id); params.set("in", place.name); params.set("month", month); remember();
    $("place-title").textContent = `Recorded in ${place.name}${month ? ` in ${MONTHS[month - 1]}` : ""}`;
    note($("place-results"), "Looking up…");
    try {
      cards($("place-results"), await api(`/api/place/${place.id}${month ? `?month=${month}` : ""}`), "No mushroom records found there.");
    } catch (e) { note($("place-results"), e.message); }
  };
  const suggest = async (q) => {
    if (q.length < 2) { $("place-options").innerHTML = ""; return; }
    try {
      const list = await api(`/api/places?q=${encodeURIComponent(q)}`);
      $("place-options").innerHTML = list.map((p) => `<button data-id="${p.id}">${esc(p.name)}</button>`).join("");
    } catch (e) { note($("place-options"), e.message); }
  };
  $("place").addEventListener("input", debounce(() => suggest($("place").value.trim())));
  $("place-options").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    place = { id: b.dataset.id, name: b.textContent };
    $("place").value = place.name;
    $("place-options").innerHTML = "";
    showPlace();
  });
  $("month").addEventListener("change", () => place && showPlace());

  // Restore a search from the address bar.
  if (params.get("q")) { $("name").value = params.get("q"); byName(params.get("q")); }
  if (params.get("place")) {
    place = { id: params.get("place"), name: params.get("in") };
    $("place").value = place.name;
    $("month").value = params.get("month") || "";
    showPlace();
  }
}

async function initSpecies() {
  const id = location.pathname.split("/").pop();
  let s;
  try { s = await api(`/api/profile/${id}`); } catch (e) {
    $("title").textContent = "Species not found";
    $("latin").textContent = e.message;
    return;
  }
  document.title = `${common(s)} · Doppelshroom`;
  $("title").textContent = common(s);
  $("latin").textContent = s.name;
  $("photo").innerHTML = photo(s, "medium");
  const tax = s.taxonomy;
  $("meta").innerHTML = `${statusTag(s)}<span>${esc(tax.family)}, ${esc(tax.order)}</span>
    <a href="https://www.inaturalist.org/taxa/${s.id}">iNaturalist</a>
    ${s.gbif ? `<a href="https://www.gbif.org/species/${s.gbif.gbif_key}">GBIF</a>` : ""}`;
  const lab = s.label;
  $("label-note").innerHTML = !lab
    ? "No label: neither this site's checked list nor Wikipedia gives an edibility for this species. No label does not mean safe to eat."
    : lab.from === "checked"
      ? `Label checked by hand for this site. Source: <a href="${esc(lab.source)}">${esc(new URL(lab.source).hostname)}</a>`
      : `Label from the <a href="${esc(lab.source)}">Wikipedia article</a>, whose infobox lists: ${lab.listed.map(esc).join(", ")}. Where it lists more than one, this site shows the most dangerous.`;
  $("about").innerHTML = s.wikipedia
    ? `<p>${esc(s.wikipedia.extract)}</p><p><a href="${esc(s.wikipedia.url)}">Read more on Wikipedia</a></p>`
    : `<p>No Wikipedia summary found for this species.</p>`;

  const looks = s.lookalikes;
  if (!looks.length) {
    $("look-summary").textContent = "No lookalikes are recorded for this species yet.";
    document.querySelector(".look-head").hidden = true;
    $("tree").closest("section").hidden = true;
    $("side").hidden = true;
    return;
  }
  const show = twinMaps();

  const close = looks.filter((l) => ["genus", "family"].includes(l.shared_rank)).length;
  const distant = looks.filter((l) => l.shared_rank === "order").length;
  $("look-summary").textContent = `Of ${looks.length} lookalikes: ${close} in the same genus or family, ${distant} in the same order, ${looks.length - close - distant} not closely related.`;
  $("lookalikes").innerHTML = looks.map((l) => `<a class="look" href="/species/${l.id}">
    <span class="sp">${photo(l, "medium")}<span>${names(l)}<small>${statusTag(l)} · ${esc(l.taxonomy.family)}</small></span></span>
    <span class="dist" data-dna="${l.id}"><em>Fetching DNA…</em></span>
    <span class="verdict"><b>${verdict(l)}</b><small>${esc(l.shared_taxon || "")}</small></span>
    <span class="times">${l.count.toLocaleString("en")} times</span>
  </a>`).join("");

  // Side by side: this species, and one lookalike chosen with the buttons.
  const pick = (l) => {
    document.querySelectorAll("#picker button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.id === String(l.id)));
    sideBySide(s, l, show);
  };
  $("picker").innerHTML = looks.map((l) => `<button data-id="${l.id}">${esc(common(l))}</button>`).join("");
  document.querySelectorAll("#picker button").forEach((b, i) => b.addEventListener("click", () => pick(looks[i])));
  pick(looks[0]);

  // DNA takes longest the first time (one download per species from NCBI), so it fills in last.
  const SCALE = 0.5; // a full bar means half of all positions differ
  const dna = await api(`/api/dna/${id}`).catch(() => ({ lookalikes: {} }));
  document.querySelectorAll("[data-dna]").forEach((el) => {
    const d = dna.lookalikes[el.dataset.dna];
    el.innerHTML = d
      ? `<span class="track"><i style="width:${Math.min(d.distance / SCALE, 1) * 100}%"></i></span><b>${pct(d.distance)}</b>`
      : `<em>No usable barcode</em>`;
    if (!d) return;
    el.title = `${d.length} positions compared, GenBank ${dna.accession} and ${d.accession}`;
    // Species in one genus rarely differ this much, so the barcode and the classification disagree.
    const look = looks.find((l) => String(l.id) === el.dataset.dna);
    if (look.shared_rank === "genus" && d.distance > 0.4) el.insertAdjacentHTML("beforeend", "<em>High for one genus. Treat with caution.</em>");
  });

  const tree = await api(`/api/family/${id}`).catch(() => null);
  if (tree) treeView($("tree"), tree, Object.fromEntries([s, ...looks].map((x) => [x.id, x])), s.id);
  else note($("tree"), "Too few of these lookalikes have a usable DNA barcode to build a tree.");
}

// ---- Two species side by side: DNA letter by letter, season and maps ----

// Neighbouring letters that look the same are merged into one span, so a 700-letter alignment stays light.
function runs(cells) {
  let html = "", cls = null, text = "";
  const flush = () => { if (text) html += cls ? `<i class="${cls}">${text}</i>` : text; text = ""; };
  cells.forEach(([ch, k]) => { if (k !== cls) { flush(); cls = k; } text += ch; });
  flush();
  return html;
}

function dnaView(el, a, b, p) {
  const d = p.dna;
  if (!d) {
    note(el, "One of these species has no GenBank barcode that overlaps enough with the other's, so they cannot be compared letter by letter.");
    return;
  }
  const regionOf = (i) => (d.regions ? d.regions.find((r) => i >= r.start && i < r.end).name : null);
  const genes = d.regions
    ? `<div class="genes">${d.regions.map((r) => `<span class="${r.name === "5.8S" ? "gene" : "spacer"}" style="flex-grow:${Math.max(r.end - r.start, 1)}">
        <b>${r.name}</b><small>${r.same === null ? "not covered" : `${pct(r.same)} same`}</small></span>`).join("")}</div>`
    : `<p class="caption">The 5.8S gene could not be found reliably in these barcodes, so the regions are not marked. A common cause is chanterelles, whose ribosomal DNA changes unusually fast.</p>`;
  const key = `<p class="key"><span><i class="sw a"></i>${esc(common(a))}, top row</span><span><i class="sw b"></i>${esc(common(b))}, bottom row</span>
    <span>${pct(1 - d.distance)} of ${d.length} positions the same</span></p>`;

  const W = 50;
  let blocks = "";
  for (let i = 0; i < d.length; i += W) {
    const top = [], mid = [], bot = [];
    for (let j = i; j < Math.min(i + W, d.length); j++) {
      const x = d.top[j], y = d.bottom[j];
      const k = x === y ? (regionOf(j) === "5.8S" ? "g" : null) : x === "-" || y === "-" ? "gap" : "diff";
      top.push([x, k]); bot.push([y, k]); mid.push([x === y ? "|" : " ", null]);
    }
    blocks += `<div class="aln-block"><span class="aln-pos">${i + 1}<br>${regionOf(i) || ""}</span><pre>${runs(top)}\n${runs(mid)}\n${runs(bot)}</pre></div>`;
  }
  const acc = (n) => `<a href="https://www.ncbi.nlm.nih.gov/nuccore/${esc(n)}">${esc(n)}</a>`;
  el.innerHTML = `${genes}${key}<details class="aln-all"><summary>Show all ${d.length} positions</summary>
    <div class="scroll">${blocks}</div>
    <p class="caption">GenBank ${acc(d.accessions[0])} (top) and ${acc(d.accessions[1])} (bottom). Shaded letters are the 5.8S gene. Numbers count alignment columns, including gaps.</p></details>`;
}

// Grouped bars: each species' records in each month, as a share of its whole year.
function seasonChart(el, pair, counts) {
  const shares = counts.map((c) => { const total = c.reduce((t, n) => t + n, 0) || 1; return c.map((n) => n / total); });
  const max = Math.max(...shares.flat(), 0.01);
  const Wd = 640, H = 200, L = 40, B = 24, T = 8, slot = (Wd - L) / 12, bw = Math.min(16, (slot - 12) / 2);
  const y = (v) => T + (H - T - B) * (1 - v / max);
  const bar = (x, v, cls) => {
    const top = y(v), base = H - B, r = Math.min(4, (base - top) / 2, bw / 2);
    return base - top < 0.5 ? "" : `<path class="${cls}" d="M${x} ${base} V${top + r} Q${x} ${top} ${x + r} ${top} H${x + bw - r} Q${x + bw} ${top} ${x + bw} ${top + r} V${base} Z"/>`;
  };
  let svg = [0, max / 2, max].map((v) => `<line class="grid" x1="${L}" x2="${Wd}" y1="${y(v)}" y2="${y(v)}"/>
    <text class="axis" x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${Math.round(v * 100)}%</text>`).join("");
  MONTHS.forEach((m, i) => {
    const x0 = L + i * slot + (slot - 2 * bw - 2) / 2;
    svg += bar(x0, shares[0][i], "s-a") + bar(x0 + bw + 2, shares[1][i], "s-b")
      + `<text class="axis" x="${L + i * slot + slot / 2}" y="${H - 6}" text-anchor="middle">${m.slice(0, 3)}</text>`
      + `<rect class="hit" data-m="${i}" x="${L + i * slot}" y="${T}" width="${slot}" height="${H - T - B}"/>`;
  });
  const total = (i) => counts[i].reduce((t, n) => t + n, 0).toLocaleString("en");
  const legend = `<p class="key">${pair.map((s, i) => `<span><i class="sw ${"ab"[i]}"></i>${esc(common(s))} · ${total(i)} records</span>`).join("")}</p>`;
  const table = `<details><summary>Show as a table</summary><div class="scroll"><table class="table">
    <tr><th></th>${MONTHS.map((m) => `<th>${m.slice(0, 3)}</th>`).join("")}</tr>
    ${pair.map((s, i) => `<tr><th>${esc(common(s))}</th>${counts[i].map((n) => `<td>${n.toLocaleString("en")}</td>`).join("")}</tr>`).join("")}</table></div></details>`;
  el.innerHTML = `${legend}<div class="chart"><svg viewBox="0 0 ${Wd} ${H}" role="img" aria-label="Share of records in each month">${svg}</svg><div class="tip" hidden></div></div>${table}`;

  const tip = el.querySelector(".tip"), chart = el.querySelector(".chart");
  el.querySelectorAll(".hit").forEach((h) => {
    h.addEventListener("mouseenter", () => {
      const i = +h.dataset.m;
      tip.innerHTML = `<b>${MONTHS[i]}</b>${pair.map((s, k) => `<span><i class="sw ${"ab"[k]}"></i>${esc(common(s))}: ${counts[k][i].toLocaleString("en")} (${pct(shares[k][i])})</span>`).join("")}`;
      tip.hidden = false;
      const box = chart.getBoundingClientRect(), r = h.getBoundingClientRect();
      tip.style.left = `${Math.max(0, Math.min(r.left - box.left + r.width / 2 - 90, box.width - 190))}px`;
    });
    h.addEventListener("mouseleave", () => { tip.hidden = true; });
  });
}

// Fills the side-by-side block for two species. A newer call makes any slower earlier one stop.
let sideToken = 0;
async function sideBySide(a, b, show) {
  const token = ++sideToken;
  note($("dna-view"), "Fetching DNA… The first time can take a minute.");
  $("season").innerHTML = "";
  for (const s of [a, b]) {
    if (s.gbif === undefined) s.gbif = await api(`/api/occurrences?name=${encodeURIComponent(s.name)}`).catch(() => null);
  }
  if (token !== sideToken) return;
  show([a, b]);
  const [p, ...counts] = await Promise.all([
    api(`/api/pair?a=${a.id}&b=${b.id}`).catch(() => ({ dna: null })),
    ...[a, b].map((s) => api(`/api/season/${s.id}`).catch(() => Array(12).fill(0))),
  ]);
  if (token !== sideToken) return;
  dnaView($("dna-view"), a, b, p);
  seasonChart($("season"), [a, b], counts);
  return p;
}

// ---- A tree drawn left to right: the root on the left, species on the right ----
function treeView(el, tree, byId, mainId) {
  const leaves = [];
  // x is the distance from the root, y the row; an inner node sits halfway between its children.
  const place = (n, x) => {
    n.x = x;
    n.children.forEach((c) => place(c, x + c.length));
    if (n.children.length) n.y = (n.children[0].y + n.children.at(-1).y) / 2;
    else { n.y = leaves.length; leaves.push(n); }
  };
  place(tree, 0);
  const depth = Math.max(...leaves.map((l) => l.x)) || 1;
  const Wd = 820, label = 420, row = 30, H = leaves.length * row + 44;
  const X = (v) => 10 + (v / depth) * (Wd - label - 30), Y = (v) => 16 + v * row;
  let svg = "";
  const draw = (n) => {
    if (!n.children.length) return;
    svg += `<path class="branch" d="M${X(n.x)} ${Y(n.children[0].y)} V${Y(n.children.at(-1).y)}"/>`;
    n.children.forEach((c) => { svg += `<path class="branch" d="M${X(n.x)} ${Y(c.y)} H${X(c.x)}"/>`; draw(c); });
  };
  draw(tree);
  svg += leaves.map((l) => {
    const s = byId[l.id], x = Wd - label;
    return `<a href="/species/${s.id}"><g class="leaf${s.id === mainId ? " main" : ""}">
      <path class="lead" d="M${X(l.x) + 4} ${Y(l.y)} H${x}"/>${shape(s.status, x + 10, Y(l.y), 5)}
      <text x="${x + 22}" y="${Y(l.y) + 4}">${esc(common(s))}<tspan class="latin"> ${esc(s.name)}</tspan></text></g></a>`;
  }).join("");
  const unit = depth > 0.3 ? 0.1 : 0.05;
  svg += `<path class="branch" d="M${X(0)} ${H - 14} H${X(unit)}"/><text class="axis" x="${X(unit) + 8}" y="${H - 10}">${pct(unit)} DNA difference</text>`;
  el.innerHTML = `<svg class="tree" viewBox="0 0 ${Wd} ${H}" role="img" aria-label="Family tree of this species and its lookalikes">${svg}</svg>
    <p class="key">${["deadly", "poisonous", "caution", "inedible", "edible", null].map((k) => `<span>${icon(k)}${STATUS[k] || "No label"}</span>`).join("")}</p>`;
}

// ---- Home page: today's mix-up, and what is out near you ----
const duo = (m) => `<div class="duo">${card(m.a)}<span class="vs">or</span>${card(m.b)}</div>${mixText(m)}`;
const mixText = (m) => `<p class="summary">${esc(verdict(m))}${m.shared_taxon ? ` (${esc(m.shared_taxon)})` : ""}.
  ${m.dna ? `Their DNA barcodes differ at ${pct(m.dna.distance)} of positions.` : "No DNA comparison is available."}
  ${m.confused ? `iNaturalist observers have confused them ${m.confused.toLocaleString("en")} times.` : ""}</p>`;

async function initSpotlight() {
  try {
    const m = await api("/api/spotlight");
    $("spotlight").innerHTML = `${duo(m)}<p><a class="more" href="/compare?a=${m.a.id}&b=${m.b.id}">Compare them side by side →</a></p>`;
  } catch (e) { note($("spotlight"), e.message); }
}

function initNear() {
  $("near-month").value = new Date().getMonth() + 1;
  let here = null;
  const show = async () => {
    const month = $("near-month").value;
    note($("near-results"), "Looking up…");
    try {
      const list = await api(`/api/near?lat=${here[0]}&lng=${here[1]}&month=${month}`);
      const bad = list.filter((s) => ["deadly", "poisonous"].includes(s.status)).length;
      $("near-title").textContent = list.length
        ? `${list.length} species recorded near you in ${MONTHS[month - 1]}. ${bad} of them are labelled poisonous or deadly.` : "";
      cards($("near-results"), list, "No mushroom records near you in that month.");
    } catch (e) { note($("near-results"), e.message); }
  };
  $("locate").addEventListener("click", () => {
    if (!navigator.geolocation) { note($("near-results"), "This browser cannot share its location."); return; }
    note($("near-results"), "Asking your browser for your location…");
    navigator.geolocation.getCurrentPosition(
      (p) => { here = [p.coords.latitude, p.coords.longitude].map((v) => v.toFixed(1)); show(); },
      () => note($("near-results"), "Location was not shared. You can search by place instead."),
      { maximumAge: 600000, timeout: 15000 });
  });
  $("near-month").addEventListener("change", () => here && show());
}

// ---- Compare page ----
function initCompare() {
  const chosen = { a: null, b: null };
  let show = null;
  const load = async () => {
    if (!chosen.a || !chosen.b) return;
    params.set("a", chosen.a.id); params.set("b", chosen.b.id); remember();
    $("side").hidden = false;
    show = show || twinMaps(); // Leaflet needs the maps to be visible when it starts
    const p = await sideBySide(chosen.a, chosen.b, show);
    if (p) $("compare-summary").textContent = `${verdict(p)}${p.shared_taxon ? ` (${p.shared_taxon})` : ""}.`;
  };
  const choose = async (side, id) => {
    $(`chosen-${side}`).innerHTML = `<p class="caption">Looking up…</p>`;
    try {
      chosen[side] = await api(`/api/profile/${id}`);
      $(`chosen-${side}`).innerHTML = `<div class="cards">${card(chosen[side])}</div>`;
      $(`pick-${side}`).value = "";
      load();
    } catch (e) { note($(`chosen-${side}`), e.message); }
  };
  for (const side of ["a", "b"]) {
    const box = $(`options-${side}`);
    $(`pick-${side}`).addEventListener("input", debounce(async () => {
      const q = $(`pick-${side}`).value.trim();
      if (q.length < 2) { box.innerHTML = ""; return; }
      try {
        const list = await api(`/api/find?q=${encodeURIComponent(q)}`);
        box.innerHTML = list.map((s) => `<button data-id="${s.id}">${esc(common(s))} <i>${esc(s.name)}</i></button>`).join("");
      } catch (e) { note(box, e.message); }
    }));
    box.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      box.innerHTML = "";
      choose(side, b.dataset.id);
    });
    if (params.get(side)) choose(side, params.get(side));
  }
}

// ---- Quiz ----
function initQuiz() {
  let right = 0, asked = 0;
  const next = async () => {
    $("reveal").innerHTML = "";
    $("choices").innerHTML = "";
    $("mystery").innerHTML = `<p class="caption">Finding a photo…</p>`;
    let q;
    try { q = await api("/api/quiz"); } catch (e) { $("mystery").innerHTML = `<p class="caption">${esc(e.message)}</p>`; return; }
    $("mystery").innerHTML = `<img src="${esc(q.photo.url)}" alt="A mushroom to identify">
      <figcaption class="caption">Photo ${esc(q.photo.attribution)}, via iNaturalist</figcaption>`;
    const options = Math.random() < 0.5 ? [q.a, q.b] : [q.b, q.a];
    // Labels stay hidden until the answer, so the guess is about looks only.
    $("choices").innerHTML = options.map((s) => `<button class="choice" data-id="${s.id}">${photo(s, "medium")}<span>${names(s)}</span></button>`).join("");
    $("choices").querySelectorAll("button").forEach((btn) => btn.addEventListener("click", () => {
      const ok = +btn.dataset.id === q.answer;
      asked += 1; right += ok;
      $("score").textContent = `Score ${right} of ${asked}`;
      $("choices").querySelectorAll("button").forEach((b) => {
        b.disabled = true;
        const s = options.find((o) => String(o.id) === b.dataset.id);
        b.classList.toggle("answer", s.id === q.answer);
        b.querySelector("span").insertAdjacentHTML("beforeend", `<small>${statusTag(s)}${s.id === q.answer ? " · The photo shows this one" : ""}</small>`);
      });
      $("reveal").innerHTML = `<p class="summary"><b>${ok ? "Right." : "Not this time."}</b></p>${mixText(q)}
        <p><a href="https://www.inaturalist.org/observations/${q.photo.observation}">See this observation on iNaturalist</a> ·
        <a href="/compare?a=${q.a.id}&b=${q.b.id}">Compare the two species</a></p>
        <button class="button" id="next">Next photo</button>`;
      $("next").addEventListener("click", next);
    }));
  };
  next();
}

function initDescribe() {
  const run = async (q) => {
    params.set("d", q); remember();
    $("describe-title").textContent = "";
    note($("describe-results"), "Asking the AI, then checking each suggestion against iNaturalist…");
    try {
      const r = await api(`/api/describe?q=${encodeURIComponent(q)}`);
      if (r.place) r.species.forEach((s) => {
        s.note = s.in_place ? `${s.in_place.toLocaleString("en")} records in ${r.place}` : `Not recorded in ${r.place}`;
      });
      $("describe-title").textContent = r.species.length ? `Possible matches${r.place ? `, checked against records in ${r.place}` : ""}` : "";
      cards($("describe-results"), r.species, "No matching species found. Try describing it differently.");
      if (r.dropped) $("describe-results").insertAdjacentHTML("afterend",
        `<p class="caption" id="dropped">${r.dropped} AI suggestion${r.dropped > 1 ? "s were" : " was"} not found on iNaturalist and left out.</p>`);
    } catch (e) { note($("describe-results"), e.message); }
  };
  $("describe-form").addEventListener("submit", (e) => {
    e.preventDefault();
    document.getElementById("dropped")?.remove();
    const q = $("describe").value.trim();
    if (q.length >= 3) run(q);
  });
  if (params.get("d")) { $("describe").value = params.get("d"); run(params.get("d")); }
}

// Shrink a picture in the browser before sending: faster, and the original never leaves the device.
function toJpeg(source, width, height, max = 1024) {
  const scale = Math.min(1, max / Math.max(width, height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  canvas.getContext("2d").drawImage(source, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.85);
}

function shrink(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(img.src); resolve(toJpeg(img, img.width, img.height)); };
    img.onerror = () => reject(new Error("That file could not be read as an image."));
    img.src = URL.createObjectURL(file);
  });
}

function initLens() {
  const drop = $("drop");
  const fromFile = async (file) => {
    if (!file) return;
    try { look(await shrink(file)); } catch (e) { note($("lens-status"), e.message); }
  };

  // Camera: a live preview inside the drop zone. The browser asks for permission first,
  // and only offers this on https or localhost, so the button stays hidden elsewhere.
  let stream = null;
  const stopCamera = () => {
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    $("video").srcObject = null;
    $("camera").hidden = true;
    $("start").hidden = false;
  };
  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) $("camera-open").hidden = false;
  $("camera-open").addEventListener("click", async () => {
    $("lens-status").innerHTML = "";
    try {
      // "environment" asks a phone for its back camera; a laptop just uses its webcam.
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 } }, audio: false });
    } catch (e) {
      note($("lens-status"), e.name === "NotAllowedError"
        ? "Camera access was not allowed. You can allow it in your browser's settings, or choose a photo instead."
        : "No camera could be opened. You can choose a photo instead.");
      return;
    }
    $("video").srcObject = stream;
    $("start").hidden = true;
    $("camera").hidden = false;
  });
  $("snap").addEventListener("click", () => {
    const v = $("video");
    if (!v.videoWidth) return; // the picture has not started yet
    const url = toJpeg(v, v.videoWidth, v.videoHeight);
    stopCamera();
    look(url);
  });
  $("camera-close").addEventListener("click", stopCamera);
  window.addEventListener("pagehide", stopCamera);

  $("file").addEventListener("change", () => { fromFile($("file").files[0]); $("file").value = ""; });
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); stopCamera(); fromFile(e.dataTransfer.files[0]); });
}

// Send a picture (a JPEG data URL) to the lens and show what comes back.
async function look(url) {
  $("preview").innerHTML = `<img src="${url}" alt="Your photo">`;
  $("preview").hidden = false;
  $("drop").classList.add("has-photo");
  $("choose").textContent = "Choose another";
  $("results").hidden = true;
  note($("lens-status"), "Looking at the photo, then checking each suggestion and its lookalikes. The first time can take half a minute…");
  try {
    const r = await api("/api/lens", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: url.split(",")[1], mime: "image/jpeg" }),
    });
    if (!r.matches.length) {
      note($("lens-status"), "No mushroom was recognised. Try a clear photo of the whole mushroom, including the stem and the underside of the cap.");
      return;
    }
    $("lens-status").innerHTML = "";
    cards($("matches"), r.matches, "");
    r.dangerous.forEach((d) => { d.note = `Mistaken for ${d.mixed_with.join(", ")}`; d.count = 0; });
    cards($("dangerous"), r.dangerous, "None of the possible matches has a poisonous lookalike on record. That does not make any of them safe.");
    $("results").hidden = false;
  } catch (e) { note($("lens-status"), e.message); }
}

if ($("name")) initSearch();
if ($("describe")) initDescribe();
if ($("file")) initLens();
if ($("lookalikes")) initSpecies();
if ($("spotlight")) initSpotlight();
if ($("locate")) initNear();
if ($("pick-a")) initCompare();
if ($("choices")) initQuiz();
