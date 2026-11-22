"""Collect new papers, keep a durable catalog, and render daily HTML reports."""

import argparse
from contextlib import nullcontext, redirect_stdout, redirect_stderr
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html import escape, unescape
import json
from pathlib import Path
import re
import sqlite3
import sys
import traceback
from threading import Lock
import time
from urllib.error import HTTPError, URLError
import unicodedata
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from presentation import grouped, translations
from publisher_watch import publisher_articles
from screening import exclusion_reason
from static_site import write_site

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))
CROSSREF = "https://api.crossref.org/works"
NCBI = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
SOURCES = json.loads((ROOT / "sources.json").read_text(encoding="utf-8-sig"))
TOPICS = SOURCES["topics"]
FEEDS = SOURCES["feeds"]
PUBLISHER_PAGES = SOURCES.get("publisher_pages", {})
HISTORY_BACKFILL = SOURCES.get("history_backfill")


# Each host has its own lock and minimum interval between request starts.
RATE_INTERVALS = {"api.crossref.org": 1.1, "eutils.ncbi.nlm.nih.gov": 0.4}
RATE_LOCKS = {host: Lock() for host in RATE_INTERVALS}
LAST_REQUEST = dict.fromkeys(RATE_INTERVALS, float("-inf"))
DEFAULT_HEADERS = {
    "User-Agent": "JournalWatch/1.0 (academic literature monitoring; "
                  "+https://github.com/captian-feng/exercise-physiology-watch)",
    "Accept-Language": "en",
}
# Publisher RSS endpoints answer 429 to a bare default user agent, so feeds get
# an explicit reader-style agent and an XML accept header.
FEED_HEADERS = {
    **DEFAULT_HEADERS,
    "User-Agent": "Mozilla/5.0 (compatible; JournalWatch/1.0; RSS reader) "
                  "academic-literature-monitoring",
    "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, "
              "text/xml;q=0.8, */*;q=0.5",
}


def fetch(url, headers=None, **params):
    if params:
        url += "?" + urlencode(params)
    host = urlsplit(url).hostname
    request = Request(url, headers={**DEFAULT_HEADERS, **(headers or {})})
    for attempt in range(4):
        with RATE_LOCKS.get(host, nullcontext()):
            if host in RATE_INTERVALS:
                pause = RATE_INTERVALS[host] - (time.monotonic() - LAST_REQUEST[host])
                if pause > 0:
                    time.sleep(pause)
                LAST_REQUEST[host] = time.monotonic()
            retry_after = 0
            try:
                with urlopen(request, timeout=15) as response:
                    return response.read()
            except HTTPError as error:
                if error.code not in {403, 429, 500, 502, 503, 504} or attempt == 3:
                    raise
                value = error.headers.get("Retry-After", "")
                retry_after = int(value) if value.isdecimal() else 0
                if retry_after > 60:
                    raise
            except (URLError, TimeoutError):
                if attempt == 3:
                    raise
            time.sleep(max(retry_after, 2 ** (attempt + 2)))



def clean(text):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", text or ""))).strip()


def identity(text):
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


def crossref(issns, since, baseline, issue_sweep=False, until=None):
    filters = ["issn:" + "|".join(issns)]
    if issue_sweep:
        filters.append("from-print-pub-date:" + since)
    else:
        filters.append(("from-pub-date:" if baseline else "from-index-date:") + since)
    if until:
        filters.append("until-pub-date:" + until)
    if not baseline and not issue_sweep:
        publication_floor = datetime.fromisoformat(since).date() - timedelta(days=90)
        filters.append("from-pub-date:" + publication_floor.isoformat())
    fields = "DOI,title,author,published-online,published,type,volume,issue,container-title,URL"
    for offset in range(0, 10000, 100):
        page = json.loads(fetch(CROSSREF, filter=",".join(filters), rows=100,
                                offset=offset, select=fields))["message"]
        for row in page["items"]:
            authors = row.get("author", [])
            date = row.get("published-online") or row.get("published") or {}
            yield {
                "doi": row.get("DOI", "").lower(), "pmid": "",
                "title": clean(next(iter(row.get("title", [])), "")),
                "author": authors[0].get("family", "") if authors else "",
                "date": "-".join(f"{part:02d}" for part in date.get("date-parts", [[]])[0]),
                "online_date": "-".join(f"{part:02d}" for part in (row.get("published-online") or {}).get("date-parts", [[]])[0]),
                "type": row.get("type", ""), "volume": row.get("volume", ""),
                "issue": row.get("issue", ""),
                "venue": next(iter(row.get("container-title", [])), ""),
                "url": row.get("URL", ""),
            }
        if len(page["items"]) < 100 or offset + 100 >= page["total-results"]:
            return
    raise ValueError("Crossref 返回结果超过单次增量窗口上限")


