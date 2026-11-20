"""Read articles directly from the publishers' current listing pages."""

from datetime import datetime
import re
from urllib.parse import unquote, urljoin, urlsplit

DOI = re.compile(r"10\.\d{4,9}/[^\s?#]+", re.I)
DATE = re.compile(r"\b\d{1,2} [A-Za-z]{3,9} \d{4}\b")
ISSUE = re.compile(r"/volumes-and-issues/(\d+)-(\d+)$")
SPRINGER_TYPE = re.compile(
    r"^(?:Original Article|Research|Review(?: Article)?|Invited Review|"
    r"Systematic Review|Perspective|Comment(?:ary)?|Letter to the Editor|"
    r"Correction|Editorial|Short Communication)$", re.I,
)


def displayed_date(text):
    match = DATE.search(text)
    if match:
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(match.group(), fmt).date().isoformat()
            except ValueError:
                pass
    return ""


def article(card, title_node, link, page_url, doi_link=None, kind=""):
    if not title_node or not link:
        return None
    title = " ".join(title_node.stripped_strings)
    if not title:
        return None
    url = urljoin(page_url, link)
    match = DOI.search(unquote(doi_link or url))
    doi = match.group() if match else ""
    if kind == "frontiers":
        doi = doi.removesuffix("/full").removesuffix("/abstract")
    issue = ISSUE.search(urlsplit(page_url).path)
    issue_fields = {"volume": issue[1], "issue": issue[2]} if issue else {}
    text = card.get_text(" ", strip=True)
    medical_type = next((line for line in card.stripped_strings if SPRINGER_TYPE.fullmatch(line)), "")
    return {"title": title, "url": url, "doi": doi.lower(),
            "date": displayed_date(text), "type": medical_type, **issue_fields}


def read_cards(soup, page_url, kind):
    if kind == "springer":
        for card in soup.select("main article.app-card-open"):
            link = card.select_one(".app-card-open__heading a[href*='/article/']")
            if link:
                yield article(card, link, link["href"], page_url)
    elif kind == "frontiers":
        for card in soup.select("main article.CardArticle"):
            link = card.select_one("a[href*='/articles/10.']")
            if link:
                yield article(card, card.select_one(".CardArticle__title"), link["href"], page_url, kind=kind)
    elif kind == "jssm":
        for card in soup.select("table.tablemaster5"):
            doi = card.select_one("a[href*='doi.org/10.']")
            if doi:
                yield article(card, card.select_one(".tablemaster5_td_1"), doi["href"], page_url)
    elif kind == "termedia":
        for card in soup.select(".magArticleNoBorder, .magArticle, .magazine-article"):
            link = card.select_one("a.magArticleTitle[href], a.magazine-article_title[href]")
            doi = card.select_one("a[href*='doi.org/10.']")
            if link:
                yield article(card, link, link["href"], page_url, doi["href"] if doi else None)
    elif kind == "human-kinetics":
        journal_path = re.match(r"(/view/journals/[^/]+/)", urlsplit(page_url).path)
        if journal_path:
            for link in soup.select("main a[href*='/article-']"):
                url = urljoin(page_url, link["href"])
                if urlsplit(url).path.startswith(journal_path[1]):
                    yield article(link.parent, link, link["href"], page_url)
    else:
        raise ValueError(f"Unrecognized publisher page format: {kind}")


def publisher_articles(source):
    # BeautifulSoup is needed only for a live update, not offline rendering.
    from bs4 import BeautifulSoup
    import requests

    url = source["url"]
    kind = source["kind"]
    paginate = source.get("paginate", False)
    seen = set()
    records = {}

    def load(page):
        response = requests.get(page, timeout=(10, 30), headers={
            "User-Agent": "Mozilla/5.0 (compatible; JournalWatch/1.0) "
                          "academic-literature-monitoring",
            "Accept-Language": "en",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        response.raise_for_status()
        return BeautifulSoup(response.content, "html.parser")

    soup = load(url)
    if source.get("current_issue"):
        link = soup.select_one("main a[href*='/volumes-and-issues/']")
        if not link or not ISSUE.search(urlsplit(link["href"]).path):
            raise ValueError("Current issue link not recognized")
        url = urljoin(url, link["href"])
        soup = load(url)

    expected = re.search(r"(\d+) articles? in this issue", soup.get_text(" ", strip=True), re.I)
    while True:
        seen.add(url)
        for item in read_cards(soup, url, kind):
            if item:
                records[item["doi"] or item["url"]] = item
        next_link = soup.select_one("a[rel='next'][href]") if paginate else None
        if not next_link:
            break
        following = urljoin(url, next_link["href"])
        if following in seen or urlsplit(following).netloc != urlsplit(url).netloc or len(seen) >= 40:
            raise ValueError("Publisher pagination did not complete")
        url = following
        soup = load(url)

    if expected and len(records) != int(expected[1]):
        raise ValueError(f"Publisher listed {expected[1]} articles but only {len(records)} parsed")
    if not records:
        if kind == "springer" and re.search(r"no articles (?:available|found|to display)", soup.get_text(" ", strip=True), re.I):
            return []
        raise ValueError("Publisher page had no recognizable article entries")
    return list(records.values())
