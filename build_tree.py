"""Pairwise-align ITS sequences, build a neighbour-joining tree, colour by edibility."""
import csv
import itertools
import json
import math

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


def align(a, b):
    """Align two sequences; return both rows trimmed to the region they share."""
    # ITS records can be stored on either strand: align both ways, keep the best.
    aln = max(aligner.align(a, b)[0], aligner.align(a, b.reverse_complement())[0],
              key=lambda x: x.score)
    s1, s2 = aln[0], aln[1]
    cols = [i for i in range(len(s1)) if s1[i] != "-" or s2[i] != "-"]
    start = max(min(i for i in cols if s1[i] != "-"), min(i for i in cols if s2[i] != "-"))
    end = min(max(i for i in cols if s1[i] != "-"), max(i for i in cols if s2[i] != "-"))
    return s1[start:end + 1], s2[start:end + 1]


def distance(s1, s2):
    return sum(x != y for x, y in zip(s1, s2)) / len(s1)  # mismatches + gaps


SATURATED = 2.0  # K2P stand-in when two barcodes differ too much for the formula to give a number


def k2p(s1, s2):
    """Kimura 2-parameter distance: estimated substitutions per site, the standard measure in DNA barcoding.
    It counts transitions (A<->G, C<->T, the common kind of mutation) apart from transversions, and corrects
    for sites that changed more than once. Gaps and ambiguous letters are skipped. Returns SATURATED when the
    sequences are too different to estimate, and None when they share no comparable site."""
    sites = transitions = transversions = 0
    for x, y in zip(str(s1).upper(), str(s2).upper()):
        if x not in "ACGT" or y not in "ACGT":
            continue
        sites += 1
        if x != y:
            if (x in "AG") == (y in "AG"):
                transitions += 1
            else:
                transversions += 1
    if not sites:
        return None
    p, q = transitions / sites, transversions / sites
    a, b = 1 - 2 * p - q, 1 - 2 * q
    if a <= 0 or b <= 0:
        return SATURATED
    return min(max(-0.5 * math.log(a) - 0.25 * math.log(b), 0.0), SATURATED)


def sample(s1, s2, width=60):
    # Pick the window whose share of differences is closest to the whole alignment's,
    # so the excerpt shown on the site is representative.
    diffs = [x != y for x, y in zip(s1, s2)]
    overall = sum(diffs) / len(diffs)
    best = min(range(len(diffs) - width + 1),
               key=lambda i: abs(sum(diffs[i:i + width]) / width - overall))
    return {"length": len(diffs), "offset": best,
            "top": s1[best:best + width], "bottom": s2[best:best + width]}


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
        rows = list(csv.DictReader(f))
    status = {r["species"].replace(" ", "_"): r["status"] for r in rows}
    pair = {r["species"].replace(" ", "_"): r["pair"] for r in rows}
    records = list(SeqIO.parse("mushrooms.fasta", "fasta"))
    names = [r.id for r in records]

    # DistanceMatrix wants a lower triangle: row i holds distances to rows 0..i.
    aligned = {(i, j): align(records[i].seq, records[j].seq)
               for i, j in itertools.combinations(range(len(records)), 2)}
    d = {k: distance(*rows) for k, rows in aligned.items()}
    with open("alignments.json", "w") as f:
        json.dump([{"a": names[i], "b": names[j], **sample(*rows)}
                   for (i, j), rows in aligned.items() if pair[names[i]] == pair[names[j]]], f)
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
