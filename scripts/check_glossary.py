"""Check that the exercise-science glossary is well formed and maintainable.

The glossary is the only hand-maintained linguistics asset in the project: it
decides which Chinese term replaces a wrong or untranslated rendering. A broken
entry fails silently (the term simply never matches), so validate the file the
same way the journal list is validated.
"""

import json
from pathlib import Path
import re

CONFIG = Path(__file__).resolve().parents[1] / "exercise_glossary.json"
HAN = re.compile(r"[\u3400-\u9fff]")
LATIN = re.compile(r"[A-Za-z]")
# A few Latin acronyms are part of the accepted Chinese term itself.
ALLOWED_LATIN = re.compile(r"(?:RNA|DNA|ATP)")


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
            if alias != alias.lower():
                raise ValueError(f"aliases 必须小写: {english} -> {alias}")
        if LATIN.search(ALLOWED_LATIN.sub("", chinese)):
            raise ValueError(f"zh 不应含拉丁字母: {english} -> {chinese}")

    with_abbreviations = sum(1 for term in terms if term["abbreviations"])
    with_variants = sum(1 for term in terms if term["variants"])
    print(f"{len(terms)} 条术语，{with_abbreviations} 条带缩写，{with_variants} 条带错译变体")


if __name__ == "__main__":
    main()
