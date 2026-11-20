"""Screen the reading report for human exercise and sport physiology.

The earlier rules matched only the article title and required an explicit
exercise word such as "exercise", "training" or "sport" in it. Titles that
describe exercise physiology without naming exercise -- "load-induced skeletal
muscle hypertrophy", "muscle protein synthesis", "heat acclimation" -- were
dropped even when they came from one of the curated journals.

This module keeps the hard exclusions (editorial, animal, bench, orthopaedic)
first, then uses three independent signals:

1. an exercise keyword in the title (``EXERCISE`` plus ``EXERCISE_EXTRA``),
2. an exercise-related MeSH heading supplied by PubMed (``EXERCISE_MESH``),
3. a human exercise-physiology context in the title of a curated journal
   (``EXERCISE_CONTEXT``), which promotes the record to the "related" tier
   instead of dropping it.

Signals 1 and 2 can produce a "core" record; signal 3 only ever produces a
"related" record, so a wider net never dilutes the core list.
"""

import re

ANIMAL = re.compile(
    r"\b(?:mice|mouse|murine|rodents?|rats?|wistar|sprague[ -]dawley|zebrafish|"
    r"drosophila|rabbits?|piglets?|porcine|swine|canine|dogs?|"
    r"chickens?|broilers?|quails?|horses?|equine|"
    r"macaques?|non[ -]human primates?|ovine|sheep|"
    r"cattle|cows?|goats?|ruminants?|animal models?)\b", re.I,
)
BENCH = re.compile(
    r"\b(?:in vitro|organoids?|cell lines?|cultured cells?|cell culture|"
    r"cadavers?|cadaveric|finite element models? of|molecular docking)\b", re.I,
)
ORTHOPEDIC = re.compile(
    r"\b(?:arthroscop\w*|arthroplast\w*|orthop[ae]edic\w*|osteotom\w*|"
    r"tenodesis|graft fixation|intra[ -]articular injections?|"
    r"menisc\w* (?:repair|transplantation|tear)|rotator cuff (?:tear|repair)|"
    r"anterior cruciate ligament (?:reconstruction|repair|tear|injury)|"
    r"acl (?:reconstruction|repair|tear|injury)|"
    r"osteochondr\w* (?:defect|lesion|repair)|tendon repair|operative|"
    r"surgery|surgical|postoperative|post[ -]operative|preoperative|meniscectomy|"
    r"femoroacetabular impingement|chondral lesions?)\b", re.I,
)
CLINICAL = re.compile(
    r"\b(?:rehabilitat\w*|patients?|diseases?|disorders?|"
    r"osteoarthritis|rheumatoid|tendinopath\w*|fractures?|concussions?|"
    r"cancer|tumou?rs?|diabet\w*|dystroph\w*|heart failure|stroke|parkinson\w*|"
    r"alzheimer\w*|dementia|fibrosis|copd|chronic pain|osteo\w*itis|"
    r"hypertensi\w*|obesity|mortality|infection\w*|syndrom\w*|hfp[eE]f)\b", re.I,
)
CLINICAL_CONTEXT = re.compile(
    r"\b(?:patients?|hospital\w*|outpatients?|inpatients?|clinical populations?|"
    r"clinical rehabilitation|rehabilitation|cardiac rehab|pulmonary rehab|"
    r"coronary (?:artery|heart) disease|heart failure|hfpef|hfref|"
    r"diabetes|diabetic|prediabet\w*|glaucoma|cancer|tumou?rs?|"
    r"osteoarthritis|rheumatoid arthritis|muscular dystroph\w*|"
    r"chronic kidney disease|dialysis|copd|pulmonary disease|"
    r"parkinson\w*|alzheimer\w*|multiple sclerosis|"
    r"post[ -]stroke|stroke survivors?|people with disabilities|"
    r"with hypertension|with obesity|with sarcopenia|chronic pain)\b", re.I,
)


def is_clinical_study(item):
    mesh = set(item.get("mesh", ()))
    return bool(CLINICAL_CONTEXT.search(item["title"]) or
                mesh & {"Patients", "Inpatients", "Outpatients", "Hospitals"})


