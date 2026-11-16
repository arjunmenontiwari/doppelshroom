"""Web app. Serves precomputed data; nothing here calls NCBI."""
import csv
import itertools
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).parent
RANKS = ("family", "order", "class", "phylum")  # most specific first


def read_json(name):
    return json.loads((ROOT / name).read_text())


def load_species():
    taxonomy = read_json("taxonomy.json")
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
COMPARISONS = load_comparisons(SPECIES)
TREE = read_json("tree.json")

app = FastAPI(title="Mushroom lookalike explorer")


@app.get("/api/species")
def species():
    return SPECIES


@app.get("/api/comparisons")
def comparisons():
    return COMPARISONS


@app.get("/api/tree")
def tree():
    return TREE


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
