"""Export the screened archive as a self-contained offline static site."""

import json
from pathlib import Path
import re
from urllib.parse import quote, urlsplit

from presentation import OTHER, PATTERNS, PUBLICATION_NOTICE, topic_for, translations
from screening import is_clinical_study, relevance_tier

ROOT = Path(__file__).resolve().parent
PRIORITY_JOURNALS = (
    "Medicine & Science in Sports & Exercise",
    "Journal of Applied Physiology",
    "European Journal of Applied Physiology",
    "International Journal of Sports Physiology and Performance",
    "Sports Medicine",
    "Journal of Strength and Conditioning Research",
    "The Journal of Physiology",
    "Experimental Physiology",
    "Journal of Sport and Health Science",
    "British Journal of Sports Medicine",
    "Scandinavian Journal of Medicine & Science in Sports",
    "European Journal of Sport Science",
    "Journal of Science and Medicine in Sport",
    "Journal of Sports Sciences",
    "Applied Physiology, Nutrition, and Metabolism",
    "Sports Medicine - Open",
    "Biology of Sport",
)
VALID_DATE = re.compile(r"[0-9]{4}(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12][0-9]|3[01]))?)?")


def identity(text):
    """Normalize a title so near-identical titles compare equal."""
    import unicodedata
    return "".join(char for char in unicodedata.normalize("NFKC", text).casefold()
                   if char.isalnum())


PREPRINT_PREFIXES = ("10.17605", "10.21203", "10.1101", "10.31234",
                     "10.26434", "10.20944", "10.31219")


def row_rank(entry):
    """Score a candidate record when two rows share a title; higher wins."""
    item, seen, tier = entry
    doi = (item.get("doi") or "").lower()
    score = 0
    if doi and not doi.startswith(PREPRINT_PREFIXES):
        score += 4          # published version beats a preprint or registration
    elif doi:
        score -= 2
    if item.get("date"):
        score += 2          # a dated record beats an undated one
    if item.get("journal"):
        score += 1          # curated journal beats an out-of-list venue
    if tier == "core":
        score += 1
    return score


def write_site(db, journals):
    candidates = []
    for raw, seen in db.execute("SELECT data, first_seen FROM articles ORDER BY id"):
        item = json.loads(raw)
        tier = relevance_tier(item)
        if tier:
            candidates.append((item, seen, tier))
    # The same paper can reach us twice - the journal version plus a preprint or
    # study registration with a different DOI. The site shows one row per title.
    best = {}
    order = []
    for entry in candidates:
        key = identity(entry[0]["title"])
        if key not in best:
            best[key] = entry
            order.append(key)
        elif row_rank(entry) > row_rank(best[key]):
            best[key] = entry
    if len(order) != len(candidates):
        print(f"Merged {len(candidates) - len(order)} duplicate titles", flush=True)
    candidates = [best[key] for key in order]
    translated, error = translations(db, [item for item, _, _ in candidates])
    if error:
        print(f"Static site translations: {error}")
    records = []
    venues = {}            # venue name -> index, keeps repeated strings out of every row
    topic_names = [*PATTERNS, PUBLICATION_NOTICE, OTHER]
    topic_index = {name: index for index, name in enumerate(topic_names)}
    for item, seen, tier in candidates:
        title = item["title"]
        doi = item.get("doi", "")
        location = "https://doi.org/" + quote(doi, safe="/:") if doi else item.get("url", "")
        if urlsplit(location).scheme not in {"http", "https"}:
            location = ""
        published = item.get("date") or ""
        name = item.get("journal") or item.get("venue") or "期刊待核实"
        row = {
            "j": venues.setdefault(name, len(venues)),
            "f": 1 if item.get("journal") else 0,
            "r": 0 if tier == "core" else 1,
            "t": topic_index[topic_for(item)],
            "c": 1 if is_clinical_study(item) else 0,
            "e": title,
            "d": doi,
            "p": published if VALID_DATE.fullmatch(published) else "",
            "s": seen,
        }
        # The browser rebuilds "https://doi.org/<doi>" itself; the URL only ships
        # when it cannot be derived that way (no DOI, or a DOI needing escapes).
        # That drops about 400 KB from the payload.
        if not doi or location != "https://doi.org/" + doi:
            row["u"] = location
        chinese = translated.get(title)
        if chinese:
            row["z"] = chinese
        records.append(row)

    updated = db.execute("SELECT MAX(day) FROM runs").fetchone()[0]
    data = {
        "records": records,
        "venues": list(venues),
        "journals": [name for name in dict.fromkeys((*PRIORITY_JOURNALS, *journals)) if name in journals],
        "topics": topic_names,
        "tiers": ["core", "related"],
        "updated": updated,
    }
    # Titles and journal metadata are untrusted text. Keep them inside the JSON script.
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    sources = ROOT / "site-src"
    page = (sources / "index.html").read_text(encoding="utf-8-sig")
    content = {
        "/* SITE_STYLES */": (sources / "styles.css").read_text(encoding="utf-8-sig"),
        "/* SITE_SCRIPT */": (sources / "app.js").read_text(encoding="utf-8-sig"),
        "/* SITE_DATA */": payload,
    }
    page = re.sub(r"/\* SITE_(?:STYLES|SCRIPT|DATA) \*/", lambda match: content[match[0]], page)
    output = ROOT / "site"
    output.mkdir(exist_ok=True)
    pending = output / "index.tmp"
    pending.write_text(page, encoding="utf-8")
    pending.replace(output / "index.html")
    print(f"{output / 'index.html'} | {len(records)} screened records")