EXERCISE = re.compile(
    r"\b(?:exercis\w*|physical activit\w*|physically active|sport(?:s|ing)?|"
    r"athlet\w*|fitness|resistance train\w*|strength train\w*|"
    r"interval train\w*|aerobic train\w*|endurance train\w*|hiit|"
    r"training (?:load|intensity|volume|adapt\w*|session|response)|"
    r"training[- ]induced|detrain\w*|"
    r"running|runners?|cyclists?|cycling|bicycl\w*|swim\w*|"
    r"sprint\w*|rowers?|rowing|triathl\w*|marathon\w*|kayak\w*|"
    r"weightlift\w*|powerlift\w*|soccer|football|basketball|volleyball|"
    r"badminton|tennis|rugby|hockey|baseball|softball|gymnast\w*|"
    r"handball|futsal|cricket|skiing|combat sport|judo|taekwondo|"
    r"wrestl\w*|canoe\w*|ultramarathon\w*|"
    r"critical (?:power|speed)|lactate threshold|lactate steady state|"
    r"running economy|oxygen uptake kinetics|aerobic capacity|"
    r"v[̇]?o[₂2] ?(?:max|peak)|ventilatory threshold|"
    r"muscle (?:contraction|strength|fatigue)|muscular strength|"
    r"grip strength|isometric|postural stability|motor (?:control|performance|adaptation)|"
    r"gait|locomot\w*|jump\w*|single[ -]leg landing|movement (?:pattern|initiation)|"
    r"work[ -]to[ -]rest|energy availability)\b", re.I,
)
# Terms that unambiguously describe exercise physiology or physical performance
# even when the title never says "exercise". Kept separate from EXERCISE so the
# additions stay reviewable, and applied before the clinical/outcome filters.
EXERCISE_EXTRA = re.compile(
    r"\b(?:skeletal muscle|muscle (?:mass|size|growth|atrophy|wasting|damage|"
    r"activation|force|power|function|protein synthesis|fib(?:re|er)|fascicle|"
    r"architecture\w*|length|quality|oxidative|glycolytic)|"
    r"hypertroph\w*|atroph\w*|myofib(?:re|er)\w*|sarcomer\w*|pennation|"
    r"myosin|excitation[- ]contraction|"
    r"tendon\w*|aponeuros\w*|fascia\w*|connective tissue|"
    r"mechanical loading|load[- ]induced|unloading|disuse|immobili[sz]ation|"
    r"bed rest|microgravity|"
    r"motor unit\w*|neuromuscular|neural drive|innervation|"
    r"training|train(?:ed|ing)|"
    r"thermoregulat\w*|heat (?:acclimation|acclimatization|acclimatisation|stress|"
    r"strain|exposure|tolerance|loss|illness)|core temperature|skin temperature|"
    r"body temperature|sweat\w*|hydrat\w*|dehydrat\w*|"
    r"energy (?:expenditure|cost|metabolism)|substrate (?:oxidation|utilization)|"
    r"fuel (?:selection|oxidation)|fat oxidation|carbohydrate oxidation|"
    r"respiratory exchange ratio|"
    r"blood (?:flow|pressure|volume|velocity)|cardiac output|stroke volume|"
    r"vascular (?:function|conductance|resistance|reactivity|remodel\w*)|"
    r"endothelial|arterial (?:stiffness|pressure|function)|"
    r"oxygen (?:uptake|consumption|delivery|extraction|saturation)|"
    r"mitochondri\w*|oxidative (?:capacity|phosphorylation|metabolism)|"
    r"fatigue\w*|fatigab\w*|soreness|delayed onset muscle|"
    r"postural (?:control|stability|sway)|balance (?:control|performance|test\w*)|"
    r"range of motion|flexibility|joint (?:moment|angle|torque|kinematic\w*|kinetic\w*)|"
    r"electromyograph\w*|emg)\b", re.I,
)
# PubMed MeSH headings that mark an exercise-physiology record even when the
# title is purely mechanistic. Only present on PubMed-sourced records.
EXERCISE_MESH = {
    "Exercise", "Exercise Therapy", "Exercise Movement Techniques",
    "Physical Conditioning, Human", "Physical Fitness", "Physical Endurance",
    "Athletic Performance", "Sports", "Resistance Training", "Muscle Strength",
    "Muscle, Skeletal", "Muscle Contraction", "Locomotion", "Motor Activity",
    "Oxygen Consumption", "Energy Metabolism", "Running", "Walking",
    "Cardiorespiratory Fitness", "Athletes", "Body Composition",
}
# Broad human exercise-physiology context. Used only for records from the
# curated journals and only to reach the "related" tier, never the core tier.
EXERCISE_CONTEXT = re.compile(
    r"\b(?:physiolog\w*|physiologic\w*|function\w*|capacity|performance|"
    r"adaptation\w*|acclimat\w*|responses?|mechanism\w*|"
    r"muscle\w*|skeletal|cardiac|cardiorespiratory|cardiovascular|vascular|"
    r"endothelial|arterial|pulmonary|respirat\w*|ventilat\w*|oxygen|"
    r"metabol\w*|mitochondri\w*|bioenergetic\w*|"
    r"blood|plasma|serum|circulat\w*|ha?emodynamic\w*|perfusion|"
    r"heat|cold|hypoxi\w*|altitude|environment\w*|"
    r"fatigue|recovery|injur\w*|damage|stress|load\w*|"
    r"body (?:composition|mass|weight)|adipos\w*|lean mass|bone density|"
    r"health|fitness|activit\w*|behavio\w*|sleep|nutrition|diet\w*|"
    r"ageing|aging|older|young|adult\w*|children|adolescen\w*)\b", re.I,
)
EXERCISE_OUTCOME = re.compile(
    r"\b(?:exercise (?:capacity|tolerance|performance|economy|response|test\w*|trial)|"
    r"cardiorespiratory (?:fitness|capacity)|functional (?:capacity|performance|fitness)|"
    r"maximal oxygen uptake|peak oxygen uptake|aerobic (?:capacity|fitness|performance)|"
    r"v[̇]?o[₂2] ?(?:max|peak)|oxygen uptake kinetics|"
    r"running economy|walking (?:distance|speed)|gait speed|"
    r"physical activit\w* (?:levels?|pattern\w*|behavio\w*|assessment|measurement)|"
    r"physically active|muscle strength|muscular strength|"
    r"neuromuscular (?:function|performance|adapt\w*)|"
    r"training (?:response|adapt\w*|load)|exercise[- ]induced)\b", re.I,
)
EXERCISE_INTERVENTION = re.compile(
    r"\b(?:(?:aerobic|resistance|endurance|strength|interval|concurrent|"
    r"combined|exercise) train\w*|physical activit\w* intervention \w*|"
    r"exercise (?:intervention|program\w*|prescription)|"
    r"exercise[ -]based (?:intervention|program\w*)|"
    r"effects? of (?:acute )?(?:physical exercise|exercis\w*)|"
    r"responses? to (?:acute )?exercis\w*)\b", re.I,
)
# Require a physiological or physical-performance question in addition to sport context.
PHYSIOLOGY_OR_PERFORMANCE = re.compile(
    r"\b(?:exercise physiolog\w*|cardiorespiratory|oxygen (?:uptake|consumption|cost|"
    r"delivery|saturation|extraction)|vo[\u0307₂2o\s_-]*2?\s*(?:max|peak)|"
    r"heart rate|blood pressure|cardiac output|stroke volume|ha?emodynam\w*|"
    r"vascular (?:function|response|reactivity)|autonomic responses?|ventilat\w*|"
    r"pulmonary gas exchange|critical (?:power|speed)|lactate|anaerobic threshold|"
    r"(?:running|walking|cycling|exercise) economy|aerobic capacity|aerobic fitness|"
    r"exercise (?:capacity|tolerance|performance|response)|physical performance|"
    r"(?:endurance|sprint|cycling|running|jump|swimming|strength) performance|"
    r"time[ -]trial|energy expenditure|energy cost|oxygenation|thermoregulat\w*|"
    r"heat (?:acclimati\w*|stress)|hypoxi\w*|glycogen|substrate oxidation|"
    r"metaboli\w*|body composition|muscle (?:strength|force|fatigue|activation|"
    r"size|architect\w*|damage|protein synthesis|power|function)|muscular strength|"
    r"neuromuscul\w*|hypertrophy|fatigab\w*|force development|electromyogra\w*|"
    r"maximal voluntary contraction|grip strength|countermovement jump|jump height|"
    r"peak power|power output|rate of perceived exertion|"
    r"polari[sz]ed (?:versus high[ -]intensity )?training|training (?:load|"
    r"adaptation\w*|response\w*)|physiological (?:response\w*|adaptation\w*|"
    r"demands|strain|recovery|effects)|exercise recovery)\b", re.I,
)

