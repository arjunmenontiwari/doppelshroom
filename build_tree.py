"""Pairwise-align ITS sequences, build a neighbour-joining tree, colour by edibility."""
import csv
import itertools
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from Bio import Phylo, SeqIO
from Bio.Align import PairwiseAligner
from Bio.Phylo.TreeConstruction import DistanceMatrix, DistanceTreeConstructor

COLOURS = {"edible": "green", "poisonous": "red", "inedible": "darkorange"}
OUTGROUP = ("Morchella_esculenta", "Gyromitra_esculenta")  # Ascomycota; the rest are Basidiomycota

aligner = PairwiseAligner(mode="global", match_score=1, mismatch_score=-1,
                          open_gap_score=-2, extend_gap_score=-0.5)
aligner.end_gap_score = 0  # don't punish sequences for covering more flanking rRNA


def distance(a, b):
    # ITS records can be stored on either strand: align both ways, keep the best.
    aln = max(aligner.align(a, b)[0], aligner.align(a, b.reverse_complement())[0],
              key=lambda x: x.score)
    s1, s2 = aln[0], aln[1]
    # Only compare the region both sequences cover (trim overhanging ends).
    cols = [i for i in range(len(s1)) if s1[i] != "-" or s2[i] != "-"]
    start = max(min(i for i in cols if s1[i] != "-"), min(i for i in cols if s2[i] != "-"))
    end = min(max(i for i in cols if s1[i] != "-"), max(i for i in cols if s2[i] != "-"))
    pairs = list(zip(s1[start:end + 1], s2[start:end + 1]))
    diffs = sum(x != y for x, y in pairs)  # mismatches + internal gaps
    return diffs / len(pairs)


def root_on_outgroup(tree):
    # Put the root halfway along the branch joining the outgroup to everything else.
    tree.root_with_outgroup(*OUTGROUP)
    out = [c for c in tree.root.clades if c.name in OUTGROUP]
    (rest,) = [c for c in tree.root.clades if c.name not in OUTGROUP]
    rest.branch_length /= 2
    stem = Phylo.BaseTree.Clade(branch_length=rest.branch_length, clades=out)
    tree.root.clades = [stem, rest]


def to_dict(clade):
    return {"name": clade.name, "length": clade.branch_length or 0.0,
            "children": [to_dict(c) for c in clade.clades]}


def main():
    with open("species.csv", newline="") as f:
        status = {r["species"].replace(" ", "_"): r["status"] for r in csv.DictReader(f)}
    records = list(SeqIO.parse("mushrooms.fasta", "fasta"))
    names = [r.id for r in records]

    # DistanceMatrix wants a lower triangle: row i holds distances to rows 0..i.
    d = {}
    for i, j in itertools.combinations(range(len(records)), 2):
        d[i, j] = distance(records[i].seq, records[j].seq)
    matrix = [[d[j, i] for j in range(i)] + [0.0] for i in range(len(records))]
    dm = DistanceMatrix(names, matrix)
    print(dm)

    tree = DistanceTreeConstructor().nj(dm)
    root_on_outgroup(tree)
    tree.ladderize()
    for clade in tree.get_nonterminals():
        clade.name = None  # hide NJ's internal "Inner" labels
    Phylo.write(tree, "mushroom_tree.nwk", "newick")
    with open("tree.json", "w") as f:
        json.dump(to_dict(tree.root), f)
    full = [[0.0 if i == j else d[min(i, j), max(i, j)] for j in range(len(names))]
            for i in range(len(names))]
    with open("distances.json", "w") as f:
        json.dump({"names": names, "matrix": full}, f)

    fig, ax = plt.subplots(figsize=(10, 6))
    Phylo.draw(tree, axes=ax, do_show=False,
               label_func=lambda c: c.name.replace("_", " ") if c.name else "",
               label_colors={n.replace("_", " "): COLOURS[status[n]] for n in names})
    ax.set_title("ITS neighbour-joining tree (green edible, red poisonous, orange inedible)")
    ax.set_xlabel("distance (substitutions per site)")
    ax.set_ylabel("")
    ax.set_yticks([])
    fig.tight_layout()
    fig.savefig("mushroom_tree.png", dpi=150)
    print("Saved mushroom_tree.png, mushroom_tree.nwk, tree.json, distances.json")


if __name__ == "__main__":
    main()
