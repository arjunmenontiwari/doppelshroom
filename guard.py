"""Protection for a small public server, as one ASGI middleware:

- per-visitor rate limits, stricter for routes that cost money (AI) or reach slow outside databases;
- a cap on how many slow requests run at once, so a burst cannot tie up every worker thread;
- a cap on request body size, enforced while the body arrives, before anything reads it whole;
- security headers on every response, including a Content Security Policy.

This only blunts abuse from a handful of addresses. A real flood (DDoS) has to be absorbed in front of the
server, by the host or a CDN such as Cloudflare.
"""
import asyncio
import base64
import hashlib
import re
import time
from pathlib import Path

# Requests per second allowed per visitor, and how many can come at once (the bucket size).
LIMITS = {
    "ai": (5 / 60, 6),      # describe, photo lens: each one can spend AI quota
    "dna": (20 / 60, 10),   # DNA finder: aligns against many barcodes
    "heavy": (2.0, 60),     # live lookups; a species page makes about ten of these
    "api": (4.0, 80),
    "page": (3.0, 60),
}
MAX_SLOW = 24               # slow requests running at once, across all visitors (the thread pool holds 40)
WAIT_FOR_SLOT = 8           # seconds a slow request may wait for a free slot before being turned away
MAX_BODY = {"/api/lens": 6_000_000}  # bytes; every other route gets DEFAULT_BODY
DEFAULT_BODY = 64_000
SLOW = ("ai", "dna", "heavy")


def tier(path):
    if path.startswith("/static/"):
        return None  # files from disk: cheap, and cached by browsers
    if path in ("/api/describe", "/api/lens"):
        return "ai"
    if path in ("/api/identify", "/api/example-sequence"):
        return "dna"
    if path.startswith(("/api/profile/", "/api/dna/", "/api/pair", "/api/family/", "/api/season/", "/api/place/",
                        "/api/near", "/api/occurrences", "/api/quiz", "/api/spotlight", "/api/facts/", "/api/prep/",
                        "/api/find", "/api/places", "/species/")):
        return "heavy"
    return "api" if path.startswith("/api/") else "page"


def csp(template):
    """A Content Security Policy that allows the one inline script in base.html by its hash, and nothing else inline."""
    scripts = re.findall(r"<script>(.*?)</script>", Path(template).read_text(encoding="utf-8"), re.S)
    hashes = " ".join(f"'sha256-{base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()}'" for s in scripts)
    return "; ".join([
        "default-src 'self'",
        f"script-src 'self' {hashes}",
        "style-src 'self' 'unsafe-inline'",  # inline style attributes set the plates' tilt and the charts' sizes
        "img-src 'self' data: blob: https://inaturalist-open-data.s3.amazonaws.com https://static.inaturalist.org "
        "https://tile.gbif.org https://api.gbif.org",
        "connect-src 'self'",
        "font-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'self' https://huggingface.co",  # the Hugging Face Space page shows the site in a frame
    ])


class Guard:
    def __init__(self, app, template):
        self.app = app
        self.buckets = {}  # (address, tier) -> [tokens, last time]
        self.pruned = time.monotonic()
        self.slow = asyncio.Semaphore(MAX_SLOW)
        self.headers = [
            (b"content-security-policy", csp(template).encode()),
            (b"x-content-type-options", b"nosniff"),
            (b"referrer-policy", b"strict-origin-when-cross-origin"),
            (b"permissions-policy", b"camera=(self), geolocation=(self), microphone=()"),
            (b"cross-origin-opener-policy", b"same-origin"),
        ]

    def allow(self, who, kind):
        """Token bucket: each visitor's bucket refills at the tier's rate up to its size; a request takes one token."""
        rate, size = LIMITS[kind]
        now = time.monotonic()
        tokens, last = self.buckets.get((who, kind), (size, now))
        tokens = min(size, tokens + (now - last) * rate)
        if tokens < 1:
            self.buckets[(who, kind)] = (tokens, now)
            return False
        self.buckets[(who, kind)] = (tokens - 1, now)
        if now - self.pruned > 60:  # forget visitors whose buckets have refilled, so memory stays small
            self.buckets = {k: v for k, v in self.buckets.items() if now - v[1] < 600}
            self.pruned = now
        return True

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        # Behind a proxy, run uvicorn with --proxy-headers so this is the visitor's address, not the proxy's.
        who = (scope.get("client") or ("?",))[0]
        kind = tier(path)

        async def send_secured(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + self.headers
                if path.startswith("/static/"):
                    # Asset links carry ?v=<last change>, so a versioned file never changes and can be kept for a year.
                    age = b"public, max-age=31536000, immutable" if b"v=" in scope.get("query_string", b"") else b"public, max-age=86400"
                    message["headers"].append((b"cache-control", age))
            await send(message)

        if kind and not self.allow(who, kind):
            return await reply(send_secured, 429, b'{"detail":"Too many requests. Wait a moment and try again."}', retry=True)

        limit = MAX_BODY.get(path, DEFAULT_BODY)
        length = dict(scope["headers"]).get(b"content-length")
        if length and (not length.isdigit() or int(length) > limit):
            return await reply(send_secured, 413, b'{"detail":"That request is too large."}')
        if scope["method"] in ("POST", "PUT", "PATCH"):
            # Read the body here, stopping as soon as it passes the limit, then hand it to the app in one piece.
            chunks, received, more = [], 0, True
            while more:
                message = await receive()
                if message["type"] != "http.request":
                    return  # the visitor went away
                chunks.append(message.get("body", b""))
                received += len(chunks[-1])
                if received > limit:
                    return await reply(send_secured, 413, b'{"detail":"That request is too large."}')
                more = message.get("more_body", False)
            body, given = b"".join(chunks), False

            async def receive_buffered():
                nonlocal given
                if not given:
                    given = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()
        else:
            receive_buffered = receive

        if kind in SLOW:
            try:
                await asyncio.wait_for(self.slow.acquire(), WAIT_FOR_SLOT)
            except asyncio.TimeoutError:
                return await reply(send_secured, 503, b'{"detail":"The site is busy. Try again in a moment."}', retry=True)
            try:
                return await self.app(scope, receive_buffered, send_secured)
            finally:
                self.slow.release()
        return await self.app(scope, receive_buffered, send_secured)


async def reply(send, status, body, retry=False):
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    if retry:
        headers.append((b"retry-after", b"10"))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
