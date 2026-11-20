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


def write_site(db, journals):
    candidates = []
    for raw, seen in db.execute("SELECT data, first_seen FROM articles ORDER BY id"):
        item = json.loads(raw)
        tier = relevance_tier(item)
        if tier:
            candidates.append((item, seen, tier))
    translated, error = translations(db, [item for item, _, _ in candidates])
    if error:
        print(f"Static site translations: {error}")
    records = []
    for item, seen, tier in candidates:
        title = item["title"]
        doi = item.get("doi", "")
        url = "https://doi.org/" + quote(doi, safe="/:") if doi else item.get("url", "")
        if urlsplit(url).scheme not in {"http", "https"}:
            url = ""
        published = item.get("date") or ""
        records.append({
            "journal": item.get("journal") or item.get("venue") or "期刊待核实",
            "focused": bool(item.get("journal")),
            "tier": tier,
            "topic": topic_for(item),
            "clinical": is_clinical_study(item),
            "en": title,
            "zh": translated.get(title, ""),
            "doi": doi,
            "url": url,
            "published": published if VALID_DATE.fullmatch(published) else "",
            "seen": seen,
        })

    updated = db.execute("SELECT MAX(day) FROM runs").fetchone()[0]
    data = {
        "records": records,
        "journals": [name for name in dict.fromkeys((*PRIORITY_JOURNALS, *journals)) if name in journals],
        "topics": [*PATTERNS, PUBLICATION_NOTICE, OTHER],
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
