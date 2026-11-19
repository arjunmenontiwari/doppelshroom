"""Gemini turns words or a photo into candidate species names, and writes short facts and preparation steps."""
import json
import os
import urllib.request
from pathlib import Path

API = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
# Free-tier models, tried in order: if one is busy or refuses, the next one is asked.
TEXT_MODELS = ("gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-flash-latest")
IMAGE_MODELS = ("gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-flash-latest")

# Each answer must have a fixed shape, so the model cannot add anything the site did not ask for.
NAMES = {"type": "OBJECT", "required": ["species", "place"], "properties": {
    "species": {"type": "ARRAY", "items": {"type": "STRING"}},
    "place": {"type": "STRING", "nullable": True},
}}
LIST = {"type": "OBJECT", "required": ["items"], "properties": {"items": {"type": "ARRAY", "items": {"type": "STRING"}}}}

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
FACTS = (
    "Give 5 short facts about the fungus {}: where and when it grows, how to recognise it, and how to tell it "
    "apart from the species it is most often confused with. One plain sentence each. Do not say whether it is "
    "edible or how to cook it."
)
PREP = (
    "{} is an edible mushroom. List the steps to clean and cook it, in order, one plain sentence each, at most 6. "
    "Put any step needed for safety first, such as cooking it fully, and say so if it must never be eaten raw."
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


def ask(models, instruction, parts, schema):
    if not KEY:
        raise Unavailable("The AI helper is not set up on this server.")
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": instruction}]},
        "contents": [{"parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema},
    }).encode()
    for model in models:
        req = urllib.request.Request(API.format(model), data=body,
                                     headers={"x-goog-api-key": KEY, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                answer = json.loads(json.load(r)["candidates"][0]["content"]["parts"][0]["text"])
            if all(isinstance(answer.get(k), list) for k in schema["required"] if k != "place"):
                return answer
        except (OSError, KeyError, IndexError, ValueError, AttributeError):
            continue  # busy, refused or a malformed answer: try the next model
    raise Unavailable("The AI helper is busy. Try again in a minute.")


def strings(items):
    return [n.strip() for n in items if isinstance(n, str) and n.strip()]


def describe(text):
    answer = ask(TEXT_MODELS, DESCRIBE, [{"text": text}], NAMES)
    return strings(answer["species"]), answer.get("place")


def photo(data, mime):
    return strings(ask(IMAGE_MODELS, LENS, [{"inline_data": {"mime_type": mime, "data": data}}], NAMES)["species"])[:5]


def facts(name):
    return strings(ask(TEXT_MODELS, FACTS.format(name), [{"text": name}], LIST)["items"])


def prep(name):
    return strings(ask(TEXT_MODELS, PREP.format(name), [{"text": name}], LIST)["items"])
