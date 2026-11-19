"""Are mushroom lookalikes close relatives? Measure it across many species and write analysis.json.

For each focal species (the most-observed mushrooms on iNaturalist, plus the field-guide mix-ups):
- its lookalikes: the species observers most often confused with it, with how often;
- the same number of random other species from the data, as a baseline;
- the Kimura 2-parameter DNA distance from the focal species to each of them.

Two permutation tests. Pairs that share a focal species are not independent, so labels are only ever
shuffled within one focal species, never across them (the idea behind a Mantel test):
1. Are lookalikes closer relatives than random species? (mean rank of distances, lookalike vs random)
2. Among lookalikes, does more confusion go with closer DNA? (Spearman correlation)

Plus the barcode gap: for each focal species, how much its own barcodes vary, against the distance to its
nearest lookalike. A positive gap means the barcode can tell the species from all its lookalikes.

Run: .venv/Scripts/python.exe analyze.py   (slow the first time: hundreds of downloads, all cached after)
"""
import datetime
import itertools
import json
import math
import random
import time
import urllib.error
from pathlib import Path

import numpy as np
from Bio.Seq import Seq

import lookup
from build_tree import SATURATED, align, distance, k2p

ROOT = Path(__file__).parent
FOCAL = 60          # most-observed species to study
PERMUTATIONS = 9999
rng = random.Random(1)


def focal_species():
    url = (f"{lookup.INAT}/observations/species_counts?taxon_id={lookup.MUSHROOMS}"
           f"&quality_grade=research&per_page={FOCAL}")
    top = [r["taxon"] for r in lookup.cached("top", FOCAL, lambda: lookup.get(url)["results"]) if r["taxon"]["rank"] == "species"]
    mixups = [c for pair in lookup.MIXUPS for c in lookup.resolve(list(pair))]
    seen, out = set(), []
    for t in top + mixups:
        if t["id"] not in seen:
            seen.add(t["id"]); out.append({"id": t["id"], "name": t["name"]})
    return out


def barcode(name):
    """One barcode, politely: NCBI allows 3 requests a second, and only uncached names cost a request."""
    fresh = not lookup.cache_path("its", name).exists()
    try:
        b = lookup.barcode(name)
    except (urllib.error.URLError, RuntimeError, OSError) as e:
        print(f"   ! {name}: {e}")
        return None
    if fresh:
        time.sleep(.4)
    return b


def compare(a, b):
    """K2P and share of differing positions between two barcodes, or None if they overlap too little."""
    rows = align(Seq(a["seq"]), Seq(b["seq"]))
    if len(rows[0]) < lookup.MIN_OVERLAP:
        return None
    return {"k2p": k2p(*rows), "p": distance(*rows), "length": len(rows[0])}


def ranks(values):
    """Average ranks (1 = smallest), ties sharing their mean rank."""
    order = np.argsort(values, kind="mergesort")
    r = np.empty(len(values))
    r[order] = np.arange(1, len(values) + 1)
    v = np.asarray(values)[order]
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[j + 1] == v[i]:
            j += 1
        r[order[i:j + 1]] = (i + j + 2) / 2
        i = j + 1
    return r


def spearman(x, y):
    rx, ry = ranks(x), ranks(y)
    return float(np.corrcoef(rx, ry)[0, 1])


def closer_test(pairs, n=PERMUTATIONS):
    """Test 1. Statistic: mean distance rank of random pairs minus that of lookalike pairs (positive = lookalikes
    closer). Shuffled within each focal species. One-sided p-value."""
    r = ranks([p["k2p"] for p in pairs])
    groups = {}
    for i, p in enumerate(pairs):
        groups.setdefault(p["focal"], []).append(i)
    labels = np.array([p["kind"] == "lookalike" for p in pairs])
    stat = lambda lab: r[~lab].mean() - r[lab].mean()
    observed = stat(labels)
    hits = 0
    for _ in range(n):
        lab = labels.copy()
        for idx in groups.values():
            lab[idx] = np.random.permutation(lab[idx])
        hits += stat(lab) >= observed
    return {"statistic": float(observed), "p": (hits + 1) / (n + 1)}


def confusion_test(looks, n=PERMUTATIONS):
    """Test 2. Spearman correlation between times confused and distance among lookalikes. Counts are shuffled
    within each focal species. Two-sided p-value."""
    rd = ranks([p["k2p"] for p in looks])
    rc = ranks([p["count"] for p in looks])  # shuffling counts within a group just shuffles their ranks there
    groups = {}
    for i, p in enumerate(looks):
        groups.setdefault(p["focal"], []).append(i)
    rho = lambda c: float(np.corrcoef(c, rd)[0, 1])
    observed = rho(rc)
    hits = 0
    for _ in range(n):
        c = rc.copy()
        for idx in groups.values():
            c[idx] = np.random.permutation(c[idx])
        hits += abs(rho(c)) >= abs(observed) - 1e-12
    return {"rho": observed, "p": (hits + 1) / (n + 1)}


