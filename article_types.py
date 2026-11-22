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
EDITORIAL_TITLE = re.compile(r"^(?:editorial|commentary|comment on|letter to|correction(?: to)?|erratum|corrigendum|retraction|reply to|response to (?:the )?(?:editor|comment|letter))\b", re.I)
CONFERENCE = re.compile(r"\b(?:conference|congress|meeting)\s+(?:abstract|paper|proceedings?)\b|\b(?:poster|abstracts? of (?:the )?(?:annual )?(?:meeting|conference|congress))\b", re.I)
GUIDANCE = re.compile(r"\b(?:guideline|consensus|position statement|recommendation|practice statement)\b", re.I)
PROTOCOL = re.compile(r"\b(?:study |trial )?protocol\b|\bprotocol for\b|\btrial registration\b", re.I)
EVIDENCE = re.compile(r"\b(?:systematic review|meta[- ]analysis|scoping review|umbrella review|narrative review|evidence synthesis|review)\b", re.I)
ORIGINAL = re.compile(r"\b(?:randomi[sz]ed|controlled trial|cohort|cross-sectional|case-control|pilot study|feasibility study|validation study|reliability|accuracy|experimental study|observational study)\b", re.I)


OVERRIDES_PATH = Path(__file__).resolve().parent / "article_type_overrides.json"
OVERRIDES = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8")) if OVERRIDES_PATH.exists() else {}


def _source_text(item):
    return " ".join(part.strip().casefold() for part in str(item.get("type", "")).split(",") if part.strip())


def article_type_for(item):
    """Return one public display category using source metadata before title clues."""
    doi = (item.get("doi") or "").strip().casefold()
    override = OVERRIDES.get(doi)
    if override in ARTICLE_TYPES and override != "类型待确认":
        return override
    title = item.get("title", "")
    source = _source_text(item)
    combined = f"{source} {title}"

    if EDITORIAL.search(source) or EDITORIAL_TITLE.search(title.strip()):
        return "评论、社论与勘误"
    if CONFERENCE.search(title) or any(token in source for token in ("conference", "congress", "meeting", "proceedings", "poster")):
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
