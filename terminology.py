"""Conservative term correction conditioned on the original English title."""

import json
from pathlib import Path
import re
import unicodedata

PATH = Path(__file__).resolve().parent / "exercise_glossary.json"
TERMS = json.loads(PATH.read_text(encoding="utf-8-sig"))["terms"]


def matches(title, term):
    normalized = unicodedata.normalize("NFKC", title).casefold()
    phrases = [term["en"], *term.get("aliases", [])]
    for phrase in phrases:
        pattern = r"(?<!\w)" + r"[\s‐‑‒–—-]+".join(
            re.escape(part) for part in re.split(r"[\s‐‑‒–—-]+", phrase.casefold())
        ) + r"(?!\w)"
        if re.search(pattern, normalized):
            return True
    return False


def correct(title, translation):
    matches_in_title = [term for term in TERMS if matches(title, term)]
    replacements = sorted(
        ((variant, term["zh"]) for term in matches_in_title for variant in term.get("variants", [])),
        key=lambda pair: len(pair[0]), reverse=True,
    )
    for variant, preferred in replacements:
        translation = translation.replace(variant, preferred)
    return translation
