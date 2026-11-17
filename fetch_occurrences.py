"""Look up each species in GBIF: its taxon key and how many records each country has."""
import csv
import json
import time
import urllib.parse
import urllib.request

API = "https://api.gbif.org/v1"
MIN_RECORDS = 10  # a handful of records in a country is often a misidentification


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "mushroom-education-script"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def occurrences(species):
    match = get(f"{API}/species/match?kingdom=Fungi&rank=SPECIES&name={urllib.parse.quote(species)}")
    if match.get("matchType") != "EXACT":
        return None
    # If GBIF files this name as a synonym, use the accepted name's key instead.
    key = match.get("acceptedUsageKey", match["usageKey"])
    # limit=0 returns no records, only the total and the per-country counts.
    found = get(f"{API}/occurrence/search?taxonKey={key}&hasCoordinate=true"
                "&limit=0&facet=country&facetLimit=300")
    return {
        "gbif_key": key,
        "records": found["count"],
        "countries": {c["name"]: c["count"] for c in found["facets"][0]["counts"]
                      if c["count"] >= MIN_RECORDS},
    }


def main():
    with open("species.csv", newline="") as f:
        species = [row["species"] for row in csv.DictReader(f)]
    out = {}
    for name in species:
        out[name] = occurrences(name)
        got = out[name] or {}
        print(f"  {name:28} key {got.get('gbif_key')!s:9} {got.get('records')!s:>7} records"
              f"  {len(got.get('countries', {}))} countries")
        time.sleep(0.5)
    with open("occurrences.json", "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
