"""Validate an agent JSON contribution against the repository schema."""
import json, sys
from pathlib import Path

REQUIRED = {"status","pmid","doi","title_en","title_zh","abstract_en","abstract_zh",
            "journal_en","journal_zh","article_type","topic","official_url","backup_url",
            "source","first_seen","published_online","processed_by","processed_at",
            "translation_source","translation_status","notes"}
STATUSES = {"new","updated","title_translation","abstract_translation","metadata_fix",
            "skipped-existing","duplicate","needs-review","source-missing"}

def main(path):
    items = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(items, dict): items = [items]
    errors, pmids, dois = [], set(), set()
    for i, item in enumerate(items, 1):
        missing = REQUIRED - item.keys()
        if missing: errors.append(f"row {i}: missing {sorted(missing)}")
        if item.get("status") not in STATUSES: errors.append(f"row {i}: invalid status")
        pmid, doi = str(item.get("pmid","")).strip(), str(item.get("doi","")).strip().lower()
        if pmid and pmid in pmids: errors.append(f"row {i}: duplicate PMID {pmid}")
        if doi and doi in dois: errors.append(f"row {i}: duplicate DOI {doi}")
        if pmid: pmids.add(pmid)
        if doi: dois.add(doi)
        for key in ("official_url","backup_url"):
            if item.get(key) and not str(item[key]).startswith(("http://","https://")):
                errors.append(f"row {i}: invalid {key}")
    if errors:
        print("\n".join(errors)); return 1
    print(f"valid contribution: {len(items)} records")
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))

