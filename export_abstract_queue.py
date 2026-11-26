"""Export papers with English abstracts but missing Chinese abstracts."""
import json, re, sqlite3
from pathlib import Path
from presentation import translations

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "待补中文摘要清单.md"

def main():
    db = sqlite3.connect(ROOT / "catalog.sqlite")
    rows = []
    for raw, seen in db.execute("SELECT data, first_seen FROM articles ORDER BY id"):
        item = json.loads(raw)
        abstract_en = (item.get("abstract_en") or item.get("abstract") or "").strip()
        abstract_zh = (item.get("abstract_zh") or "").strip()
        if abstract_en and not abstract_zh:
            rows.append((item, abstract_en))
    title_map, _ = translations(db, [item for item, _ in rows])
    lines = [
        "# 待补中文摘要论文清单", "",
        "仅填写最后一列“中文摘要”；请保留 PMID、DOI、英文标题和英文摘要不变。", "",
        "| # | PMID | DOI | 英文标题 | 中文标题 | 期刊 | 英文摘要 | 中文摘要 |", 
        "|---:|---|---|---|---|---|---|---|",
    ]
    for i, (item, abstract_en) in enumerate(rows, 1):
        def clean(value):
            return re.sub(r"\s+", " ", str(value or "")).replace("|", "\\|").strip()
        lines.append("| %d | %s | %s | %s | %s | %s | %s | |" % (
            i, clean(item.get("pmid")), clean(item.get("doi")),
            clean(item.get("title")), clean(title_map.get(item.get("title"), "")),
            clean(item.get("journal") or item.get("venue")), clean(abstract_en)))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"abstract queue: {len(rows)} papers")
    db.close()

if __name__ == "__main__":
    main()

