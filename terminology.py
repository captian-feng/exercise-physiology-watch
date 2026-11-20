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
# Python treats CJK characters as \w, so a plain (?<!\w) fails whenever an
# English term sits directly after Chinese ("网络Meta-Analysis"). Bound the
# match with ASCII word characters instead.
BEFORE = r"(?<![A-Za-z0-9])"
AFTER = r"(?![A-Za-z0-9])"


def pattern_for(phrase):
    # Titles mix singular and plural ("inflammatory biomarker(s)"), so allow a
    # trailing s without letting the match run into the next word.
    core = JOINER.join(re.escape(part) for part in re.split(JOINER, phrase.casefold()))
    if re.search(r"[A-Za-z]$", phrase) and not phrase.lower().endswith("s"):
        core += "s?"
    return BEFORE + core + AFTER


def _compiled():
    """Precompile every term's patterns once; matching runs per title, not per term."""
    table = []
    for term in TERMS:
        phrases = [re.compile(pattern_for(phrase))
                   for phrase in (term["en"], *term.get("aliases", []))]
        acronyms = [re.compile(BEFORE + re.escape(abbreviation) + AFTER)
                    for abbreviation in term.get("abbreviations", [])
                    if len(abbreviation) >= 3 and abbreviation.isupper()]
        table.append((term, phrases, acronyms))
    return table


COMPILED = _compiled()


def matched_terms(title):
    """All glossary terms that the English title actually mentions."""
    normalized = unicodedata.normalize("NFKC", title).casefold()
    original = unicodedata.normalize("NFKC", title)
    hits = []
    for term, phrases, acronyms in COMPILED:
        if any(pattern.search(normalized) for pattern in phrases):
            hits.append(term)
        elif acronyms and any(pattern.search(original) for pattern in acronyms):
            hits.append(term)
    return hits


def matches(title, term):
    normalized = unicodedata.normalize("NFKC", title).casefold()
    phrases = [term["en"], *term.get("aliases", [])]
    if any(re.search(pattern_for(phrase), normalized) for phrase in phrases):
        return True
    # A title may mention only the acronym ("Wearable IMU", "HIIT versus ...").
    # Short acronyms are skipped; two letters are too ambiguous to key on.
    original = unicodedata.normalize("NFKC", title)
    for abbreviation in term.get("abbreviations", []):
        if len(abbreviation) >= 3 and abbreviation.isupper():
            if re.search(BEFORE + re.escape(abbreviation) + AFTER, original):
                return True
    return False


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
    matched = matched_terms(title)
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
    # Defense in depth: a variant that sits inside a longer wrong rendering can
    # leave the approved term doubled, because the model wrote the first
    # characters itself ("随机" + "控制的审" -> "随机随机对照试验判").
    for chinese in approved:
        escaped = re.escape(chinese)
        translation = re.sub(f"({escaped})\\1+", chinese, translation)
        if len(chinese) >= 3:
            head = re.escape(chinese[:2])
            translation = re.sub(f"{head}({escaped})", chinese, translation)
    leftovers = sorted(
        ((pattern_for(phrase), term["zh"]) for term in matched
         for phrase in (term["en"], *term.get("aliases", []))),
        key=lambda pair: len(pair[0]), reverse=True,
    )
    for pattern, preferred in leftovers:
        translation = re.sub(pattern, preferred, translation, flags=re.IGNORECASE)
    # Acronyms the model leaves in English (IMU, ACL, HIIT) are unambiguous for
    # this vocabulary, so replace them only when the exact casing appears and the
    # acronym is genuinely part of the English title.
    normalized = unicodedata.normalize("NFKC", title)
    acronyms = sorted(
        ((abbreviation, term["zh"]) for term in matched
         for abbreviation in term.get("abbreviations", [])
         if len(abbreviation) >= 2 and abbreviation.isupper()),
        key=lambda pair: len(pair[0]), reverse=True,
    )
    for abbreviation, preferred in acronyms:
        if re.search(BEFORE + re.escape(abbreviation) + AFTER, normalized):
            translation = re.sub(BEFORE + re.escape(abbreviation) + AFTER,
                                 preferred, translation)
    return translation
