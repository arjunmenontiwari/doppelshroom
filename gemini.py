"""Gemini turns words or a photo into candidate species names. Nothing else it says reaches the site."""
import json
import os
import urllib.request
from pathlib import Path

API = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
# Free-tier models, tried in order: if one is busy or refuses, the next one is asked.
TEXT_MODELS = ("gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-flash-latest")
IMAGE_MODELS = ("gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-flash-latest")

# The answer must have this shape, so the model cannot add advice or edibility claims.
SCHEMA = {"type": "OBJECT", "required": ["species", "place"], "properties": {
    "species": {"type": "ARRAY", "items": {"type": "STRING"}},
    "place": {"type": "STRING", "nullable": True},
}}

DESCRIBE = (
    "You help people find mushroom species in a database. Read the description and list up to 8 "
    "scientific names (genus and species) of fungi that best fit it, most likely first. Include species "
    "that are often confused with each other when they fit. If the description names a place, return "
    "that place as written, otherwise null. Return names only."
)
LENS = (
    "Look at the photo. If it shows a mushroom or another fungus, list up to 5 scientific names (genus "
    "and species) it could be, most likely first. If it shows no fungus, return an empty list. "
    "Place is always null. Return names only."
)


class Unavailable(Exception):
    pass


def read_key():
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    env = Path(__file__).parent / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        name, _, value = line.partition("=")
        if name.strip() == "GEMINI_API_KEY":
            return value.strip()


KEY = read_key()


def ask(models, instruction, parts):
    if not KEY:
        raise Unavailable("The AI helper is not set up on this server.")
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": instruction}]},
        "contents": [{"parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA},
    }).encode()
    for model in models:
        req = urllib.request.Request(API.format(model), data=body,
                                     headers={"x-goog-api-key": KEY, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                answer = json.loads(json.load(r)["candidates"][0]["content"]["parts"][0]["text"])
            return [n.strip() for n in answer["species"] if isinstance(n, str)], answer.get("place")
        except (OSError, KeyError, IndexError, ValueError):
            continue  # busy, refused or a malformed answer: try the next model
    raise Unavailable("The AI helper is busy. Try again in a minute.")


def describe(text):
    return ask(TEXT_MODELS, DESCRIBE, [{"text": text}])


def photo(data, mime):
    names, _ = ask(IMAGE_MODELS, LENS, [{"inline_data": {"mime_type": mime, "data": data}}])
    return names[:5]