EXCLUDED_PUBLICATION = re.compile(
    r"^(?:erratum|corrigendum|retraction notice|correction(?: to)?[:.]|"
    r"editorial board|masthead|table of contents)(?=\W|$)|\bletter to the editor\b", re.I,
)
CELL_MECHANISM = re.compile(
    r"\b(?:micrornas?|lncrnas?|lactylation|methylation|transcriptom\w*|"
    r"signal(?:l)?ing pathways?|cell remodell?ing|mitochondrial remodell?ing|"
    r"neural remodell?ing|renoprotection|molecular mechanisms?|epigenetic enzymes|"
    r"single[ -]fib(?:re|er)|channel gating|candidate mechanism)\b", re.I,
)
HUMAN_CONTEXT = re.compile(
    r"\b(?:humans?|athlet\w*|participants?|men|women|males?|females?|"
    r"adults?|children|adolescents?|older people|cyclists?|runners?|"
    r"randomi[sz]ed|cohort|trained individuals)\b", re.I,
)
UNCERTAIN_RELEVANCE = "题名未显示运动生理或身体表现结局"
RECOVERED_CONTEXT = "题名未直接出现运动字样，但属运动生理相关主题"
NON_RESEARCH_TYPES = {"editorial", "published erratum", "retraction of publication", "news"}


