"""Download one ITS barcode sequence per species from NCBI into mushrooms.fasta."""
import csv
import os
import time

from Bio import Entrez, SeqIO

Entrez.email = os.environ.get("NCBI_EMAIL")  # NCBI asks for a contact email
REFSEQ_ITS = "PRJNA177353[BioProject]"       # NCBI's curated fungal ITS RefSeq set


def search(query, n=5):
    with Entrez.esearch(db="nucleotide", term=query, retmax=n) as h:
        return Entrez.read(h)["IdList"]


def fetch_its(species):
    # Prefer curated RefSeq ITS; fall back to any ITS record of sensible length.
    base = f'"{species}"[Organism]'
    ids = search(f"{base} AND {REFSEQ_ITS}") or search(
        f'{base} AND (ITS1[All Fields] OR "internal transcribed spacer"[All Fields]) AND 450:1000[SLEN]'
    )
    if not ids:
        return None
    with Entrez.efetch(db="nucleotide", id=ids[0], rettype="fasta", retmode="text") as h:
        return SeqIO.read(h, "fasta")


def fetch_its_many(species, n=6):
    """Up to n ITS records of one species from different submissions, to see how much the barcode varies within it."""
    ids = search(f'"{species}"[Organism] AND (ITS1[All Fields] OR "internal transcribed spacer"[All Fields]) AND 450:1000[SLEN]', n)
    if not ids:
        return []
    with Entrez.efetch(db="nucleotide", id=",".join(ids), rettype="fasta", retmode="text") as h:
        return list(SeqIO.parse(h, "fasta"))


def main():
    with open("species.csv", newline="") as f:
        species = [row["species"] for row in csv.DictReader(f)]

    records = []
    for name in species:
        rec = fetch_its(name)
        if rec is None:
            print(f"  !! no ITS found for {name}")
            continue
        print(f"  {name:28} {rec.id:14} {len(rec.seq)} bp  {rec.description[:60]}")
        rec.description = rec.id            # keep accession for traceability
        rec.id = name.replace(" ", "_")     # tree labels use species name
        records.append(rec)
        time.sleep(0.4)                     # NCBI limit: 3 requests/s without API key

    SeqIO.write(records, "mushrooms.fasta", "fasta")
    print(f"Wrote {len(records)} sequences to mushrooms.fasta")


if __name__ == "__main__":
    main()