def main():
    np.random.seed(1)
    focal = focal_species()
    print(f"{len(focal)} focal species")
    pairs, gaps, pool = [], [], {}

    profiles = {}
    for f in focal:
        try:
            profiles[f["id"]] = lookup.profile(f["id"])
        except urllib.error.URLError as e:
            print(f"   ! profile {f['name']}: {e}")
        time.sleep(.3)
    for p in profiles.values():
        if p:
            pool[p["name"]] = p
            for l in p["lookalikes"]:
                pool.setdefault(l["name"], l)
    print(f"{len(pool)} species in the pool; fetching barcodes")
    codes = {}
    for i, name in enumerate(sorted(pool)):
        codes[name] = barcode(name)
        if i % 50 == 0:
            print(f"   {i}/{len(pool)}")
    with_code = [n for n in pool if codes.get(n)]

    for f in focal:
        p = profiles.get(f["id"])
        if not p or not codes.get(p["name"]):
            continue
        mine = codes[p["name"]]
        looks = [l for l in p["lookalikes"] if codes.get(l["name"])]
        names = {l["name"] for l in p["lookalikes"]} | {p["name"]}
        nearest = None
        for l in looks:
            c = compare(mine, codes[l["name"]])
            if not c:
                continue
            pairs.append({"focal": p["name"], "focal_id": p["id"], "other": l["name"], "other_id": l["id"],
                          "common": l["common_name"], "focal_common": p["common_name"], "kind": "lookalike",
                          "count": l["count"], "rank": l["shared_rank"], "status": l["status"], **c})
            if nearest is None or c["k2p"] < nearest["k2p"]:
                nearest = {"name": l["name"], "k2p": c["k2p"]}
        # Baseline: as many random species as this focal species has lookalikes, never one of them.
        others = [n for n in with_code if n not in names]
        for name in rng.sample(others, min(len(looks), len(others))):
            c = compare(mine, codes[name])
            if c:
                rank = lookup.shared(p["taxonomy"] or {}, pool[name].get("taxonomy") or {})[0]
                pairs.append({"focal": p["name"], "other": name, "kind": "random", "rank": rank, **c})

        # Barcode gap: the most this species' own barcodes differ, against its nearest lookalike.
        try:
            many = [b for b in lookup.barcodes(p["name"]) if len(b["seq"]) >= lookup.MIN_OVERLAP]
        except (urllib.error.URLError, RuntimeError, OSError) as e:
            print(f"   ! barcodes {p['name']}: {e}")
            many = []
        within = [c["k2p"] for a, b in itertools.combinations(many, 2) if (c := compare(a, b))]
        if within and nearest:
            gaps.append({"name": p["name"], "id": p["id"], "common": p["common_name"], "barcodes": len(many),
                         "within": max(within), "nearest": nearest["name"], "between": nearest["k2p"],
                         "gap": nearest["k2p"] - max(within)})
        print(f"   {p['name']}: {len(looks)} lookalikes, {len(many)} own barcodes")

    looks = [p for p in pairs if p["kind"] == "lookalike"]
    rand = [p for p in pairs if p["kind"] == "random"]
    near = lambda ps, ranks_: sum(p.get("rank") in ranks_ for p in ps) / len(ps)
    out = {
        "generated": datetime.date.today().isoformat(),
        "focal": len({p["focal"] for p in looks}),
        "saturated": SATURATED,
        "lookalike": {"pairs": len(looks), "median": float(np.median([p["k2p"] for p in looks])),
                      "same_family": near(looks, ("genus", "family"))},
        "random": {"pairs": len(rand), "median": float(np.median([p["k2p"] for p in rand])),
                   "same_family": near(rand, ("genus", "family"))},
        "closer": closer_test(pairs),
        "confusion": confusion_test(looks),
        "pairs": looks,
        "random_k2p": [round(p["k2p"], 4) for p in rand],
        "gaps": sorted(gaps, key=lambda g: g["gap"]),
        "permutations": PERMUTATIONS,
    }
    (ROOT / "analysis.json").write_text(json.dumps(out), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("focal", "lookalike", "random", "closer", "confusion")}, indent=1))
    print(f"barcode gaps: {sum(g['gap'] > 0 for g in gaps)} of {len(gaps)} species have one")


if __name__ == "__main__":
    main()
