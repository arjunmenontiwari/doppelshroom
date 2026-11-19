import pytest

import gemini
import lookup


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """Tests never touch the network or the real cache: any outside request fails loudly."""
    def no_network(*args, **kwargs):
        raise AssertionError("a test tried to reach the network")
    monkeypatch.setattr(lookup, "get", no_network)
    monkeypatch.setattr(gemini, "ask", no_network)
    monkeypatch.setattr(lookup, "CACHE", tmp_path)
    lookup._refs.update(files=-1, list=[])


def card(id, name, status=None, source="checked"):
    """A species card as the site passes them around."""
    label = status and {"status": status, "from": source}
    return {"id": id, "name": name, "common_name": None, "photo": None, "taxonomy": None, "status": status, "label": label}
