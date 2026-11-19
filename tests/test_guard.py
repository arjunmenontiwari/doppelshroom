"""Abuse protection: only real photos reach the AI, floods get cut off, and oversized requests are refused."""
import base64
import io
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

import app
import guard
import lookup


def b64(data):
    return base64.b64encode(data).decode()


def picture(fmt="PNG", size=(40, 30)):
    out = io.BytesIO()
    Image.new("RGB", size, (200, 120, 40)).save(out, fmt)
    return out.getvalue()


def test_real_photos_are_accepted_and_redrawn_as_jpeg():
    for fmt in ("PNG", "JPEG", "WEBP"):
        clean = app.clean_photo(b64(picture(fmt)))
        assert clean and Image.open(io.BytesIO(base64.b64decode(clean))).format == "JPEG"


def test_anything_that_is_not_a_photo_is_refused():
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    fakes = [
        b"%PDF-1.7 a document",
        b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>",
        b"<html><script>alert(1)</script></html>",
        b"MZ\x90\x00 a windows program",
        b"\x89PNG\r\n\x1a\n but then garbage",  # a real PNG's first bytes, nothing after
        gif.getvalue(),                        # a real image, but not an allowed kind
    ]
    for data in fakes:
        assert app.clean_photo(b64(data)) is None, data[:12]
    assert app.clean_photo("this is not base64 !!!") is None


def test_lens_route_refuses_a_non_photo_even_if_it_claims_to_be_jpeg(monkeypatch):
    monkeypatch.setattr(lookup, "lens", lambda *a: (_ for _ in ()).throw(AssertionError("must not reach the AI")))
    r = TestClient(app.app).post("/api/lens", json={"image": b64(b"%PDF-1.7 not a photo"), "mime": "image/jpeg"})
    assert r.status_code == 422


def fresh_client():
    """A guard of its own around a tiny app, so these tests never share rate limits with the others."""
    tiny = FastAPI()
    tiny.get("/api/find")(lambda: {"ok": True})
    tiny.post("/api/identify")(lambda: {"ok": True})
    return TestClient(guard.Guard(tiny, template=app.ROOT / "templates" / "base.html"))


def test_a_flood_of_calls_is_cut_off():
    client = fresh_client()
    start = time.monotonic()
    codes = [client.get("/api/find").status_code for _ in range(1_000)]
    elapsed = time.monotonic() - start
    allowed = codes.count(200)
    rate, size = guard.LIMITS["heavy"]
    assert allowed <= size + rate * elapsed + 1  # the burst, then only the steady refill rate
    assert allowed < 300
    assert codes.count(429) == len(codes) - allowed


def test_oversized_bodies_are_refused():
    client = fresh_client()
    assert client.post("/api/identify", content=b"A" * 100_000, headers={"content-type": "application/json"}).status_code == 413


def test_security_headers_are_sent():
    r = fresh_client().get("/api/find")
    assert "frame-ancestors 'self' https://huggingface.co" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
