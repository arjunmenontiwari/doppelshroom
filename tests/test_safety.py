"""The safety rules: cooking steps only for edible labels, and the lens never calls anything edible."""
import pytest

import gemini
import lookup
from conftest import card


@pytest.fixture
def species(monkeypatch):
    """A fake taxon lookup and labels, and a Gemini that records whether it was asked."""
    asked = []
    taxa = {1: card(1, "Edibilis checked"), 2: card(2, "Edibilis wiki"), 3: card(3, "Mortalis deadly"),
            4: card(4, "Cautio wiki"), 5: card(5, "Nullus label")}
    labels = {"Edibilis checked": {"status": "edible", "from": "checked"}, "Edibilis wiki": {"status": "edible", "from": "wikipedia"},
              "Mortalis deadly": {"status": "deadly", "from": "wikipedia"}, "Cautio wiki": {"status": "caution", "from": "wikipedia"},
              "Nullus label": None}
    monkeypatch.setattr(lookup, "taxon", lambda i: taxa.get(i))
    monkeypatch.setattr(lookup, "labels", lambda names: {n: labels[n] for n in names})
    monkeypatch.setattr(gemini, "prep", lambda name: asked.append(name) or ["Cook it fully."])
    return asked


@pytest.mark.parametrize("inat_id", [1, 2])
def test_prep_for_edible_labels(species, inat_id):
    assert lookup.prep(inat_id) == ["Cook it fully."]


@pytest.mark.parametrize("inat_id", [3, 4, 5, 999])
def test_no_prep_otherwise_and_ai_never_asked(species, inat_id):
    assert lookup.prep(inat_id) is None
    assert species == []  # Gemini is not even asked to write steps for these


def test_lens_never_says_edible(monkeypatch):
    matches = [card(1, "Edibilis checked", "edible"), card(2, "Mortalis deadly", "deadly")]
    monkeypatch.setattr(gemini, "photo", lambda data, mime: ["Edibilis checked", "Mortalis deadly"])
    monkeypatch.setattr(lookup, "resolve", lambda names: [dict(c) for c in matches])
    monkeypatch.setattr(lookup, "profile", lambda i: {"lookalikes": []})
    out = lookup.lens("data", "image/jpeg")
    assert [m["status"] for m in out["matches"]] == [None, "deadly"]  # the edible label is removed, the warning kept
