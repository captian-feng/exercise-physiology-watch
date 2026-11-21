"""Mine the title+abstract corpus and persist a compact term-frequency file.

The repository keeps a compressed n-gram frequency table in data/term_corpus.json.gz
so the lab can grow the glossary without re-fetching PubMed. Run this after
scripts/fetch_abstracts.py, then read the top phrases not yet in the glossary.

    python scripts/mine_corpus.py --database catalog.sqlite \
        --abstracts abstracts.json --output data/term_corpus.json.gz
"""

import argparse
import collections
import gzip
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terminology import TERMS  # noqa: E402

WORD = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")
STOP = set("""
the a an of in on at to for with by from as is are was were be been being this that these those its their
and or but not no than then there here we our us it they them he she his her which who whom whose what
can could may might must shall should will would do does did done have has had having more most less least
using used use between among during after before into within without about across over under above below
study studies research results result effect effects analysis analyses review systematic meta randomized
controlled trial trials group groups subject subjects participant participants mean means compared comparison
significantly significant difference differences increased decreased higher lower greater smaller larger
""".split())


def titles(database):
    if not database.is_file():
        return []
    rows = sqlite3.connect(database).execute("SELECT data FROM articles")
    out = []
    for (raw,) in rows:
        item = json.loads(raw)
        if item.get("title"):
            out.append(item["title"])
    return out


def abstracts(path):
    if not path.is_file():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")).values())


def count(texts):
    freqs = collections.Counter()
    for text in texts:
        words = [word for word in WORD.findall(text.lower()) if word not in STOP]
        for size in (2, 3):
            for index in range(len(words) - size + 1):
                gram = words[index:index + size]
                if any(len(part) < 3 for part in gram):
                    continue
                freqs[" ".join(gram)] += 1
    return freqs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=ROOT / "catalog.sqlite")
    parser.add_argument("--abstracts", type=Path, default=ROOT / "abstracts.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "term_corpus.json.gz")
    parser.add_argument("--min-count", type=int, default=8)
    parser.add_argument("--show", type=int, default=40, help="打印前 N 个未收录短语")
    options = parser.parse_args()

    freqs = count(titles(options.database) + abstracts(options.abstracts))
    kept = {phrase: n for phrase, n in freqs.items() if n >= options.min_count}
    options.output.parent.mkdir(exist_ok=True)
    options.output.write_bytes(gzip.compress(
        json.dumps(kept, ensure_ascii=False, separators=(",", ":")).encode(), 6))

    known = {term["en"] for term in TERMS}
    fresh = [(n, phrase) for phrase, n in freqs.most_common()
             if n >= options.min_count and phrase not in known]
    print(f"语料 n-gram（频次>={options.min_count}）{len(kept)} 个 -> {options.output}")
    print(f"未收录的高频短语 top {options.show}:")
    for n, phrase in fresh[:options.show]:
        print(f"  {n:5d}  {phrase}")


if __name__ == "__main__":
    main()