def openalex(issns, since):
    cursor = "*"
    while cursor:
        filters = "primary_location.source.issn:" + "|".join(issns)
        filters += ",from_publication_date:" + since
        page = json.loads(fetch("https://api.openalex.org/works", filter=filters,
                                cursor=cursor, per_page=100, corpus="all",
                                select="id,doi,title,publication_date,type,biblio,authorships,primary_location"))
        for row in page["results"]:
            authors = row.get("authorships") or []
            biblio = row.get("biblio") or {}
            location = row.get("primary_location") or {}
            yield {
                "doi": (row.get("doi") or "").removeprefix("https://doi.org/").lower(),
                "title": clean(row.get("title")), "date": row.get("publication_date") or "",
                "type": row.get("type") or "", "volume": biblio.get("volume") or "",
                "issue": biblio.get("issue") or "",
                "url": location.get("landing_page_url") or row["id"],
            }
        cursor = page["meta"].get("next_cursor") if len(page["results"]) == 100 else None


def pubmed_ids(query, start, end, field="crdt"):
    window = f'"{start:%Y/%m/%d}"[{field}] : "{end:%Y/%m/%d}"[{field}]'
    search = json.loads(fetch(NCBI + "esearch.fcgi", db="pubmed", retmode="json",
                              retmax=9999, term=f"({query}) AND ({window})"))
    result = search["esearchresult"]
    ids = result["idlist"]
    if int(result["count"]) <= len(ids):
        yield from ids
        return
    if start == end:
        raise ValueError(f"PubMed query still exceeds the per-request cap on {start}")
    midpoint = start + (end - start) // 2
    yield from pubmed_ids(query, start, midpoint, field)
    yield from pubmed_ids(query, midpoint + timedelta(days=1), end, field)


def pubmed(query, since, until=None):
    start_date = datetime.fromisoformat(since).date()
    end = datetime.fromisoformat(until).date() if until else max(start_date, datetime.now(TZ).date())
    ids = list(pubmed_ids(query, start_date, end, "pdat" if until else "crdt"))
    for start in range(0, len(ids), 100):
        batch = ElementTree.fromstring(fetch(NCBI + "efetch.fcgi", db="pubmed",
                                             id=",".join(ids[start:start + 100]), retmode="xml"))
        for citation in batch.findall("PubmedArticle"):
            article = citation.find("./MedlineCitation/Article")
            if article is None:
                continue
            pmid = citation.findtext("./MedlineCitation/PMID", "")
            identifiers = {node.get("IdType"): node.text
                           for node in citation.findall("./PubmedData/ArticleIdList/ArticleId")}
            title = article.find("ArticleTitle")
            online = article.find("ArticleDate")
            date_parts = [online.findtext(part, "") for part in ("Year", "Month", "Day")] if online is not None else []
            yield {
                "pmid": pmid, "doi": (identifiers.get("doi") or "").lower(),
                "title": clean("".join(title.itertext())) if title is not None else "",
                "author": article.findtext("./AuthorList/Author/LastName", ""),
                "venue": article.findtext("./Journal/Title", ""),
                "mesh": [node.text for node in citation.findall(
                    "./MedlineCitation/MeshHeadingList/MeshHeading/DescriptorName") if node.text],
                "issns": [article.findtext("./Journal/ISSN", ""),
                          citation.findtext("./MedlineCitation/MedlineJournalInfo/ISSNLinking", "")],
                "date": "-".join(filter(None, date_parts)),
                "online_date": "-".join(filter(None, date_parts)),
                "type": ", ".join(node.text for node in article.findall("./PublicationTypeList/PublicationType") if node.text),
                "volume": article.findtext("./Journal/JournalIssue/Volume", ""),
                "issue": article.findtext("./Journal/JournalIssue/Issue", ""),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            }


