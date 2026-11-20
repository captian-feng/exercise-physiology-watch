"""Export the screened archive as a self-contained offline static site."""

import json
from pathlib import Path
import re
from urllib.parse import quote, urlsplit

from presentation import OTHER, PATTERNS, PUBLICATION_NOTICE, topic_for, translations
from screening import exclusion_reason

ROOT = Path(__file__).resolve().parent
VALID_DATE = re.compile(r"[0-9]{4}(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12][0-9]|3[01]))?)?")


def write_site(db, journals):
    candidates = []
    for raw, seen in db.execute("SELECT data, first_seen FROM articles ORDER BY id"):
        item = json.loads(raw)
        if not exclusion_reason(item):
            candidates.append((item, seen))
    translated, error = translations(db, [item for item, _ in candidates])
    if error:
        print(f"Static site translations: {error}")
    records = []
    for item, seen in candidates:
        title = item["title"]
        doi = item.get("doi", "")
        url = "https://doi.org/" + quote(doi, safe="/:") if doi else item.get("url", "")
        if urlsplit(url).scheme not in {"http", "https"}:
            url = ""
        published = item.get("date") or ""
        records.append({
            "journal": item.get("journal") or item.get("venue") or "期刊待核实",
            "focused": bool(item.get("journal")),
            "topic": topic_for(item),
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
        "journals": journals,
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

