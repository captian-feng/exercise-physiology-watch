"""Run the journal collection pipeline in an isolated working directory."""

import argparse
from contextlib import closing
import gzip
from hashlib import file_digest
import json
import os
from pathlib import Path
from shutil import copy2, copyfileobj, copytree
import sqlite3
from subprocess import run
import sys
from tempfile import TemporaryDirectory
from time import sleep
from urllib.error import URLError
from urllib.request import Request, urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "catalog.sqlite.gz"
MODEL_NAME = "translate-en_zh-1_9"
MODEL_URL = "https://argos-net.com/v1/translate-en_zh-1_9.argosmodel"
MODEL_HASHES = {
    "model/config.json": "3a8660f12559a223969532ff191e5e6f50d4ff24164517edbd6a5090dc5144c6",
    "model/model.bin": "1a039114d9456b6528fabb65b455b6f156319634a0f984b1f6018f7737d67598",
    "model/shared_vocabulary.json": "c0b6e24705ec0489d5b810de365959c1013aecd644cfeca161b54ea1df6a7dc0",
    "sentencepiece.model": "872224b85a11edc9d769a94949fd387b67ea85b50708db9f91f32f5b497a9af3",
}


def checked(path, expected):
    if not path.is_file():
        return False
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest() == expected


def install_model(work):
    model = work / "models" / MODEL_NAME
    cached = ROOT / "models" / MODEL_NAME
    if all(checked(cached / name, sha) for name, sha in MODEL_HASHES.items()):
        copytree(cached, model)
        return
    package = work / "argos.zip"
    request = Request(MODEL_URL, headers={"User-Agent": "JournalWatch/1.0"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=60) as response, package.open("wb") as output:
                copyfileobj(response, output)
            break
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
            sleep(2 ** (attempt + 1))
    with ZipFile(package) as archive:
        for name, sha in MODEL_HASHES.items():
            path = model / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(f"{MODEL_NAME}/{name}") as stream, path.open("wb") as output:
                copyfileobj(stream, output)
            if not checked(path, sha):
                raise ValueError(f"Model integrity check failed for {name}")
    copytree(model, cached, dirs_exist_ok=True)


def validate(db_path, site):
    page = site.read_text(encoding="utf-8")
    dataset = page.split('<script id="dataset" type="application/json">', 1)[1].split("</script>", 1)[0]
    data = json.loads(dataset)
    if not data["records"]:
        raise ValueError("Generated site is empty")
    # The payload stores venues, themes and tiers once and references them by
    # index, and leaves out the Chinese title when there is none. Check the shape
    # here so a schema change fails with a clear message instead of a KeyError.
    for key in ("venues", "topics", "tiers"):
        if key not in data:
            raise ValueError(f"Site payload is missing {key}")
    for row in data["records"]:
        missing = {"e", "j", "t", "r"} - row.keys()
        if missing:
            raise ValueError(f"Site record is missing {sorted(missing)}")
    untranslated = sum(not row.get("z") for row in data["records"])
    # The same paper can arrive twice (journal version plus a preprint with its
    # own DOI), so the published page must never show the same title twice.
    seen_titles = set()
    duplicates = []
    for row in data["records"]:
        key = "".join(char for char in row["e"].casefold() if char.isalnum())
        if key in seen_titles:
            duplicates.append(row["e"])
        seen_titles.add(key)
    if duplicates:
        raise ValueError(f"Duplicate titles on the page: {duplicates[:3]}")
    with closing(sqlite3.connect(db_path)) as db:
        if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ValueError("SQLite integrity check failed")
        latest = db.execute("SELECT MAX(day) FROM runs").fetchone()[0]
        if data["updated"] != latest:
            raise ValueError("Site and database use different update dates")
        scanned = db.execute("SELECT history FROM report_history WHERE day=?", (latest,)).fetchone()
    history = json.loads(scanned[0]) if scanned else []
    failed = [(source, label, error) for source, label, _, error in history if error]
    print(f"Verified {len(data['records'])} records through {latest}, "
          f"{len(failed)}/{len(history)} source failures, {untranslated} without Chinese titles")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as output:
            output.write(f"## 文献库更新 {latest}\n\n")
            output.write(f"- 纳入 {len(data['records'])} 条\n")
            output.write(f"- 来源失败 {len(failed)} / {len(history)} 项\n")
            output.write(f"- 仍待中文译名 {untranslated} 条\n")
            for source, label, error in failed:
                message = " ".join(f"{source} · {label} · {error}".split()).replace("<", "&lt;")
                output.write(f"  - {message}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--render-only", metavar="YYYY-MM-DD")
    options = parser.parse_args()
    with TemporaryDirectory(prefix="journal-watch-") as scratch:
        work = Path(scratch)
        for name in ("watch.py", "presentation.py", "screening.py", "static_site.py", "deepseek_enrichment.py", "article_types.py", "scope_verify.py", "article_type_overrides.json", "pubmed_online_dates.json", "crossref_online_dates.json", "publisher_online_dates.json", "publisher_watch.py", "terminology.py", "exercise_glossary.json", "journals.txt", "sources.json"):
            copy2(ROOT / name, work / name)
        trial = ROOT / 'deepseek_top100.json'
        if trial.exists():
            copy2(trial, work / trial.name)
        # The scope-verification cache is optional: without it the build simply
        # re-checks ambiguous records, subject to its per-run lookup budget.
        verification = ROOT / "scope_verification.json"
        if verification.exists():
            copy2(verification, work / verification.name)
        copytree(ROOT / "site-src", work / "site-src")
        db_path = work / "catalog.sqlite"
        with gzip.open(STATE, "rb") as stream, db_path.open("wb") as output:
            copyfileobj(stream, output)
        arguments = [sys.executable, "-X", "utf8", "watch.py"]
        if options.render_only:
            arguments += ["--render-only", options.render_only]
        else:
            install_model(work)
        run_timeout = 21000 if os.environ.get("DEEPSEEK_FULL") == "1" else 1500
        run(arguments, cwd=work, check=True, timeout=run_timeout)
        site = work / "site" / "index.html"
        validate(db_path, site)
        if options.render_only:
            return
        next_state = STATE.with_suffix(".tmp")
        site_path = ROOT / "dist" / "index.html"
        next_site = site_path.with_suffix(".tmp")
        copy2(site, next_site)
        with db_path.open("rb") as stream, next_state.open("wb") as output:
            with gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as packed:
                copyfileobj(stream, packed)
        next_state.replace(STATE)
        next_site.replace(site_path)
        # Verdicts learned during this run are written back so the next build
        # reuses them instead of repeating the lookups.
        learned = work / verification.name
        if learned.exists():
            copy2(learned, verification)


if __name__ == "__main__":
    main()



