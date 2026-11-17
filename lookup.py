"""Live lookups for any species. Answers are saved in cache/, so each question is asked once."""
import csv
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from build_tree import align, distance
from fetch_occurrences import occurrences
from fetch_sequences import fetch_its

ROOT = Path(__file__).parent
CACHE = ROOT / "cache"
INAT = "https://api.inaturalist.org/v1"
MUSHROOMS = "50814,152032"  # iNaturalist ids: Agaricomycetes (most mushrooms), Pezizomycetes (morels, cups)
RANKS = ("genus", "family", "order", "class", "phylum")  # most specific first
MIN_OVERLAP = 300  # two barcodes that share fewer positions than this are not compared
ncbi = threading.Lock()  # NCBI allows 3 requests a second, so only one visitor fetches at a time

with open(ROOT / "species.csv", newline="") as f:
    LABELS = {r["species"]: {"status": r["status"], "source": r["source"]} for r in csv.DictReader(f)}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "mushroom-education-script"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def cached(kind, key, make):
    """Return the saved answer for this question, or work it out and save it."""
    path = CACHE / kind / (re.sub(r"\W+", "_", str(key)) + ".json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    value = make()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return value


def card(taxon, **extra):
    """The fields the site shows for a species. Labels come only from species.csv."""
    photo = taxon.get("default_photo") or {}
    licensed = bool(photo.get("license_code"))  # only show photos with a Creative Commons licence
    ranks = {a["rank"]: a["name"] for a in taxon.get("ancestors", [])}
    return {
        "id": taxon["id"],
        "name": taxon["name"],
        "common_name": taxon.get("preferred_common_name"),
        "status": LABELS.get(taxon["name"], {}).get("status"),
        "source": LABELS.get(taxon["name"], {}).get("source"),
        "photo": {"square": photo["square_url"], "medium": photo["medium_url"],
                  "attribution": photo["attribution"]} if licensed else None,
        "taxonomy": {r: ranks.get(r) for r in RANKS} if ranks else None,
        **extra,
    }


def search(q):
    q = urllib.parse.quote(q)
    found = get(f"{INAT}/taxa/autocomplete?q={q}&taxon_id={MUSHROOMS}&rank=species&per_page=12")
    return [card(t) for t in found["results"]]


def places(q):
    found = get(f"{INAT}/places/autocomplete?q={urllib.parse.quote(q)}&per_page=8")
    return [{"id": p["id"], "name": p["display_name"]} for p in found["results"]]


def in_place(place_id, month=None):
    """Mushroom species recorded in a place, most recorded first."""
    url = (f"{INAT}/observations/species_counts?taxon_id={MUSHROOMS}&place_id={place_id}"
           "&quality_grade=research&per_page=48") + (f"&month={month}" if month else "")
    return cached("place", f"{place_id}-{month or 0}", lambda: [
        card(r["taxon"], count=r["count"]) for r in get(url)["results"] if r["taxon"]["rank"] == "species"])


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
    similar = get(f"{INAT}/identifications/similar_species?taxon_id={inat_id}")["results"]
    counts = {r["taxon"]["id"]: r["count"] for r in similar
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
            "lookalikes": lookalikes}


def profile(inat_id):
    return cached("profile", inat_id, lambda: build_profile(inat_id))


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
    from Bio.Seq import Seq
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
