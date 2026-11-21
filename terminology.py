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
    acronym_owners = {}
    for term in TERMS:
        for abbreviation in term.get("abbreviations", []):
            acronym_owners.setdefault(abbreviation, set()).add(term["en"])
    for term in TERMS:
        phrases = [re.compile(pattern_for(phrase))
                   for phrase in (term["en"], *term.get("aliases", []))]
        acronyms = [re.compile(BEFORE + re.escape(abbreviation) + AFTER)
                    for abbreviation in term.get("abbreviations", [])
                    if len(abbreviation) >= 3 and abbreviation.isupper()
                    and len(acronym_owners[abbreviation]) == 1]
        table.append((term, phrases, acronyms))
    return table


COMPILED = _compiled()
WORD_SPLIT = re.compile(r"[\s‐‑‒–—-]+")
# Titles keep punctuation attached to words ("muscle:", "strength,"), so index
# keys are built from bare alphanumeric tokens instead of whitespace splits.
WORD_TOKEN = re.compile(r"[a-z0-9]+")


def _stem(word):
    """Reduce a head word to a lookup key that survives plural forms.

    A term like "muscle" must still be found in "muscles"; the compiled pattern
    allows the plural, so the index key has to line up with the title's word.
    """
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def _first_word_index():
    """Index terms by the stem of the first word of their English phrase.

    A term can only match if its first word occurs in the title, so the scan
    only has to test the terms whose head word is present. With a thousand
    entries that turns a per-title full scan into a small lookup.
    """
    index = {}
    with_acronym = []
    for entry in COMPILED:
        term, _, acronyms = entry
        for phrase in (term["en"], *term.get("aliases", [])):
            parts = [part for part in WORD_SPLIT.split(phrase.casefold()) if part]
            if parts:
                index.setdefault(_stem(parts[0]), []).append(entry)
        if acronyms:
            with_acronym.append(entry)
    return index, with_acronym


FIRST_WORD_INDEX, ACRONYM_TERMS = _first_word_index()


def matched_terms(title):
    """All glossary terms that the English title actually mentions."""
    normalized = unicodedata.normalize("NFKC", title).casefold()
    original = unicodedata.normalize("NFKC", title)
    words = set(WORD_TOKEN.findall(normalized))
    keys = set()
    for word in words:
        keys.add(_stem(word))
        keys.add(word + "s")
    candidates = []
    seen = set()
    for key in keys:
        for entry in FIRST_WORD_INDEX.get(key, ()):
            if id(entry) not in seen:
                seen.add(id(entry))
                candidates.append(entry)
    hits = [entry[0] for entry in candidates
            if any(pattern.search(normalized) for pattern in entry[1])]
    # Acronyms are checked for every term that has one: a candidate whose phrase
    # did not match can still be referred to by its acronym ("Post-COVID").
    hit_names = {term["en"] for term in hits}
    for entry in ACRONYM_TERMS:
        if entry[0]["en"] in hit_names:
            continue
        if any(pattern.search(original) for pattern in entry[2]):
            hits.append(entry[0])
            hit_names.add(entry[0]["en"])
    return hits


def matches(title, term):
    normalized = unicodedata.normalize("NFKC", title).casefold()
    phrases = [term["en"], *term.get("aliases", [])]
    if any(re.search(pattern_for(phrase), normalized) for phrase in phrases):
        return True
    # A title may mention only the acronym ("Wearable IMU", "HIIT versus ...").
    # Short acronyms are skipped; two letters are too ambiguous to key on.
    original = unicodedata.normalize("NFKC", title)
    ambiguous = {abbr for other in TERMS if other is not term
                 for abbr in other.get("abbreviations", [])}
    for abbreviation in term.get("abbreviations", []):
        if len(abbreviation) >= 3 and abbreviation.isupper() and abbreviation not in ambiguous:
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
    acronym_owners = {}
    for term in TERMS:
        for abbreviation in term.get("abbreviations", []):
            acronym_owners.setdefault(abbreviation, set()).add(term["en"])
    acronyms = sorted(
        ((abbreviation, term["zh"]) for term in matched
         for abbreviation in term.get("abbreviations", [])
         if len(abbreviation) >= 3 and abbreviation.isupper()
         and len(acronym_owners[abbreviation]) == 1),
        key=lambda pair: len(pair[0]), reverse=True,
    )
    for abbreviation, preferred in acronyms:
        if re.search(BEFORE + re.escape(abbreviation) + AFTER, normalized):
            translation = re.sub(BEFORE + re.escape(abbreviation) + AFTER,
                                 preferred, translation)
    return translation