def exercise_signal(item):
    """True when the title or a PubMed MeSH heading marks an exercise record."""
    if EXERCISE.search(item["title"]) or EXERCISE_EXTRA.search(item["title"]):
        return True
    return bool(set(item.get("mesh", ())) & EXERCISE_MESH)


def exclusion_reason(item):
    title = item["title"]
    types = {kind.strip().casefold() for kind in item.get("type", "").split(",")}
    mesh = set(item.get("mesh", ()))
    # Hard exclusions run first so a wider vocabulary can never resurrect them.
    if EXCLUDED_PUBLICATION.search(title) or types & NON_RESEARCH_TYPES:
        return "编辑信息与勘误"
    if ANIMAL.search(title) or ("Animals" in mesh and "Humans" not in mesh):
        return "动物研究"
    if BENCH.search(title):
        return "体外、尸体或纯建模研究"
    if ORTHOPEDIC.search(title):
        return "临床骨科"
    if CELL_MECHANISM.search(title) and "Humans" not in mesh and not HUMAN_CONTEXT.search(title):
        return "人体运动证据不明确的机制研究"
    if not exercise_signal(item):
        # Second chance: a curated journal writing about a human physiology topic
        # is treated as related reading rather than dropped outright.
        if item.get("journal") and EXERCISE_CONTEXT.search(title) and not (
            CLINICAL.search(title)
            and not (EXERCISE_OUTCOME.search(title) or EXERCISE_INTERVENTION.search(title))
        ):
            return RECOVERED_CONTEXT
        return "题名未显示直接的运动关联"
    if CLINICAL.search(title) and not (
        EXERCISE_OUTCOME.search(title) or EXERCISE_INTERVENTION.search(title)
    ):
        return "疾病、损伤或康复为主"
    if not PHYSIOLOGY_OR_PERFORMANCE.search(title):
        return UNCERTAIN_RELEVANCE
    return None


def relevance_tier(item):
    reason = exclusion_reason(item)
    if reason is None:
        return "core"
    if reason in (UNCERTAIN_RELEVANCE, RECOVERED_CONTEXT) and not is_clinical_study(item):
        return "related"
    return None
