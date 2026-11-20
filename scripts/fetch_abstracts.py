"""Collect PubMed abstracts for the archived PMIDs (maintenance tool, not part of the build).

The site translates titles only, but the glossary is grown from real abstracts:
they contain the methods and statistics vocabulary that titles never spell out.
Run this occasionally, review the mined candidates, and add the terms you want
to exercise_glossary.json.

    python scripts/fetch_abstracts.py --output abstracts.json --limit 2000

The output is a JSON object of {pmid: abstract text}. It is a working file, not
a build input, so keep it out of the repository.
"""

import argparse
import json
from pathlib import Path
import sqlite3
import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
NCBI = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def archived_pmids(database):
    rows = sqlite3.connect(database).execute("SELECT data FROM articles")
    pmids = set()
    for (raw,) in rows:
        pmid = json.loads(raw).get("pmid")
        if pmid:
            pmids.add(pmid)
    return sorted(pmids)


def fetch_batch(pmids, attempts=4):
    query = urlencode({"db": "pubmed", "id": ",".join(pmids),
                       "retmode": "xml", "rettype": "abstract"})
    for attempt in range(attempts):
        try:
            with urlopen(f"{NCBI}?{query}", timeout=60) as response:
                return response.read()
        except (URLError, TimeoutError):
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** (attempt + 1))
    return b""


def parse(payload, collected):
    root = ElementTree.fromstring(payload)
    for citation in root.findall("PubmedArticle"):
        pmid = citation.findtext("./MedlineCitation/PMID", "")
        parts = ["".join(node.itertext()).strip()
                 for node in citation.findall(".//Abstract/AbstractText")]
        text = " ".join(part for part in parts if part)
        if pmid and text:
            collected[pmid] = text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=ROOT / "catalog.sqlite",
                        help="解压后的归档数据库（cloud_refresh 的初始快照）")
    parser.add_argument("--output", type=Path, default=ROOT / "abstracts.json")
    parser.add_argument("--limit", type=int, default=0, help="只抓前 N 条，0 表示全部")
    options = parser.parse_args()
    pmids = archived_pmids(options.database)
    if options.limit:
        pmids = pmids[:options.limit]
    print(f"待抓取 {len(pmids)} 条 PMID")
    collected = {}
    for start in range(0, len(pmids), 100):
        parse(fetch_batch(pmids[start:start + 100]), collected)
        if start % 1000 == 0:
            print(f"  {start}/{len(pmids)}，已获得 {len(collected)} 条")
        time.sleep(0.4)
    options.output.write_text(json.dumps(collected, ensure_ascii=False), encoding="utf-8")
    print(f"完成：{len(collected)} 条摘要 -> {options.output}")


if __name__ == "__main__":
    main()
