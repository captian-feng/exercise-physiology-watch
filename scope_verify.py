"""Resolve ambiguous records by reading their abstract online, once, and caching it.

The title alone cannot always tell whether a paper studies exercising people or a
dish of cells: "Effects of exercise on inflammatory signalling in trained men"
and "Exercise and inflammatory signalling in cultured myotubes" look alike in a
title. `screening` drops every ambiguous title by default, which is safe but
lossy. This module gives those records a second chance: it fetches the abstract
from PubMed/OpenAlex/Crossref and decides from the text.

Design constraints that matter for the build:

* Every verdict is cached in ``scope_verification.json`` so a rebuild never
  repeats a lookup and the site stays deterministic.
* A run performs at most ``MAX_LOOKUPS_PER_RUN`` network calls, so a build cannot
  stall on a slow API. Uncached records simply stay out this time.
* A failed lookup is never treated as "include"; the record stays out.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CACHE_PATH = Path(__file__).resolve().parent / "scope_verification.json"
MAX_LOOKUPS_PER_RUN = 80
USER_AGENT = "exercise-physiology-watch/1.0 (+https://github.com/captian-feng/exercise-physiology-watch)"

# --- evidence vocabulary, applied to abstract text -------------------------
HUMAN_SUBJECT = re.compile(
    r"\b(?:participants?|volunteers?|subjects|athletes?|players?|runners?|cyclists?"
    r"|swimmers?|weightlifters?|lifters?|soldiers?|students|children|adolescents?"
    r"|adults?|men|women|males?|females?|humans?|patients?)\b", re.I)
EXERCISE_STIMULUS = re.compile(
    r"\b(?:exercis\w*|training|trained|physical activity|sprint\w*|running|cycling"
    r"|swimming|resistance|strength|endurance|aerobic|anaerobic|hiit|interval"
    r"|jump\w*|squat\w*|plyometric|time trial|treadmill|ergometer|match play)\b", re.I)
PHYSIOLOGICAL_OUTCOME = re.compile(
    r"\b(?:vo[\u0307₂2o\s_-]*2?\s*(?:max|peak)|oxygen uptake|heart rate|blood lactate"
    r"|lactate|blood pressure|cardiac output|stroke volume|arterial stiffness"
    r"|flow[- ]mediated dilation|vascular function|muscle (?:strength|power|thickness"
    r"|mass|activation|oxygenation|damage|force)|force|torque|power output|peak power"
    r"|velocity|kinematic\w*|biomechanic\w*|jump height|sprint (?:time|speed|performance)"
    r"|endurance performance|aerobic capacity|anaerobic capacity|energy expenditure"
    r"|substrate oxidation|body composition|lean mass|fat mass|core temperature"
    r"|skin temperature|sweat rate|thermoregulat\w*|hydration|oxygen saturation"
    r"|autonomic|heart rate variability|cortisol|blood flow|ventilation"
    r"|pulmonary function|lung function|fitness|performance)\b", re.I)
ANIMAL_OR_CELL = re.compile(
    r"\b(?:mice|mouse|murine|rats?|rodents?|rabbits?|zebrafish|piglets?|porcine"
    r"|canine|equine|in vitro|cultured? (?:cells?|myotubes?|fibroblasts?)"
    r"|cell culture|myotubes?|c2c12|organoids?|ex vivo|western blot|knockout"
    r"|knockdown|transfect\w*|single[- ]fib(?:re|er))\b", re.I)
NO_HUMAN_DECLARED = re.compile(
    r"\b(?:we|were|was|this study)\b[^.]{0,80}\b(?:no humans?|not in humans?)\b", re.I)
# Titles that are not a physiological study at all, whatever the abstract says.
NOT_A_STUDY = re.compile(
    r"\b(?:questionnaire|survey|qualitative|interview|focus group|ethnograph\w*"
    r"|systematic review|narrative review|scoping review|meta-analysis"
    r"|commentary|editorial|study protocol|consensus statement|position stand)\b", re.I)
# Psychosocial constructs anywhere in the title: mental fatigue, mindfulness,
# self-talk and affect are studied as such even when a performance score follows.
# "affect" is matched only as a noun ("affect mediates", "positive affect") so the
# verb in "exercise-induced weight loss affect..." is not read as psychology.
PSYCH_TOPIC = re.compile(
    r"\b(?:mental fatigue|mindfulness|self[- ]talk|ego depletion|"
    r"affective|positive affect|negative affect|\baffect (?:mediates|predicts|"
    r"regulation|and\b)"
    r"|psychometric|motivation\w*|self[- ]regulation|well-?being|anxiety|"
    r"burnout|self[- ]efficacy|perceived stress|attentional control)\b", re.I)
# Objective, numeric measurements of a person. A title that carries molecular or
# psychosocial vocabulary must show one of these in the abstract to be admitted,
# so a "genetic landscape of injury" paper cannot slip in on the word "athletes".
STRONG_MEASURE = re.compile(
    r"\b(?:vo[\u0307₂2o\s_-]*2?\s*(?:max|peak)|maximal oxygen uptake|peak oxygen uptake"
    r"|oxygen uptake|heart rate|blood lactate|lactate (?:concentration|threshold)"
    r"|power output|peak power|mean power|muscle (?:strength|thickness|cross-sectional area)"
    r"|one[- ]repetition maximum|1[- ]rm|jump height|sprint (?:time|speed)"
    r"|time trial|time to exhaustion|running economy|body composition|lean mass"
    r"|fat mass|core temperature|skin temperature|sweat rate|blood pressure"
    r"|arterial stiffness|flow[- ]mediated dilation|muscle activation|electromyograph\w*"
    r"|energy expenditure|substrate oxidation|force|torque|velocity)\b", re.I)


def _get(url, timeout=30):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None


def _pubmed(pmid):
    """Return (abstract, publication types, mesh terms) for a PMID."""
    params = urllib.parse.urlencode({"db": "pubmed", "id": pmid, "retmode": "xml"})
    payload = _get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + params)
    if not payload:
        return None
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return None
    node = root.find("PubmedArticle")
    if node is None:
        return None
    parts = ["".join(n.itertext()) for n in node.findall("./MedlineCitation/Article/Abstract/AbstractText")]
    abstract = " ".join(p.strip() for p in parts if p and p.strip())
    types = [t.text for t in node.findall("./MedlineCitation/Article/PublicationTypeList/PublicationType") if t.text]
    mesh = [m.findtext("DescriptorName", "") for m in node.findall("./MedlineCitation/MeshHeadingList/MeshHeading")]
    return abstract, types, mesh


def _openalex(doi):
    url = "https://api.openalex.org/works/https://doi.org/" + urllib.parse.quote(doi, safe="")
    payload = _get(url)
    if not payload:
        return None
    try:
        message = json.loads(payload)
    except ValueError:
        return None
    inverted = message.get("abstract_inverted_index")
    abstract = ""
    if inverted:
        position = {}
        for word, places in inverted.items():
            for place in places:
                position[place] = word
        abstract = " ".join(position[i] for i in sorted(position))
    return abstract, [], []


def judge(title, abstract, types=(), mesh=()):
    """Decide scope from the abstract text.

    Returns (include: bool, why: str). Only a positive human-plus-exercise-plus-
    physiology reading includes the record; everything else stays out.
    """
    import screening  # local import keeps the module importable on its own

    text = f"{title}. {abstract}"
    mesh_set = set(mesh)
    type_set = {t.casefold() for t in types}
    if type_set & {"editorial", "comment", "letter", "published erratum", "retraction of publication"}:
        return False, "editorial or correction"
    if NOT_A_STUDY.search(title) or type_set & {"review", "systematic review", "meta-analysis"}:
        return False, "not a primary study (review, survey or protocol)"
    # A psychosocial opening or a patient population is decisive on its own: the
    # paper is about that subject even when it also reports a performance score.
    if screening.PSYCHOSOCIAL_HEAD.match(title):
        return False, "psychosocial subject"
    if PSYCH_TOPIC.search(title):
        return False, "psychosocial subject"
    if screening.CLINICAL.search(title) and not screening.ATHLETE_CONTEXT.search(title):
        return False, "clinical population rather than exercisers"
    if len(abstract) < 120:
        return False, "abstract too short to judge"
    if ANIMAL_OR_CELL.search(abstract) and not HUMAN_SUBJECT.search(abstract):
        return False, "animal or cell study"
    if NO_HUMAN_DECLARED.search(abstract):
        return False, "explicitly not human"
    if not HUMAN_SUBJECT.search(abstract):
        return False, "no human participants in abstract"
    if not EXERCISE_STIMULUS.search(text):
        return False, "no exercise stimulus"
    if not PHYSIOLOGICAL_OUTCOME.search(abstract):
        return False, "no physiological outcome"
    # A title that reads as molecular or psychosocial is only admitted when the
    # abstract reports an objective whole-body measurement.
    if (screening.MOLECULAR_LEVEL.search(title) or screening.PSYCHOSOCIAL.search(title)) \
            and not STRONG_MEASURE.search(abstract):
        return False, "molecular or psychosocial topic without a whole-body measurement"
    if mesh_set and "Humans" not in mesh_set and "Animals" in mesh_set:
        return False, "indexed as animal study"
    return True, "abstract reports exercising humans with a physiological outcome"


def _key(item):
    doi = (item.get("doi") or "").strip().lower()
    if doi:
        return "doi:" + doi
    pmid = str(item.get("pmid") or "").strip()
    if pmid.isdigit():
        return "pmid:" + pmid
    return ""


def load_cache(path=CACHE_PATH):
    if Path(path).exists():
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def save_cache(cache, path=CACHE_PATH):
    Path(path).write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                          encoding="utf-8")


class Verifier:
    """Resolve ambiguous records against online abstracts, honouring a call budget."""

    def __init__(self, cache=None, budget=MAX_LOOKUPS_PER_RUN, path=CACHE_PATH):
        self.cache = cache if cache is not None else load_cache(path)
        self.budget = budget
        self.path = path
        self.lookups = 0
        self.changed = False

    def verify(self, item):
        """Return 'core' when the abstract confirms scope, else None."""
        key = _key(item)
        if not key:
            return None
        verdict = self.cache.get(key)
        if verdict is None:
            if self.lookups >= self.budget:
                return None
            evidence = None
            pmid = str(item.get("pmid") or "").strip()
            if pmid.isdigit():
                evidence = _pubmed(pmid)
            if not evidence:
                doi = (item.get("doi") or "").strip()
                if doi:
                    evidence = _openalex(doi)
            self.lookups += 1
            self.changed = True
            if not evidence:
                verdict = {"include": False, "why": "no online abstract found"}
            else:
                abstract, types, mesh = evidence
                include, why = judge(item["title"], abstract, types, mesh)
                verdict = {"include": include, "why": why}
            self.cache[key] = verdict
        return "core" if verdict.get("include") else None

    def flush(self):
        if self.changed:
            save_cache(self.cache, self.path)
            self.changed = False
