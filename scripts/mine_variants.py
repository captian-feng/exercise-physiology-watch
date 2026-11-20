"""Surface how the offline model actually renders each glossary term.

When the approved Chinese of a term is missing from a translated title, the
model rendered it some other way. Comparing Chinese n-grams of the affected
titles against the whole corpus shows which fragments are over-represented there:
those are the model's habitual wrong renderings and become candidates for the
term's ``variants`` list.

    python scripts/mine_variants.py --site dist/index.html

Output is a report; a human confirms each candidate before it is added to
exercise_glossary.json, because a fragment can also be a real word or a name.
"""

import argparse
import collections
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terminology import TERMS, matched_terms  # noqa: E402

HAN = re.compile(r"[\u4e00-\u9fff]+")
SIZES = (2, 3, 4)


def load_records(page):
    html = page.read_text(encoding="utf-8")
    match = re.search(r'<script id="dataset" type="application/json">(.*?)</script>', html, re.S)
    if not match:
        raise ValueError("页面里没有 dataset，先运行一次完整采集")
    payload = json.loads(match.group(1))
    # The published payload is compact: short keys, index references, and the
    # Chinese title omitted when it is empty. Expand it to the reading shape.
    venues, topics = payload["venues"], payload["topics"]
    records = []
    for row in payload["records"]:
        if not row.get("z"):
            continue
        records.append({
            "en": row["e"],
            "zh": row["z"],
            "journal": venues[row["j"]],
            "topic": topics[row["t"]],
        })
    return records


def grams(text):
    counts = collections.Counter()
    for run in HAN.findall(text):
        for size in SIZES:
            for index in range(len(run) - size + 1):
                counts[run[index:index + size]] += 1
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, default=ROOT / "dist" / "index.html")
    parser.add_argument("--output", type=Path, default=ROOT / "variant-report.json")
    parser.add_argument("--top", type=int, default=40)
    options = parser.parse_args()

    records = load_records(options.site)
    overall = collections.Counter()
    for record in records:
        overall.update(grams(record["zh"]))
    total = len(records)

    gaps = collections.defaultdict(list)
    for record in records:
        for term in matched_terms(record["en"]):
            if term["zh"] not in record["zh"]:
                gaps[term["en"]].append(record)
    ranked = sorted(gaps.items(), key=lambda pair: len(pair[1]), reverse=True)
    print(f"{total} 条记录，{len(ranked)} 个术语存在译文缺口")

    report = {}
    for name, items in ranked[:options.top]:
        term = next(entry for entry in TERMS if entry["en"] == name)
        local = collections.Counter()
        for record in items:
            local.update(grams(record["zh"]))
        scored = []
        for gram, count in local.items():
            if count < max(3, len(items) // 4) or gram in term["zh"]:
                continue
            expected = overall[gram] * len(items) / total
            lift = count / expected if expected > 0 else count
            if lift >= 3 and count >= 4:
                scored.append({"variant": gram, "lift": round(lift, 1), "count": count})
        scored.sort(key=lambda item: item["lift"], reverse=True)
        report[name] = {"gap_records": len(items), "approved": term["zh"],
                        "candidates": scored[:6]}
        print(f"[{len(items):3d}] {name} -> {term['zh']}")
        for item in scored[:5]:
            print(f"        ×{item['lift']:5.1f}  {item['count']:3d}  {item['variant']}")

    options.output.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n报告已写出 {options.output}；确认后把候选填入 exercise_glossary.json 的 variants")


if __name__ == "__main__":
    main()
