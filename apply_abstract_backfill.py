"""Apply a Markdown abstract backfill by PMID, then DOI, without overwriting English text."""
import json, re, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUEUE = ROOT / "translation-backfill"
ROW = re.compile(r"^| d+ | ([^|]*) | ([^|]*) | (.*?) | (.*?) | (.*?) | (.*?) | (.*?) |$")

def main():
    db = sqlite3.connect(ROOT / "catalog.sqlite")
    applied = 0
    for path in sorted(QUEUE.glob("*.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            m = ROW.match(line)
            if not m or not m.group(8).strip():
                continue
            pmid, doi, _, _, _, _, abstract_zh = [x.strip().replace("\|", "|") for x in m.groups()]
            row = db.execute("SELECT id, data FROM articles WHERE pmid=? OR (doi<>'' AND doi=?) LIMIT 1", (pmid, doi)).fetchone()
            if not row:
                continue
            item = json.loads(row[1])
            item["abstract_zh"] = abstract_zh
            db.execute("UPDATE articles SET data=? WHERE id=?", (json.dumps(item, ensure_ascii=False), row[0]))
            applied += 1
    db.commit()
    db.close()
    print(f"applied abstracts: {applied}")

if __name__ == "__main__":
    main()

