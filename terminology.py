"""Conservative term correction conditioned on the original English title.

Two passes, both conditioned on the English title so a term that is not in the
title is never rewritten:

1. Chinese variants: the offline model renders a known term the wrong way
   ("关键功率" for critical power) and we swap in the approved translation.
2. English leftovers: the model leaves some terms untranslated
   ("Creatine Kinase", "Wellness Questionnaire") and we substitute the approved
   Chinese term, which is what the growing glossary is for.
"""

import json
from pathlib import Path
import re
import unicodedata

PATH = Path(__file__).resolve().parent / "exercise_glossary.json"
TERMS = json.loads(PATH.read_text(encoding="utf-8-sig"))["terms"]
JOINER = r"[\s‐‑‒–—-]+"


def pattern_for(phrase):
    # Titles mix singular and plural ("inflammatory biomarker(s)"), so allow a
    # trailing s without letting the match run into the next word.
    return r"(?<!\w)" + JOINER.join(
        re.escape(part) for part in re.split(JOINER, phrase.casefold())
    ) + r"s?(?!\w)"


def matches(title, term):
    normalized = unicodedata.normalize("NFKC", title).casefold()
    phrases = [term["en"], *term.get("aliases", [])]
    return any(re.search(pattern_for(phrase), normalized) for phrase in phrases)


def correct(title, translation):
    matched = [term for term in TERMS if matches(title, term)]
    # Longest variants first so "最大摄氧量" wins over a shorter substring.
    replacements = sorted(
        ((variant, term["zh"]) for term in matched for variant in term.get("variants", [])),
        key=lambda pair: len(pair[0]), reverse=True,
    )
    for variant, preferred in replacements:
        translation = translation.replace(variant, preferred)
    leftovers = sorted(
        ((phrase, term["zh"]) for term in matched
         for phrase in (term["en"], *term.get("aliases", []))),
        key=lambda pair: len(pair[0]), reverse=True,
    )
    for phrase, preferred in leftovers:
        translation = re.sub(pattern_for(phrase), preferred, translation, flags=re.IGNORECASE)
    return translation
