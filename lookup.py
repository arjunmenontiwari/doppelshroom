"""Live lookups for any species. Answers are saved in cache/, so each question is asked once."""
import csv
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from Bio.Align import PairwiseAligner
from Bio.Seq import Seq

import gemini
from build_tree import align, distance
from fetch_occurrences import occurrences
from fetch_sequences import fetch_its

ROOT = Path(__file__).parent
CACHE = ROOT / "cache"
INAT = "https://api.inaturalist.org/v1"
WIKI = "https://en.wikipedia.org/w/api.php"
MUSHROOMS = "50814,152032"  # iNaturalist ids: Agaricomycetes (most mushrooms), Pezizomycetes (morels, cups)
RANKS = ("genus", "family", "order", "class", "phylum")  # most specific first
MIN_OVERLAP = 300  # two barcodes that share fewer positions than this are not compared
RECHECK = 30 * 24 * 3600  # seconds before a "no label" answer is asked again
ncbi = threading.Lock()  # NCBI allows 3 requests a second, so only one visitor fetches at a time

with open(ROOT / "species.csv", newline="") as f:
    CHECKED = {r["species"]: {"status": r["status"], "source": r["source"], "from": "checked"}
               for r in csv.DictReader(f)}

# Values a Wikipedia mushroom infobox can give, most dangerous first, and the label each becomes.
DANGER = {"deadly": "deadly", "poisonous": "poisonous", "psychoactive": "caution", "allergenic": "caution",
          "caution": "caution", "inedible": "inedible", "edible": "edible", "choice": "edible"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "mushroom-education-script"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def cache_path(kind, key):
    return CACHE / kind / (re.sub(r"\W+", "_", str(key)) + ".json")


def save(kind, key, value):
    path = cache_path(kind, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def cached(kind, key, make):
    """Return the saved answer for this question, or work it out and save it."""
    path = cache_path(kind, key)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    value = make()
    save(kind, key, value)
    return value


def wiki_labels(names):
    """Edibility from each species' Wikipedia infobox. One request covers up to 50 species."""
    params = {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
              "redirects": 1, "format": "json", "formatversion": 2, "titles": "|".join(names)}
    q = get(f"{WIKI}?{urllib.parse.urlencode(params)}")["query"]
    # Wikipedia may answer under another title (a redirect from an old name), so follow the moves.
    moved = {m["from"]: m["to"] for m in q.get("normalized", []) + q.get("redirects", [])}
    pages = {p["title"]: p for p in q["pages"]}
    out = {}
    for name in names:
        title = name
        for _ in range(3):
            title = moved.get(title, title)
        page = pages.get(title, {})
        # Only trust a page about one species: a redirect to a genus page would describe other species.
        if "revisions" not in page or not re.fullmatch(r"[A-Z][a-z]+ [a-z-]+", title):
            out[name] = None
            continue
        text = page["revisions"][0]["slots"]["main"]["content"]
        if len(re.findall(r"\{\{\s*mycomorphbox", text, re.I)) != 1:
            out[name] = None
            continue
        listed = [v.strip().lower() for v in re.findall(r"\|\s*howEdible\d?\s*=\s*([^|\n}]*)", text)]
        listed = [v for v in listed if v in DANGER]
        worst = min(listed, key=list(DANGER).index) if listed else None
        out[name] = worst and {"status": DANGER[worst], "listed": listed, "from": "wikipedia",
                               "source": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")}
    return out


def labels(names):
    """A label per species: the hand-checked list first, then Wikipedia. Never generated."""
    out = {n: CHECKED[n] for n in names if n in CHECKED}
    todo = []
    for n in set(names) - set(out):
        path = cache_path("label", n)
        value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        # "No label" is checked again after a while, in case Wikipedia has added one since.
        if value or (path.exists() and time.time() - path.stat().st_mtime < RECHECK):
            out[n] = value
        else:
            todo.append(n)
    for i in range(0, len(todo), 50):
        try:
            found = wiki_labels(todo[i:i + 50])
        except urllib.error.URLError:
            continue  # Wikipedia did not answer: show no label now, ask again next time
        for n, value in found.items():
            save("label", n, value)
            out[n] = value
    return out


def with_labels(cards):
    fill_photos(cards)
    found = labels([c["name"] for c in cards])
    for c in cards:
        c["label"] = found.get(c["name"])
        c["status"] = c["label"] and c["label"]["status"]
    return cards


def pick_photo(taxon):
    """The main photo if it has an open licence, otherwise the first of the species' other photos that does."""
    options = [taxon.get("default_photo")] + [p["photo"] for p in taxon.get("taxon_photos", [])]
    p = next((p for p in options if p and p.get("license_code")), None)
    return p and {"square": p["square_url"], "medium": p["medium_url"], "attribution": p["attribution"]}


def fill_photos(cards):
    """Search results only include the main photo. For species whose main photo is not openly
    licensed, look through their other photos: one request covers up to 30 species."""
    todo = []
    for c in cards:
        path = cache_path("photo", c["id"])
        if c["photo"]:
            continue
        if path.exists():
            c["photo"] = json.loads(path.read_text(encoding="utf-8"))
        else:
            todo.append(c)
    for i in range(0, len(todo), 30):
        chunk = todo[i:i + 30]
        try:
            found = {t["id"]: pick_photo(t) for t in get(f"{INAT}/taxa/{','.join(str(c['id']) for c in chunk)}")["results"]}
        except urllib.error.URLError:
            continue  # no photo now, ask again next time
        for c in chunk:
            c["photo"] = found.get(c["id"])
            save("photo", c["id"], c["photo"])


def card(taxon, **extra):
    """The fields the site shows for a species. Labels and missing photos are added later by with_labels."""
    ranks = {a["rank"]: a["name"] for a in taxon.get("ancestors", [])}
    return {
        "id": taxon["id"],
        "name": taxon["name"],
        "common_name": taxon.get("preferred_common_name"),
        "photo": pick_photo(taxon),
        "taxonomy": {r: ranks.get(r) for r in RANKS} if ranks else None,
        **extra,
    }


def search(q):
    q = urllib.parse.quote(q)
    found = get(f"{INAT}/taxa/autocomplete?q={q}&taxon_id={MUSHROOMS}&rank=species&per_page=12")
    return with_labels([card(t) for t in found["results"]])


def places(q):
    found = get(f"{INAT}/places/autocomplete?q={urllib.parse.quote(q)}&per_page=8")
    return [{"id": p["id"], "name": p["display_name"]} for p in found["results"]]


def in_place(place_id, month=None):
    """Mushroom species recorded in a place, most recorded first."""
    url = (f"{INAT}/observations/species_counts?taxon_id={MUSHROOMS}&place_id={place_id}"
           "&quality_grade=research&per_page=48") + (f"&month={month}" if month else "")
    return with_labels(cached("place", f"{place_id}-{month or 0}", lambda: [
        card(r["taxon"], count=r["count"]) for r in get(url)["results"] if r["taxon"]["rank"] == "species"]))


def wikipedia(name):
    try:
        page = get("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(name.replace(" ", "_")))
    except urllib.error.HTTPError:
        return None
    if page.get("type") != "standard":
        return None
    return {"extract": page["extract"], "url": page["content_urls"]["desktop"]["page"]}


def shared(a, b):
    """The most specific rank two species share, e.g. ("family", "Boletaceae")."""
    return next(((r, a[r]) for r in RANKS if a.get(r) and a.get(r) == b.get(r)), (None, None))


def build_profile(inat_id):
    found = get(f"{INAT}/taxa/{inat_id}")["results"]
    if not found or found[0]["rank"] != "species" or found[0].get("iconic_taxon_name") != "Fungi":
        return None
    main = card(found[0])

    # Species that observers most often confuse with this one, from corrected identifications.
    try:
        similar = get(f"{INAT}/identifications/similar_species?taxon_id={inat_id}")["results"]
    except urllib.error.HTTPError:
        similar = None  # iNaturalist sometimes fails on this one query; show the rest and try again later
    counts = {r["taxon"]["id"]: r["count"] for r in similar or []
              if r["taxon"]["rank"] == "species" and r["taxon"].get("iconic_taxon_name") == "Fungi"}
    top = sorted(counts, key=counts.get, reverse=True)[:10]
    # One more request gets the full classification of all the lookalikes at once.
    details = get(f"{INAT}/taxa/{','.join(map(str, top))}")["results"] if top else []
    lookalikes = []
    for t in sorted(details, key=lambda t: -counts[t["id"]]):
        c = card(t, count=counts[t["id"]])
        c["shared_rank"], c["shared_taxon"] = shared(main["taxonomy"], c["taxonomy"])
        lookalikes.append(c)

    return {**main, "wikipedia": wikipedia(main["name"]), "gbif": occurrences(main["name"]),
            "lookalikes": lookalikes, "partial": similar is None}


def profile(inat_id):
    p = cached("profile", inat_id, lambda: build_profile(inat_id))
    if p and p.get("partial"):
        cache_path("profile", inat_id).unlink()  # incomplete: build it again next time
    if p:
        with_labels([p, *p["lookalikes"]])
    return p


def gbif(name):
    return cached("gbif", name, lambda: occurrences(name))


def barcode(name):
    def fetch():
        with ncbi:
            rec = fetch_its(name)
        return rec and {"accession": rec.id, "seq": str(rec.seq)}
    return cached("its", name, fetch)


def build_dna(inat_id):
    """DNA difference between a species and each of its lookalikes."""
    p = profile(inat_id)
    if p is None:
        return None
    mine = barcode(p["name"])
    out = {"accession": mine and mine["accession"], "lookalikes": {}}
    for other in p["lookalikes"]:
        theirs = barcode(other["name"]) if mine else None
        rows = align(Seq(mine["seq"]), Seq(theirs["seq"])) if theirs else None
        if not rows or len(rows[0]) < MIN_OVERLAP:
            out["lookalikes"][other["id"]] = None
            continue
        out["lookalikes"][other["id"]] = {"distance": distance(*rows), "length": len(rows[0]),
                                          "accession": theirs["accession"]}
    return out


def dna(inat_id):
    return cached("dna", inat_id, lambda: build_dna(inat_id))


def resolve(names):
    """Keep only the suggested names that are real mushroom species on iNaturalist."""
    def find(name):
        q = urllib.parse.quote(name)
        hits = get(f"{INAT}/taxa/autocomplete?q={q}&taxon_id={MUSHROOMS}&rank=species&per_page=5")["results"]
        # An exact match on the name, or on an old name (synonym) that iNaturalist knows.
        hit = next((t for t in hits if name.lower() in (t["name"].lower(), t.get("matched_term", "").lower())), None)
        return hit and card(hit)

    found, seen = [], set()
    for name in names[:8]:
        c = cached("name", name.lower(), lambda: find(name))
        if c and c["id"] not in seen:
            seen.add(c["id"])
            found.append(c)
    return with_labels(found)


def describe(text):
    text = " ".join(text.lower().split())
    names, place = cached("describe", hashlib.sha1(text.encode()).hexdigest(), lambda: gemini.describe(text))
    found = resolve(names)
    where = places(place)[:1] if place else []
    if where and found:
        # How often each suggestion has been recorded in that place: a fact check on the AI's guess.
        ids = ",".join(str(c["id"]) for c in found)
        counts = get(f"{INAT}/observations/species_counts?taxon_id={ids}&place_id={where[0]['id']}"
                     "&quality_grade=research&per_page=50")["results"]
        counts = {r["taxon"]["id"]: r["count"] for r in counts}
        for c in found:
            c["in_place"] = counts.get(c["id"], 0)
    return {"species": found, "place": where[0]["name"] if where else None, "dropped": len(names) - len(found)}


DANGEROUS = ("deadly", "poisonous")


def never_edible(c):
    # The lens never calls anything edible: an edible label is removed, not shown.
    if c["status"] == "edible":
        c["status"] = c["label"] = None
    return c


def lens(data, mime):
    matches = resolve(gemini.photo(data, mime))
    with ThreadPoolExecutor(max_workers=5) as pool:
        profiles = list(pool.map(lambda c: profile(c["id"]), matches))
    ids = {c["id"] for c in matches}
    danger = {}
    for match, p in zip(matches, profiles):
        for look in (p or {}).get("lookalikes", []):
            if look["status"] in DANGEROUS and look["id"] not in ids:
                entry = danger.setdefault(look["id"], {**look, "mixed_with": [], "count": 0})
                entry["mixed_with"].append(match["common_name"] or match["name"])
                entry["count"] += look["count"]
    dangerous = sorted(danger.values(), key=lambda c: -c["count"])[:8]
    return {"matches": [never_edible(c) for c in matches], "dangerous": dangerous}


# The 5.8S ribosomal RNA gene of a mushroom (Amanita). It barely changes between species, so a local
# alignment against it finds the gene in almost any barcode, and with it the two spacers on either side.
GENE_5_8S = Seq("CAACTTTCAACAACGGATCTCTTGGCTCTCGCATCGATGAAGAACGCAGCGAAATGCGATAAGTAATGTGAATTGCAGAATTCAGTGAAT"
                "CATCGAATCTTTGAACGCACCTTGCGCCCCTTGGTATTCCGAGGGGCATGCCTGTTTGAGTGTCATT")
local = PairwiseAligner(mode="local", match_score=1, mismatch_score=-1, open_gap_score=-2, extend_gap_score=-0.5)
MIN_GENE_SCORE = 100  # out of 157: below this the match could be chance


def find_gene(seq):
    """(start, end, strand) of the 5.8S gene in a sequence, or None if it cannot be found reliably."""
    seq = Seq(seq)
    hits = [(local.align(s, GENE_5_8S)[0], strand) for s, strand in ((seq, 1), (seq.reverse_complement(), -1))]
    hit, strand = max(hits, key=lambda h: h[0].score)
    if hit.score < MIN_GENE_SCORE:
        return None
    return hit.aligned[0][0][0], hit.aligned[0][-1][1], strand


def regions(top, bottom):
    """Split an alignment into ITS1, 5.8S and ITS2, with the share of identical positions in each."""
    gene = find_gene(top.replace("-", ""))
    if gene and gene[2] == -1:  # stored on the other strand: flip both rows so the genes read in order
        top, bottom = (str(Seq(r).reverse_complement()) for r in (top, bottom))
        gene = find_gene(top.replace("-", ""))
    if not gene:
        return top, bottom, None
    cols = [i for i, ch in enumerate(top) if ch != "-"]  # ungapped position -> alignment column
    start, end = cols[gene[0]], cols[gene[1] - 1] + 1
    out = []
    for name, a, b in (("ITS1", 0, start), ("5.8S", start, end), ("ITS2", end, len(top))):
        same = sum(x == y for x, y in zip(top[a:b], bottom[a:b]))
        out.append({"name": name, "start": a, "end": b, "same": same / (b - a) if b > a else None})
    return top, bottom, out


def taxon(inat_id):
    def fetch():
        found = get(f"{INAT}/taxa/{inat_id}")["results"]
        ok = found and found[0]["rank"] == "species" and found[0].get("iconic_taxon_name") == "Fungi"
        return card(found[0]) if ok else None
    return cached("taxon", inat_id, fetch)


def build_pair(a_id, b_id):
    """Two species compared: how they are classified, and their barcodes aligned letter by letter."""
    a, b = taxon(a_id), taxon(b_id)
    if not a or not b:
        return None
    rank, name = shared(a["taxonomy"], b["taxonomy"])
    out = {"shared_rank": rank, "shared_taxon": name, "dna": None}
    ma, mb = barcode(a["name"]), barcode(b["name"])
    rows = align(Seq(ma["seq"]), Seq(mb["seq"])) if ma and mb else None
    if not rows or len(rows[0]) < MIN_OVERLAP:
        return out
    top, bottom, parts = regions(*rows)
    out["dna"] = {"distance": distance(top, bottom), "length": len(top), "top": top, "bottom": bottom,
                  "regions": parts, "accessions": [ma["accession"], mb["accession"]]}
    return out


def pair(a_id, b_id):
    return cached("pair", f"{a_id}-{b_id}", lambda: build_pair(a_id, b_id))


def build_family(inat_id):
    """A neighbour-joining tree of a species and those lookalikes whose barcodes could be compared."""
    from Bio.Phylo.TreeConstruction import DistanceMatrix, DistanceTreeConstructor
    p, d = profile(inat_id), dna(inat_id)
    if not p or not d:
        return None
    members = [p] + [l for l in p["lookalikes"] if d["lookalikes"].get(str(l["id"])) or d["lookalikes"].get(l["id"])]
    if len(members) < 3:
        return None
    seqs = [Seq(barcode(m["name"])["seq"]) for m in members]
    # DistanceMatrix wants a lower triangle: row i holds the distances to rows 0..i.
    matrix = [[distance(*align(seqs[i], seqs[j])) for j in range(i)] + [0.0] for i in range(len(seqs))]
    tree = DistanceTreeConstructor().nj(DistanceMatrix([str(m["id"]) for m in members], matrix))
    tree.root_at_midpoint()  # no outgroup here, so root halfway between the two most different species
    tree.ladderize()

    def to_dict(c):
        return {"id": int(c.name) if c.is_terminal() else None, "length": max(c.branch_length or 0.0, 0.0),
                "children": [to_dict(k) for k in c.clades]}
    return to_dict(tree.root)


def family(inat_id):
    return cached("family", inat_id, lambda: build_family(inat_id))


def season(inat_id):
    """Confirmed records per month of the year, January first."""
    url = (f"{INAT}/observations/histogram?taxon_id={inat_id}&date_field=observed"
           "&interval=month_of_year&quality_grade=research")
    return cached("season", inat_id, lambda: [get(url)["results"]["month_of_year"][str(m)] for m in range(1, 13)])


def near(lat, lng, month):
    """Mushroom species recorded within 50 km of a point in a given month."""
    url = (f"{INAT}/observations/species_counts?taxon_id={MUSHROOMS}&lat={lat}&lng={lng}&radius=50"
           f"&month={month}&quality_grade=research&per_page=48")
    return with_labels(cached("near", f"{lat}_{lng}_{month}", lambda: [
        card(r["taxon"], count=r["count"]) for r in get(url)["results"] if r["taxon"]["rank"] == "species"]))


# Well-known mix-ups from field guides, used for the daily spotlight and the quiz.
# Only the names are chosen here: labels, DNA and records are all looked up.
MIXUPS = [
    ("Cantharellus cibarius", "Omphalotus olearius"),
    ("Cantharellus cibarius", "Hygrophoropsis aurantiaca"),
    ("Agaricus campestris", "Amanita virosa"),
    ("Macrolepiota procera", "Chlorophyllum molybdites"),
    ("Morchella esculenta", "Gyromitra esculenta"),
    ("Armillaria mellea", "Galerina marginata"),
    ("Kuehneromyces mutabilis", "Galerina marginata"),
    ("Hypholoma capnoides", "Hypholoma fasciculare"),
    ("Boletus edulis", "Tylopilus felleus"),
    ("Amanita caesarea", "Amanita muscaria"),
    ("Volvopluteus gloiocephalus", "Amanita phalloides"),
    ("Russula virescens", "Amanita phalloides"),
    ("Agaricus arvensis", "Agaricus xanthodermus"),
    ("Craterellus tubaeformis", "Cortinarius rubellus"),
]


def mixup(i):
    """The i-th mix-up as two species cards plus their comparison, or None if a name is not found."""
    found = [resolve([n]) for n in MIXUPS[i % len(MIXUPS)]]
    if not all(found):
        return None
    a, b = found[0][0], found[1][0]
    # How often iNaturalist observers confused them, if it is on record.
    looks = {l["id"]: l["count"] for l in (profile(a["id"]) or {}).get("lookalikes", [])}
    return {"a": a, "b": b, "confused": looks.get(b["id"]), **pair(a["id"], b["id"])}


def photos(inat_id):
    """Openly licensed photos from confirmed observations, most voted first."""
    url = (f"{INAT}/observations?taxon_id={inat_id}&quality_grade=research&photos=true&order_by=votes"
           "&photo_license=cc0,cc-by,cc-by-nc,cc-by-sa,cc-by-nc-sa&per_page=30")
    return cached("photos", inat_id, lambda: [
        {"url": o["photos"][0]["url"].replace("/square.", "/medium."), "attribution": o["photos"][0]["attribution"],
         "observation": o["id"]} for o in get(url)["results"] if o["photos"]])
