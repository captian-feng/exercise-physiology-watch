"""Merge validated JSON contributions into catalog.sqlite without silent overwrites."""
import gzip, json, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("doi","title","author","date","type","venue","url","journal","sources","pmid","issns",
          "topics","volume","issue","abstract_en","abstract_zh")

def main():
    db = sqlite3.connect(ROOT / "catalog.sqlite")
    db.execute("CREATE TABLE IF NOT EXISTS translations (title TEXT PRIMARY KEY, zh TEXT NOT NULL)")
    merged = skipped = conflicts = 0
    for path in sorted((ROOT / "contributions").glob("**/*.json")):
        if path.name == "README.json": continue
        items = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(items, dict): items = [items]
        for item in items:
            if item.get("status") in {"skipped-existing","duplicate","needs-review","source-missing"}:
                skipped += 1; continue
            pmid, doi = str(item.get("pmid","")).strip(), str(item.get("doi","")).strip().lower()
            row = db.execute("SELECT id,data,first_seen FROM articles WHERE pmid=? OR (doi<>'' AND lower(doi)=?) LIMIT 1", (pmid,doi)).fetchone()
            if row:
                data = json.loads(row[1])
                for key, value in (("title_zh","title_zh"),("abstract_en","abstract_en"),("abstract_zh","abstract_zh")):
                    incoming = str(item.get(key,"") or "").strip()
                    if not incoming: continue
                    if key == "title_zh":
                        db.execute("INSERT OR REPLACE INTO translations(title,zh) VALUES (?,?)", (data.get("title",""), incoming))
                    elif data.get(value) and data.get(value) != incoming:
                        conflicts += 1
                    else:
                        data[value] = incoming
                db.execute("UPDATE articles SET data=? WHERE id=?", (json.dumps(data,ensure_ascii=False),row[0]))
                merged += 1
                continue
            if not item.get("title_en") or not (pmid or doi):
                conflicts += 1; continue
            data = {k:item.get(src,"") for src,k in [("doi","doi"),("title_en","title"),("journal_en","journal"),("pmid","pmid"),("article_type","type"),("official_url","url"),("source","sources")]}
            data["abstract_en"] = item.get("abstract_en","")
            data["abstract_zh"] = item.get("abstract_zh","")
            data["topics"] = [item.get("topic","")] if item.get("topic") else []
            fp = f"{pmid}|{doi}|{data['title']}".lower()
            db.execute("INSERT INTO articles(doi,pmid,fingerprint,data,first_seen) VALUES (?,?,?,?,?)",
                       (doi,pmid,fp,json.dumps(data,ensure_ascii=False),item.get("first_seen") or item.get("processed_at","")[:10]))
            if item.get("title_zh"): db.execute("INSERT OR REPLACE INTO translations VALUES (?,?)",(data["title"],item["title_zh"]))
            merged += 1
    db.commit(); db.close()
    print(f"merged={merged} skipped={skipped} conflicts={conflicts}")
    return 1 if conflicts else 0

if __name__ == "__main__":
    raise SystemExit(main())

