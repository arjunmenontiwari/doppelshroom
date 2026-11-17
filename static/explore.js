// Search page and species page. Everything here is looked up live through /api.
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error((await r.json()).detail || "Something went wrong.");
  return r.json();
}

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
  <span>${names(s)}<small>${s.status ? statusTag(s) : ""}${s.count ? `${s.count.toLocaleString("en")} record${s.count > 1 ? "s" : ""}` : ""}</small></span></a>`;
const cards = (el, list, empty) => { el.innerHTML = list.length ? list.map(card).join("") : `<p class="caption">${empty}</p>`; };
const note = (el, text) => { el.innerHTML = `<p class="caption">${esc(text)}</p>`; };

function initSearch() {
  const params = new URLSearchParams(location.search);
  const remember = () => history.replaceState(null, "", "?" + params); // so the back button returns to these results

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
  $("label-note").innerHTML = s.status
    ? `Label source: <a href="${esc(s.source)}">${esc(new URL(s.source).hostname)}</a>`
    : "No label: this site only labels species that were checked by hand against a source. No label does not mean safe to eat.";
  $("about").innerHTML = s.wikipedia
    ? `<p>${esc(s.wikipedia.extract)}</p><p><a href="${esc(s.wikipedia.url)}">Read more on Wikipedia</a></p>`
    : `<p>No Wikipedia summary found for this species.</p>`;

  const show = twinMaps();
  const looks = s.lookalikes;
  if (!looks.length) {
    $("look-summary").textContent = "No lookalikes are recorded for this species yet.";
    document.querySelector(".look-head").hidden = true;
    show([s]);
    return;
  }

  const close = looks.filter((l) => ["genus", "family"].includes(l.shared_rank)).length;
  const distant = looks.filter((l) => l.shared_rank === "order").length;
  $("look-summary").textContent = `Of ${looks.length} lookalikes: ${close} in the same genus or family, ${distant} in the same order, ${looks.length - close - distant} not closely related.`;
  $("lookalikes").innerHTML = looks.map((l) => `<a class="look" href="/species/${l.id}">
    <span class="sp">${photo(l, "medium")}<span>${names(l)}<small>${statusTag(l)} · ${esc(l.taxonomy.family)}</small></span></span>
    <span class="dist" data-dna="${l.id}"><em>Fetching DNA…</em></span>
    <span class="verdict"><b>${verdict(l)}</b><small>${esc(l.shared_taxon || "")}</small></span>
    <span class="times">${l.count.toLocaleString("en")} times</span>
  </a>`).join("");

  // Maps: this species on the left, one lookalike on the right.
  const pick = async (l) => {
    document.querySelectorAll("#picker button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.id === String(l.id)));
    if (l.gbif === undefined) l.gbif = await api(`/api/occurrences?name=${encodeURIComponent(l.name)}`).catch(() => null);
    show([s, l]);
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
}

if ($("name")) initSearch();
if ($("lookalikes")) initSpecies();
