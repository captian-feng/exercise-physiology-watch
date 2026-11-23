"""Screen the reading report for human exercise and sport physiology.

The original rules matched only the article title and demanded an explicit
exercise word such as "exercise", "training" or "sport". Titles that describe
exercise physiology without naming exercise -- "load-induced skeletal muscle
hypertrophy", "muscle protein synthesis", "heat acclimation" -- were dropped
even when they came from one of the curated journals.

This module keeps the hard exclusions (editorial, animal, bench, orthopaedic)
first, then uses three independent signals:

1. an exercise keyword in the title (``EXERCISE`` plus ``EXERCISE_EXTRA``),
2. an exercise-related MeSH heading supplied by PubMed (``EXERCISE_MESH``),
3. a human outcome in the title of a curated journal (``HUMAN_OUTCOME``),
   which promotes the record to the "related" tier instead of dropping it.

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
# Human physiological / performance outcome vocabulary. A title from a curated
# journal that matches this can reach the "related" tier; a title that also
# carries an exercise signal reaches "core". The earlier version of this list
# only accepted a handful of phrases, which pushed genuine exercise physiology
# (bone density, muscle damage, body composition, sleep, injury risk) into the
# related tier.
HUMAN_OUTCOME = re.compile(
    r"\b(?:performance|strength|power|endurance|fatigue\w*|fatigab\w*|recovery|"
    r"soreness|readiness|athlet\w*|players?|elite|collegiate|professional|"
    r"injur\w*|concussion\w*|illness|pain|"
    r"sleep|cognition|cognitive|brain|mental health|mood|anxiety|depress\w*|"
    r"bone|cartilage|tendon\w*|ligament\w*|fascia|connective tissue|"
    r"body (?:fat|composition|mass|weight)|adipos\w*|fat mass|lean mass|obesity|"
    r"insulin|glucose|glyc\w*|lipid\w*|cholesterol|triglycerid\w*|"
    r"immun\w*|inflamm\w*|cytokine\w*|microbiome|gut|"
    r"hepatic|liver|kidney|renal|"
    r"menstrual|hormon\w*|testosterone|estrogen|cortisol|"
    r"blood (?:flow|pressure|volume)|ha?emodynamic\w*|vascular|endothelial|"
    r"arterial|respirat\w*|pulmonary|bronch\w*|asthma|"
    r"cardiac|heart rate|cardiovascular|"
    r"thermoregulat\w*|heat|cold|hypoxi\w*|altitude|hydration|dehydrat\w*|sweat\w*|"
    r"aging|ageing|longevity|sarcopenia|frailty|"
    r"fitness|capacity|function\w*|"
    r"sedentary|wearable|acceleromet\w*|step count|"
    r"exercise (?:capacity|tolerance|performance|economy|response|test\w*|trial)|"
    r"cardiorespiratory|maximal oxygen uptake|peak oxygen uptake|"
    r"aerobic|anaerobic|lactate|vo[\u0307₂2o\s_-]*2?\s*(?:max|peak)|"
    r"running economy|oxygen uptake|energy expenditure|energy availability|"
    r"body temperature|core temperature|"
    r"muscle (?:strength|force|fatigue|activation|size|architect\w*|damage|"
    r"protein synthesis|power|function|mass|thickness|cross-sectional area)|"
    r"neuromuscul\w*|hypertroph\w*|electromyogra\w*|maximal voluntary contraction|"
    r"grip strength|countermovement jump|jump height|peak power|power output|"
    r"rate of perceived exertion|training (?:load|adaptation\w*|response\w*)|"
    r"physiological (?:response\w*|adaptation\w*|demands|strain|recovery)|"
    r"gait|balance|postural|locomot\w*|kinematic\w*|kinetic\w*|biomechanic\w*|"
    r"range of motion|flexibility|mobility|proprioception|motor (?:control|learning)|"
    r"quality of life|well-?being|health|mortality|morbidity|risk factors?)\b",
    re.I,
)
PHYSIOLOGY_OR_PERFORMANCE = HUMAN_OUTCOME
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

# ---------------------------------------------------------------------------
# Scope of the library: human exercise physiology, meaning studies that record a
# physiological or physical-performance measurement in people who exercise.
#
# Three families of work are out of scope even when the title mentions exercise.
# They used to leak into the core list because HUMAN_OUTCOME contained terms such
# as "mental health", "brain", "immune" and EXERCISE_EXTRA contained "skeletal
# muscle" and "mitochondria":
#
#   1. psychosocial and behavioural sport science,
#   2. molecular, cellular and tissue-level work,
#   3. single-omics / bioinformatics analyses of athletes' samples.
#
# A record is dropped only when it matches one of those families *and* reports no
# whole-body measurement, so a training study that also measured anxiety is kept.
# ---------------------------------------------------------------------------
PSYCHOSOCIAL = re.compile(
    r"\b(?:psycholog\w*|psychometric\w*|mental health|mental fatigue|"
    r"well-?being|quality of life|anxiety|depress\w*|burnout|motivation\w*|"
    r"self[- ](?:efficacy|regulation|determination|confidence|compassion|talk)|"
    r"perception\w*|perspectives?|attitudes?|beliefs?|expectations?|knowledge|"
    r"coach(?:es|ing)?|leadership|career|talent (?:development|identification)|"
    r"enjoyment|mood|emotion\w*|resilience|thriving|coping|"
    r"satisfaction|adherence|compliance|behavio(?:u)?r(?:al)? change|"
    r"questionnaire\w*|survey\w*|interview\w*|qualitative|ethnograph\w*|"
    r"cognit\w* (?:function|performance|testing|training|impairment|decline)|"
    r"academic (?:performance|achievement)|executive function\w*|"
    r"memory|attention|decision[- ]making|"
    r"social (?:support|media|network|determinants|inclusion)|socioeconomic\w*|"
    r"athlete (?:thriving|burnout|identity)|narrative|discourse|"
    r"reinvestment|learning methods?|motor learning|self[- ]report|"
    # Tool-building work: the contribution is a model, not a physiological finding.
    r"algorithm\w*|machine learning|deep learning|neural network|classifier\w*|"
    r"predictive model\w*|prediction model\w*|sensor[- ]based|"
    r"wearable (?:sensor|device) (?:design|development)|"
    r"data[- ]driven (?:approach|model))\b", re.I,
)
# A title that opens with a psychosocial subject is about that subject, even when
# the outcome is a performance score ("Psychological Self-Report Questionnaires
# Are Not Associated With Decrements in Physical Performance").
PSYCHOSOCIAL_HEAD = re.compile(
    r"^(?:psychological|psychosocial|psychometric|mental\b|motivation\w*|"
    r"perception\w*|perspectives?\b|attitudes?\b|coach(?:es|ing)?\b|"
    r"self[- ](?:efficacy|regulation|determination|report)|"
    r"the role of (?:psychological|motivation|perception))", re.I,
)
MOLECULAR_LEVEL = re.compile(
    r"\b(?:gene(?:s|tic|tics)?|genom\w*|polymorphism\w*|allele\w*|genotype\w*|"
    r"epigenet\w*|methylation|histone\w*|micrornas?|mirnas?|lncrnas?|mrna|"
    r"transcriptom\w*|proteom\w*|metabolom\w*|lipidom\w*|single[- ]cell\w*|"
    # "inflammation" itself is a routine human outcome (CRP, IL-6 after
    # exercise), so only the clearly molecular markers are listed here.
    r"cytokine\w*|chemokine\w*|interleukin\w*|tnf|nf-?kb|"
    r"inflammasom\w*|ferroptosis|apoptosis|autophagy|senescence|"
    r"signal(?:l)?ing (?:pathway|cascade)|molecular\w*|"
    r"pentose phosphate|oxidative stress|reactive oxygen|"
    r"cxcl\d*|ilm\d*|rs\d{3,}|actn3|epas1|furin|aldh2|apoe|"
    r"nrf2|mtor|ampk|sirtuin\w*|pgc-1|hif-\d|mapk|pi3k|akt\b|"
    r"knock(?:down|out)|overexpress\w*|transfect\w*|"
    r"cell culture|cultured (?:cells?|myotubes?)|in vitro|ex vivo|"
    r"myotubes?|organoids?|fibroblast\w*|endothelial cells?|stem cells?|"
    r"exosom\w*|extracellular vesicle\w*|western blot|pcr|"
    r"immunohistochem\w*|histolog\w*|biops(?:y|ies)|single[- ]fib(?:re|er)|"
    r"mitochondrial (?:respiration|dysfunction|biogenesis|density)|"
    r"oxidative phosphorylation|respiratory chain|sarcomere[- ]level)\b", re.I,
)
# A training stimulus is itself the central event of exercise physiology: a study
# of resistance, endurance, interval, sprint or plyometric training is about how
# the body adapts, even when its title names no measured outcome ("Biceps femoris
# motor unit discharge rates ...", "Cluster vs. rest-redistribution set
# configurations"). Records whose title states one of these reach the core tier
# instead of the related tier.
TRAINING_STIMULUS = re.compile(
    r"\b(?:resistance training|strength training|weight training|"
    r"endurance training|aerobic training|anaerobic training|"
    r"interval training|hiit|sprint interval training|repeated[- ]sprint training|"
    r"speed training|sprint training|velocity[- ]based training|"
    r"concurrent training|combined training|complex training|cluster (?:set|sets)|"
    r"plyometric(?:\s+(?:training|exercise|drill|jump\w*|protocol))?|power training|jump training|ballistic training|"
    r"eccentric (?:training|exercise)|nordic hamstring|blood flow restriction|"
    r"occlusion training|thermal training|heat training|hypoxic training|"
    r"electromyostimulation|whole[- ]body vibration|stretching|foam rolling|"
    r"autoregulat\w* training|periodi[sz]ation|training (?:volume|frequency|"
    r"intensity|density|distribution|program\w*|intervention\w*|period|block\w*)"
    r"|exercise (?:training|program\w*|intervention\w*|protocol)|"
    r"anaerobic (?:power|capacity|performance|speed|test\w*|threshold)|"
    r"aerobic (?:power|capacity|performance|test\w*)|"
    r"physical fitness|fitness test\w*|performance test\w*|incremental test|"
    r"maximal (?:strength|power|speed) test\w*|time to (?:failure|exhaustion)|"
    # Strength-training laboratory vocabulary that names the exercise or the
    # loading variable without the word "training" ("load-velocity relationship
    # in the bench press", "1RM prediction", "muscle forces during the squat").
    r"load[- ]velocity (?:relationship|profile\w*)|force[- ]velocity (?:relationship|profile\w*)"
    r"|velocity[- ]based|one[- ]repetition maximum|1[- ]rm|repetition maximum"
    r"|(?:back|front|split|hack|goblet) squat|bench press|deadlift|power ?clean"
    r"|snatch|clean and jerk|overhead press|lunge|hip thrust|leg press"
    r"|resisted sprint|assisted sprint|exoskeleton|weighted vest\w*"
    r"|metabolic costs? (?:of|during) (?:walking|running|cycling)"
    r"|costs? of (?:walking|running|cycling)|energy cost\w* of"
    r"|muscle (?:activity|activation|forces?|morphology|architecture|thickness|"
    r"cross[- ]sectional area) (?:during|in|across|at|and|of)"
    r"|torque[- ]velocity|electromagnetic resistance|blood flow restriction"
    r"|pre-?participation (?:screening|evaluation|assessment)|"
    r"(?:cardiac|cardiovascular|ecg|electrocardiograph\w*|medical) screening|"
    r"athlete (?:screening|screening programme|health assessment)|"
    r"screening (?:in|of|among) (?:elite |competitive |professional |young )?"
    r"(?:athletes?|footballers?|players?|runners?|swimmers?)|"
    r"injury (?:surveillance|incidence|epidemiology|patterns?|rates?)"
    r"(?: in| of| among)? (?:elite |professional |competitive )?"
    r"(?:athletes?|players?|footballers?|rugby|soccer|football))\b",
    re.I,
)
# A whole-body physiological or physical-performance measurement. Titles that
# carry one stay in scope even when they also mention a psychosocial or
# molecular term.
WHOLE_BODY_MEASURE = re.compile(
    r"\b(?:vo[\u0307₂2o\s_-]*2?\s*(?:max|peak)|maximal oxygen uptake|"
    r"peak oxygen uptake|oxygen uptake kinetics|heart rate|"
    r"blood lactate|lactate (?:threshold|concentration|steady state)|"
    r"ventilatory threshold|critical (?:power|speed)|"
    r"time to exhaustion|time trial|endurance performance|"
    r"aerobic (?:capacity|performance|power)|anaerobic (?:capacity|power|performance)|"
    r"sprint (?:speed|time|performance|mechanics|kinematics)|"
    r"jump (?:height|performance|kinetics|kinematics)|"
    r"power output|peak power|mean power|"
    r"muscle (?:strength|power|thickness|cross-sectional area|volume|"
    r"activation|oxygenation)|muscular strength|"
    r"one[- ]repetition maximum|1[- ]rm|"
    r"force[- ]velocity|load[- ]velocity|torque|"
    r"running economy|energy expenditure|substrate oxidation|"
    r"body composition|lean mass|fat mass|"
    r"core temperature|skin temperature|sweat rate|"
    r"arterial (?:stiffness|pressure)|blood pressure|"
    r"pulmonary function\w*|lung function\w*|"
    r"cardiorespiratory fitness|physical fitness|physical performance|muscle damage|"
    r"postural (?:control|stability)|balance (?:control|performance)|"
    r"gait (?:speed|kinematics|analysis)|"
    # Whole-body regulatory physiology: these are measurements of the person,
    # not of a cell or a molecule, so a paper reporting one stays in scope even
    # when its title also mentions emotion, a gene or a signalling pathway.
    r"autonomic|neuroendocrine|cortisol|heart rate variability|"
    r"vascular|arterial|brachial|flow[- ]mediated dilation|"
    r"blood flow|cardiac output|stroke volume|"
    r"thermoregulat\w*|sweat\w*|hydration|hypohydration|"
    r"heat acclimat\w*|"
    r"oxygen saturation|arterial oxygen|muscle oxygenation|"
    r"sleep (?:efficiency|quality|duration)|nocturnal)\b", re.I,
)
UNCERTAIN_RELEVANCE = "题名未显示运动生理或身体表现结局"
RECOVERED_CONTEXT = "题名未直接出现运动字样，但属运动生理相关主题"
# Reasons that a title alone cannot settle. A record dropped for one of these is
# handed to scope_verify, which reads the abstract before giving a final answer.
SCOPE_AMBIGUOUS = {"心理学、社会科学或教练研究", "纯分子、细胞或组织层面研究"}
# Exercising people, as opposed to a patient group.
ATHLETE_CONTEXT = re.compile(
    r"\b(?:athletes?|players?|runners?|cyclists?|swimmers?|weightlifters?"
    r"|healthy (?:men|women|adults|volunteers|participants|subjects)"
    r"|trained (?:men|women|males|females|individuals|participants|subjects)"
    r"|recreationally active|physically active)\b", re.I,
)


def needs_verification(item):
    """True when the title is ambiguous and the abstract should decide."""
    return exclusion_reason(item) in SCOPE_AMBIGUOUS
NON_RESEARCH_TYPES = {"editorial", "published erratum", "retraction of publication", "news"}


def exercise_signal(item):
    """True when the title or a PubMed MeSH heading marks an exercise record."""
    if EXERCISE.search(item["title"]) or EXERCISE_EXTRA.search(item["title"]):
        return True
    if TRAINING_STIMULUS.search(item["title"]):
        return True
    return bool(set(item.get("mesh", ())) & EXERCISE_MESH)


def out_of_scope_reason(title):
    """Return a drop reason when research is not human exercise physiology.

    Only fires when the title shows no whole-body physiological or performance
    measurement, so an exercise study that also reports anxiety or a gene
    variant is retained. A title that *opens* with a psychosocial subject is
    dropped regardless, because the paper is about that subject even when the
    outcome is a performance score.
    """
    if PSYCHOSOCIAL_HEAD.match(title):
        return "心理学、社会科学或教练研究"
    if WHOLE_BODY_MEASURE.search(title):
        return None
    if PSYCHOSOCIAL.search(title):
        return "心理学、社会科学或教练研究"
    if MOLECULAR_LEVEL.search(title):
        return "纯分子、细胞或组织层面研究"
    return None


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
    out_of_scope = out_of_scope_reason(title)
    if out_of_scope:
        return out_of_scope
    if CELL_MECHANISM.search(title) and "Humans" not in mesh and not HUMAN_CONTEXT.search(title):
        return "人体运动证据不明确的机制研究"
    if not exercise_signal(item):
        # Second chance: a curated journal writing about a human outcome is
        # treated as related reading rather than dropped outright.
        if item.get("journal") and HUMAN_OUTCOME.search(title) and not (
            CLINICAL.search(title)
            and not (EXERCISE_OUTCOME.search(title) or EXERCISE_INTERVENTION.search(title))
        ):
            return RECOVERED_CONTEXT
        return "题名未显示直接的运动关联"
    if CLINICAL.search(title) and not (
        EXERCISE_OUTCOME.search(title) or EXERCISE_INTERVENTION.search(title)
    ):
        return "疾病、损伤或康复为主"
    if TRAINING_STIMULUS.search(title):
        # A training study is exercise physiology even when the title states no
        # measured outcome: the intervention is the subject.
        return None
    if not HUMAN_OUTCOME.search(title):
        return UNCERTAIN_RELEVANCE
    return None


def relevance_tier(item):
    reason = exclusion_reason(item)
    if reason is None:
        return "core"
    if reason in (UNCERTAIN_RELEVANCE, RECOVERED_CONTEXT) and not is_clinical_study(item):
        return "related"
    return None
