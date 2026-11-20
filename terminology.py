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


def apply_variant(text, variant, preferred):
    """Replace a wrong rendering without corrupting an already-correct one.

    A variant can overlap the approved term in two ways. As a prefix
    ("心率变异" inside "心率变异性") a blind replace yields "心率变异性性", so
    those occurrences are excluded by lookahead. Inside the approved term
    ("汗率" inside "出汗率") a blind replace yields "出出汗率", so the approved
    term is protected while the variant is replaced.
    """
    if preferred.startswith(variant):
        rest = preferred[len(variant):]
        return re.sub(re.escape(variant) + "(?!" + re.escape(rest) + ")", preferred, text)
    if variant in preferred:
        marker = "\x00approved\x00"
        return text.replace(preferred, marker).replace(variant, preferred).replace(marker, preferred)
    return text.replace(variant, preferred)


def correct(title, translation):
    matched = [term for term in TERMS if matches(title, term)]
    approved = sorted({term["zh"] for term in matched}, key=len, reverse=True)
    # Longest variants first so "最大摄氧量" wins over a shorter substring.
    replacements = sorted(
        ((variant, term["zh"]) for term in matched for variant in term.get("variants", [])),
        key=lambda pair: len(pair[0]), reverse=True,
    )
    for variant, preferred in replacements:
        # A longer approved term may contain this variant ("髌腱病" contains
        # "腱病"), and a generic term's variant must not corrupt it. Approved
        # terms no longer than the variant are left alone so that a short
        # correct term ("心率") cannot shield a longer wrong one ("心率变异").
        guards = {}
        for index, chinese in enumerate(approved):
            if len(chinese) > len(variant) and variant in chinese:
                marker = f"\x00g{index}\x00"
                if chinese in translation:
                    translation = translation.replace(chinese, marker)
                    guards[marker] = chinese
        translation = apply_variant(translation, variant, preferred)
        for marker, chinese in guards.items():
            translation = translation.replace(marker, chinese)
    leftovers = sorted(
        ((phrase, term["zh"]) for term in matched
         for phrase in (term["en"], *term.get("aliases", []))),
        key=lambda pair: len(pair[0]), reverse=True,
    )
    for phrase, preferred in leftovers:
        translation = re.sub(pattern_for(phrase), preferred, translation, flags=re.IGNORECASE)
    return translation
