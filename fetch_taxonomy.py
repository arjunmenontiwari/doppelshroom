"""Look up each species' lineage in NCBI Taxonomy and save it to taxonomy.json."""
import csv
import json
import os
import time

from Bio import Entrez

Entrez.email = os.environ.get("NCBI_EMAIL")
RANKS = ("phylum", "class", "order", "family", "genus")


def lineage(species):
    with Entrez.esearch(db="taxonomy", term=f'"{species}"[Scientific Name]') as h:
        ids = Entrez.read(h)["IdList"]
    if not ids:
        return None
    with Entrez.efetch(db="taxonomy", id=ids[0]) as h:
        record = Entrez.read(h)[0]
    ranks = {x["Rank"]: x["ScientificName"] for x in record["LineageEx"]}
    return {"taxid": ids[0], **{r: ranks.get(r) for r in RANKS}}


def main():
    with open("species.csv", newline="") as f:
        species = [row["species"] for row in csv.DictReader(f)]
    out = {}
    for name in species:
        out[name] = lineage(name)
        print(f"  {name:28} {out[name]}")
        time.sleep(0.7)
    with open("taxonomy.json", "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