def feed(url):
    payload = fetch(url, headers=FEED_HEADERS)
    try:
        document = ElementTree.fromstring(payload)
    except ElementTree.ParseError as error:
        # Some feeds embed raw control characters, which the strict parser
        # rejects at a random position. Strip them and try once more.
        cleaned = re.sub(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]", b"", payload)
        try:
            document = ElementTree.fromstring(cleaned)
        except ElementTree.ParseError:
            # A rate-limit or challenge page is not XML; say what came back so
            # the run summary explains the failure instead of "invalid token".
            snippet = re.sub(r"\s+", " ", payload[:160].decode("utf-8", "replace")).strip()
            raise ValueError(f"RSS 不是合法 XML（{error}）：{snippet or '空响应'}") from None
    if document.tag.rsplit("}", 1)[-1].lower() not in {"rss", "feed", "rdf"}:
        raise ValueError("响应不是 RSS 或 Atom")
    for item in document.findall(".//{*}item") + document.findall(".//{*}entry"):
        title = item.findtext("{*}title", "")
        link = item.find("{*}link")
        article_url = (link.get("href") or link.text or "").strip() if link is not None else ""
        encoded = " ".join(item.itertext()) + " " + article_url
        match = re.search(r"10\.\d{4,9}/[^\s<>\"?&#]+", encoded, re.I)
        yield {"title": title, "doi": match.group().rstrip(".,;").lower() if match else "",
               "url": article_url}


def pull(fn, args):
    try:
        return list(fn(*args)), ""
    except (OSError, ValueError, KeyError, ElementTree.ParseError) as error:
        return [], str(error)


# DOI prefixes that identify a preprint or a study registration rather than the
# published article. The same paper can arrive twice through these, once from the
# journal and once from the repository, and the published version should win.
PREPRINT_PREFIXES = ("10.17605", "10.21203", "10.1101", "10.31234",
                     "10.26434", "10.20944", "10.31219")


def is_preprint(doi):
    return doi.startswith(PREPRINT_PREFIXES)


def upsert(db, item, label, source, day, is_journal):
    title = item.get("title", "")
    if not title:
        return
    doi = item.get("doi") or ""
    pmid = item.get("pmid") or ""
    venue = label if is_journal else item.get("venue", "")
    fingerprint = identity(venue) + "|" + identity(title)
    keys = (doi, doi, pmid, pmid, fingerprint)
    candidates = db.execute(
        """SELECT id, data FROM articles WHERE (doi != '' AND doi = ? AND ? != '')
           OR (pmid != '' AND pmid = ? AND ? != '') OR fingerprint = ?""", keys
    ).fetchall()
    previous = {}
    article_id = None
    for candidate_id, raw in candidates:
        known = json.loads(raw)
        if doi and known.get("doi") and doi != known["doi"]:
            # Same journal and title but a different DOI is normally the
            # preprint/registration of the published article; only a genuinely
            # different pair of DOI types is treated as a separate record.
            if not (is_preprint(doi) or is_preprint(known["doi"])):
                continue
        if pmid and known.get("pmid") and pmid != known["pmid"]:
            continue
        first_author = identity(item.get("author", ""))
        known_author = identity(known.get("author", ""))
        if not ((doi and doi == known.get("doi")) or (pmid and pmid == known.get("pmid"))):
            if first_author and known_author and first_author != known_author:
                continue
        article_id, previous = candidate_id, known
        break
    merged = {**previous, **{key: value for key, value in item.items() if value}}
    previous_doi = previous.get("doi", "")
    incoming_doi = item.get("doi", "")
    if previous_doi and incoming_doi and previous_doi != incoming_doi:
        # A preprint and the journal article can share a title, but their
        # publication dates belong to different DOIs.
        if is_preprint(incoming_doi) and not is_preprint(previous_doi):
            merged["doi"] = previous_doi
            for date_key in ("date", "online_date"):
                if previous.get(date_key):
                    merged[date_key] = previous[date_key]
                else:
                    merged.pop(date_key, None)
        elif is_preprint(previous_doi) and not is_preprint(incoming_doi):
            for date_key in ("date", "online_date"):
                if item.get(date_key):
                    merged[date_key] = item[date_key]
                else:
                    merged.pop(date_key, None)
    if is_journal:
        merged["journal"] = label
        fingerprint = identity(label) + "|" + identity(title)
    else:
        merged["topics"] = sorted(set(previous.get("topics", [])) | {label})
        if merged.get("journal"):
            fingerprint = identity(merged["journal"]) + "|" + identity(title)
    merged["sources"] = sorted(set(previous.get("sources", [])) | {source})
    values = (merged.get("doi", ""), merged.get("pmid", ""), fingerprint,
              json.dumps(merged, ensure_ascii=False))
    if article_id is None:
        db.execute("INSERT INTO articles(doi, pmid, fingerprint, data, first_seen) VALUES (?, ?, ?, ?, ?)",
                   (*values, day))
    else:
        db.execute("UPDATE articles SET doi=?, pmid=?, fingerprint=?, data=? WHERE id=?",
                   (*values, article_id))


