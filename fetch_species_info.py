"""Get a common name and an openly licensed photo per species from iNaturalist."""
import csv
import json
import time
import urllib.parse
import urllib.request

API = "https://api.inaturalist.org/v1/taxa"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "mushroom-education-script"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def info(species):
    hits = get(f"{API}?q={urllib.parse.quote(species)}&rank=species")["results"]
    match = next((t for t in hits if t["name"] == species), None)
    if match is None:
        return None
    taxon = get(f"{API}/{match['id']}")["results"][0]
    # Only use photos whose owner chose a Creative Commons licence.
    photos = [p["photo"] for p in taxon.get("taxon_photos", [])]
    photo = next((p for p in photos if p.get("license_code")), None)
    return {
        "inat_id": taxon["id"],
        "common_name": taxon.get("preferred_common_name"),
        "wikipedia_url": taxon.get("wikipedia_url"),
        "photo": photo and {
            "square": photo["square_url"],
            "medium": photo["medium_url"],
            "attribution": photo["attribution"],
            "license": photo["license_code"],
        },
    }


def main():
    with open("species.csv", newline="") as f:
        species = [row["species"] for row in csv.DictReader(f)]
    out = {}
    for name in species:
        out[name] = info(name)
        got = out[name] or {}
        print(f"  {name:28} {got.get('common_name')!s:26} photo: {(got.get('photo') or {}).get('license')}")
        time.sleep(1)  # iNaturalist asks for about one request per second
    with open("species_info.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
