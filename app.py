"""Web app. The five pairs are served from precomputed files; any other species is looked up live."""
import base64
import binascii
import csv
import datetime
import itertools
import json
import random
import urllib.error
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

import gemini
import lookup

ROOT = Path(__file__).parent
RANKS = ("family", "order", "class", "phylum")  # most specific first
PAGES = {"/": "index.html", "/lens": "lens.html", "/compare": "compare.html", "/quiz": "quiz.html",
         "/glossary": "glossary.html",
         "/method": "method.html", "/sources": "sources.html",
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
    "alignments": read_json("alignments.json"),
}

app = FastAPI(title="Doppelshroom")
templates = Jinja2Templates(directory=ROOT / "templates")


def asset(name):
    # The file's last-change time goes in the link, so a browser fetches it again after every edit
    # instead of reusing an old copy.
    return f"/static/{name}?v={int((ROOT / 'static' / name).stat().st_mtime)}"


templates.env.globals["asset"] = asset


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


@app.get("/api/pair")
def pair(a: int, b: int):
    return found(lookup.pair(a, b))


@app.get("/api/family/{inat_id}")
def family(inat_id: int):
    return lookup.family(inat_id)  # null when too few lookalikes have a barcode


@app.get("/api/season/{inat_id}")
def season(inat_id: int):
    return lookup.season(inat_id)


@app.get("/api/near")
def near(lat: float = Query(ge=-90, le=90), lng: float = Query(ge=-180, le=180), month: int = Query(ge=1, le=12)):
    # Rounded to about 10 km: precise enough for a 50 km search, and the exact location is never stored.
    return lookup.near(round(lat, 1), round(lng, 1), month)


@app.get("/api/spotlight")
def spotlight():
    day = datetime.date.today().toordinal()
    # A new mix-up every day; if one of its names is not found, move on to the next.
    return next(m for i in range(len(lookup.MIXUPS)) if (m := lookup.mixup(day + i)))


@app.get("/api/quiz")
def quiz():
    m = None
    while not m:
        m = lookup.mixup(random.randrange(len(lookup.MIXUPS)))
    answer = random.choice([m["a"], m["b"]])
    pics = lookup.photos(answer["id"])
    if not pics:
        raise HTTPException(status_code=502, detail="No photo found. Try again.")
    return {**m, "photo": random.choice(pics), "answer": answer["id"]}


@app.exception_handler(gemini.Unavailable)
def ai_down(request, error):
    return JSONResponse({"detail": str(error)}, status_code=503)


# AI helpers: Gemini only suggests names, which are then checked against iNaturalist (see lookup.py).
@app.get("/api/describe")
def describe(q: str = Query(min_length=3, max_length=200)):
    return lookup.describe(q)


class Photo(BaseModel):
    image: str = Field(max_length=4_000_000)  # base64; the page shrinks photos before sending
    mime: Literal["image/jpeg", "image/png", "image/webp"]


@app.post("/api/lens")
def lens(photo: Photo):
    try:
        base64.b64decode(photo.image, validate=True)
    except binascii.Error:
        raise HTTPException(status_code=422, detail="That file is not an image.")
    return lookup.lens(photo.image, photo.mime)


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