def report(day, records, history, baseline, journal_order, translated, translation_error, excluded):
    def article(item):
        url = ("https://doi.org/" + item["doi"]) if item.get("doi") else item.get("url", "")
        original = escape(item["title"])
        chinese = translated.get(item["title"])
        heading = escape(chinese) if chinese else original
        if urlsplit(url).scheme in {"https", "http"}:
            heading = f'<a href="{escape(url, quote=True)}">{heading}</a>'
        original_line = f'<div lang="en" class="original">{original}</div>' if chinese else ""
        tags = " · ".join(filter(None, [item.get("date"), item.get("type"),
                                        "、".join(item.get("topics", []))]))
        return f"<li>{heading}{original_line}<div>{escape(tags)}</div></li>"

    def journal_section(items, prefix, ordered=()):
        groups = grouped(items, ordered)
        if not groups:
            return "<p>无新增条目。</p>"
        links = []
        sections = []
        for index, (journal, topics) in enumerate(groups, 1):
            anchor = f"{prefix}-{index}"
            journal_name = escape(journal)
            count = sum(len(articles) for _, articles in topics)
            links.append(f'<li><a href="#{anchor}">{journal_name}</a>（{count}）</li>')
            subsections = []
            for topic, articles in topics:
                listing = "".join(article(item) for item in articles)
                subsections.append(f"<h4>{escape(topic)}（{len(articles)}）</h4><ul>{listing}</ul>")
            contents = "".join(subsections)
            sections.append(f'<section id="{anchor}"><h3>{journal_name}（{count}）</h3>{contents}</section>')
        index_links = "".join(links)
        return f'<nav aria-label="期刊目录"><ul>{index_links}</ul></nav>' + "".join(sections)

    focused = [item for item in records if item.get("journal")]
    other = [item for item in records if not item.get("journal")]
    failed = sum(bool(error) for _, _, _, error in history)
    summary = f"重点刊 {len(focused)} 篇 · 刊外 {len(other)} 篇 · 来源失败 {failed}/{len(history)}"
    feed_count = len({label for source, label, _, error in history if source.startswith("RSS") and not error})
    state = "".join(f"<tr><td>{escape(source)}</td><td>{escape(label)}</td>"
                    f"<td>{escape(error) if error else count}</td></tr>"
                    for source, label, count, error in history)
    translated_count = sum(item["title"] in translated for item in records)
    translation_status = f"中文机器译名 {translated_count}/{len(records)}。主题按题名和已有检索标签自动判定。"
    if translation_error:
        translation_status += " 翻译状态：" + translation_error
    heading = "启动回填与今日新增" if baseline else "今日首次发现"
    screened_count = len(records) + sum(excluded.values())
    reasons = "".join(f"<li>{escape(reason)}（{count}）</li>" for reason, count in excluded.most_common())
    screening_details = f"<details><summary>筛选范围与结果</summary><ul>{reasons}</ul></details>" if reasons else ""
    html = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{day} 期刊追踪日报｜人体运动与运动生理</title><style>
