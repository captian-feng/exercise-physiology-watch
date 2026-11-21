"""Check that the exercise-science glossary is well formed and maintainable.

The glossary is the only hand-maintained linguistics asset in the project: it
decides which Chinese term replaces a wrong or untranslated rendering. A broken
entry fails silently (the term simply never matches), so validate the file the
same way the journal list is validated.
"""

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CONFIG = ROOT / "exercise_glossary.json"
HAN = re.compile(r"[\u3400-\u9fff]")
LATIN = re.compile(r"[A-Za-z]")
# Domains let the library be audited per area (strength and conditioning,
# training theory, physiology, ...) instead of as one flat list.
# Domains let the library be audited per area (strength and conditioning,
# training theory, physiology, ...) instead of as one flat list. Keep this in step
# with the domains used in exercise_glossary.json - the check below fails loudly
# when a new domain is introduced without being listed here.
DOMAINS = {"运动生理", "体能训练", "运动训练", "训练理论", "解剖与动作", "生物力学",
           "运动医学", "研究方法", "营养代谢", "监测技术", "人群健康",
           "心血管", "神经与认知", "免疫与分子", "内分泌与代谢", "肾脏与体液",
           "呼吸系统", "环境生理", "体能测试", "体成分", "睡眠与恢复", "运动控制",
           "临床医学", "其他"}
# A few Latin acronyms are part of the accepted Chinese term itself.
ACCEPTED_LATIN = {"RNA", "DNA", "ATP"}
ALLOWED_LATIN = re.compile("|".join(sorted(ACCEPTED_LATIN)))
LATIN_RUN = re.compile(r"[A-Za-z]+")
UPPER_RUN = re.compile(r"[A-Z]+")


def main():
    data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    if data.get("version") != 1:
        raise ValueError("exercise_glossary.json 的 version 必须为 1")
    terms = data.get("terms")
    if not isinstance(terms, list) or not terms:
        raise ValueError("terms 必须是非空数组")

    seen = {}
    for index, term in enumerate(terms):
        if not isinstance(term, dict):
            raise ValueError(f"第 {index + 1} 条不是对象")
        for key in ("en", "zh", "abbreviations", "variants"):
            if key not in term:
                raise ValueError(f"第 {index + 1} 条缺少字段 {key}: {term}")
        english, chinese = term["en"], term["zh"]
        if not isinstance(english, str) or not english.strip():
            raise ValueError(f"第 {index + 1} 条的 en 为空")
        if english != english.lower():
            raise ValueError(f"en 必须小写: {english}")
        if english in seen:
            raise ValueError(f"en 重复: {english}（第 {seen[english]} 与第 {index + 1} 条）")
        seen[english] = index + 1
        if not isinstance(chinese, str) or not HAN.search(chinese):
            raise ValueError(f"zh 必须是中文: {english} -> {chinese!r}")
        if not isinstance(term["abbreviations"], list):
            raise ValueError(f"abbreviations 必须是数组: {english}")
        if not isinstance(term["variants"], list):
            raise ValueError(f"variants 必须是数组: {english}")
        for variant in term["variants"]:
            if not isinstance(variant, str) or not variant.strip():
                raise ValueError(f"variants 含空项: {english}")
            if not HAN.search(variant):
                raise ValueError(f"variants 必须是中文错译: {english} -> {variant!r}")
            if variant == chinese:
                raise ValueError(f"variants 不能与规范译名相同: {english}")
        for alias in term.get("aliases", []):
            if not isinstance(alias, str) or not alias.strip():
                raise ValueError(f"aliases 含空项: {english}")
            # Matching ignores case, so aliases are written lowercase except for
            # acronyms, which stay upper ("diastolic BP" is fine, "Diastolic BP"
            # is not, because a capitalised word means someone typed prose).
            if any(len(run) == 1 for run in UPPER_RUN.findall(alias)):
                raise ValueError(f"aliases 除缩写外应小写: {english} -> {alias}")
        if LATIN.search(ALLOWED_LATIN.sub("", chinese)):
            # Some approved Chinese terms keep a short Latin marker by convention
            # ("B型利钠肽", "C反应蛋白", "Y平衡测试", "RR间期"): one or two letters
            # attached to Chinese is fine, a word left untranslated is not.
            leftovers = [run for run in LATIN_RUN.finditer(chinese)
                         if run.group() not in ACCEPTED_LATIN]
            for run in leftovers:
                start, end = run.start(), run.end()
                before = chinese[start - 1] if start else ""
                after = chinese[end] if end < len(chinese) else ""
                if len(run.group()) <= 2 and (HAN.match(before or "") or HAN.match(after or "")):
                    continue
                raise ValueError(f"zh 不应含拉丁字母: {english} -> {chinese}")

        domain = term.get("domain")
        if domain is not None and domain not in DOMAINS:
            raise ValueError(f"未知领域 {domain!r}: {english}")

    # Correction must be idempotent: applying it to the approved translation
    # has to leave it untouched. This catches a variant that is a prefix of its
    # own approved term, which would render "心率变异性" as "心率变异性性".
    from terminology import correct
    for term in terms:
        result = correct(term["en"], term["zh"])
        if result != term["zh"]:
            raise ValueError(
                f"术语修正不幂等: {term['en']} 的规范译名 {term['zh']!r} 被改成了 {result!r}"
            )

    counts = {}
    for term in terms:
        counts[term.get("domain", "未分类")] = counts.get(term.get("domain", "未分类"), 0) + 1
    with_abbreviations = sum(1 for term in terms if term["abbreviations"])
    with_variants = sum(1 for term in terms if term["variants"])
    print(f"{len(terms)} 条术语，{with_abbreviations} 条带缩写，{with_variants} 条带错译变体")
    summary = "  ".join(f"{name}{count}" for name, count in sorted(counts.items(), key=lambda pair: -pair[1]))
    print(summary)


if __name__ == "__main__":
    main()
