"""Web app. The five pairs are served from precomputed files; any other species is looked up live."""
import base64
import binascii
import csv
import datetime
import io
import itertools
import json
import random
import urllib.error
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path as PathParam, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from PIL import Image
from pydantic import BaseModel, Field

import gemini
import guard
import lookup

ROOT = Path(__file__).parent
RANKS = ("family", "order", "class", "phylum")  # most specific first
PAGES = {"/": "index.html", "/lens": "lens.html", "/compare": "compare.html", "/quiz": "quiz.html",
         "/glossary": "glossary.html",
         "/method": "method.html", "/sources": "sources.html", "/privacy": "privacy.html", "/about": "about.html", "/analysis": "analysis.html"}


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

app = FastAPI(title="Doppelshroom", docs_url=None, redoc_url=None, openapi_url=None)  # no public list of every route
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(guard.Guard, template=ROOT / "templates" / "base.html")  # added last, so it runs first
Id = Annotated[int, PathParam(ge=1, le=99_999_999)]  # iNaturalist ids; anything else never reaches the outside databases
templates = Jinja2Templates(directory=ROOT / "templates")


def asset(name):
    # The file's last-change time goes in the link, so a browser fetches it again after every edit
    # instead of reusing an old copy.
    return f"/static/{name}?v={int((ROOT / 'static' / name).stat().st_mtime)}"


templates.env.globals["asset"] = asset


@app.exception_handler(StarletteHTTPException)
def not_found(request, error):
    """Unknown pages get a friendly page; the API and static files keep plain JSON errors."""
    path = request.url.path
    if error.status_code == 404 and not path.startswith(("/api/", "/static/")):
        return templates.TemplateResponse(request, "404.html", status_code=404)
    return JSONResponse({"detail": error.detail}, status_code=error.status_code, headers=getattr(error, "headers", None))


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
def place(place_id: Id, month: int | None = Query(None, ge=1, le=12)):
    return lookup.in_place(place_id, month)


@app.get("/api/profile/{inat_id}")
def profile(inat_id: Id):
    return found(lookup.profile(inat_id))


@app.get("/api/dna/{inat_id}")
def dna(inat_id: Id):
    return found(lookup.dna(inat_id))


@app.get("/api/occurrences")
def occurrences(name: str = Query(pattern=r"^[A-Za-z][A-Za-z .-]{2,60}$")):
    return found(lookup.gbif(name))


@app.get("/api/pair")
def pair(a: int = Query(ge=1, le=99_999_999), b: int = Query(ge=1, le=99_999_999)):
    return found(lookup.pair(a, b))


@app.get("/api/family/{inat_id}")
def family(inat_id: Id):
    return lookup.family(inat_id)  # null when too few lookalikes have a barcode


@app.get("/api/season/{inat_id}")
def season(inat_id: Id):
    return lookup.season(inat_id)


@app.get("/api/near")
def near(lat: float = Query(ge=-90, le=90), lng: float = Query(ge=-180, le=180), month: int = Query(ge=1, le=12)):
    # Rounded to about 10 km: precise enough for a 50 km search, and the exact location is never stored.
    return lookup.near(round(lat, 1), round(lng, 1), month)


@app.get("/api/spotlight")
def spotlight():
    day = datetime.date.today().toordinal()
    # A new mix-up every day; if one of its names is not found, move on to the next.
    found = next((m for i in range(len(lookup.MIXUPS)) if (m := lookup.mixup(day + i))), None)
    if not found:
        raise HTTPException(status_code=502, detail="Today's mix-up could not be looked up. Try again later.")
    return found


@app.get("/api/quiz")
def quiz():
    m = None
    for _ in range(5):  # a few tries, never an endless loop if the databases are down
        m = lookup.mixup(random.randrange(len(lookup.MIXUPS)))
        if m:
            break
    if not m:
        raise HTTPException(status_code=502, detail="No quiz question could be looked up. Try again.")
    answer = random.choice([m["a"], m["b"]])
    pics = lookup.photos(answer["id"])
    if not pics:
        raise HTTPException(status_code=502, detail="No photo found. Try again.")
    return {**m, "photo": random.choice(pics), "answer": answer["id"]}


