"""Classify article format for display without treating all journal records as original research."""

from __future__ import annotations

import re
import json
from pathlib import Path

ARTICLE_TYPES = (
    "原创研究",
    "系统综述与证据整合",
    "方案与注册",
    "指南、共识与立场文件",
    "会议摘要、海报与会议论文",
    "评论、社论与勘误",
    "类型待确认",
)

EDITORIAL = re.compile(r"\b(?:editorial|commentary|comment|letter|correction|erratum|corrigendum|retraction|reply|response)\b", re.I)
EDITORIAL_TITLE = re.compile(r"^(?:editorial|commentary|comment on|letter to|correction(?: to)?|erratum|corrigendum|retraction|reply to|response to (?:the )?(?:editor|comment|letter))\b|^(?:response|reply)\s+to\b", re.I)
CONFERENCE = re.compile(r"\b(?:conference|congress|meeting)\s+(?:abstract|paper|proceedings?)\b|\b(?:poster|abstracts? of (?:the )?(?:annual )?(?:meeting|conference|congress))\b", re.I)
GUIDANCE = re.compile(r"\b(?:guideline|consensus|position statement|recommendation|practice statement)\b", re.I)
PROTOCOL = re.compile(r"\b(?:study |trial )?protocol\b|\bprotocol for\b|\btrial registration\b", re.I)
EVIDENCE = re.compile(r"\b(?:systematic review|meta[- ]analysis|scoping review|umbrella review|narrative review|evidence synthesis|review)\b", re.I)
ORIGINAL = re.compile(r"\b(?:randomi[sz]ed|controlled trial|cohort|cross-sectional|case-control|pilot study|feasibility study|validation study|reliability|accuracy|experimental study|observational study)\b", re.I)
# Meeting proceedings are published as a supplemental issue ("S1", "10S", "Suppl 2")
# with no page range, which is how APS and ACSM print their annual meeting abstracts.
SUPPLEMENT_ISSUE = re.compile(r"^(?:s\d+|suppl(?:ement)?\.?\s*\d*|\d+s)$", re.I)


OVERRIDES_PATH = Path(__file__).resolve().parent / "article_type_overrides.json"
OVERRIDES = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8")) if OVERRIDES_PATH.exists() else {}


def _source_text(item):
    return " ".join(part.strip().casefold() for part in str(item.get("type", "")).split(",") if part.strip())


def _is_supplement_issue(item):
    """True when the record sits in a meeting-supplement issue rather than an article slot.

    Two guarantees are required before a record is called a meeting abstract:
      * the issue label looks like S1/10S/Suppl 2, and
      * the record carries no page range.
    PubMed records often omit the page field entirely, so "no page" is only
    trusted when the page key is present and empty; a missing key could equally
    mean an ordinary article whose page range PubMed simply did not publish.
    """
    issue = str(item.get("issue") or "").strip()
    if not issue or not SUPPLEMENT_ISSUE.match(issue):
        return False
    if "page" not in item:
        return False
    return not str(item.get("page") or "").strip()


def article_type_for(item):
    """Return one public display category using source metadata before title clues."""
    doi = (item.get("doi") or "").strip().casefold()
    pmid = str(item.get("pmid") or "").strip()
    override = OVERRIDES.get(doi) or (OVERRIDES.get("pmid:" + pmid) if pmid.isdigit() else None)
    if override in ARTICLE_TYPES and override != "类型待确认":
        return override
    title = item.get("title", "")
    source = _source_text(item)
    combined = f"{source} {title}"

    if EDITORIAL.search(source) or EDITORIAL_TITLE.search(title.strip()):
        return "评论、社论与勘误"
    if CONFERENCE.search(title) or any(token in source for token in ("conference", "congress", "meeting", "proceedings", "poster")):
        return "会议摘要、海报与会议论文"
    if _is_supplement_issue(item):
        # Supplemental issues carry meeting abstracts; only an explicit override
        # above can claim otherwise.
        return "会议摘要、海报与会议论文"
    if GUIDANCE.search(combined):
        return "指南、共识与立场文件"
    if PROTOCOL.search(combined):
        return "方案与注册"
    if EVIDENCE.search(combined):
        return "系统综述与证据整合"
    if ORIGINAL.search(combined):
        return "原创研究"
    return "类型待确认"
