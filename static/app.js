// The "How it works" and "Sources" pages, built from the ten hand-checked example species.
const RANKS = ["phylum", "class", "order", "family", "genus"];

let species, byId, comparisons, alignments;

const key = (a, b) => [a, b].sort().join("|");
const lookalikes = () => comparisons.filter((c) => c.pair).sort((p, q) => p.distance - q.distance);

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
    <td><a href="https://www.gbif.org/species/${s.gbif.gbif_key}">${s.gbif.records.toLocaleString("en")}</a></td>
    <td class="credit">${s.photo ? `${s.photo.attribution} · <a href="https://www.inaturalist.org/taxa/${s.inat_id}">iNaturalist</a>` : ""}</td>
  </tr>`).join("");
}

async function main() {
  [species, comparisons, alignments] = await Promise.all(
    ["species", "comparisons", "alignments"].map((p) => fetch(`/api/${p}`).then((r) => r.json())));
  byId = Object.fromEntries(species.map((s) => [s.id, s]));

  // Each page only contains some of these containers.
  if ($("strip")) renderMethod();
  if ($("sources")) renderSources();
}

main();