@app.exception_handler(gemini.Unavailable)
def ai_down(request, error):
    return JSONResponse({"detail": str(error)}, status_code=503)


# AI helpers. Suggested names are checked against iNaturalist; facts and cooking steps are shown as AI-written.
@app.get("/api/describe")
def describe(q: str = Query(min_length=3, max_length=200)):
    return lookup.describe(q)


@app.get("/api/facts/{inat_id}")
def facts(inat_id: Id):
    return found(lookup.facts(inat_id))


@app.get("/api/prep/{inat_id}")
def prep(inat_id: Id):
    return found(lookup.prep(inat_id))  # 404 unless the species is labelled edible


class Photo(BaseModel):
    image: str = Field(max_length=4_000_000)  # base64; the page shrinks photos before sending
    mime: Literal["image/jpeg", "image/png", "image/webp"]


def clean_photo(data):
    """The photo's actual bytes must decode as a JPEG, PNG or WebP picture, whatever the browser claimed it was.
    It is then redrawn as a fresh JPEG, so only pixels go on to the AI: no hidden data, no location, no other file."""
    try:
        raw = base64.b64decode(data, validate=True)
        with Image.open(io.BytesIO(raw)) as im:
            if im.format not in ("JPEG", "PNG", "WEBP"):
                return None
            if im.width * im.height > 40_000_000:  # a tiny file can claim to be enormous (a "decompression bomb")
                return None
            im.load()
            im = im.convert("RGB")
            im.thumbnail((1600, 1600))
            out = io.BytesIO()
            im.save(out, "JPEG", quality=88)
    except (binascii.Error, ValueError, OSError, Image.DecompressionBombError):
        return None
    return base64.b64encode(out.getvalue()).decode()


@app.post("/api/lens")
def lens(photo: Photo):
    clean = clean_photo(photo.image)
    if not clean:
        raise HTTPException(status_code=422, detail="That file is not a photo. Use a JPEG, PNG or WebP picture.")
    return lookup.lens(clean, "image/jpeg")


class Sequence(BaseModel):
    sequence: str = Field(max_length=20_000)


@app.post("/api/identify")
def identify(body: Sequence):
    seq = lookup.clean_sequence(body.sequence)
    if not seq:
        raise HTTPException(status_code=422, detail="Paste a DNA sequence of 100 to 5000 letters, using only A, C, G, T and N.")
    return lookup.identify(seq)


@app.get("/api/example-sequence")
def example_sequence():
    return lookup.example_sequence()


_analysis = {"mtime": None, "data": None}


@app.get("/api/analysis")
def analysis():
    path = ROOT / "analysis.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="The analysis has not been run yet (python analyze.py).")
    if path.stat().st_mtime != _analysis["mtime"]:  # read once, and again only after analyze.py rewrites it
        _analysis.update(mtime=path.stat().st_mtime, data=json.loads(path.read_text(encoding="utf-8")))
    return _analysis["data"]


@app.get("/api/{name}")
def api(name: str):
    if name not in DATA:
        raise HTTPException(status_code=404, detail="unknown dataset")
    return DATA[name]


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(ROOT / "static" / "favicon.ico", headers={"Cache-Control": "public, max-age=604800"})


@app.get("/species/{inat_id}", include_in_schema=False)
def species_page(request: Request, inat_id: str):
    if not inat_id.isdigit() or len(inat_id) > 8:
        raise HTTPException(status_code=404)
    try:
        t = lookup.taxon(int(inat_id))
    except urllib.error.URLError:
        t = False  # iNaturalist did not answer: show the page anyway, with a plain link preview
    if t is None:
        raise HTTPException(status_code=404)  # not a mushroom species
    og = {}
    if t:
        name = " ".join(w[:1].upper() + w[1:] for w in (t["common_name"] or t["name"]).split(" "))
        og = {"title": f"{name} · Doppelshroom",
              "description": f"{name} ({t['name']}) and the mushrooms it is mistaken for, compared by DNA. Educational, not an identification tool."}
    return templates.TemplateResponse(request, "species.html", {"og": og})


def add_page(path, template):
    @app.get(path, include_in_schema=False)
    def page(request: Request):
        return templates.TemplateResponse(request, template)


for path, template in PAGES.items():
    add_page(path, template)

app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
