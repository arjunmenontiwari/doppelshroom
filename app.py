"""Web app. The five pairs are served from precomputed files; any other species is looked up live."""
import csv
import itertools
import json
import urllib.error
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import lookup

ROOT = Path(__file__).parent
RANKS = ("family", "order", "class", "phylum")  # most specific first
PAGES = {"/": "index.html", "/tree": "tree.html", "/distances": "distances.html", "/map": "map.html",
         "/method": "method.html", "/sources": "sources.html", "/search": "search.html",
         "/species/{inat_id}": "species.html"}


def read_json(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def load_species():
    taxonomy = read_json("taxonomy.json")
    info = read_json("species_info.json")
    occurrences = read_json("occurrences.json")
    accessions = dict(line[1:].split()[:2]
                      for line in (ROOT / "mushrooms.fasta").read_text().splitlines()
                      if line.startswith(">"))
    with open(ROOT / "species.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    return [{
        "id": (sid := r["species"].replace(" ", "_")),
        "name": r["species"],
        "pair": int(r["pair"]),
        "status": r["status"],
        "source": r["source"],
        "accession": accessions.get(sid),
        "taxonomy": taxonomy.get(r["species"]),
        "gbif": occurrences.get(r["species"]),
        **(info.get(r["species"]) or {}),
    } for r in rows]


def load_comparisons(species):
    dist = read_json("distances.json")
    index = {name: i for i, name in enumerate(dist["names"])}
    out = []
    for a, b in itertools.combinations(species, 2):
        ta, tb = a["taxonomy"] or {}, b["taxonomy"] or {}
        # The most specific rank both species share, e.g. "order" for two Agaricales.
        rank = next((r for r in RANKS if ta.get(r) and ta.get(r) == tb.get(r)), None)
        out.append({
            "a": a["id"], "b": b["id"],
            "distance": dist["matrix"][index[a["id"]]][index[b["id"]]],
            "shared_rank": rank,
            "shared_taxon": ta.get(rank) if rank else None,
            "pair": a["pair"] if a["pair"] == b["pair"] else None,
        })
    return out


SPECIES = load_species()
DATA = {
    "species": SPECIES,
    "comparisons": load_comparisons(SPECIES),
    "tree": read_json("tree.json"),
    "alignments": read_json("alignments.json"),
}

app = FastAPI(title="Doppelshroom")
templates = Jinja2Templates(directory=ROOT / "templates")


@app.exception_handler(urllib.error.URLError)
def source_down(request, error):
    return JSONResponse({"detail": "A data source did not answer. Try again in a moment."}, status_code=502)


def found(value):
    if value is None:
        raise HTTPException(status_code=404, detail="not a mushroom species")
    return value


# Live lookups for any species (see lookup.py). These must come before /api/{name}.
@app.get("/api/find")
def find(q: str = Query(min_length=2, max_length=60)):
    return lookup.search(q)


@app.get("/api/places")
def places(q: str = Query(min_length=2, max_length=60)):
    return lookup.places(q)


@app.get("/api/place/{place_id}")
def place(place_id: int, month: int | None = Query(None, ge=1, le=12)):
    return lookup.in_place(place_id, month)


@app.get("/api/profile/{inat_id}")
def profile(inat_id: int):
    return found(lookup.profile(inat_id))


@app.get("/api/dna/{inat_id}")
def dna(inat_id: int):
    return found(lookup.dna(inat_id))


@app.get("/api/occurrences")
def occurrences(name: str = Query(pattern=r"^[A-Za-z][A-Za-z .-]{2,60}$")):
    return found(lookup.gbif(name))


@app.get("/api/{name}")
def api(name: str):
    if name not in DATA:
        raise HTTPException(status_code=404, detail="unknown dataset")
    return DATA[name]


def add_page(path, template):
    @app.get(path, include_in_schema=False)
    def page(request: Request):
        return templates.TemplateResponse(request, template)


for path, template in PAGES.items():
    add_page(path, template)

app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
