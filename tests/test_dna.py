"""DNA distances, sequence cleaning and the k-mer species finder."""
import json
import math

import pytest
from Bio.Seq import Seq

import lookup
from build_tree import SATURATED, align, distance, k2p
from conftest import card


def test_k2p_matches_the_formula():
    assert k2p("ACGTACGTAC", "ACGTACGTAC") == 0.0
    # One transition (A->G) in 10 sites: P = 0.1, Q = 0.
    assert k2p("AAAAAAAAAA", "GAAAAAAAAA") == pytest.approx(-0.5 * math.log(0.8))
    # One transversion (A->C) in 10 sites: P = 0, Q = 0.1.
    assert k2p("AAAAAAAAAA", "CAAAAAAAAA") == pytest.approx(-0.5 * math.log(0.9) - 0.25 * math.log(0.8))


def test_k2p_skips_gaps_and_handles_extremes():
    assert k2p("AC-T", "AC-T") == 0.0
    assert k2p("----", "----") is None
    assert k2p("AAAA", "CCCC") == SATURATED  # too different for the formula


def test_align_finds_the_other_strand():
    a = Seq("ATGCGTACGTTAGCCGATCGATCGGCTAAGCTTACG" * 4)
    top, bottom = align(a, a.reverse_complement())
    assert distance(top, bottom) == 0


@pytest.mark.parametrize("text, expected", [
    (">my sample\nacgu\nACGT 12 ACGT\n" + "A" * 100, "ACGTACGTACGT" + "A" * 100),
    ("ACGT" * 10, None),        # too short
    ("HELLO" * 40, None),       # not DNA
])
def test_clean_sequence(text, expected):
    assert lookup.clean_sequence(text) == expected


def test_identify_finds_a_mutated_barcode_on_either_strand(monkeypatch):
    import random
    rng = random.Random(3)
    refs = {name: "".join(rng.choice("ACGT") for _ in range(600)) for name in ("Alpha one", "Beta two", "Gamma three")}
    (lookup.CACHE / "its").mkdir()
    for name, seq in refs.items():
        (lookup.CACHE / "its" / f"{name.replace(' ', '_')}.json").write_text(json.dumps({"accession": name[:3], "seq": seq}))
    monkeypatch.setattr(lookup, "resolve", lambda names: [card(i, n) for i, n in enumerate(names)])
    monkeypatch.setattr(lookup, "profile", lambda i: {"lookalikes": []})

    query = list(refs["Beta two"])
    for i in range(0, 600, 50):  # 2% of letters changed
        query[i] = "A" if query[i] != "A" else "C"
    query = str(Seq("".join(query)).reverse_complement())
    out = lookup.identify(query)
    assert out["matches"][0]["name"] == "Beta two"
    assert out["matches"][0]["identity"] == pytest.approx(0.98, abs=0.01)
