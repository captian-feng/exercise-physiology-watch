"""Check that every journal config entry uses a valid and unique ISSN."""

import json
from pathlib import Path
import re
from urllib.parse import urlsplit

CONFIG = Path(__file__).resolve().parents[1] / "journals.txt"
ISSN_FORMAT = re.compile(r"[0-9]{4}-[0-9]{3}[0-9X]")


def valid_issn(value):
    if not ISSN_FORMAT.fullmatch(value):
        return False
    compact = value.replace("-", "")
    check = 10 if compact[-1] == "X" else int(compact[-1])
    return (sum(int(number) * weight for number, weight in zip(compact[:7], range(8, 1, -1))) + check) % 11 == 0


def main():
    journals = set()
    identifiers = set()
    for number, line in enumerate(CONFIG.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        name, separator, raw = line.partition("|")
        if not separator or not name or name != name.strip() or name.casefold() in journals:
            raise ValueError(f"Invalid or duplicate journal on line {number}: {line}")
        journals.add(name.casefold())
        for value in raw.split(","):
            if not valid_issn(value) or value in identifiers:
                raise ValueError(f"Invalid or duplicate ISSN on line {number}: {value}")
            identifiers.add(value)
    if not journals:
        raise ValueError("The journal list is empty")
    sources = json.loads(CONFIG.with_name("sources.json").read_text(encoding="utf-8-sig"))
    topics = sources["topics"]
    if not isinstance(topics, dict) or any(not name.strip() or not isinstance(query, str)
                                            or not query.strip() for name, query in topics.items()):
        raise ValueError("Invalid PubMed topic configuration")
    for journal, urls in sources["feeds"].items():
        if journal.casefold() not in journals:
            raise ValueError(f"Feed configured for an unknown journal: {journal}")
        if not isinstance(urls, list) or any(urlsplit(url).scheme != "https" or not urlsplit(url).hostname
                                            for url in urls):
            raise ValueError(f"Feed URLs must be valid HTTPS URLs: {journal}")
    print(f"{len(journals)} journals, {len(identifiers)} ISSNs, {len(topics)} PubMed topics")


if __name__ == "__main__":
    main()
