"""The safety rules: recipe links only for edible labels, and the lens never calls anything edible."""
import pytest

import gemini
import lookup
from conftest import card


@pytest.fixture
def species(monkeypatch):
    """A fake taxon lookup and labels."""
    taxa = {1: card(1, "Edibilis checked"), 2: card(2, "Edibilis wiki"), 3: card(3, "Mortalis deadly"),
            4: card(4, "Cautio wiki"), 5: card(5, "Nullus label")}
    labels = {"Edibilis checked": {"status": "edible", "from": "checked"}, "Edibilis wiki": {"status": "edible", "from": "wikipedia"},
              "Mortalis deadly": {"status": "deadly", "from": "wikipedia"}, "Cautio wiki": {"status": "caution", "from": "wikipedia"},
              "Nullus label": None}
    monkeypatch.setattr(lookup, "taxon", lambda i: taxa.get(i))
    monkeypatch.setattr(lookup, "labels", lambda names: {n: labels[n] for n in names})


@pytest.mark.parametrize("inat_id", [1, 2])
def test_recipes_for_edible_labels(species, inat_id):
    links = lookup.recipes(inat_id)
    assert len(links) == 3 and all(l["url"].startswith("https://") and "mushroom" in l["url"] for l in links)


@pytest.mark.parametrize("inat_id", [3, 4, 5, 999])
def test_no_recipes_otherwise(species, inat_id):
    assert lookup.recipes(inat_id) is None


def test_lens_never_says_edible(monkeypatch):
    matches = [card(1, "Edibilis checked", "edible"), card(2, "Mortalis deadly", "deadly")]
    monkeypatch.setattr(gemini, "photo", lambda data, mime: ["Edibilis checked", "Mortalis deadly"])
    monkeypatch.setattr(lookup, "resolve", lambda names: [dict(c) for c in matches])
    monkeypatch.setattr(lookup, "profile", lambda i: {"lookalikes": []})
    out = lookup.lens("data", "image/jpeg")
    assert [m["status"] for m in out["matches"]] == [None, "deadly"]  # the edible label is removed, the warning kept
