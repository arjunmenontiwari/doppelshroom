"""The web app's routes: friendly 404s, API errors as JSON, input checks and the cooking-steps gate."""
from fastapi.testclient import TestClient

import app
import lookup

client = TestClient(app.app)


def test_unknown_page_is_a_friendly_404():
    r = client.get("/no-such-page")
    assert r.status_code == 404 and "Lost in the woods" in r.text


def test_api_errors_stay_json():
    r = client.get("/api/no-such-dataset")
    assert r.status_code == 404 and r.json()["detail"]


def test_identify_rejects_text_that_is_not_dna():
    r = client.post("/api/identify", json={"sequence": "this is not a DNA sequence at all " * 5})
    assert r.status_code == 422


def test_recipes_refused_for_a_poisonous_species(monkeypatch):
    monkeypatch.setattr(lookup, "taxon", lambda i: {"id": i, "name": "Amanita virosa"})
    r = client.get("/api/recipes/58685")
    assert r.status_code == 404  # Amanita virosa is poisonous in species.csv, so no recipes


def test_pages_render():
    for path in ("/", "/about", "/analysis", "/privacy", "/glossary"):
        assert client.get(path).status_code == 200, path