body{{font:16px/1.6 system-ui,sans-serif;max-width:950px;margin:3rem auto;padding:0 1.5rem;color:#18243a}}
a{{color:#135695}} li{{margin:.65rem 0}} li div{{color:#4b586a;font-size:.88rem}}
h2{{border-bottom:2px solid #c4d5e8;padding-bottom:.35rem}}
h3{{background:#eef3f9;padding:.45rem .65rem}}
h4{{margin-bottom:.3rem}} h4+ul{{margin-top:0}}
nav ul{{columns:2;padding-left:1.4rem}} nav li{{break-inside:avoid}}
@media(max-width:650px){{nav ul{{columns:1}}}}
td,th{{padding:.35rem .7rem;text-align:left;border-bottom:1px solid #dbe2ea}}
</style><h1>{day} 期刊追踪日报</h1><p>{heading} · {summary}</p>
<p>配置 {len(journal_order)} 本重点刊。{feed_count} 本本次取得可解析的官网 RSS。</p>
<p>人体运动与运动生理 · 纳入 {len(records)} / {screened_count} 篇</p>
{screening_details}
<p>{escape(translation_status)}</p>
<h2>重点期刊</h2>{journal_section(focused, "focused", journal_order)}
<h2>刊单外主题补漏</h2>{journal_section(other, "other")}
<h2>采集状态</h2><table><tr><th>来源</th><th>期刊或主题</th><th>返回条目 / 错误</th></tr>{state}</table></html>"""
    directory = ROOT / "reports"
    directory.mkdir(exist_ok=True)
    path = directory / (day + ".html")
    pending = path.with_suffix(".tmp")
    pending.write_text(html, encoding="utf-8")
    pending.replace(path)
    print(f"{path} | {summary} | {translated_count}/{len(records)} translated")


def previous_history(db, day):
    row = db.execute("SELECT history FROM report_history WHERE day=?", (day,)).fetchone()
    if row:
        return json.loads(row[0])
    old_path = ROOT / "reports" / (day + ".html")
    if not old_path.is_file():
        return []
    old_report = old_path.read_text(encoding="utf-8")
    previous = []
    for source, label, value in re.findall(
        r"<tr><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td></tr>", old_report
    ):
        source, label, value = map(unescape, (source, label, value))
        previous.append((source, label, int(value) if value.isdecimal() else 0,
                         "" if value.isdecimal() else value))
    return previous


def render_catalog(db, day, journal_order, baseline, history):
    records = [json.loads(row[0]) for row in db.execute(
        "SELECT data FROM articles WHERE first_seen=?", (day,))]
    records.sort(key=lambda item: (item.get("date", ""), item["title"]), reverse=True)
    included = []
    excluded = Counter()
    for item in records:
        reason = exclusion_reason(item)
        if reason:
            excluded[reason] += 1
        else:
            included.append(item)
    translated, error = translations(db, included)
    report(day, included, history, baseline, journal_order, translated, error, excluded)
    write_site(db, journal_order)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, help="Override the lookback window for recovery")
    parser.add_argument("--render-only", metavar="YYYY-MM-DD", help="Rebuild a saved report without fetching papers")
    options = parser.parse_args()
    now = datetime.now(TZ)
    day = datetime.strptime(options.render_only, "%Y-%m-%d").date().isoformat() if options.render_only else now.date().isoformat()
    database = sqlite3.connect(ROOT / "catalog.sqlite", timeout=60)
    with database as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY, doi TEXT, pmid TEXT, fingerprint TEXT, data TEXT, first_seen TEXT
        );
        CREATE INDEX IF NOT EXISTS articles_doi ON articles(doi);
        CREATE INDEX IF NOT EXISTS articles_pmid ON articles(pmid);
        CREATE INDEX IF NOT EXISTS articles_fingerprint ON articles(fingerprint);
        CREATE TABLE IF NOT EXISTS checkpoints (source TEXT, label TEXT, day TEXT,
            PRIMARY KEY(source, label));
        CREATE TABLE IF NOT EXISTS runs (day TEXT PRIMARY KEY, baseline INTEGER);
        CREATE TABLE IF NOT EXISTS report_history (day TEXT PRIMARY KEY, history TEXT NOT NULL);
        """)
        run = db.execute("SELECT baseline FROM runs WHERE day=?", (day,)).fetchone()
        baseline = bool(run[0]) if run else not db.execute("SELECT 1 FROM runs LIMIT 1").fetchone()
        journals = [
            (name, identifiers.split(","))
            for name, identifiers in (line.split("|") for line in
                (ROOT / "journals.txt").read_text(encoding="utf-8-sig").splitlines()
                if line.strip() and not line.startswith("#"))
        ]
        journal_order = [name for name, _ in journals]
        if options.render_only:
            if not run:
                parser.error("该日期没有已采集的报告")
            render_catalog(db, day, journal_order, baseline, previous_history(db, day))
            return 0
        jobs = []
        def enqueue(source, label, fn, args, journal, dated=True):
            if dated:
                checkpoint = db.execute("SELECT day FROM checkpoints WHERE source=? AND label=?",
                                        (source, label)).fetchone()
                anchor = datetime.fromisoformat(checkpoint[0]).date() if checkpoint else now.date()
                start = (anchor - timedelta(days=options.days or (4 if checkpoint else 30))).isoformat()
                args = (*args, start)
                if fn is crossref:
                    args = (*args, checkpoint is None)
            jobs.append((source, label, fn, args, journal))

        journal_ids = dict(journals)
        issue_start = (now.date() - timedelta(days=55)).isoformat()
        for name, issns in journals:
            enqueue("Crossref", name, crossref, (issns,), True)
            for source in PUBLISHER_PAGES.get(name, []):
                enqueue("官网 " + source["label"], name, publisher_articles, (source,), True, dated=False)
            if not any(source["label"] == "当前卷期" for source in PUBLISHER_PAGES.get(name, [])):
                # Published-print is the issue date. The article may have appeared online much earlier.
                enqueue("Crossref 正式卷期补查", name, crossref, (issns, issue_start, True, True), True, dated=False)
            for index, url in enumerate(FEEDS.get(name, []), start=1):
                enqueue(f"RSS {index}", name, feed, (url,), True, dated=False)
        issn_names = {issn: name for name, issns in journals for issn in issns}
        pubmed_journals = " OR ".join(f'"{issn}"[is]' for issn in issn_names)
        enqueue("PubMed", "全部重点刊", pubmed, (pubmed_journals,), True)
        for topic, query in TOPICS.items():
            enqueue("PubMed", topic, pubmed, (query,), False)
        if HISTORY_BACKFILL:
            start, until = HISTORY_BACKFILL["from"], HISTORY_BACKFILL["through"]
            period = start + " 至 " + until
            backfill_crossref = "历史 Crossref " + period
            backfill_pubmed = "历史 PubMed " + period
            done = set(db.execute(
                "SELECT source, label FROM checkpoints WHERE source IN (?, ?)",
                (backfill_crossref, backfill_pubmed),
            ))
            plans = [
                (backfill_crossref, name, crossref, (issns, start, True, False, until), True)
                for name, issns in journals
            ]
            plans.extend(
                (backfill_pubmed, name, pubmed,
                 (" OR ".join(f'"{issn}"[is]' for issn in issns), start, until), True)
                for name, issns in journals
            )
            plans.extend((backfill_pubmed, topic, pubmed, (query, start, until), False)
                         for topic, query in TOPICS.items())
            jobs.extend(plan for plan in plans if plan[:2] not in done)
        history = []
        completed = []
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(pull, fn, args) for _, _, fn, args, _ in jobs]
            for (source, label, _, _, journal), future in zip(jobs, futures):
                items, error = future.result()
                history.append((source, label, len(items), error))
                if error:
                    print(f"{source} | {label} | {error}", flush=True)
                    if source == "官网 当前卷期":
                        backup = "Crossref 正式卷期补查"
                        items, fallback_error = pull(crossref, (journal_ids[label], issue_start, True, True))
                        history.append((backup, label, len(items), fallback_error))
                        if not fallback_error:
                            completed.append((backup, label, items, True, False))
                    if source != "Crossref":
                        continue
                    fallback_since = (now.date() - timedelta(days=30)).isoformat()
                    matching_issns = journal_ids[label]
                    items, fallback_error = pull(openalex, (matching_issns, fallback_since))
                    history.append(("OpenAlex", label, len(items), fallback_error))
                    if fallback_error:
                        continue
                    completed.append(("OpenAlex", label, items, True, False))
                    continue
                completed.append((source, label, items, journal, True))
        db.execute("BEGIN IMMEDIATE")
        for source, label, items, journal, advance in completed:
            for item in items:
                canonical = next((issn_names[issn] for issn in item.get("issns", [])
                                  if issn in issn_names), None)
                if journal and (source == "PubMed" or source.startswith("历史 PubMed ")) and not canonical:
                    continue
                upsert(db, item, canonical or label if journal else label, source, day, journal)
                if canonical and not journal:
                    upsert(db, item, canonical, source, day, True)
            if advance:
                db.execute("INSERT OR REPLACE INTO checkpoints VALUES (?, ?, ?)", (source, label, day))
        db.execute("INSERT OR IGNORE INTO runs VALUES (?, ?)", (day, baseline))
        db.execute("INSERT OR REPLACE INTO report_history VALUES (?, ?)",
                   (day, json.dumps(history, ensure_ascii=False)))
    with database as db:
        render_catalog(db, day, journal_order, baseline, history)
    return int(all(error for _, _, _, error in history))


if __name__ == "__main__":
    if "--log" in sys.argv:
        sys.argv.remove("--log")
        log_directory = ROOT / "logs"
        log_directory.mkdir(exist_ok=True)
        with (log_directory / "run.log").open("a", encoding="utf-8", buffering=1) as log:
            with redirect_stdout(log), redirect_stderr(log):
                print(f"[{datetime.now(TZ).isoformat()}] started")
                try:
                    raise SystemExit(main())
                except Exception:
                    traceback.print_exc()
                    raise SystemExit(1)
    raise SystemExit(main())











